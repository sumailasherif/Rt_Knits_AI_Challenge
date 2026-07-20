"""
Router: /webhook

Two endpoints:
  GET  /webhook  — Meta webhook verification (one-time setup)
  POST /webhook  — Inbound WhatsApp messages from Meta Cloud API

The POST handler:
  1. Validates the X-Hub-Signature-256 header (HMAC-SHA256)
  2. Parses the WhatsApp payload
  3. Deduplicates via whatsapp_message_id
  4. Routes to the Orchestrator graph
  5. Handles special reply patterns (feedback, tech acknowledgement)
  6. Marks message as read
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import get_orchestrator
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.agents import OrchestratorState
from app.schemas.whatsapp import WhatsAppInbound
from app.services.rating_gate import check_rating_gate, parse_and_save_feedback
from app.services.requester_resolver import get_or_create_requester
from app.services.whatsapp import mark_message_read, send_whatsapp_message

router = APIRouter(tags=["WhatsApp Webhook"])
log = structlog.get_logger(__name__)
settings = get_settings()

# Simple in-process deduplication cache (message_id → True)
# In production, replace with Redis SET with TTL
_seen_message_ids: set[str] = set()
_MAX_SEEN = 10_000


# ─────────────────────────────────────────────────────────────────────────────
# GET /webhook — Meta hub verification
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> Response:
    """
    Meta calls this once to verify your webhook URL.
    Returns the hub.challenge value as plain text on success.
    """
    if (
        hub_mode == "subscribe"
        and hub_verify_token == settings.whatsapp_verify_token
        and hub_challenge
    ):
        log.info("webhook_verified")
        return Response(content=hub_challenge, media_type="text/plain")

    log.warning("webhook_verification_failed", token=hub_verify_token)
    raise HTTPException(status_code=403, detail="Forbidden")


# ─────────────────────────────────────────────────────────────────────────────
# POST /webhook — Inbound messages
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_hub_signature_256: Annotated[str | None, Header()] = None,
) -> dict:
    """
    Receive and process inbound WhatsApp messages.
    Returns 200 immediately — Meta expects a fast response.
    """
    raw_body = await request.body()

    # ── HMAC validation ───────────────────────────────────────────────────────
    _verify_signature(raw_body, x_hub_signature_256)

    # ── Parse payload ─────────────────────────────────────────────────────────
    try:
        payload = WhatsAppInbound.model_validate(json.loads(raw_body))
    except Exception as exc:
        log.warning("webhook_parse_failed", error=str(exc))
        return {"status": "ignored"}

    messages = payload.get_messages()
    if not messages:
        # Delivery receipts, read receipts, etc. — ignore silently
        return {"status": "ok"}

    for msg, _display_phone in messages:
        # ── Deduplication ─────────────────────────────────────────────────────
        if msg.id in _seen_message_ids:
            log.debug("webhook_duplicate_message", message_id=msg.id)
            continue
        _seen_message_ids.add(msg.id)
        if len(_seen_message_ids) > _MAX_SEEN:
            _seen_message_ids.clear()

        # Mark as read immediately (blue double tick)
        await mark_message_read(msg.id)

        # ── Resolve or create requester ───────────────────────────────────────
        phone = msg.sender_phone
        requester_id = await get_or_create_requester(phone, db)

        # ── Handle interactive button replies ─────────────────────────────────
        if msg.is_button_reply:
            await _handle_button_reply(msg.button_reply_id or "", phone, requester_id, db)
            continue

        # ── Handle plain-text replies (feedback rating / commands) ────────────
        text = msg.text_body or ""

        # Check if this is a feedback rating submission
        saved, fb_reply = await parse_and_save_feedback(text, requester_id, db)
        if saved:
            await send_whatsapp_message(to=phone, body=fb_reply)
            continue

        # ── Main Orchestrator flow ────────────────────────────────────────────
        await _route_to_orchestrator(msg, phone, requester_id, db)

    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _verify_signature(body: bytes, signature_header: str | None) -> None:
    """
    Validate X-Hub-Signature-256 header.
    Skip in development to ease local testing.
    """
    if settings.app_env == "development":
        return
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing signature")
    app_secret = settings.whatsapp_app_secret or settings.app_secret_key
    expected = "sha256=" + hmac.new(
        app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature")


async def _route_to_orchestrator(
    msg,
    phone: str,
    requester_id: str,
    db: AsyncSession,
) -> None:
    """Build initial OrchestratorState and run the agent graph."""
    orchestrator = get_orchestrator()

    # Build the message dict that goes into OrchestratorState.messages
    message_entry: dict = {"role": "user", "type": msg.type}
    if msg.type == "text" and msg.text:
        message_entry["content"] = msg.text.body
    elif msg.type == "image" and msg.image:
        message_entry["media_id"] = msg.image.id
        message_entry["caption"] = msg.image.caption
    elif msg.type == "audio" and msg.audio:
        message_entry["media_id"] = msg.audio.id

    initial_state = OrchestratorState(
        session_id=str(uuid.uuid4()),
        sender_phone=phone,
        whatsapp_message_id=msg.id,
        messages=[message_entry],
    )

    try:
        await orchestrator.invoke(initial_state)
    except Exception as exc:
        log.error("orchestrator_invoke_failed", phone=phone, error=str(exc), exc_info=True)
        await send_whatsapp_message(
            to=phone,
            body="⚠️ Something went wrong processing your request. Please try again in a moment.",
        )


async def _handle_button_reply(
    button_id: str,
    phone: str,
    requester_id: str,
    db: AsyncSession,
) -> None:
    """
    Handle technician/requester interactive button replies:
      ack_<assignment_id[:8]>      — technician acknowledged dispatch
      arrived_<assignment_id[:8]>  — technician on site
      done_<assignment_id[:8]>     — technician completed job
      confirm_plan_<plan_id[:8]>   — technician confirmed daily plan
      conflict_plan_<plan_id[:8]>  — technician has scheduling conflict
    """
    log.info("button_reply", button_id=button_id, phone=phone)

    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.db.models import Assignment, DailyPlan

    now = datetime.now(timezone.utc)

    if button_id.startswith("ack_"):
        partial = button_id[4:]
        result = await db.execute(
            select(Assignment).where(Assignment.assignment_id.ilike(f"{partial}%"))
        )
        a = result.scalar_one_or_none()
        if a and not a.acknowledged_at:
            a.acknowledged_at = now
            log.info("assignment_acknowledged", assignment_id=a.assignment_id)
            await send_whatsapp_message(
                to=phone,
                body=f"✅ Assignment `{partial}` acknowledged. Head to the site and tap ON SITE when you arrive.",
                buttons=[("arrived_" + partial, "📍 ON SITE")],
            )

    elif button_id.startswith("arrived_"):
        partial = button_id[8:]
        result = await db.execute(
            select(Assignment).where(Assignment.assignment_id.ilike(f"{partial}%"))
        )
        a = result.scalar_one_or_none()
        if a and not a.arrived_at:
            a.arrived_at = now
            log.info("assignment_arrived", assignment_id=a.assignment_id)
            await send_whatsapp_message(
                to=phone,
                body=f"📍 Location confirmed for `{partial}`. Reply DONE when complete.",
                buttons=[("done_" + partial, "✅ DONE")],
            )

    elif button_id.startswith("done_"):
        partial = button_id[5:]
        result = await db.execute(
            select(Assignment).where(Assignment.assignment_id.ilike(f"{partial}%"))
        )
        a = result.scalar_one_or_none()
        if a and not a.completed_at:
            from app.services.reward import calculate_completion_and_close
            await calculate_completion_and_close(a.wo_id, a.assignment_id, None, db)
            log.info("assignment_completed", assignment_id=a.assignment_id)
            # Notify requester to rate the job
            await _notify_requester_to_rate(a.wo_id, db)
            await send_whatsapp_message(
                to=phone,
                body=f"✅ Job `{partial}` marked as *COMPLETED*. Great work! 🎉",
            )

    elif button_id.startswith("confirm_plan_"):
        partial = button_id[13:]
        result = await db.execute(
            select(DailyPlan).where(DailyPlan.plan_id.ilike(f"{partial}%"))
        )
        plan = result.scalar_one_or_none()
        if plan:
            plan.confirmed = True
            await send_whatsapp_message(to=phone, body="✅ Shift plan confirmed. See you tomorrow!")

    elif button_id.startswith("conflict_plan_"):
        partial = button_id[14:]
        await send_whatsapp_message(
            to=phone,
            body=(
                "⚠️ Conflict noted. Please reply with your reason and the Planning Agent "
                "will adjust your schedule before shift start."
            ),
        )


async def _notify_requester_to_rate(wo_id: str, db: AsyncSession) -> None:
    """Send a rating request to the requester when their WO is completed."""
    from sqlalchemy import select
    from app.db.models import Requester, TaskRequest, WorkOrder

    result = await db.execute(
        select(Requester)
        .join(TaskRequest, TaskRequest.requester_id == Requester.requester_id)
        .join(WorkOrder, WorkOrder.request_id == TaskRequest.request_id)
        .where(WorkOrder.wo_id == wo_id)
        .limit(1)
    )
    requester = result.scalar_one_or_none()
    if not requester:
        return

    await send_whatsapp_message(
        to=requester.phone_number,
        body=(
            f"✅ Your maintenance request (WO `{wo_id[:8]}`) has been *completed*!\n\n"
            "Please rate the service from 1 to 5:\n"
            f"Reply: `{wo_id[:8]} 5` (replace 5 with your rating)"
        ),
    )
