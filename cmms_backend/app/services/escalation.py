"""
P0 Escalation Service

When a P0 assignment is created, this service schedules an APScheduler
one-shot job that fires after P0_ESCALATION_MINUTES (default 5).

If the assignment.acknowledged_at is still null at that point:
  1. Mark current assignment as expired
  2. Find the next available technician
  3. Create a new assignment
  4. Send re-routing WhatsApp notification
  5. Reschedule another escalation countdown for the new assignment
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Assignment, Technician, WorkOrder
from app.db.session import db_context

log = structlog.get_logger(__name__)
settings = get_settings()

# Scheduler is initialised and started in main.py
_scheduler: Optional[AsyncIOScheduler] = None


def set_scheduler(scheduler: AsyncIOScheduler) -> None:
    global _scheduler
    _scheduler = scheduler


def schedule_p0_escalation(assignment_id: str, wo_id: str) -> None:
    """Schedule a one-shot escalation check after P0_ESCALATION_MINUTES."""
    if _scheduler is None:
        log.error("escalation_scheduler_not_set")
        return

    from datetime import timedelta

    run_at = datetime.now(timezone.utc) + timedelta(minutes=settings.p0_escalation_minutes)

    _scheduler.add_job(
        _check_and_escalate,
        trigger="date",
        run_date=run_at,
        args=[assignment_id, wo_id],
        id=f"p0_escalation_{assignment_id}",
        replace_existing=True,
        misfire_grace_time=60,
    )
    log.info(
        "p0_escalation_scheduled",
        assignment_id=assignment_id,
        wo_id=wo_id,
        run_at=run_at.isoformat(),
    )


async def _check_and_escalate(assignment_id: str, wo_id: str) -> None:
    """
    Fired by APScheduler after P0_ESCALATION_MINUTES.
    If the assignment is still unacknowledged, re-route to next available tech.
    """
    log.info("p0_escalation_fired", assignment_id=assignment_id, wo_id=wo_id)

    async with db_context() as db:
        # Fetch assignment
        result = await db.execute(
            select(Assignment).where(Assignment.assignment_id == assignment_id)
        )
        assignment = result.scalar_one_or_none()

        if not assignment:
            log.warning("p0_escalation_assignment_not_found", assignment_id=assignment_id)
            return

        # Already acknowledged — no escalation needed
        if assignment.acknowledged_at is not None:
            log.info("p0_escalation_already_acked", assignment_id=assignment_id)
            return

        # Fetch work order
        wo_result = await db.execute(
            select(WorkOrder).where(WorkOrder.wo_id == wo_id)
        )
        wo = wo_result.scalar_one_or_none()

        if not wo or wo.status in ("Completed", "Cancelled"):
            log.info("p0_escalation_wo_done", wo_id=wo_id)
            return

        # Mark old assignment as abandoned (set completed_at so it's excluded from active queries)
        assignment.completed_at = datetime.now(timezone.utc)
        assignment.completion_notes = "⚡ P0 ESCALATION — unacknowledged, re-routed"

        log.warning(
            "p0_escalation_rererouting",
            old_assignment=assignment_id,
            wo_id=wo_id,
            tech_id=assignment.tech_id,
        )

        # Import here to avoid circular dependency
        from app.agents.dispatch_agent import DispatchAgent
        from app.schemas.agents import DispatchInput
        from app.services.whatsapp import send_whatsapp_message

        dispatch = DispatchAgent()
        dispatch_input = DispatchInput(
            wo_id=wo_id,
            priority="P0",
            required_trade=wo.required_trade or "Mechanical",
            estimated_minutes=wo.estimated_minutes or 30,
        )

        try:
            new_output = await dispatch.run(
                dispatch_input,
                db,
                send_whatsapp_fn=_send_with_escalation_note,
            )
            log.info(
                "p0_escalation_reassigned",
                new_assignment=new_output.assignment_id,
                new_tech=new_output.assigned_tech.tech_name,
            )
            # Schedule another escalation for the new assignment
            schedule_p0_escalation(new_output.assignment_id, wo_id)
        except RuntimeError:
            # Still no tech available — notify supervisor
            log.error("p0_escalation_no_tech_available", wo_id=wo_id)
            await _notify_supervisor_no_tech(wo_id)


async def _send_with_escalation_note(
    to: str, body: str, buttons: Optional[list] = None
) -> None:
    """Wrapper that prepends an escalation note to the dispatch message."""
    from app.services.whatsapp import send_whatsapp_message

    escalation_msg = f"⚡ *ESCALATED P0 — Previous tech did not respond*\n\n{body}"
    await send_whatsapp_message(to=to, body=escalation_msg, buttons=buttons)


async def _notify_supervisor_no_tech(wo_id: str) -> None:
    """
    Last resort: no technician available after escalation.
    Log at CRITICAL level. In production, this would page a supervisor.
    """
    log.critical(
        "P0_NO_TECH_AVAILABLE_AFTER_ESCALATION",
        wo_id=wo_id,
        message="MANUAL INTERVENTION REQUIRED",
    )
