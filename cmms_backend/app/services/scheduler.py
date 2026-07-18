"""
APScheduler configuration — manages two recurring jobs:

Loop 1 (Nightly Batch Planning):
  Fires every evening at NIGHTLY_PLAN_HOUR:NIGHTLY_PLAN_MINUTE.
  Calls PlanningAgent to assign tomorrow's workload and push WA schedules.

Loop 2 (Continuous — triggered on demand):
  P0 escalation one-shot jobs are registered dynamically via
  escalation.schedule_p0_escalation() when a P0 work order is dispatched.

The scheduler is started/stopped inside the FastAPI lifespan context manager.
"""
from __future__ import annotations

from datetime import date

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from app.core.config import get_settings
from app.services.escalation import set_scheduler

log = structlog.get_logger(__name__)
settings = get_settings()

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        tz = pytz.timezone(settings.timezone)
        _scheduler = AsyncIOScheduler(timezone=tz)
        set_scheduler(_scheduler)
    return _scheduler


def start_scheduler() -> AsyncIOScheduler:
    """Initialise, register jobs, and start the scheduler."""
    scheduler = get_scheduler()

    # ── Loop 1: Nightly Planning ──────────────────────────────────────────────
    scheduler.add_job(
        _run_nightly_planning,
        trigger=CronTrigger(
            hour=settings.nightly_plan_hour,
            minute=settings.nightly_plan_minute,
            timezone=pytz.timezone(settings.timezone),
        ),
        id="nightly_planning",
        name="Nightly Planning Loop",
        replace_existing=True,
        misfire_grace_time=300,   # fire up to 5 min late if server was down
    )

    scheduler.start()
    log.info(
        "scheduler_started",
        nightly_hour=settings.nightly_plan_hour,
        nightly_minute=settings.nightly_plan_minute,
        timezone=settings.timezone,
    )
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("scheduler_stopped")


async def _run_nightly_planning() -> None:
    """
    Nightly planning job — instantiates PlanningAgent and runs it.
    Wrapped in its own DB context.
    """
    tomorrow = date.today().isoformat()
    log.info("nightly_planning_job_start", plan_date=tomorrow)

    try:
        from app.agents.planning_agent import PlanningAgent
        from app.schemas.agents import PlanningInput
        from app.services.whatsapp import send_whatsapp_message
        from app.db.session import db_context

        planning = PlanningAgent()

        async with db_context() as db:
            result = await planning.run(
                PlanningInput(plan_date=tomorrow, force=False),
                db=db,
                send_whatsapp_fn=send_whatsapp_message,
            )

        log.info(
            "nightly_planning_job_done",
            plans=len(result.plans_created),
            backlog=len(result.backlog_rolled_forward),
            msgs_sent=result.messages_sent,
        )
    except Exception as exc:
        log.error("nightly_planning_job_failed", error=str(exc), exc_info=True)


async def trigger_planning_now(plan_date: str, force: bool = False) -> dict:
    """
    Manual trigger endpoint — runs planning immediately.
    Returns the PlanningOutput as a dict.
    """
    from app.agents.planning_agent import PlanningAgent
    from app.schemas.agents import PlanningInput
    from app.services.whatsapp import send_whatsapp_message
    from app.db.session import db_context

    planning = PlanningAgent()

    async with db_context() as db:
        result = await planning.run(
            PlanningInput(plan_date=plan_date, force=force),
            db=db,
            send_whatsapp_fn=send_whatsapp_message,
        )

    return result.model_dump()
