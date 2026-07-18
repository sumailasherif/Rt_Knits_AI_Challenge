"""
Rating Gate Service

Business rule: a requester cannot submit a new task_request if they have
any Completed work orders with no corresponding Feedback row.

check_rating_gate() is injected into the Orchestrator at startup.
submit_feedback() handles the requester's reply (e.g. "WO12345 4").
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback, Requester, WorkOrder
from app.schemas.agents import RatingGateBlock

log = structlog.get_logger(__name__)


async def check_rating_gate(requester_id: str, db: AsyncSession) -> RatingGateBlock:
    """
    Return a RatingGateBlock.
    blocked=True if the requester has completed WOs without feedback.
    """
    # Find completed WOs for this requester (via task_request)
    stmt = (
        select(WorkOrder.wo_id)
        .join(WorkOrder.task_request)
        .where(WorkOrder.task_request.has(requester_id=requester_id))
        .where(WorkOrder.status == "Completed")
    )
    result = await db.execute(stmt)
    completed_wo_ids = [row[0] for row in result.all()]

    if not completed_wo_ids:
        return RatingGateBlock(blocked=False)

    # Find which ones already have feedback
    fb_stmt = select(Feedback.wo_id).where(Feedback.wo_id.in_(completed_wo_ids))
    fb_result = await db.execute(fb_stmt)
    rated_wo_ids = {row[0] for row in fb_result.all()}

    pending = [wid for wid in completed_wo_ids if wid not in rated_wo_ids]

    if not pending:
        return RatingGateBlock(blocked=False)

    return RatingGateBlock(
        blocked=True,
        pending_wo_ids=pending,
        message=(
            "⭐ Please rate your recent repair(s) before submitting a new request.\n"
            f"Pending: {', '.join(wid[:8] for wid in pending[:3])}"
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rating submission parser
# ─────────────────────────────────────────────────────────────────────────────

_RATING_PATTERN = re.compile(
    r"(?:wo)?[\s\-_]?([0-9a-f\-]{6,36})[\s\-_,]+([1-5])\b",
    re.IGNORECASE,
)
_SIMPLE_RATING = re.compile(r"^\s*([1-5])\s*$")


async def parse_and_save_feedback(
    text: str,
    requester_id: str,
    db: AsyncSession,
) -> tuple[bool, str]:
    """
    Try to parse a rating reply like "WO12345 4" or just "4".

    Returns (success, reply_message).
    If text matches, saves Feedback and returns success message.
    """
    # First try: WO ID + rating
    match = _RATING_PATTERN.search(text)
    if match:
        wo_partial_id = match.group(1).lower()
        rating = int(match.group(2))

        # Find WO by partial ID
        result = await db.execute(
            select(WorkOrder)
            .join(WorkOrder.task_request)
            .where(WorkOrder.task_request.has(requester_id=requester_id))
            .where(WorkOrder.status == "Completed")
            .where(WorkOrder.wo_id.ilike(f"{wo_partial_id}%"))
            .limit(1)
        )
        wo = result.scalar_one_or_none()

        if wo:
            return await _save_feedback(wo, requester_id, rating, text, db)
        return False, f"Could not find work order `{wo_partial_id}`. Please check the WO ID."

    # Second try: just a number — apply to oldest pending WO
    simple = _SIMPLE_RATING.match(text)
    if simple:
        rating = int(simple.group(1))
        # Find oldest pending WO for this requester
        result = await db.execute(
            select(WorkOrder)
            .join(WorkOrder.task_request)
            .where(WorkOrder.task_request.has(requester_id=requester_id))
            .where(WorkOrder.status == "Completed")
            .outerjoin(Feedback, Feedback.wo_id == WorkOrder.wo_id)
            .where(Feedback.feedback_id.is_(None))
            .order_by(WorkOrder.closed_at.asc())
            .limit(1)
        )
        wo = result.scalar_one_or_none()
        if wo:
            return await _save_feedback(wo, requester_id, rating, text, db)

    return False, ""


async def _save_feedback(
    wo: WorkOrder,
    requester_id: str,
    rating: int,
    raw_comment: str,
    db: AsyncSession,
) -> tuple[bool, str]:
    """Persist feedback and trigger reward score update."""
    # Idempotency: skip if already rated
    existing = await db.execute(
        select(Feedback).where(Feedback.wo_id == wo.wo_id)
    )
    if existing.scalar_one_or_none():
        return True, f"You already rated WO `{wo.wo_id[:8]}`. Thank you!"

    fb = Feedback(
        wo_id=wo.wo_id,
        requester_id=requester_id,
        rating=rating,
        comment=raw_comment if len(raw_comment) > 3 else None,
    )
    db.add(fb)
    await db.flush()

    # Update technician reward score
    from app.services.reward import update_reward_score
    await update_reward_score(wo.wo_id, rating, db)

    log.info("feedback_saved", wo_id=wo.wo_id, rating=rating)
    stars = "⭐" * rating
    return True, f"Thank you! {stars} ({rating}/5) recorded for WO `{wo.wo_id[:8]}`."
