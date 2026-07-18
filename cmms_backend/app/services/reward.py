"""
Technician Reward Loop

On completion of a work order, calculates a reward score delta and
adds it to the technician's cumulative reward_score.

Score formula (0-10 per job):
  base          = 3.0
  + urgency     = P0 → +3.0, P1 → +1.5, P2 → 0
  + quality     = (rating - 3) * 1.0  →  range -2..+2
  + speed bonus = if actual_minutes <= estimated_minutes * 0.9 → +1.0
  + volume      = +0.5 (flat per completion, encourages throughput)

Total is clamped to [0, 10].
"""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Assignment, Technician, WorkOrder

log = structlog.get_logger(__name__)

URGENCY_BONUS = {"P0": 3.0, "P1": 1.5, "P2": 0.0}
BASE_SCORE = 3.0
VOLUME_BONUS = 0.5


async def update_reward_score(
    wo_id: str,
    rating: int,
    db: AsyncSession,
) -> None:
    """
    Called after a Feedback row is saved for a completed work order.
    Finds the completing technician and updates their reward_score.
    """
    # Get the work order
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.wo_id == wo_id))
    wo = wo_result.scalar_one_or_none()
    if not wo:
        log.warning("reward_wo_not_found", wo_id=wo_id)
        return

    # Get the completing assignment (most recent completed one)
    assign_result = await db.execute(
        select(Assignment)
        .where(Assignment.wo_id == wo_id)
        .where(Assignment.completed_at.isnot(None))
        .order_by(Assignment.completed_at.desc())
        .limit(1)
    )
    assignment = assign_result.scalar_one_or_none()
    if not assignment:
        log.warning("reward_assignment_not_found", wo_id=wo_id)
        return

    # Get the technician
    tech_result = await db.execute(
        select(Technician).where(Technician.tech_id == assignment.tech_id)
    )
    tech = tech_result.scalar_one_or_none()
    if not tech:
        return

    # ── Score calculation ──────────────────────────────────────────────────────
    score = BASE_SCORE

    # Urgency bonus
    score += URGENCY_BONUS.get(wo.priority, 0.0)

    # Quality component from rating (1-5, centred at 3)
    quality = (rating - 3) * 1.0   # -2 to +2
    score += quality

    # Speed bonus — did they finish faster than estimated?
    if (
        assignment.arrived_at
        and assignment.completed_at
        and wo.estimated_minutes
    ):
        actual_secs = (assignment.completed_at - assignment.arrived_at).total_seconds()
        actual_minutes = actual_secs / 60
        if actual_minutes <= wo.estimated_minutes * 0.9:
            score += 1.0
            log.debug("reward_speed_bonus", tech_id=tech.tech_id, actual=actual_minutes)

    # Volume bonus
    score += VOLUME_BONUS

    # Clamp
    delta = max(0.0, min(10.0, score))

    old_score = tech.reward_score
    tech.reward_score = round(old_score + delta, 2)
    await db.flush()

    log.info(
        "reward_score_updated",
        tech_id=tech.tech_id,
        tech_name=tech.name,
        wo_id=wo_id,
        delta=delta,
        old_score=old_score,
        new_score=tech.reward_score,
    )


async def calculate_completion_and_close(
    wo_id: str,
    assignment_id: str,
    completion_notes: str | None,
    db: AsyncSession,
) -> None:
    """
    Called when a technician marks a job as DONE via WhatsApp reply.
    Stamps completed_at, closes the work order, and triggers reward calc.
    """
    from datetime import datetime, timezone

    # Stamp assignment
    assign_result = await db.execute(
        select(Assignment).where(Assignment.assignment_id == assignment_id)
    )
    assignment = assign_result.scalar_one_or_none()
    if not assignment:
        return

    now = datetime.now(timezone.utc)
    assignment.completed_at = now
    assignment.completion_notes = completion_notes

    # Close work order
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.wo_id == wo_id))
    wo = wo_result.scalar_one_or_none()
    if wo:
        wo.status = "Completed"
        wo.closed_at = now

    await db.flush()
    log.info("work_order_closed", wo_id=wo_id, assignment_id=assignment_id)
