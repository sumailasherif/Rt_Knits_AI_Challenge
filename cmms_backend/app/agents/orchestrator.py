"""
Agent 1 — Maintenance Supervisor (Orchestrator)

LangGraph StateGraph routing every inbound WhatsApp message through agents.

Fixes applied:
  - Removed unused imports: lru_cache, Annotated, add_messages
  - _triage_node: single db_factory() context for both TaskRequest + WorkOrder
    persistence (was opening two nested contexts → double-commit risk)
  - _triage_node: asset_is_critical and asset_required_trade now resolved from
    DB using the fault's asset_id instead of being hardcoded False/None
  - _send_reply_node: guard against None outbound_message
  - OrchestratorState used directly as LangGraph state (Pydantic model supported)
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

import structlog
from langgraph.graph import END, StateGraph
from sqlalchemy import select

from app.agents.analytics_agent import AnalyticsAgent
from app.agents.dispatch_agent import DispatchAgent
from app.agents.intake_agent import IntakeAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.planning_agent import PlanningAgent
from app.agents.triage_agent import TriageAgent
from app.schemas.agents import (
    DispatchInput,
    IntakeInput,
    KnowledgeInput,
    KnowledgeOutput,
    OrchestratorState,
    RatingGateBlock,
    TriageInput,
)

log = structlog.get_logger(__name__)


class OrchestratorGraph:
    """
    Compiled LangGraph that processes one WhatsApp message per invoke() call.
    All dependencies are injected at construction time.
    """

    def __init__(
        self,
        db_factory,                   # asynccontextmanager → AsyncSession
        send_whatsapp_fn,             # async (to, body, buttons?) → None
        check_rating_gate_fn,         # async (requester_id, db) → RatingGateBlock
        get_or_create_requester_fn,   # async (phone, db) → str  (requester_id)
    ) -> None:
        self._db_factory = db_factory
        self._send_whatsapp = send_whatsapp_fn
        self._check_rating_gate = check_rating_gate_fn
        self._get_or_create_requester = get_or_create_requester_fn

        # Agent singletons — created once, reused across all requests
        self.intake    = IntakeAgent()
        self.knowledge = KnowledgeAgent()
        self.triage    = TriageAgent()
        self.dispatch  = DispatchAgent()
        self.planning  = PlanningAgent()
        self.analytics = AnalyticsAgent()

        self._graph = self._build_graph()

    # ── Graph wiring ──────────────────────────────────────────────────────────

    def _build_graph(self):
        builder = StateGraph(OrchestratorState)

        builder.add_node("rating_gate", self._rating_gate_node)
        builder.add_node("intake",      self._intake_node)
        builder.add_node("knowledge",   self._knowledge_node)
        builder.add_node("triage",      self._triage_node)
        builder.add_node("dispatch",    self._dispatch_node)
        builder.add_node("send_reply",  self._send_reply_node)

        builder.set_entry_point("rating_gate")

        builder.add_conditional_edges(
            "rating_gate",
            self._route_after_gate,
            {"blocked": "send_reply", "proceed": "intake"},
        )
        builder.add_conditional_edges(
            "intake",
            self._route_after_intake,
            {"clarify": "send_reply", "proceed": "knowledge"},
        )

        builder.add_edge("knowledge",  "triage")
        builder.add_edge("triage",     "dispatch")
        builder.add_edge("dispatch",   "send_reply")
        builder.add_edge("send_reply", END)

        return builder.compile()

    # ── Node: rating gate ─────────────────────────────────────────────────────

    async def _rating_gate_node(self, state: OrchestratorState) -> dict:
        async with self._db_factory() as db:
            requester_id = await self._get_or_create_requester(state.sender_phone, db)
            gate = await self._check_rating_gate(requester_id, db)

        if gate.blocked:
            wo_list = ", ".join(f"`{wid[:8]}`" for wid in gate.pending_wo_ids[:3])
            msg = (
                "⭐ *Please rate your recent repair(s) before submitting a new request.*\n\n"
                f"Pending ratings: {wo_list}\n\n"
                "Reply with the WO ID and a rating (1-5).\nExample: `WO12345 4`"
            )
            return {
                "rating_gate": RatingGateBlock(
                    blocked=True,
                    pending_wo_ids=gate.pending_wo_ids,
                    message=msg,
                ),
                "outbound_message": msg,
                "current_route": "end",
            }

        return {"rating_gate": RatingGateBlock(blocked=False), "current_route": "intake"}

    # ── Node: intake ──────────────────────────────────────────────────────────

    async def _intake_node(self, state: OrchestratorState) -> dict:
        async with self._db_factory() as db:
            requester_id = await self._get_or_create_requester(state.sender_phone, db)

        intake_input = IntakeInput(
            sender_phone=state.sender_phone,
            whatsapp_message_id=state.whatsapp_message_id or "",
            raw_text=self._latest_text(state),
            image_media_id=self._latest_image_id(state),
            audio_media_id=self._latest_audio_id(state),
        )
        request_id = str(uuid.uuid4())

        try:
            output = await self.intake.run(intake_input, requester_id, request_id)
        except Exception as exc:
            log.error("orchestrator_intake_failed", error=str(exc), exc_info=True)
            return {
                "error": str(exc),
                "outbound_message": (
                    "⚠️ Sorry, I couldn't process your message. Please try again."
                ),
                "current_route": "end",
            }

        updates: dict[str, Any] = {"intake_output": output, "current_route": "knowledge"}

        if not output.is_complete:
            updates["outbound_message"] = output.clarification_needed
            updates["awaiting_reply"] = True

        return updates

    # ── Node: knowledge ───────────────────────────────────────────────────────

    async def _knowledge_node(self, state: OrchestratorState) -> dict:
        if not state.intake_output:
            return {"knowledge_output": None}

        fault = state.intake_output.fault
        query = " ".join(filter(None, [
            fault.fault_description,
            fault.asset_name,
            fault.urgency_signal,
        ]))

        try:
            output = await self.knowledge.run(
                KnowledgeInput(query=query, asset_id=fault.asset_id, top_k=3)
            )
        except Exception as exc:
            log.warning("orchestrator_knowledge_failed", error=str(exc))
            output = KnowledgeOutput(snippets=[], combined_context="")

        return {"knowledge_output": output, "current_route": "triage"}

    # ── Node: triage ──────────────────────────────────────────────────────────

    async def _triage_node(self, state: OrchestratorState) -> dict:
        if not state.intake_output:
            return {
                "error": "No intake output available for triage",
                "outbound_message": "⚠️ Unable to process request. Please try again.",
                "current_route": "end",
            }

        knowledge_ctx = (
            state.knowledge_output.combined_context
            if state.knowledge_output else ""
        )

        intake = state.intake_output
        fault  = intake.fault

        # ── FIX: resolve asset metadata from DB in a SINGLE context ──────────
        asset_is_critical    = False
        asset_required_trade: Optional[str] = None

        async with self._db_factory() as db:
            # Resolve asset attributes if we have an asset_id
            if fault.asset_id:
                from app.db.models import Asset
                asset_result = await db.execute(
                    select(Asset).where(Asset.asset_id == fault.asset_id)
                )
                asset_row = asset_result.scalar_one_or_none()
                if asset_row:
                    asset_is_critical    = bool(asset_row.is_critical)
                    asset_required_trade = asset_row.required_trade

            triage_input = TriageInput(
                request_id=intake.request_id,
                fault=fault,
                asset_is_critical=asset_is_critical,
                asset_required_trade=asset_required_trade,
            )

            try:
                output = await self.triage.run(triage_input, knowledge_context=knowledge_ctx)
            except Exception as exc:
                log.error("orchestrator_triage_failed", error=str(exc), exc_info=True)
                return {
                    "error": str(exc),
                    "outbound_message": (
                        "⚠️ Sorry, we couldn't prioritise your request. "
                        "Please try again in a moment."
                    ),
                    "current_route": "end",
                }

            # ── FIX: persist TaskRequest + WorkOrder in the SAME db context ──
            from datetime import datetime, timedelta, timezone
            from app.db.models import TaskRequest, WorkOrder as WOModel

            existing_tr = await db.execute(
                select(TaskRequest).where(
                    TaskRequest.request_id == intake.request_id
                )
            )
            if existing_tr.scalar_one_or_none() is None:
                db.add(
                    TaskRequest(
                        request_id=intake.request_id,
                        requester_id=intake.requester_id,
                        asset_id=fault.asset_id,
                        raw_text=fault.translated_text or fault.fault_description,
                        audio_transcription=fault.audio_transcript,
                        structured_fault=fault.model_dump_json(),
                        whatsapp_message_id=state.whatsapp_message_id,
                    )
                )

            sla_due = datetime.now(timezone.utc) + timedelta(hours=output.sla_hours)
            db.add(
                WOModel(
                    wo_id=output.wo_id,
                    request_id=intake.request_id,
                    asset_id=fault.asset_id,
                    priority=output.priority,
                    status="Open",
                    description=fault.fault_description,
                    required_trade=output.required_trade,
                    estimated_minutes=output.estimated_minutes,
                    sla_due_at=sla_due,
                    assigned_techs=[],
                )
            )
            # db_context commits on exit — single transaction for both rows

        return {"triage_output": output, "current_route": "dispatch"}

    # ── Node: dispatch ────────────────────────────────────────────────────────

    async def _dispatch_node(self, state: OrchestratorState) -> dict:
        if not state.triage_output:
            return {
                "error": "No triage output for dispatch",
                "outbound_message": "⚠️ Unable to assign a technician. Please try again.",
                "current_route": "end",
            }

        t = state.triage_output
        dispatch_input = DispatchInput(
            wo_id=t.wo_id,
            priority=t.priority,          # type: ignore[arg-type]
            required_trade=t.required_trade,
            estimated_minutes=t.estimated_minutes,
        )

        try:
            async with self._db_factory() as db:
                output = await self.dispatch.run(
                    dispatch_input, db, self._send_whatsapp
                )
        except RuntimeError as exc:
            # No technician available — WO is already set to Queued by dispatch agent
            log.warning("orchestrator_no_tech_available", wo_id=t.wo_id, error=str(exc))
            return {
                "dispatch_output": None,
                "outbound_message": (
                    f"✅ Your request has been logged "
                    f"(WO `{t.wo_id[:8]}`, priority {t.priority}).\n"
                    "No technician is currently available — "
                    "you'll be notified when one is assigned."
                ),
                "current_route": "end",
            }
        except Exception as exc:
            log.error("orchestrator_dispatch_failed", error=str(exc), exc_info=True)
            return {
                "error": str(exc),
                "outbound_message": (
                    "⚠️ Dispatch failed. Our team has been notified."
                ),
                "current_route": "end",
            }

        # Schedule P0 escalation countdown
        if t.priority == "P0" and output.escalation_scheduled:
            from app.services.escalation import schedule_p0_escalation
            schedule_p0_escalation(output.assignment_id, output.wo_id)

        msg = (
            f"✅ *Work Order Created* — {t.priority}\n"
            f"WO ID: `{t.wo_id[:8]}`\n"
            f"Technician: {output.assigned_tech.tech_name}\n"
            f"ETA: ~{t.estimated_minutes} min\n\n"
            "You will receive an update when the job is completed, "
            "then be asked to rate the service."
        )
        return {
            "dispatch_output": output,
            "outbound_message": msg,
            "current_route": "end",
        }

    # ── Node: send reply ──────────────────────────────────────────────────────

    async def _send_reply_node(self, state: OrchestratorState) -> dict:
        """Send the final outbound message back to the requester via WhatsApp."""
        if not state.outbound_message:
            return {}
        try:
            await self._send_whatsapp(
                to=state.sender_phone,
                body=state.outbound_message,
                buttons=state.outbound_buttons,
            )
        except Exception as exc:
            log.error(
                "orchestrator_send_reply_failed",
                phone=state.sender_phone,
                error=str(exc),
            )
        return {}

    # ── Routing conditions ────────────────────────────────────────────────────

    @staticmethod
    def _route_after_gate(state: OrchestratorState) -> str:
        return "blocked" if state.rating_gate.blocked else "proceed"

    @staticmethod
    def _route_after_intake(state: OrchestratorState) -> str:
        if state.intake_output and not state.intake_output.is_complete:
            return "clarify"
        return "proceed"

    # ── Message extraction helpers ────────────────────────────────────────────

    @staticmethod
    def _latest_text(state: OrchestratorState) -> Optional[str]:
        for msg in reversed(state.messages):
            if msg.get("type") == "text":
                return msg.get("content")
        return None

    @staticmethod
    def _latest_image_id(state: OrchestratorState) -> Optional[str]:
        for msg in reversed(state.messages):
            if msg.get("type") == "image":
                return msg.get("media_id")
        return None

    @staticmethod
    def _latest_audio_id(state: OrchestratorState) -> Optional[str]:
        for msg in reversed(state.messages):
            if msg.get("type") == "audio":
                return msg.get("media_id")
        return None

    # ── Public entry point ────────────────────────────────────────────────────

    async def invoke(self, initial_state: OrchestratorState) -> OrchestratorState:
        log.info(
            "orchestrator_invoke",
            session_id=initial_state.session_id,
            phone=initial_state.sender_phone,
        )
        result = await self._graph.ainvoke(initial_state)
        if isinstance(result, dict):
            return OrchestratorState(**result)
        return result


# ── Singleton management ──────────────────────────────────────────────────────

_orchestrator_instance: Optional[OrchestratorGraph] = None


def init_orchestrator(
    db_factory,
    send_whatsapp_fn,
    check_rating_gate_fn,
    get_or_create_requester_fn,
) -> OrchestratorGraph:
    global _orchestrator_instance
    _orchestrator_instance = OrchestratorGraph(
        db_factory=db_factory,
        send_whatsapp_fn=send_whatsapp_fn,
        check_rating_gate_fn=check_rating_gate_fn,
        get_or_create_requester_fn=get_or_create_requester_fn,
    )
    return _orchestrator_instance


def get_orchestrator() -> OrchestratorGraph:
    if _orchestrator_instance is None:
        raise RuntimeError(
            "Orchestrator not initialised. Call init_orchestrator() during app startup."
        )
    return _orchestrator_instance
