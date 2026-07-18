"""
Router: /work-orders

CRUD endpoints for work orders + assignment management.
Used by the supervisor dashboard and mobile app.
"""
from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Assignment, Feedback, WorkOrder
from app.db.session import get_db
from app.schemas.assignment import AssignmentRead, AssignmentUpdate
from app.schemas.work_order import WorkOrderCreate, WorkOrderRead, WorkOrderUpdate

router = APIRouter(prefix="/work-orders", tags=["Work Orders"])
log = structlog.get_logger(__name__)


@router.get("", response_model=list[WorkOrderRead])
async def list_work_orders(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[WorkOrderRead]:
    stmt = select(WorkOrder).order_by(WorkOrder.created_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(WorkOrder.status == status)
    if priority:
        stmt = stmt.where(WorkOrder.priority == priority)
    result = await db.execute(stmt)
    wos = result.scalars().all()
    return [WorkOrderRead.model_validate(w) for w in wos]


@router.get("/{wo_id}", response_model=WorkOrderRead)
async def get_work_order(wo_id: str, db: AsyncSession = Depends(get_db)) -> WorkOrderRead:
    result = await db.execute(select(WorkOrder).where(WorkOrder.wo_id == wo_id))
    wo = result.scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    read = WorkOrderRead.model_validate(wo)
    # Attach feedback rating if available
    fb_result = await db.execute(select(Feedback).where(Feedback.wo_id == wo_id))
    fb = fb_result.scalar_one_or_none()
    if fb:
        read.feedback_rating = fb.rating
    return read


@router.post("", response_model=WorkOrderRead, status_code=status.HTTP_201_CREATED)
async def create_work_order(
    payload: WorkOrderCreate, db: AsyncSession = Depends(get_db)
) -> WorkOrderRead:
    import uuid
    wo = WorkOrder(wo_id=str(uuid.uuid4()), **payload.model_dump())
    db.add(wo)
    await db.flush()
    return WorkOrderRead.model_validate(wo)


@router.patch("/{wo_id}", response_model=WorkOrderRead)
async def update_work_order(
    wo_id: str, payload: WorkOrderUpdate, db: AsyncSession = Depends(get_db)
) -> WorkOrderRead:
    result = await db.execute(select(WorkOrder).where(WorkOrder.wo_id == wo_id))
    wo = result.scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(wo, field, val)
    await db.flush()
    return WorkOrderRead.model_validate(wo)


@router.get("/{wo_id}/assignments", response_model=list[AssignmentRead])
async def get_assignments(wo_id: str, db: AsyncSession = Depends(get_db)) -> list[AssignmentRead]:
    result = await db.execute(
        select(Assignment).where(Assignment.wo_id == wo_id).order_by(Assignment.created_at)
    )
    assignments = result.scalars().all()
    return [AssignmentRead.model_validate(a) for a in assignments]


@router.patch("/{wo_id}/assignments/{assignment_id}", response_model=AssignmentRead)
async def update_assignment(
    wo_id: str,
    assignment_id: str,
    payload: AssignmentUpdate,
    db: AsyncSession = Depends(get_db),
) -> AssignmentRead:
    result = await db.execute(
        select(Assignment)
        .where(Assignment.assignment_id == assignment_id)
        .where(Assignment.wo_id == wo_id)
    )
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(a, field, val)
    # If completing via API, trigger reward + close WO
    if payload.completed_at:
        from app.services.reward import calculate_completion_and_close
        await calculate_completion_and_close(wo_id, assignment_id, payload.completion_notes, db)
    await db.flush()
    return AssignmentRead.model_validate(a)
