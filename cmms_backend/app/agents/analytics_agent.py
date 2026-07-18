"""
Agent 7 — Analytics Agent

Responsibilities:
  - KPI dashboard: totals, avg resolution, avg rating, SLA compliance
  - Technician performance: jobs completed, avg duration, avg rating, reward score
  - Asset failure patterns: most failed assets, most common trades
  - Natural-language summary generation for WhatsApp / dashboard display
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import and_, func, select
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
        return """You are the Analytics Agent for RT Knits CMMS.
Summarise maintenance KPIs into a concise WhatsApp-friendly report.
Use plain text, no markdown headers. Keep it under 200 words.
Highlight the most actionable insights."""

    async def run(self, inp: AnalyticsInput, db: AsyncSession) -> AnalyticsOutput:
        log.info("analytics_agent_start", report_type=inp.report_type)

        # Parse date filters
        date_from: Optional[datetime] = None
        date_to: Optional[datetime] = None
        if inp.date_from:
            date_from = datetime.fromisoformat(inp.date_from).replace(tzinfo=timezone.utc)
        if inp.date_to:
            date_to = datetime.fromisoformat(inp.date_to).replace(tzinfo=timezone.utc)

        output = AnalyticsOutput(
            report_type=inp.report_type,
            generated_at=datetime.now(timezone.utc),
        )

        if inp.report_type == "kpi_summary":
            output.kpi = await self._kpi_summary(db, date_from, date_to, inp.dept_id)

        elif inp.report_type == "technician_performance":
            output.technician_performance = await self._tech_performance(db, date_from, date_to)

        elif inp.report_type == "asset_failures":
            output.asset_failures = await self._asset_failures(db, date_from, date_to, inp.dept_id)

        elif inp.report_type == "sla_compliance":
            output.kpi = await self._kpi_summary(db, date_from, date_to, inp.dept_id)

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

        base_q = select(WorkOrder)
        if filters:
            base_q = base_q.where(and_(*filters))

        result = await db.execute(base_q)
        wos = result.scalars().all()

        total = len(wos)
        completed = sum(1 for w in wos if w.status == "Completed")
        open_ = sum(1 for w in wos if w.status in ("Open", "Queued", "Assigned", "InProgress"))
        p0 = sum(1 for w in wos if w.priority == "P0")
        p1 = sum(1 for w in wos if w.priority == "P1")
        p2 = sum(1 for w in wos if w.priority == "P2")

        # Avg resolution hours
        resolution_hours = []
        for w in wos:
            if w.status == "Completed" and w.closed_at and w.created_at:
                delta = (w.closed_at - w.created_at).total_seconds() / 3600
                resolution_hours.append(delta)
        avg_res = sum(resolution_hours) / len(resolution_hours) if resolution_hours else 0.0

        # SLA breaches
        sla_breaches = sum(
            1 for w in wos
            if w.sla_due_at and w.closed_at and w.closed_at > w.sla_due_at
        )

        # Avg feedback rating
        fb_result = await db.execute(select(func.avg(Feedback.rating)))
        avg_rating = float(fb_result.scalar_one() or 0.0)

        return KPISummary(
            total_work_orders=total,
            completed=completed,
            open=open_,
            avg_resolution_hours=round(avg_res, 2),
            avg_feedback_rating=round(avg_rating, 2),
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
        stmt = (
            select(
                Technician,
                func.count(Assignment.assignment_id).label("job_count"),
                func.avg(
                    func.extract(
                        "epoch",
                        Assignment.completed_at - Assignment.arrived_at,
                    )
                    / 60
                ).label("avg_minutes"),
            )
            .outerjoin(Assignment, Technician.tech_id == Assignment.tech_id)
            .where(Assignment.completed_at.isnot(None))
            .group_by(Technician.tech_id)
            .order_by(func.count(Assignment.assignment_id).desc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        perfs: list[TechPerformance] = []
        for tech, job_count, avg_minutes in rows:
            # Avg rating for this tech's completed WOs
            rating_stmt = (
                select(func.avg(Feedback.rating))
                .join(WorkOrder, Feedback.wo_id == WorkOrder.wo_id)
                .join(Assignment, WorkOrder.wo_id == Assignment.wo_id)
                .where(Assignment.tech_id == tech.tech_id)
            )
            rating_result = await db.execute(rating_stmt)
            avg_rating = float(rating_result.scalar_one() or 0.0)

            perfs.append(
                TechPerformance(
                    tech_id=tech.tech_id,
                    tech_name=tech.name,
                    completed_jobs=int(job_count or 0),
                    avg_duration_minutes=round(float(avg_minutes or 0), 1),
                    avg_rating=round(avg_rating, 2),
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
        stmt = (
            select(
                Asset,
                func.count(WorkOrder.wo_id).label("failure_count"),
                func.mode().within_group(WorkOrder.required_trade).label("common_trade"),
            )
            .join(WorkOrder, Asset.asset_id == WorkOrder.asset_id)
            .group_by(Asset.asset_id)
            .order_by(func.count(WorkOrder.wo_id).desc())
            .limit(20)
        )
        if dept_id:
            stmt = stmt.where(Asset.dept_id == dept_id)

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

    async def generate_summary(self, output: AnalyticsOutput) -> str:
        """Generate a WhatsApp-friendly natural language summary."""
        data_str = output.model_dump_json(indent=2)
        prompt = (
            f"Generate a WhatsApp maintenance report summary from this data:\n\n{data_str}\n\n"
            "Keep it under 200 words. Plain text only. Lead with the most important metric."
        )
        try:
            return await self._chat(prompt, json_mode=False, max_tokens=300)
        except Exception as exc:
            log.error("analytics_summary_failed", error=str(exc))
            if output.kpi:
                k = output.kpi
                return (
                    f"📊 CMMS Summary\n"
                    f"Total WOs: {k.total_work_orders} | Completed: {k.completed}\n"
                    f"Avg resolution: {k.avg_resolution_hours}h\n"
                    f"Avg rating: {k.avg_feedback_rating}/5\n"
                    f"SLA breaches: {k.sla_breach_count}"
                )
            return "Analytics data unavailable."
