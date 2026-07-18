"""
Agent 1 — Maintenance Supervisor (Orchestrator)

This module builds the LangGraph StateGraph that routes every inbound
WhatsApp message through the correct sequence of agents.

Graph topology:
                   ┌─────────────────┐
  WhatsApp msg ──► │  rating_gate    │
                   └────────┬────────┘
                     blocked│  clear
                    send_fb │  ▼
                    request │  ┌──────────────┐
                            │  │  intake_node  │
                            │  └──────┬───────┘
                            │  needs_more│  complete
                            │  ask_user  │  ▼
                            │            │  ┌──────────────────┐
                            │            │  │  knowledge_node   │
                            │            │  └──────┬───────────┘
                            │            │         │
                            │            │  ┌──────▼───────┐
                            │            │  │  triage_node  │
                            │            │  └──────┬────────┘
                            │            │    P0/P1/P2│
                            │            │  ┌─────────▼──────┐
                            │            │  │  dispatch_node  │
                            │            │  └─────────────────┘
                            │            │         │
                            └────────────┴─────────▼
                                                  END
"""
from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Annotated, Any, Optional

import structlog
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from sqlalchemy.ext.asyncio import AsyncSession

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
    OrchestratorState,
    RatingGateBlock,
    TriageInput,
)

log = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# LangGraph State type alias
# We use the OrchestratorState Pydantic model directly as the graph state.
# LangGraph accepts any TypedDict or Pydantic model.
# ─────────────────────────────────────────────────────────────────────────────
GraphState = OrchestratorState


class OrchestratorGraph:
    """
    Wraps the compiled LangGraph and exposes a single `invoke()` entry point.
    Each inbound WhatsApp message creates a fresh state and runs through the graph.
    """

    def __init__(
        self,
        db_factory,             # callable → AsyncSession (injected at runtime)
        send_whatsapp_fn,       # async fn(to, body, buttons?) for outbound msgs
        check_rating_gate_fn,   # async fn(requester_id, db) → RatingGateBlock
        get_or_create_requester_fn,  # async fn(phone, db) → requester_id
    ) -> None:
        self._db_factory = db_factory
        self._send_whatsapp = send_whatsapp_fn
        self._check_rating_gate = check_rating_gate_fn
        self._get_or_create_requester = get_or_create_requester_fn

        # ── Agent singletons ──────────────────────────────────────────────────
        self.intake = IntakeAgent()
        self.knowledge = KnowledgeAgent()
        self.triage = TriageAgent()
        self.dispatch = DispatchAgent()
        self.planning = PlanningAgent()
        self.analytics = AnalyticsAgent()

        self._graph = self._build_graph()

    # ─────────────────────────────────────────────────────────────────────────
    # Graph construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_graph(self):
        builder = StateGraph(OrchestratorState)

        # Register nodes
        builder.add_node("rating_gate", self._rating_gate_node)
        builder.add_node("intake", self._intake_node)
        builder.add_node("knowledge", self._knowledge_node)
        builder.add_node("triage", self._triage_node)
        builder.add_node("dispatch", self._dispatch_node)
        builder.add_node("send_reply", self._send_reply_node)

        # Set entry point
        builder.set_entry_point("rating_gate")

        # Conditional routing after rating gate
        builder.add_conditional_edges(
            "rating_gate",
            self._route_after_gate,
            {
                "blocked": "send_reply",    # send feedback request to requester
                "proceed": "intake",
            },
        )

        # Conditional routing after intake
        builder.add_conditional_edges(
            "intake",
            self._route_after_intake,
            {
                "clarify": "send_reply",    # ask for more details
                "proceed": "knowledge",
            },
        )

        # Linear: knowledge → triage → dispatch → send_reply → END
        builder.add_edge("knowledge", "triage")
        builder.add_edge("triage", "dispatch")
        builder.add_edge("dispatch", "send_reply")
        builder.add_edge("send_reply", END)

        return builder.compile()

    # ─────────────────────────────────────────────────────────────────────────
    # Nodes
    # ─────────────────────────────────────────────────────────────────────────

    async def _rating_gate_node(self, state: OrchestratorState) -> dict:
        """Check if requester has unrated completed work orders."""
        async with self._db_factory() as db:
            requester_id = await self._get_or_create_requester(state.sender_phone, db)
            gate = await self._check_rating_gate(requester_id, db)

        if gate.blocked:
            # Build a blocking message
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

    async def _intake_node(self, state: OrchestratorState) -> dict:
        """Run the Intake Agent to extract structured fault details."""
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
            log.error("orchestrator_intake_failed", error=str(exc))
            return {
                "error": str(exc),
                "outbound_message": "⚠️ Sorry, I couldn't process your message. Please try again.",
                "current_route": "end",
            }

        updates: dict[str, Any] = {"intake_output": output, "current_route": "knowledge"}

        if not output.is_complete:
            updates["outbound_message"] = output.clarification_needed
            updates["awaiting_reply"] = True

        return updates

    async def _knowledge_node(self, state: OrchestratorState) -> dict:
        """Query knowledge base for relevant SOPs/manuals."""
        if not state.intake_output:
            return {"knowledge_output": None}

        fault = state.intake_output.fault
        query = (
            f"{fault.fault_description} "
            f"{fault.asset_name or ''} "
            f"{fault.urgency_signal or ''}"
        ).strip()

        try:
            output = await self.knowledge.run(
                KnowledgeInput(
                    query=query,
                    asset_id=fault.asset_id,
                    top_k=3,
                )
            )
        except Exception as exc:
            log.warning("orchestrator_knowledge_failed", error=str(exc))
            from app.schemas.agents import KnowledgeOutput
            output = KnowledgeOutput(snippets=[], combined_context="")

        return {"knowledge_output": output, "current_route": "triage"}

    async def _triage_node(self, state: OrchestratorState) -> dict:
        """Run triage to assign priority, trade, and SLA."""
        if not state.intake_output:
            return {"error": "No intake output for triage"}

        knowledge_ctx = (
            state.knowledge_output.combined_context
            if state.knowledge_output
            else ""
        )

        triage_input = TriageInput(
            request_id=state.intake_output.request_id,
            fault=state.intake_output.fault,
            asset_is_critical=False,   # TODO: resolve from DB asset record
            asset_required_trade=None,
        )

        try:
            output = await self.triage.run(triage_input, knowledge_context=knowledge_ctx)
        except Exception as exc:
            log.error("orchestrator_triage_failed", error=str(exc))
            return {"error": str(exc)}

        # Persist work order to DB
        async with self._db_factory() as db:
            from datetime import datetime, timedelta, timezone
            from app.db.models import WorkOrder as WOModel
            from app.agents.triage_agent import SLA_MAP

            sla_due = datetime.now(timezone.utc) + timedelta(hours=output.sla_hours)
            wo = WOModel(
                wo_id=output.wo_id,
                request_id=state.intake_output.request_id,
                priority=output.priority,
                status="Open",
                description=state.intake_output.fault.fault_description,
                required_trade=output.required_trade,
                estimated_minutes=output.estimated_minutes,
                sla_due_at=sla_due,
                assigned_techs=[],
            )
            db.add(wo)

        return {"triage_output": output, "current_route": "dispatch"}

    async def _dispatch_node(self, state: OrchestratorState) -> dict:
        """Assign a technician and create the assignment."""
        if not state.triage_output:
            return {"error": "No triage output for dispatch"}

        t = state.triage_output
        dispatch_input = DispatchInput(
            wo_id=t.wo_id,
            priority=t.priority,  # type: ignore[arg-type]
            required_trade=t.required_trade,
            estimated_minutes=t.estimated_minutes,
        )

        try:
            async with self._db_factory() as db:
                output = await self.dispatch.run(dispatch_input, db, self._send_whatsapp)
        except RuntimeError as exc:
            # No tech available — inform requester, WO stays Queued
            log.warning("orchestrator_no_tech", wo_id=t.wo_id, error=str(exc))
            msg = (
                f"✅ Your request has been logged (WO `{t.wo_id[:8]}`, priority {t.priority}).\n"
                "No technician is currently available but you'll be notified when one is assigned."
            )
            return {
                "dispatch_output": None,
                "outbound_message": msg,
                "current_route": "end",
            }
        except Exception as exc:
            log.error("orchestrator_dispatch_failed", error=str(exc))
            return {"error": str(exc)}

        # Schedule P0 escalation via background task
        if t.priority == "P0" and output.escalation_scheduled:
            from app.services.escalation import schedule_p0_escalation
            schedule_p0_escalation(output.assignment_id, output.wo_id)

        # Build confirmation message for requester
        msg = (
            f"✅ *Work Order Created* — {t.priority}\n"
            f"WO ID: `{t.wo_id[:8]}`\n"
            f"Technician: {output.assigned_tech.tech_name}\n"
            f"ETA: ~{t.estimated_minutes} min\n\n"
            "You'll receive an update when the job is completed. "
            "You'll then be asked to rate the service."
        )

        return {
            "dispatch_output": output,
            "outbound_message": msg,
            "current_route": "end",
        }

    async def _send_reply_node(self, state: OrchestratorState) -> dict:
        """Send the final outbound message back to the requester."""
        if state.outbound_message:
            try:
                await self._send_whatsapp(
                    to=state.sender_phone,
                    body=state.outbound_message,
                    buttons=state.outbound_buttons,
                )
            except Exception as exc:
                log.error("orchestrator_send_reply_failed", error=str(exc))
        return {}

    # ─────────────────────────────────────────────────────────────────────────
    # Routing functions
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _route_after_gate(state: OrchestratorState) -> str:
        return "blocked" if state.rating_gate.blocked else "proceed"

    @staticmethod
    def _route_after_intake(state: OrchestratorState) -> str:
        if state.intake_output and not state.intake_output.is_complete:
            return "clarify"
        return "proceed"

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers to extract media from state messages
    # ─────────────────────────────────────────────────────────────────────────

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

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    async def invoke(self, initial_state: OrchestratorState) -> OrchestratorState:
        """
        Run a single WhatsApp message through the full agent graph.
        Returns the final state.
        """
        log.info(
            "orchestrator_invoke",
            session_id=initial_state.session_id,
            phone=initial_state.sender_phone,
        )
        result = await self._graph.ainvoke(initial_state)
        return OrchestratorState(**result) if isinstance(result, dict) else result


# ─────────────────────────────────────────────────────────────────────────────
# Singleton factory — instantiated once at app startup
# ─────────────────────────────────────────────────────────────────────────────

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
        raise RuntimeError("Orchestrator not initialised. Call init_orchestrator() at startup.")
    return _orchestrator_instance
