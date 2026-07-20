"""
Router: /webhook

Two endpoints:
  GET  /webhook  — Meta hub verification (one-time setup)
  POST /webhook  — Inbound WhatsApp messages from Meta Cloud API

Fixes applied:
  - hub.mode / hub.verify_token / hub.challenge query params now use
    FastAPI Query aliases (dot-notation) so Meta's GET verification works.
  - HMAC validation uses whatsapp_app_secret (Meta App Secret) not the
    generic app_secret_key; falls back gracefully when field is empty.
  - Removed unused imports (Query on GET was previously bare param names).
  - _notify_requester_to_rate now uses an explicit join instead of a
    lazy relationship load, safe for async sessions.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Optional

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

# In-process dedup cache — replace with Redis for multi-worker deployments
_seen_message_ids: set[str] = set()
_MAX_SEEN = 10_000


# ─────────────────────────────────────────────────────────────────────────────
# GET /webhook — Meta hub verification
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/webhook")
async def verify_webhook(
    # BUG FIX: Meta sends "hub.mode", "hub.verify_token", "hub.challenge"
    # as query parameters. FastAPI doesn't allow dots in parameter names
    # natively, so we MUST use Query(alias=...) for each.
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
) -> Response:
    """
    Meta calls this endpoint once to verify your webhook URL during setup.
    Must return hub.challenge as plain text with HTTP 200.
    """
    if (
        hub_mode == "subscribe"
        and hub_verify_token == settings.whatsapp_verify_token
        and hub_challenge
    ):
        log.info("webhook_verified")
        return Response(content=hub_challenge, media_type="text/plain")

    log.warning(
        "webhook_verification_failed",
        mode=hub_mode,
        token_matches=(hub_verify_token == settings.whatsapp_verify_token),
    )
    raise HTTPException(status_code=403, detail="Forbidden")


# ─────────────────────────────────────────────────────────────────────────────
# POST /webhook — Inbound messages
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_hub_signature_256: Annotated[Optional[str], Header()] = None,
) -> dict:
    """
    Receive and process inbound WhatsApp messages.
    Always returns 200 — Meta will retry on any non-200 response.
    """
    raw_body = await request.body()

    # ── HMAC signature validation ─────────────────────────────────────────────
    _verify_signature(raw_body, x_hub_signature_256)

    # ── Parse top-level payload ───────────────────────────────────────────────
    try:
        payload = WhatsAppInbound.model_validate(json.loads(raw_body))
    except Exception as exc:
        log.warning("webhook_parse_failed", error=str(exc))
        # Return 200 to stop Meta from retrying a malformed payload
        return {"status": "ignored"}

    messages = payload.get_messages()
    if not messages:
        # Delivery/read receipts — acknowledge silently
        return {"status": "ok"}

    for msg, _display_phone in messages:
        # ── Deduplication ─────────────────────────────────────────────────────
        if msg.id in _seen_message_ids:
            log.debug("webhook_duplicate_skipped", message_id=msg.id)
            continue
        _seen_message_ids.add(msg.id)
        if len(_seen_message_ids) > _MAX_SEEN:
            _seen_message_ids.clear()

        # ── Mark inbound message as read (double blue tick) ───────────────────
        await mark_message_read(msg.id)

        # ── Resolve or auto-create requester record ───────────────────────────
        phone = msg.sender_phone
        requester_id = await get_or_create_requester(phone, db)

        # ── Interactive button replies (technician workflow) ──────────────────
        if msg.is_button_reply:
            await _handle_button_reply(
                button_id=msg.button_reply_id or "",
                phone=phone,
                requester_id=requester_id,
                db=db,
            )
            continue

        # ── Plain-text: check for feedback rating first ───────────────────────
        text = msg.text_body or ""
        saved, fb_reply = await parse_and_save_feedback(text, requester_id, db)
        if saved:
            await send_whatsapp_message(to=phone, body=fb_reply)
            continue

        # ── Default: route through the full agent orchestrator ────────────────
        await _route_to_orchestrator(msg, phone, db)

    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# Signature validation helper
# ─────────────────────────────────────────────────────────────────────────────

def _verify_signature(body: bytes, signature_header: Optional[str]) -> None:
    """
    Validate X-Hub-Signature-256 using the Meta App Secret.

    Skipped in development mode for easier local testing.
    In production, set WHATSAPP_APP_SECRET in .env to your Meta App Secret.
    """
    if settings.app_env == "development":
        return

    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    # BUG FIX: use whatsapp_app_secret (Meta App Secret), not the generic
    # app_secret_key. Fall back to app_secret_key only if not explicitly set.
    secret = (settings.whatsapp_app_secret or settings.app_secret_key).encode()

    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


# ─────────────────────────────────────────────────────────────────────────────
# Route to orchestrator
# ─────────────────────────────────────────────────────────────────────────────

async def _route_to_orchestrator(msg, phone: str, db: AsyncSession) -> None:
    """Build initial OrchestratorState and run the full LangGraph pipeline."""
    orchestrator = get_orchestrator()

    # Pack inbound message into the state messages list
    message_entry: dict = {"role": "user", "type": msg.type}
    if msg.type == "text" and msg.text:
        message_entry["content"] = msg.text.body
    elif msg.type == "image" and msg.image:
        message_entry["media_id"] = msg.image.id
        message_entry["caption"] = msg.image.caption or ""
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
        log.error(
            "orchestrator_invoke_failed",
            phone=phone,
            message_id=msg.id,
            error=str(exc),
            exc_info=True,
        )
        await send_whatsapp_message(
            to=phone,
            body=(
                "⚠️ Something went wrong processing your request. "
                "Please try again in a moment."
            ),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Button reply dispatcher
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_button_reply(
    button_id: str,
    phone: str,
    requester_id: str,
    db: AsyncSession,
) -> None:
    """
    Dispatch technician lifecycle button taps:

      ack_<id[:8]>           — technician acknowledged
      arrived_<id[:8]>       — technician on site
      done_<id[:8]>          — technician completed job
      confirm_plan_<id[:8]>  — technician confirmed daily plan
      conflict_plan_<id[:8]> — technician has a conflict with daily plan
    """
    from datetime import datetime, timezone

    from app.db.models import Assignment, DailyPlan

    log.info("button_reply_received", button_id=button_id, phone=phone)
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
                body=(
                    f"✅ Assignment `{partial}` acknowledged.\n"
                    "Head to the site and tap ON SITE when you arrive."
                ),
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
                body=f"📍 On-site confirmed for `{partial}`. Tap DONE when the job is complete.",
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
            await calculate_completion_and_close(
                wo_id=a.wo_id,
                assignment_id=a.assignment_id,
                completion_notes=None,
                db=db,
            )
            log.info("assignment_completed_via_button", assignment_id=a.assignment_id)
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
            log.info("daily_plan_confirmed", plan_id=plan.plan_id)
            await send_whatsapp_message(
                to=phone,
                body="✅ Shift plan confirmed. See you tomorrow!",
            )

    elif button_id.startswith("conflict_plan_"):
        await send_whatsapp_message(
            to=phone,
            body=(
                "⚠️ Conflict noted. Please reply with the reason and the Planning Agent "
                "will adjust your schedule before shift start."
            ),
        )

    else:
        log.warning("unknown_button_reply", button_id=button_id)


# ─────────────────────────────────────────────────────────────────────────────
# Notify requester to rate a completed job
# ─────────────────────────────────────────────────────────────────────────────

async def _notify_requester_to_rate(wo_id: str, db: AsyncSession) -> None:
    """
    Find the requester who filed the work order and ask them to rate it.

    BUG FIX: replaced lazy relationship load with an explicit JOIN so this
    works correctly inside async sessions without triggering greenlet errors.
    """
    from app.db.models import Requester, TaskRequest, WorkOrder

    result = await db.execute(
        select(Requester.phone_number)
        .join(TaskRequest, TaskRequest.requester_id == Requester.requester_id)
        .join(WorkOrder, WorkOrder.request_id == TaskRequest.request_id)
        .where(WorkOrder.wo_id == wo_id)
        .limit(1)
    )
    row = result.first()
    if not row:
        log.warning("notify_rate_requester_not_found", wo_id=wo_id)
        return

    phone = row[0]
    await send_whatsapp_message(
        to=phone,
        body=(
            f"✅ Your maintenance request (WO `{wo_id[:8]}`) has been *completed*!\n\n"
            "Please rate the service from 1 to 5 stars.\n"
            f"Reply: `{wo_id[:8]} 5`  (replace 5 with your rating)"
        ),
    )
