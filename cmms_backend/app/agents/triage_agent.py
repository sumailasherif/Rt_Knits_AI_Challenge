"""
Agent 2 — Triage Agent

Responsibilities:
  - Map fault to P0 / P1 / P2 priority using rule-based criteria + LLM
  - Determine required trade (Mechanical / Electrical / Civil / Plumbing / IT)
  - Set estimated repair time and SLA deadline
  - Inject Knowledge Agent context into the decision

PRIORITY RULES (non-negotiable, enforced before LLM call):
  P0 — Production Down or Safety Risk:
       keywords: stopped, fire, sparks, explosion, flooding, no power, emergency,
                 safety, critical, down, cannot run
  P1 — Scheduled / Will impact production within 8 hours:
       keywords: leaking, overheating, unusual noise, slow, reduced output,
                 intermittent, warning light
  P2 — Anytime / Cosmetic or minor:
       everything else
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.schemas.agents import FaultDetail, TriageInput, TriageOutput, TriageRationale

log = structlog.get_logger(__name__)
settings = get_settings()

# SLA targets in hours
SLA_MAP = {"P0": 0.5, "P1": 8.0, "P2": 48.0}
VALID_PRIORITIES = frozenset(SLA_MAP)

# Estimated minutes by priority (fallback if LLM doesn't provide)
DEFAULT_MINUTES = {"P0": 30, "P1": 90, "P2": 120}

P0_KEYWORDS = {
    "stopped", "stop", "down", "no power", "power cut", "fire", "flame",
    "smoke", "sparks", "spark", "explosion", "explode", "flooding", "flood",
    "water everywhere", "emergency", "safety", "critical", "danger",
    "cannot run", "not running", "production halt", "halt",
}
P1_KEYWORDS = {
    "leak", "leaking", "overheat", "overheating", "hot", "noise", "noisy",
    "vibration", "slow", "reduced", "intermittent", "warning", "alert",
    "error code", "unusual", "strange", "blocked",
}

TRADE_KEYWORDS = {
    "Mechanical": {
        "bearing", "belt", "gear", "motor", "pump", "valve", "shaft", "jam",
        "needle", "cam", "knitting", "spindle", "roller", "chain",
    },
    "Electrical": {
        "electric", "electrical", "power", "fuse", "breaker", "panel",
        "wire", "short", "circuit", "voltage", "current", "sensor", "plc",
        "inverter", "motor drive",
    },
    "Civil": {
        "wall", "floor", "ceiling", "roof", "crack", "structural", "concrete",
        "pipe burst", "civil",
    },
    "Plumbing": {
        "water", "pipe", "drain", "tap", "leak", "flooding", "sewage",
        "plumbing",
    },
    "IT": {
        "computer", "software", "network", "internet", "server", "screen",
        "printer", "scan", "barcode", "system", "it ",
    },
}


def _rule_based_priority(text: str, asset_is_critical: bool) -> tuple[str, str]:
    """Return (priority, rule_matched) based on keyword rules."""
    lower = text.lower()

    # P0: production-stop / safety keywords OR critical asset
    for kw in P0_KEYWORDS:
        if kw in lower:
            return "P0", f"P0 keyword matched: '{kw}'"
    if asset_is_critical and any(kw in lower for kw in P1_KEYWORDS):
        return "P0", "Critical asset with P1 symptom → escalated to P0"

    # P1: degradation keywords
    for kw in P1_KEYWORDS:
        if kw in lower:
            return "P1", f"P1 keyword matched: '{kw}'"

    return "P2", "No urgency keywords — defaulting to P2"


def _rule_based_trade(text: str, asset_required_trade: str | None) -> str:
    """Infer required trade from fault text, falling back to asset's required_trade."""
    if asset_required_trade:
        return asset_required_trade
    lower = text.lower()
    scores: dict[str, int] = {t: 0 for t in TRADE_KEYWORDS}
    for trade, keywords in TRADE_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[trade] += 1
    best = max(scores, key=lambda t: scores[t])
    return best if scores[best] > 0 else "Mechanical"


class TriageAgent(BaseAgent):
    name = "TriageAgent"

    @property
    def system_prompt(self) -> str:
        return """You are the Triage Agent for RT Knits factory CMMS.

Your job is to validate a preliminary priority assignment and estimate repair time.
You have been given:
  1. The fault description
  2. A rule-based priority (P0/P1/P2) derived from keywords
  3. Relevant knowledge base snippets from SOPs and manuals
  4. The required trade

You must respond with a JSON object containing:
{
  "priority": "P0" | "P1" | "P2",
  "required_trade": "Mechanical" | "Electrical" | "Civil" | "Plumbing" | "IT" | "General",
  "estimated_minutes": integer (realistic repair time),
  "rationale": {
    "rule_matched": "string explaining the rule",
    "evidence": "string explaining why this priority was chosen"
  }
}

RULES:
- You MAY upgrade a priority (P2→P1, P1→P0) if the fault description warrants it.
- You may NOT downgrade a P0 — safety is non-negotiable.
- estimated_minutes should reflect: P0=15-60, P1=30-180, P2=30-240.
- Be concise and deterministic — this feeds directly into production dispatch.
"""

    async def run(
        self,
        inp: TriageInput,
        knowledge_context: str = "",
    ) -> TriageOutput:
        log.info("triage_agent_start", request_id=inp.request_id)

        fault_text = (
            f"{inp.fault.fault_description} "
            f"{inp.fault.urgency_signal or ''} "
            f"{inp.fault.photo_analysis or ''}"
        )

        # ── Rule-based pre-pass ───────────────────────────────────────────────
        rule_priority, rule_matched = _rule_based_priority(fault_text, inp.asset_is_critical)
        rule_trade = _rule_based_trade(fault_text, inp.asset_required_trade)

        # ── LLM validation ────────────────────────────────────────────────────
        prompt = f"""Fault Report:
Asset: {inp.fault.asset_name or 'Unknown'}
Description: {inp.fault.fault_description}
Urgency signal: {inp.fault.urgency_signal or 'none'}
Photo analysis: {inp.fault.photo_analysis or 'none'}
Asset is critical: {inp.asset_is_critical}

Rule-based preliminary assessment:
  Priority: {rule_priority} (reason: {rule_matched})
  Required trade: {rule_trade}

Knowledge base context:
{knowledge_context or 'No relevant documents found.'}

Validate or adjust the priority and estimate repair time. Respond in JSON."""

        try:
            raw = await self._chat(prompt, json_mode=True)
            data = self._parse_json(raw)
            priority = data.get("priority", rule_priority)
            if priority not in VALID_PRIORITIES:
                priority = rule_priority
            # Enforce P0 cannot be downgraded
            if rule_priority == "P0" and priority != "P0":
                priority = "P0"
            required_trade = data.get("required_trade", rule_trade)
            estimated_minutes = int(
                data.get("estimated_minutes", DEFAULT_MINUTES[priority])
            )
            rationale = TriageRationale(
                rule_matched=data.get("rationale", {}).get("rule_matched", rule_matched),
                evidence=data.get("rationale", {}).get("evidence", "LLM validation"),
            )
        except Exception as exc:
            log.warning("triage_llm_failed_using_rules", error=str(exc))
            priority = rule_priority
            required_trade = rule_trade
            estimated_minutes = DEFAULT_MINUTES[priority]
            rationale = TriageRationale(rule_matched=rule_matched, evidence="Rule-based fallback")

        sla_hours = SLA_MAP[priority]
        wo_id = str(uuid.uuid4())

        output = TriageOutput(
            wo_id=wo_id,
            priority=priority,  # type: ignore[arg-type]
            required_trade=required_trade,
            estimated_minutes=estimated_minutes,
            sla_hours=sla_hours,
            rationale=rationale,
            knowledge_snippets=[knowledge_context] if knowledge_context else [],
        )

        log.info(
            "triage_agent_complete",
            wo_id=wo_id,
            priority=priority,
            trade=required_trade,
            est_min=estimated_minutes,
        )
        return output
