"""
Agent 3 — Dispatch Agent

Responsibilities:
  - Find the best available technician for a work order
  - Handle P0 preemption: pause active job, reassign technician immediately
  - Create assignment row in DB
  - Send WhatsApp notification to technician
  - Schedule P0 escalation countdown (5 min → re-route if unacknowledged)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.db.models import Assignment, Technician, WorkOrder
from app.schemas.agents import DispatchInput, DispatchOutput, TechCandidate

log = structlog.get_logger(__name__)
settings = get_settings()


class DispatchAgent(BaseAgent):
    name = "DispatchAgent"

    @property
    def system_prompt(self) -> str:
        return """You are the Dispatch Agent for RT Knits factory CMMS.
You allocate the best-fit technician for a maintenance work order.
When multiple candidates exist, prefer: correct trade > fewest active jobs > highest reward score.
You never dispatch an off-shift technician unless priority is P0 and no on-shift options exist.
"""

    async def find_technician(
        self,
        db: AsyncSession,
        required_trade: str,
        priority: str,
    ) -> Optional[TechCandidate]:
        """
        Query the DB for the best available technician.
        Returns None if nobody is available.
        """
        # Count active (non-completed, non-cancelled) assignments per tech
        active_sq = (
            select(
                Assignment.tech_id,
                func.count(Assignment.assignment_id).label("active_count"),
            )
            .where(Assignment.completed_at.is_(None))
            .where(Assignment.paused_at.is_(None))
            .group_by(Assignment.tech_id)
            .subquery()
        )

        stmt = (
            select(
                Technician,
                func.coalesce(active_sq.c.active_count, 0).label("active_count"),
            )
            .outerjoin(active_sq, Technician.tech_id == active_sq.c.tech_id)
            .where(Technician.is_active.is_(True))
            .where(Technician.trade == required_trade)
        )

        # For P0: accept off-shift if no on-shift available
        if priority != "P0":
            stmt = stmt.where(Technician.on_shift.is_(True))

        # Must not exceed max_concurrent_jobs
        stmt = stmt.where(
            func.coalesce(active_sq.c.active_count, 0) < Technician.max_concurrent_jobs
        )

        # Order: fewest active jobs first, then highest reward_score
        stmt = stmt.order_by(
            func.coalesce(active_sq.c.active_count, 0).asc(),
            Technician.reward_score.desc(),
        )

        result = await db.execute(stmt.limit(1))
        row = result.first()

        if not row:
            # P0 fallback: try ANY on-shift tech regardless of trade
            if priority == "P0":
                fallback_stmt = (
                    select(
                        Technician,
                        func.coalesce(active_sq.c.active_count, 0).label("active_count"),
                    )
                    .outerjoin(active_sq, Technician.tech_id == active_sq.c.tech_id)
                    .where(Technician.is_active.is_(True))
                    .where(Technician.on_shift.is_(True))
                    .where(
                        func.coalesce(active_sq.c.active_count, 0) < Technician.max_concurrent_jobs
                    )
                    .order_by(
                        func.coalesce(active_sq.c.active_count, 0).asc(),
                        Technician.reward_score.desc(),
                    )
                )
                result = await db.execute(fallback_stmt.limit(1))
                row = result.first()

        if not row:
            return None

        tech, active_count = row
        return TechCandidate(
            tech_id=tech.tech_id,
            tech_name=tech.name,
            phone_number=tech.phone_number,
            trade=tech.trade,
            current_load=int(active_count),
            reward_score=tech.reward_score,
        )

    async def pause_active_job(
        self,
        db: AsyncSession,
        tech_id: str,
    ) -> Optional[str]:
        """
        Pause the technician's current active assignment (for P0 preemption).
        Returns the paused assignment_id, or None if nothing was active.
        """
        stmt = (
            select(Assignment)
            .where(Assignment.tech_id == tech_id)
            .where(Assignment.completed_at.is_(None))
            .where(Assignment.paused_at.is_(None))
            .order_by(Assignment.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        assignment = result.scalar_one_or_none()

        if not assignment:
            return None

        assignment.paused_at = datetime.now(timezone.utc)

        # Also update parent work order status to Paused
        wo_result = await db.execute(
            select(WorkOrder).where(WorkOrder.wo_id == assignment.wo_id)
        )
        wo = wo_result.scalar_one_or_none()
        if wo:
            wo.status = "Paused"

        await db.flush()
        log.info("dispatch_paused_assignment", assignment_id=assignment.assignment_id)
        return assignment.assignment_id

    async def run(
        self,
        inp: DispatchInput,
        db: AsyncSession,
        send_whatsapp_fn,  # injected to avoid circular import
    ) -> DispatchOutput:
        log.info("dispatch_agent_start", wo_id=inp.wo_id, priority=inp.priority)

        # ── Find best technician ──────────────────────────────────────────────
        candidate = await self.find_technician(db, inp.required_trade, inp.priority)

        if not candidate:
            # No technician available — escalate immediately for P0, queue for others
            log.warning("dispatch_no_tech_available", wo_id=inp.wo_id, priority=inp.priority)
            # Update work order to Queued
            result = await db.execute(select(WorkOrder).where(WorkOrder.wo_id == inp.wo_id))
            wo = result.scalar_one_or_none()
            if wo:
                wo.status = "Queued"
            await db.flush()
            raise RuntimeError(
                f"No available {inp.required_trade} technician for WO {inp.wo_id}"
            )

        preempted_assignment_id: Optional[str] = None

        # ── P0 Preemption ─────────────────────────────────────────────────────
        if inp.priority == "P0":
            preempted_assignment_id = await self.pause_active_job(db, candidate.tech_id)
            if preempted_assignment_id:
                log.info(
                    "dispatch_p0_preemption",
                    tech_id=candidate.tech_id,
                    paused=preempted_assignment_id,
                )

        # ── Create Assignment ─────────────────────────────────────────────────
        assignment_id = str(uuid.uuid4())
        assignment = Assignment(
            assignment_id=assignment_id,
            wo_id=inp.wo_id,
            tech_id=candidate.tech_id,
            is_preempted=bool(preempted_assignment_id),
        )
        db.add(assignment)

        # Update work order status
        result = await db.execute(select(WorkOrder).where(WorkOrder.wo_id == inp.wo_id))
        wo = result.scalar_one_or_none()
        if wo:
            wo.status = "Assigned"
            wo.assigned_techs = [candidate.tech_id]

        await db.flush()

        # ── Send WhatsApp notification ────────────────────────────────────────
        whatsapp_sent = False
        try:
            msg = _build_dispatch_message(inp, candidate, preempted_assignment_id)
            await send_whatsapp_fn(
                to=candidate.phone_number,
                body=msg,
                buttons=[
                    ("ack_" + assignment_id[:8], "✅ ACKNOWLEDGE"),
                    ("arrived_" + assignment_id[:8], "📍 ON SITE"),
                ],
            )
            whatsapp_sent = True
        except Exception as exc:
            log.error("dispatch_whatsapp_failed", error=str(exc))

        output = DispatchOutput(
            assignment_id=assignment_id,
            wo_id=inp.wo_id,
            assigned_tech=candidate,
            preempted_assignment_id=preempted_assignment_id,
            escalation_scheduled=inp.priority == "P0",
            whatsapp_sent=whatsapp_sent,
        )

        log.info(
            "dispatch_agent_complete",
            assignment_id=assignment_id,
            tech=candidate.tech_name,
            priority=inp.priority,
        )
        return output


def _build_dispatch_message(
    inp: DispatchInput,
    candidate: TechCandidate,
    preempted_id: Optional[str],
) -> str:
    priority_emoji = {"P0": "🚨", "P1": "⚠️", "P2": "🔧"}.get(inp.priority, "🔧")
    lines = [
        f"{priority_emoji} *NEW WORK ORDER — {inp.priority}*",
        f"WO ID: `{inp.wo_id[:8]}`",
        f"Trade: {inp.required_trade}",
        f"Est. time: {inp.estimated_minutes} min",
    ]
    if preempted_id:
        lines.append("⚡ Your previous job has been *paused* for this P0 emergency.")
    lines.append("\nTap ACKNOWLEDGE to confirm receipt.")
    return "\n".join(lines)
