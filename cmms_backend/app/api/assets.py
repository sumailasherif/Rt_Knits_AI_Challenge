"""
Router: /assets  — factory asset CRUD
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Asset
from app.db.session import get_db
from app.schemas.asset import AssetCreate, AssetRead, AssetUpdate

router = APIRouter(prefix="/assets", tags=["Assets"])
log = structlog.get_logger(__name__)


@router.get("", response_model=list[AssetRead])
async def list_assets(
    dept_id: str | None = Query(None),
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[AssetRead]:
    stmt = select(Asset).order_by(Asset.name)
    if dept_id:
        stmt = stmt.where(Asset.dept_id == dept_id)
    if category:
        stmt = stmt.where(Asset.category == category)
    result = await db.execute(stmt)
    return [AssetRead.model_validate(a) for a in result.scalars().all()]


@router.get("/{asset_id}", response_model=AssetRead)
async def get_asset(asset_id: str, db: AsyncSession = Depends(get_db)) -> AssetRead:
    result = await db.execute(select(Asset).where(Asset.asset_id == asset_id))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Asset not found")
    return AssetRead.model_validate(a)


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(payload: AssetCreate, db: AsyncSession = Depends(get_db)) -> AssetRead:
    import uuid
    a = Asset(asset_id=str(uuid.uuid4()), **payload.model_dump())
    db.add(a)
    await db.flush()
    return AssetRead.model_validate(a)


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(
    asset_id: str, payload: AssetUpdate, db: AsyncSession = Depends(get_db)
) -> AssetRead:
    result = await db.execute(select(Asset).where(Asset.asset_id == asset_id))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Asset not found")
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(a, field, val)
    await db.flush()
    return AssetRead.model_validate(a)
