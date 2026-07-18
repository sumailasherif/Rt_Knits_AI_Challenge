"""
Agent 6 — Planning Agent  (Nightly Batch)

Responsibilities:
  - Pull open/queued work orders + rolling backlog
  - Balance workload across on-shift technicians by trade and estimated minutes
  - Write DailyPlan rows to DB
  - Push formatted WhatsApp shift plans to each technician
  - Accept conflict re-scheduling replies via /whatsapp/technician-reply
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.db.models import DailyPlan, Technician, WorkOrder
from app.schemas.agents import PlanningInput, PlanningOutput, TechPlan

log = structlog.get_logger(__name__)
settings = get_settings()

# Max minutes per technician per shift (8-hour shift minus breaks)
SHIFT_CAPACITY_MINUTES = 420


class PlanningAgent(BaseAgent):
    name = "PlanningAgent"

    @property
    def system_prompt(self) -> str:
        return """You are the Planning Agent for RT Knits factory CMMS.
You balance maintenance workload across technicians for the next shift.
Prioritise P0 > P1 > P2. Never over-allocate beyond shift capacity.
Return a JSON array of technician plans."""

    async def run(
        self,
        inp: PlanningInput,
        db: AsyncSession,
        send_whatsapp_fn,
    ) -> PlanningOutput:
        plan_date = date.fromisoformat(inp.plan_date)
        log.info("planning_agent_start", plan_date=str(plan_date))

        # ── Guard: skip if already ran today and not forced ───────────────────
        if not inp.force:
            existing = await db.execute(
                select(DailyPlan).where(DailyPlan.plan_date == plan_date).limit(1)
            )
            if existing.scalar_one_or_none():
                log.info("planning_already_ran", plan_date=str(plan_date))
                return PlanningOutput(
                    plan_date=inp.plan_date,
                    plans_created=[],
                    backlog_rolled_forward=[],
                    messages_sent=0,
                )

        # ── 1. Fetch on-shift technicians ─────────────────────────────────────
        tech_result = await db.execute(
            select(Technician)
            .where(Technician.on_shift.is_(True))
            .where(Technician.is_active.is_(True))
            .order_by(Technician.trade, Technician.reward_score.desc())
        )
        technicians = tech_result.scalars().all()

        if not technicians:
            log.warning("planning_no_techs_on_shift")
            return PlanningOutput(
                plan_date=inp.plan_date,
                plans_created=[],
                backlog_rolled_forward=[],
                messages_sent=0,
            )

        # ── 2. Fetch open work orders (not Completed / Cancelled / Assigned) ──
        wo_result = await db.execute(
            select(WorkOrder)
            .where(WorkOrder.status.in_(["Open", "Queued", "Paused"]))
            .order_by(
                # Priority order: P0 first
                WorkOrder.priority.asc(),
                WorkOrder.created_at.asc(),
            )
        )
        open_wos = wo_result.scalars().all()

        # ── 3. Balance workload using greedy bin-packing by trade ─────────────
        # Build tech buckets: {tech_id: {remaining_minutes, wo_ids}}
        buckets: dict[str, dict] = {
            t.tech_id: {
                "tech": t,
                "remaining": SHIFT_CAPACITY_MINUTES,
                "wo_ids": [],
            }
            for t in technicians
        }

        backlog: list[str] = []

        for wo in open_wos:
            est = wo.estimated_minutes or 60
            trade = wo.required_trade or "Mechanical"

            # Find best-fit technician: matching trade, most remaining capacity
            candidates = [
                b for b in buckets.values()
                if b["tech"].trade == trade and b["remaining"] >= est
            ]

            if not candidates:
                # Try any trade with capacity (general fallback)
                candidates = [
                    b for b in buckets.values() if b["remaining"] >= est
                ]

            if not candidates:
                backlog.append(wo.wo_id)
                continue

            # Pick the one with most remaining capacity (best-fit decreasing)
            best = max(candidates, key=lambda b: b["remaining"])
            best["wo_ids"].append(wo.wo_id)
            best["remaining"] -= est

        # ── 4. Write DailyPlan rows ───────────────────────────────────────────
        plans_created: list[TechPlan] = []
        messages_sent = 0

        for tech_id, bucket in buckets.items():
            if not bucket["wo_ids"]:
                continue

            tech = bucket["tech"]
            used_minutes = SHIFT_CAPACITY_MINUTES - bucket["remaining"]

            plan = DailyPlan(
                tech_id=tech_id,
                plan_date=plan_date,
                items=bucket["wo_ids"],
                sent_at=None,
                confirmed=False,
            )
            db.add(plan)
            await db.flush()

            # ── 5. Send WhatsApp plan to technician ───────────────────────────
            try:
                msg = _build_plan_message(tech, bucket["wo_ids"], plan_date, used_minutes)
                await send_whatsapp_fn(
                    to=tech.phone_number,
                    body=msg,
                    buttons=[
                        ("confirm_plan_" + plan.plan_id[:8], "✅ CONFIRM"),
                        ("conflict_plan_" + plan.plan_id[:8], "⚠️ CONFLICT"),
                    ],
                )
                plan.sent_at = datetime.now(timezone.utc)
                messages_sent += 1
            except Exception as exc:
                log.error("planning_whatsapp_failed", tech_id=tech_id, error=str(exc))

            plans_created.append(
                TechPlan(
                    tech_id=tech_id,
                    tech_name=tech.name,
                    phone_number=tech.phone_number,
                    ordered_wo_ids=bucket["wo_ids"],
                    total_estimated_minutes=used_minutes,
                )
            )

        log.info(
            "planning_agent_complete",
            plans=len(plans_created),
            backlog=len(backlog),
            msgs_sent=messages_sent,
        )

        return PlanningOutput(
            plan_date=inp.plan_date,
            plans_created=plans_created,
            backlog_rolled_forward=backlog,
            messages_sent=messages_sent,
        )


def _build_plan_message(
    tech: Technician,
    wo_ids: list[str],
    plan_date: date,
    used_minutes: int,
) -> str:
    lines = [
        f"📋 *Your Shift Plan — {plan_date.strftime('%A %d %b')}*",
        f"Hello {tech.name}, here are your {len(wo_ids)} jobs for tomorrow:",
        "",
    ]
    for i, wo_id in enumerate(wo_ids, 1):
        lines.append(f"  {i}. WO `{wo_id[:8]}`")
    lines += [
        "",
        f"⏱ Estimated total: {used_minutes} min",
        "",
        "Reply CONFIRM to accept or CONFLICT if you have scheduling issues.",
    ]
    return "\n".join(lines)
