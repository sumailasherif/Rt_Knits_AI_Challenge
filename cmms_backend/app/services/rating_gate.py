"""
Rating Gate Service

Business rule: a requester cannot submit a new task_request if they have
any Completed work orders with no corresponding Feedback row.

Fixes applied:
  - check_rating_gate: replaced WorkOrder.task_request.has() lazy-relationship
    filter (unsafe in async sessions) with an explicit JOIN on TaskRequest.
  - parse_and_save_feedback: same pattern — explicit JOIN replacing .has().
  - Both queries now use fully explicit joins compatible with async SQLAlchemy.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback, TaskRequest, WorkOrder
from app.schemas.agents import RatingGateBlock

log = structlog.get_logger(__name__)


async def check_rating_gate(requester_id: str, db: AsyncSession) -> RatingGateBlock:
    """
    Returns RatingGateBlock(blocked=True) when the requester has Completed
    work orders that have not yet received a Feedback rating.

    FIX: uses explicit JOIN on TaskRequest instead of lazy .has() filter,
    which triggers greenlet errors inside async sessions.
    """
    # Step 1: all completed WO ids linked to this requester
    completed_stmt = (
        select(WorkOrder.wo_id)
        .join(TaskRequest, TaskRequest.request_id == WorkOrder.request_id)
        .where(TaskRequest.requester_id == requester_id)
        .where(WorkOrder.status == "Completed")
    )
    completed_result = await db.execute(completed_stmt)
    completed_wo_ids = [row[0] for row in completed_result.all()]

    if not completed_wo_ids:
        return RatingGateBlock(blocked=False)

    # Step 2: which of those already have feedback
    fb_result = await db.execute(
        select(Feedback.wo_id).where(Feedback.wo_id.in_(completed_wo_ids))
    )
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


# ── Rating submission parser ──────────────────────────────────────────────────

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
    Parse a rating reply such as "WO12345 4" or a bare digit "4".

    Returns (success: bool, reply_message: str).

    FIX: all WO lookups use explicit JOINs instead of lazy .has() filters.
    """
    # ── Pattern 1: WO partial-id + rating ────────────────────────────────────
    match = _RATING_PATTERN.search(text)
    if match:
        wo_partial = match.group(1).lower()
        rating = int(match.group(2))

        result = await db.execute(
            select(WorkOrder)
            .join(TaskRequest, TaskRequest.request_id == WorkOrder.request_id)
            .where(TaskRequest.requester_id == requester_id)
            .where(WorkOrder.status == "Completed")
            .where(WorkOrder.wo_id.ilike(f"{wo_partial}%"))
            .limit(1)
        )
        wo = result.scalar_one_or_none()
        if wo:
            return await _save_feedback(wo, requester_id, rating, text, db)
        return False, (
            f"Could not find a completed work order starting with `{wo_partial}`. "
            "Please check the WO ID and try again."
        )

    # ── Pattern 2: bare digit → apply to oldest pending WO ───────────────────
    simple = _SIMPLE_RATING.match(text)
    if simple:
        rating = int(simple.group(1))
        result = await db.execute(
            select(WorkOrder)
            .join(TaskRequest, TaskRequest.request_id == WorkOrder.request_id)
            .outerjoin(Feedback, Feedback.wo_id == WorkOrder.wo_id)
            .where(TaskRequest.requester_id == requester_id)
            .where(WorkOrder.status == "Completed")
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
    """Persist a Feedback row and trigger the technician reward update."""
    # Idempotency guard
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

    from app.services.reward import update_reward_score
    await update_reward_score(wo.wo_id, rating, db)

    log.info("feedback_saved", wo_id=wo.wo_id, rating=rating)
    stars = "⭐" * rating
    return True, f"Thank you! {stars} ({rating}/5) recorded for WO `{wo.wo_id[:8]}`."
