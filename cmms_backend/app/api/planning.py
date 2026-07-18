"""
Router: /planning

Endpoints for the nightly planning loop (Loop 1):
  POST /planning/trigger   — manually trigger nightly planning
  GET  /planning/plans     — list daily plans
  POST /planning/technician-reply  — handle conflict re-scheduling
"""
from __future__ import annotations

from datetime import date

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyPlan
from app.db.session import get_db
from app.schemas.daily_plan import DailyPlanRead, DailyPlanUpdate
from app.services.scheduler import trigger_planning_now

router = APIRouter(prefix="/planning", tags=["Planning"])
log = structlog.get_logger(__name__)


@router.post("/trigger")
async def trigger_planning(
    plan_date: str = Query(default=str(date.today()), description="ISO date YYYY-MM-DD"),
    force: bool = Query(default=False, description="Re-run even if plans already exist today"),
) -> dict:
    """
    Manually trigger the nightly planning loop.
    Useful for testing and supervisor overrides.
    """
    log.info("planning_manual_trigger", plan_date=plan_date, force=force)
    result = await trigger_planning_now(plan_date=plan_date, force=force)
    return {"status": "ok", "result": result}


@router.get("/plans", response_model=list[DailyPlanRead])
async def list_plans(
    plan_date: date | None = Query(None),
    tech_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[DailyPlanRead]:
    stmt = select(DailyPlan).order_by(DailyPlan.plan_date.desc(), DailyPlan.created_at.desc())
    if plan_date:
        stmt = stmt.where(DailyPlan.plan_date == plan_date)
    if tech_id:
        stmt = stmt.where(DailyPlan.tech_id == tech_id)
    result = await db.execute(stmt.limit(200))
    plans = result.scalars().all()
    return [DailyPlanRead.model_validate(p) for p in plans]


@router.patch("/plans/{plan_id}", response_model=DailyPlanRead)
async def update_plan(
    plan_id: str,
    payload: DailyPlanUpdate,
    db: AsyncSession = Depends(get_db),
) -> DailyPlanRead:
    result = await db.execute(select(DailyPlan).where(DailyPlan.plan_id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(plan, field, val)
    await db.flush()
    return DailyPlanRead.model_validate(plan)


@router.post("/technician-reply")
async def technician_conflict_reply(
    plan_id: str,
    tech_id: str,
    conflict_note: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Handle a technician's conflict note submitted before shift start.
    The Planning Agent can re-balance the plan accordingly.
    """
    result = await db.execute(
        select(DailyPlan)
        .where(DailyPlan.plan_id == plan_id)
        .where(DailyPlan.tech_id == tech_id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan.conflict_note = conflict_note[:500]
    await db.flush()

    log.info("tech_conflict_noted", plan_id=plan_id, tech_id=tech_id, note=conflict_note[:80])
    return {"status": "conflict_noted", "plan_id": plan_id}
