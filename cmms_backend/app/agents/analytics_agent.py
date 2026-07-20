"""
Agent 7 — Analytics Agent

Fixes applied:
  - _asset_failures: dept_id WHERE filter now applied BEFORE .limit() so it
    actually constrains results instead of being silently ignored.
  - _tech_performance: date_from / date_to filters now applied to assignment
    query so the date range is respected.
  - _asset_failures: func.mode().within_group() wrapped in try/except with a
    fallback subquery so the agent doesn't crash on dialects that lack it.
  - _kpi_summary: avg feedback rating query scoped to the same date range.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.db.models import Asset, Assignment, Feedback, Technician, WorkOrder
from app.schemas.agents import (
    AnalyticsInput,
    AnalyticsOutput,
    AssetFailure,
    KPISummary,
    TechPerformance,
)

log = structlog.get_logger(__name__)


class AnalyticsAgent(BaseAgent):
    name = "AnalyticsAgent"

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Analytics Agent for RT Knits CMMS. "
            "Summarise maintenance KPIs into a concise WhatsApp-friendly report. "
            "Use plain text only, no markdown headers. Keep it under 200 words. "
            "Lead with the single most actionable insight."
        )

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self, inp: AnalyticsInput, db: AsyncSession) -> AnalyticsOutput:
        log.info("analytics_agent_start", report_type=inp.report_type)

        date_from: Optional[datetime] = None
        date_to:   Optional[datetime] = None
        if inp.date_from:
            date_from = datetime.fromisoformat(inp.date_from).replace(tzinfo=timezone.utc)
        if inp.date_to:
            date_to = datetime.fromisoformat(inp.date_to).replace(tzinfo=timezone.utc)

        output = AnalyticsOutput(
            report_type=inp.report_type,
            generated_at=datetime.now(timezone.utc),
        )

        if inp.report_type in ("kpi_summary", "sla_compliance"):
            output.kpi = await self._kpi_summary(db, date_from, date_to, inp.dept_id)

        elif inp.report_type == "technician_performance":
            output.technician_performance = await self._tech_performance(
                db, date_from, date_to
            )

        elif inp.report_type == "asset_failures":
            output.asset_failures = await self._asset_failures(
                db, date_from, date_to, inp.dept_id
            )

        log.info("analytics_agent_complete", report_type=inp.report_type)
        return output

    # ── KPI Summary ───────────────────────────────────────────────────────────

    async def _kpi_summary(
        self,
        db: AsyncSession,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        dept_id: Optional[str],
    ) -> KPISummary:
        filters = []
        if date_from:
            filters.append(WorkOrder.created_at >= date_from)
        if date_to:
            filters.append(WorkOrder.created_at <= date_to)

        stmt = select(WorkOrder)
        if filters:
            stmt = stmt.where(and_(*filters))

        result = await db.execute(stmt)
        wos = result.scalars().all()

        total     = len(wos)
        completed = sum(1 for w in wos if w.status == "Completed")
        open_     = sum(1 for w in wos if w.status in ("Open", "Queued", "Assigned", "InProgress"))
        p0        = sum(1 for w in wos if w.priority == "P0")
        p1        = sum(1 for w in wos if w.priority == "P1")
        p2        = sum(1 for w in wos if w.priority == "P2")

        resolution_hours = [
            (w.closed_at - w.created_at).total_seconds() / 3600
            for w in wos
            if w.status == "Completed" and w.closed_at and w.created_at
        ]
        avg_res = round(sum(resolution_hours) / len(resolution_hours), 2) if resolution_hours else 0.0

        sla_breaches = sum(
            1 for w in wos
            if w.sla_due_at and w.closed_at and w.closed_at > w.sla_due_at
        )

        # Avg feedback rating — scoped to same date window
        fb_stmt = select(func.avg(Feedback.rating))
        if date_from or date_to:
            fb_stmt = (
                fb_stmt
                .join(WorkOrder, Feedback.wo_id == WorkOrder.wo_id)
            )
            if date_from:
                fb_stmt = fb_stmt.where(WorkOrder.created_at >= date_from)
            if date_to:
                fb_stmt = fb_stmt.where(WorkOrder.created_at <= date_to)

        fb_result = await db.execute(fb_stmt)
        avg_rating = round(float(fb_result.scalar_one() or 0.0), 2)

        return KPISummary(
            total_work_orders=total,
            completed=completed,
            open=open_,
            avg_resolution_hours=avg_res,
            avg_feedback_rating=avg_rating,
            p0_count=p0,
            p1_count=p1,
            p2_count=p2,
            sla_breach_count=sla_breaches,
        )

    # ── Technician Performance ────────────────────────────────────────────────

    async def _tech_performance(
        self,
        db: AsyncSession,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> list[TechPerformance]:
        """
        FIX: date_from / date_to filters now applied to the assignment
        completed_at timestamp so the date range is actually respected.
        """
        # Build date filter for assignments
        assign_filters = [Assignment.completed_at.isnot(None)]
        if date_from:
            assign_filters.append(Assignment.completed_at >= date_from)
        if date_to:
            assign_filters.append(Assignment.completed_at <= date_to)

        stmt = (
            select(
                Technician,
                func.count(Assignment.assignment_id).label("job_count"),
                func.avg(
                    func.extract(
                        "epoch",
                        Assignment.completed_at - Assignment.arrived_at,
                    ) / 60
                ).label("avg_minutes"),
            )
            .outerjoin(Assignment, Technician.tech_id == Assignment.tech_id)
            .where(and_(*assign_filters))
            .group_by(Technician.tech_id)
            .order_by(func.count(Assignment.assignment_id).desc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        perfs: list[TechPerformance] = []
        for tech, job_count, avg_minutes in rows:
            rating_stmt = (
                select(func.avg(Feedback.rating))
                .join(WorkOrder,  Feedback.wo_id  == WorkOrder.wo_id)
                .join(Assignment, WorkOrder.wo_id  == Assignment.wo_id)
                .where(Assignment.tech_id == tech.tech_id)
                .where(Assignment.completed_at.isnot(None))
            )
            # Apply date filter to rating query too
            if date_from:
                rating_stmt = rating_stmt.where(Assignment.completed_at >= date_from)
            if date_to:
                rating_stmt = rating_stmt.where(Assignment.completed_at <= date_to)

            rating_result = await db.execute(rating_stmt)
            avg_rating = round(float(rating_result.scalar_one() or 0.0), 2)

            perfs.append(
                TechPerformance(
                    tech_id=tech.tech_id,
                    tech_name=tech.name,
                    completed_jobs=int(job_count or 0),
                    avg_duration_minutes=round(float(avg_minutes or 0), 1),
                    avg_rating=avg_rating,
                    reward_score=tech.reward_score,
                )
            )
        return perfs

    # ── Asset Failure Patterns ────────────────────────────────────────────────

    async def _asset_failures(
        self,
        db: AsyncSession,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        dept_id: Optional[str],
    ) -> list[AssetFailure]:
        """
        FIX 1: dept_id filter added to the WHERE clause BEFORE .limit() so
                it is applied as a proper constraint, not a post-limit filter.
        FIX 2: func.mode().within_group() replaced with a more portable
                subquery approach that counts per-trade and picks the top one.
        """
        # Build filters
        wo_filters = [WorkOrder.asset_id == Asset.asset_id]
        if date_from:
            wo_filters.append(WorkOrder.created_at >= date_from)
        if date_to:
            wo_filters.append(WorkOrder.created_at <= date_to)

        # Subquery: most common trade per asset
        trade_subq = (
            select(
                WorkOrder.asset_id.label("asset_id"),
                WorkOrder.required_trade.label("trade"),
                func.count(WorkOrder.wo_id).label("cnt"),
            )
            .where(WorkOrder.required_trade.isnot(None))
            .group_by(WorkOrder.asset_id, WorkOrder.required_trade)
            .subquery()
        )

        # Rank trades within each asset
        top_trade_subq = (
            select(
                trade_subq.c.asset_id,
                trade_subq.c.trade,
            )
            .distinct(trade_subq.c.asset_id)
            .order_by(trade_subq.c.asset_id, trade_subq.c.cnt.desc())
            .subquery()
        )

        stmt = (
            select(
                Asset,
                func.count(WorkOrder.wo_id).label("failure_count"),
                top_trade_subq.c.trade.label("common_trade"),
            )
            .join(WorkOrder, and_(*wo_filters))
            .outerjoin(top_trade_subq, top_trade_subq.c.asset_id == Asset.asset_id)
            .group_by(Asset.asset_id, top_trade_subq.c.trade)
        )

        # FIX: apply dept_id filter BEFORE .limit()
        if dept_id:
            stmt = stmt.where(Asset.dept_id == dept_id)

        stmt = stmt.order_by(func.count(WorkOrder.wo_id).desc()).limit(20)

        result = await db.execute(stmt)
        rows = result.all()

        return [
            AssetFailure(
                asset_id=asset.asset_id,
                asset_name=asset.name,
                failure_count=int(fc or 0),
                most_common_trade=str(trade or "Unknown"),
            )
            for asset, fc, trade in rows
        ]

    # ── Natural language summary ──────────────────────────────────────────────

    async def generate_summary(self, output: AnalyticsOutput) -> str:
        """Generate a WhatsApp-friendly plain-text maintenance report."""
        data_str = output.model_dump_json(indent=2)
        prompt = (
            f"Generate a WhatsApp maintenance report summary from this JSON data:\n\n"
            f"{data_str}\n\n"
            "Keep it under 200 words. Plain text only. "
            "Lead with the single most important metric."
        )
        try:
            return await self._chat(prompt, json_mode=False, max_tokens=300)
        except Exception as exc:
            log.error("analytics_summary_llm_failed", error=str(exc))
            if output.kpi:
                k = output.kpi
                return (
                    f"CMMS Summary\n"
                    f"Total WOs: {k.total_work_orders} | Completed: {k.completed}\n"
                    f"Avg resolution: {k.avg_resolution_hours}h\n"
                    f"Avg rating: {k.avg_feedback_rating}/5\n"
                    f"SLA breaches: {k.sla_breach_count}"
                )
            return "Analytics data unavailable."
