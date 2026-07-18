"""
Router: /technicians

CRUD for technicians + shift toggle endpoint.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Assignment, Technician
from app.db.session import get_db
from app.schemas.technician import TechnicianCreate, TechnicianRead, TechnicianUpdate

router = APIRouter(prefix="/technicians", tags=["Technicians"])
log = structlog.get_logger(__name__)


@router.get("", response_model=list[TechnicianRead])
async def list_technicians(
    on_shift: bool | None = Query(None),
    trade: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[TechnicianRead]:
    stmt = select(Technician).where(Technician.is_active.is_(True))
    if on_shift is not None:
        stmt = stmt.where(Technician.on_shift.is_(on_shift))
    if trade:
        stmt = stmt.where(Technician.trade == trade)
    result = await db.execute(stmt.order_by(Technician.reward_score.desc()))
    techs = result.scalars().all()

    reads = []
    for t in techs:
        r = TechnicianRead.model_validate(t)
        # Count active jobs
        active_result = await db.execute(
            select(func.count(Assignment.assignment_id))
            .where(Assignment.tech_id == t.tech_id)
            .where(Assignment.completed_at.is_(None))
        )
        r.active_jobs = active_result.scalar_one() or 0
        reads.append(r)
    return reads


@router.get("/{tech_id}", response_model=TechnicianRead)
async def get_technician(tech_id: str, db: AsyncSession = Depends(get_db)) -> TechnicianRead:
    result = await db.execute(select(Technician).where(Technician.tech_id == tech_id))
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    return TechnicianRead.model_validate(tech)


@router.post("", response_model=TechnicianRead, status_code=status.HTTP_201_CREATED)
async def create_technician(
    payload: TechnicianCreate, db: AsyncSession = Depends(get_db)
) -> TechnicianRead:
    import uuid
    tech = Technician(tech_id=str(uuid.uuid4()), **payload.model_dump())
    db.add(tech)
    await db.flush()
    return TechnicianRead.model_validate(tech)


@router.patch("/{tech_id}", response_model=TechnicianRead)
async def update_technician(
    tech_id: str, payload: TechnicianUpdate, db: AsyncSession = Depends(get_db)
) -> TechnicianRead:
    result = await db.execute(select(Technician).where(Technician.tech_id == tech_id))
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(tech, field, val)
    await db.flush()
    return TechnicianRead.model_validate(tech)


@router.post("/{tech_id}/shift-on", response_model=TechnicianRead)
async def start_shift(tech_id: str, db: AsyncSession = Depends(get_db)) -> TechnicianRead:
    result = await db.execute(select(Technician).where(Technician.tech_id == tech_id))
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    tech.on_shift = True
    await db.flush()
    log.info("tech_shift_on", tech_id=tech_id)
    return TechnicianRead.model_validate(tech)


@router.post("/{tech_id}/shift-off", response_model=TechnicianRead)
async def end_shift(tech_id: str, db: AsyncSession = Depends(get_db)) -> TechnicianRead:
    result = await db.execute(select(Technician).where(Technician.tech_id == tech_id))
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    tech.on_shift = False
    await db.flush()
    log.info("tech_shift_off", tech_id=tech_id)
    return TechnicianRead.model_validate(tech)
