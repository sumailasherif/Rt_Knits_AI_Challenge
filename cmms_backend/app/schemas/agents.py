"""
Pydantic v2 I/O schemas for all 7 CMMS agents.

These schemas serve two purposes:
  1. Validate agent inputs and outputs at each LangGraph node boundary.
  2. Act as the typed state slots in OrchestratorState.

Design rule: every agent output is a strict subset of OrchestratorState so
the orchestrator can merge results by spreading the output dict into state.
"""
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Shared enumerations (string literals for Pydantic v2 use_enum_values compat)
# ─────────────────────────────────────────────────────────────────────────────

PriorityLiteral = Literal["P0", "P1", "P2"]
RouteLiteral = Literal[
    "intake", "triage", "dispatch", "planning", "knowledge", "analytics", "end"
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Intake Agent
# ─────────────────────────────────────────────────────────────────────────────

class IntakeInput(BaseModel):
    sender_phone: str
    whatsapp_message_id: str
    raw_text: Optional[str] = None
    image_media_id: Optional[str] = None   # WhatsApp media ID — must be fetched via API
    audio_media_id: Optional[str] = None   # WhatsApp voice note media ID
    language_hint: Optional[str] = "en"


class FaultDetail(BaseModel):
    """Structured fault extracted by the Intake Agent."""
    asset_name: Optional[str] = None
    asset_id: Optional[str] = None
    fault_description: str
    location: Optional[str] = None
    urgency_signal: Optional[str] = None   # e.g. "machine stopped", "sparks", "water leak"
    photo_analysis: Optional[str] = None   # GPT-4o vision summary
    audio_transcript: Optional[str] = None
    detected_language: str = "en"
    translated_text: Optional[str] = None  # English translation if original is non-English


class IntakeOutput(BaseModel):
    request_id: str
    requester_id: str
    fault: FaultDetail
    is_complete: bool = True               # False = still missing required details
    clarification_needed: Optional[str] = None  # Question to ask the requester


# ─────────────────────────────────────────────────────────────────────────────
# 2. Triage Agent
# ─────────────────────────────────────────────────────────────────────────────

class TriageInput(BaseModel):
    request_id: str
    fault: FaultDetail
    asset_is_critical: bool = False
    asset_required_trade: Optional[str] = None


class TriageRationale(BaseModel):
    rule_matched: str
    evidence: str


class TriageOutput(BaseModel):
    wo_id: str
    priority: PriorityLiteral
    required_trade: str
    estimated_minutes: int = Field(..., ge=5, description="Estimated repair time in minutes")
    sla_hours: float = Field(..., description="Hours until SLA breach: P0=0.5, P1=8, P2=48")
    rationale: TriageRationale
    knowledge_snippets: list[str] = Field(
        default_factory=list, description="Relevant SOP/manual excerpts from Knowledge Agent"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Dispatch Agent
# ─────────────────────────────────────────────────────────────────────────────

class DispatchInput(BaseModel):
    wo_id: str
    priority: PriorityLiteral
    required_trade: str
    estimated_minutes: int


class TechCandidate(BaseModel):
    tech_id: str
    tech_name: str
    phone_number: str
    trade: str
    current_load: int   # number of active assignments
    reward_score: float


class DispatchOutput(BaseModel):
    assignment_id: str
    wo_id: str
    assigned_tech: TechCandidate
    # If P0 preemption happened, carry the paused assignment id
    preempted_assignment_id: Optional[str] = None
    escalation_scheduled: bool = False     # True = APScheduler P0 countdown started
    whatsapp_sent: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# 4. Planning Agent  (nightly batch)
# ─────────────────────────────────────────────────────────────────────────────

class PlanningInput(BaseModel):
    plan_date: str   # ISO date string YYYY-MM-DD
    force: bool = False  # bypass "already ran today" guard


class TechPlan(BaseModel):
    tech_id: str
    tech_name: str
    phone_number: str
    ordered_wo_ids: list[str]
    total_estimated_minutes: int


class PlanningOutput(BaseModel):
    plan_date: str
    plans_created: list[TechPlan]
    backlog_rolled_forward: list[str]   # wo_ids that couldn't fit today
    messages_sent: int


# ─────────────────────────────────────────────────────────────────────────────
# 5. Knowledge Agent
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeInput(BaseModel):
    query: str
    asset_id: Optional[str] = None
    top_k: int = Field(3, ge=1, le=10)


class KnowledgeSnippet(BaseModel):
    doc_id: str
    title: str
    source_type: str
    snippet: str
    relevance_score: float


class KnowledgeOutput(BaseModel):
    snippets: list[KnowledgeSnippet]
    combined_context: str   # pre-formatted string injected into Triage Agent prompt


# ─────────────────────────────────────────────────────────────────────────────
# 6. Analytics Agent
# ─────────────────────────────────────────────────────────────────────────────

class AnalyticsInput(BaseModel):
    report_type: Literal[
        "kpi_summary", "technician_performance", "asset_failures", "sla_compliance"
    ]
    date_from: Optional[str] = None   # ISO date
    date_to: Optional[str] = None
    dept_id: Optional[str] = None


class KPISummary(BaseModel):
    total_work_orders: int
    completed: int
    open: int
    avg_resolution_hours: float
    avg_feedback_rating: float
    p0_count: int
    p1_count: int
    p2_count: int
    sla_breach_count: int


class TechPerformance(BaseModel):
    tech_id: str
    tech_name: str
    completed_jobs: int
    avg_duration_minutes: float
    avg_rating: float
    reward_score: float


class AssetFailure(BaseModel):
    asset_id: str
    asset_name: str
    failure_count: int
    most_common_trade: str


class AnalyticsOutput(BaseModel):
    report_type: str
    generated_at: datetime
    kpi: Optional[KPISummary] = None
    technician_performance: Optional[list[TechPerformance]] = None
    asset_failures: Optional[list[AssetFailure]] = None
    raw_data: Optional[dict[str, Any]] = None


# ─────────────────────────────────────────────────────────────────────────────
# 7. Orchestrator State  (LangGraph StateGraph typed dict)
# ─────────────────────────────────────────────────────────────────────────────

class RatingGateBlock(BaseModel):
    """Populated when a requester is blocked from submitting new requests."""
    blocked: bool = False
    pending_wo_ids: list[str] = Field(default_factory=list)
    message: Optional[str] = None   # WhatsApp message to send


class OrchestratorState(BaseModel):
    """
    Full state passed between LangGraph nodes.
    Each agent reads what it needs and writes back its output fields.
    """
    # ── Session metadata ──────────────────────────────────────────────────────
    session_id: str
    sender_phone: str
    whatsapp_message_id: Optional[str] = None
    current_route: Optional[RouteLiteral] = None
    # Conversation turn history (list of {role, content} dicts)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    # If True, the orchestrator has sent a reply and is waiting for user input
    awaiting_reply: bool = False

    # ── Rating Gate ────────────────────────────────────────────────────────────
    rating_gate: RatingGateBlock = Field(default_factory=RatingGateBlock)

    # ── Intake Agent output ───────────────────────────────────────────────────
    intake_output: Optional[IntakeOutput] = None

    # ── Triage Agent output ───────────────────────────────────────────────────
    triage_output: Optional[TriageOutput] = None

    # ── Dispatch Agent output ─────────────────────────────────────────────────
    dispatch_output: Optional[DispatchOutput] = None

    # ── Knowledge Agent output ────────────────────────────────────────────────
    knowledge_output: Optional[KnowledgeOutput] = None

    # ── Planning Agent output ─────────────────────────────────────────────────
    planning_output: Optional[PlanningOutput] = None

    # ── Analytics Agent output ────────────────────────────────────────────────
    analytics_output: Optional[AnalyticsOutput] = None

    # ── Error tracking ────────────────────────────────────────────────────────
    error: Optional[str] = None
    retry_count: int = 0

    # ── Final reply to send back to WhatsApp ──────────────────────────────────
    outbound_message: Optional[str] = None
    outbound_buttons: Optional[list[tuple[str, str]]] = None  # [(id, title)]
