"""
WhatsApp Cloud API outbound message service.

All agents call send_whatsapp_message() to send replies.
This module is the single place where HTTP calls to graph.facebook.com happen.
"""
from __future__ import annotations

from typing import Optional

import httpx
import structlog

from app.core.config import get_settings
from app.schemas.whatsapp import OutboundInteractiveMessage, OutboundTextMessage

log = structlog.get_logger(__name__)
settings = get_settings()

_HEADERS = {
    "Content-Type": "application/json",
}


def _auth_headers() -> dict[str, str]:
    return {**_HEADERS, "Authorization": f"Bearer {settings.whatsapp_access_token}"}


async def send_whatsapp_message(
    to: str,
    body: str,
    buttons: Optional[list[tuple[str, str]]] = None,
) -> dict:
    """
    Send a WhatsApp message to a phone number.

    If `buttons` is provided (max 3 tuples of (id, title)), sends an
    interactive button message. Otherwise sends plain text.

    Returns the raw API response dict.
    """
    to_clean = to.lstrip("+")   # Meta API expects number without leading +

    if buttons:
        msg = OutboundInteractiveMessage.build_buttons(
            to=to_clean,
            body_text=body,
            buttons=buttons[:3],  # hard cap at 3
        )
        payload = msg.model_dump()
    else:
        msg = OutboundTextMessage.build(to=to_clean, body=body)
        payload = msg.model_dump()

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            settings.whatsapp_api_url,
            headers=_auth_headers(),
            json=payload,
        )

    if resp.status_code not in (200, 201):
        log.error(
            "whatsapp_send_failed",
            status=resp.status_code,
            body=resp.text[:500],
            to=to,
        )
        resp.raise_for_status()

    result = resp.json()
    log.info("whatsapp_sent", to=to, type="interactive" if buttons else "text")
    return result


async def send_template_message(
    to: str,
    template_name: str,
    language_code: str = "en",
    components: Optional[list[dict]] = None,
) -> dict:
    """Send a pre-approved WhatsApp template message."""
    from app.schemas.whatsapp import OutboundTemplateMessage

    to_clean = to.lstrip("+")
    msg = OutboundTemplateMessage.build(
        to=to_clean,
        template_name=template_name,
        language_code=language_code,
        components=components,
    )

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            settings.whatsapp_api_url,
            headers=_auth_headers(),
            json=msg.model_dump(),
        )

    if resp.status_code not in (200, 201):
        log.error("whatsapp_template_failed", status=resp.status_code, body=resp.text[:500])
        resp.raise_for_status()

    return resp.json()


async def mark_message_read(message_id: str) -> None:
    """Mark an inbound WhatsApp message as read (shows double blue ticks)."""
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                settings.whatsapp_api_url,
                headers=_auth_headers(),
                json=payload,
            )
    except Exception as exc:
        log.warning("whatsapp_mark_read_failed", message_id=message_id, error=str(exc))
