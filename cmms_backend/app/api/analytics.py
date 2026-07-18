"""
Router: /analytics

Endpoints for the Analytics Agent:
  GET /analytics/kpi           — KPI dashboard summary
  GET /analytics/technicians   — per-technician performance
  GET /analytics/assets        — asset failure heatmap
  GET /analytics/sla           — SLA compliance report
  GET /analytics/summary       — natural-language WhatsApp-style report
"""
from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analytics_agent import AnalyticsAgent
from app.db.session import get_db
from app.schemas.agents import AnalyticsInput, AnalyticsOutput

router = APIRouter(prefix="/analytics", tags=["Analytics"])
log = structlog.get_logger(__name__)

_analytics = AnalyticsAgent()


@router.get("/kpi", response_model=AnalyticsOutput)
async def kpi_summary(
    date_from: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None),
    dept_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOutput:
    return await _analytics.run(
        AnalyticsInput(report_type="kpi_summary", date_from=date_from, date_to=date_to, dept_id=dept_id),
        db=db,
    )


@router.get("/technicians", response_model=AnalyticsOutput)
async def technician_performance(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOutput:
    return await _analytics.run(
        AnalyticsInput(report_type="technician_performance", date_from=date_from, date_to=date_to),
        db=db,
    )


@router.get("/assets", response_model=AnalyticsOutput)
async def asset_failures(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    dept_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOutput:
    return await _analytics.run(
        AnalyticsInput(report_type="asset_failures", date_from=date_from, date_to=date_to, dept_id=dept_id),
        db=db,
    )


@router.get("/sla", response_model=AnalyticsOutput)
async def sla_compliance(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOutput:
    return await _analytics.run(
        AnalyticsInput(report_type="sla_compliance", date_from=date_from, date_to=date_to),
        db=db,
    )


@router.get("/summary")
async def natural_language_summary(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Returns a WhatsApp-friendly plain-text maintenance report."""
    output = await _analytics.run(
        AnalyticsInput(report_type="kpi_summary", date_from=date_from, date_to=date_to),
        db=db,
    )
    summary = await _analytics.generate_summary(output)
    return {"summary": summary}
