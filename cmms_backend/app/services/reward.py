"""
Technician Reward Loop

Fix applied:
  - calculate_completion_and_close now calls update_reward_score when a
    feedback row already exists for the WO (covers the WhatsApp DONE button
    path where feedback may have been submitted before job was formally closed).
  - Added a pending_rating lookup: if feedback already exists at completion
    time, apply the reward immediately. Otherwise reward fires later via
    _save_feedback in rating_gate.py when the requester rates.
  - This ensures reward is never silently skipped regardless of order.

Score formula (0–10 per job, cumulative):
  base          = 3.0
  + urgency     P0 → +3.0 | P1 → +1.5 | P2 → 0
  + quality     (rating − 3) × 1.0  →  range −2 .. +2
  + speed bonus actual_min ≤ estimated × 0.9 → +1.0
  + volume      +0.5 flat per completion
"""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Assignment, Feedback, Technician, WorkOrder

log = structlog.get_logger(__name__)

URGENCY_BONUS = {"P0": 3.0, "P1": 1.5, "P2": 0.0}
BASE_SCORE    = 3.0
VOLUME_BONUS  = 0.5


async def update_reward_score(wo_id: str, rating: int, db: AsyncSession) -> None:
    """
    Update the completing technician's reward_score.
    Called from _save_feedback (rating path) and calculate_completion_and_close
    (completion path when feedback already exists).
    """
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.wo_id == wo_id))
    wo = wo_result.scalar_one_or_none()
    if not wo:
        log.warning("reward_wo_not_found", wo_id=wo_id)
        return

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

    tech_result = await db.execute(
        select(Technician).where(Technician.tech_id == assignment.tech_id)
    )
    tech = tech_result.scalar_one_or_none()
    if not tech:
        log.warning("reward_tech_not_found", tech_id=assignment.tech_id)
        return

    # ── Score formula ─────────────────────────────────────────────────────────
    score = BASE_SCORE
    score += URGENCY_BONUS.get(wo.priority, 0.0)
    score += (rating - 3) * 1.0          # quality:  −2 .. +2

    if (
        assignment.arrived_at
        and assignment.completed_at
        and wo.estimated_minutes
    ):
        actual_minutes = (
            assignment.completed_at - assignment.arrived_at
        ).total_seconds() / 60
        if actual_minutes <= wo.estimated_minutes * 0.9:
            score += 1.0
            log.debug("reward_speed_bonus", tech_id=tech.tech_id, actual_min=actual_minutes)

    score += VOLUME_BONUS
    delta = max(0.0, min(10.0, score))

    old_score         = tech.reward_score
    tech.reward_score = round(old_score + delta, 2)
    await db.flush()

    log.info(
        "reward_score_updated",
        tech_id=tech.tech_id,
        tech_name=tech.name,
        wo_id=wo_id,
        rating=rating,
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
    Called when a technician taps DONE via WhatsApp or the REST API.

    1. Stamps assignment.completed_at
    2. Closes the work order (status = Completed)
    3. FIX: checks if feedback already exists and immediately fires
       update_reward_score if so — prevents reward from being silently
       skipped when a requester rates before the job button is tapped.
    """
    from datetime import datetime, timezone

    assign_result = await db.execute(
        select(Assignment).where(Assignment.assignment_id == assignment_id)
    )
    assignment = assign_result.scalar_one_or_none()
    if not assignment:
        log.warning("completion_assignment_not_found", assignment_id=assignment_id)
        return

    now = datetime.now(timezone.utc)
    assignment.completed_at    = now
    assignment.completion_notes = completion_notes

    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.wo_id == wo_id))
    wo = wo_result.scalar_one_or_none()
    if wo:
        wo.status   = "Completed"
        wo.closed_at = now

    await db.flush()
    log.info("work_order_closed", wo_id=wo_id, assignment_id=assignment_id)

    # FIX: if feedback was already submitted (e.g. requester rated before
    # technician tapped DONE), apply the reward now.
    fb_result = await db.execute(
        select(Feedback).where(Feedback.wo_id == wo_id)
    )
    existing_fb = fb_result.scalar_one_or_none()
    if existing_fb:
        log.info(
            "reward_applying_existing_feedback",
            wo_id=wo_id,
            rating=existing_fb.rating,
        )
        await update_reward_score(wo_id, existing_fb.rating, db)
