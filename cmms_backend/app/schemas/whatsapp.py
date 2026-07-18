"""
Pydantic v2 schemas for Meta WhatsApp Cloud API payloads.

Inbound: mirrors the exact structure of the webhook POST body.
Outbound: typed builders for text, template, and interactive messages.

Reference: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
"""
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# INBOUND  (webhook payload from Meta)
# ─────────────────────────────────────────────────────────────────────────────

class WhatsAppProfile(BaseModel):
    name: str


class WhatsAppContact(BaseModel):
    profile: WhatsAppProfile
    wa_id: str


class WhatsAppTextBody(BaseModel):
    body: str


class WhatsAppImageBody(BaseModel):
    id: str
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    caption: Optional[str] = None


class WhatsAppAudioBody(BaseModel):
    id: str
    mime_type: Optional[str] = None
    voice: bool = False


class WhatsAppButtonReply(BaseModel):
    id: str
    title: str


class WhatsAppListReply(BaseModel):
    id: str
    title: str
    description: Optional[str] = None


class WhatsAppInteractiveBody(BaseModel):
    type: Literal["button_reply", "list_reply"]
    button_reply: Optional[WhatsAppButtonReply] = None
    list_reply: Optional[WhatsAppListReply] = None


class WhatsAppMessage(BaseModel):
    """Single message inside a webhook payload."""
    id: str                        # WhatsApp message ID — used for deduplication
    from_: str = Field(..., alias="from")
    timestamp: str
    type: Literal["text", "image", "audio", "interactive", "document", "sticker", "reaction"]
    text: Optional[WhatsAppTextBody] = None
    image: Optional[WhatsAppImageBody] = None
    audio: Optional[WhatsAppAudioBody] = None
    interactive: Optional[WhatsAppInteractiveBody] = None

    model_config = {"populate_by_name": True}

    @property
    def sender_phone(self) -> str:
        """Return E.164 phone number with leading +."""
        num = self.from_
        return num if num.startswith("+") else f"+{num}"

    @property
    def text_body(self) -> Optional[str]:
        return self.text.body if self.text else None

    @property
    def is_button_reply(self) -> bool:
        return (
            self.type == "interactive"
            and self.interactive is not None
            and self.interactive.type == "button_reply"
        )

    @property
    def button_reply_id(self) -> Optional[str]:
        if self.is_button_reply and self.interactive and self.interactive.button_reply:
            return self.interactive.button_reply.id
        return None


class WhatsAppValue(BaseModel):
    messaging_product: str
    metadata: dict[str, Any]
    contacts: Optional[list[WhatsAppContact]] = None
    messages: Optional[list[WhatsAppMessage]] = None
    statuses: Optional[list[dict[str, Any]]] = None


class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str


class WhatsAppEntry(BaseModel):
    id: str
    changes: list[WhatsAppChange]


class WhatsAppInbound(BaseModel):
    """Top-level webhook POST body from Meta."""
    object: str
    entry: list[WhatsAppEntry]

    def get_messages(self) -> list[tuple[WhatsAppMessage, str]]:
        """
        Yields (message, display_phone_number) tuples for all inbound messages.
        Filters out status updates (delivery receipts, read receipts).
        """
        results: list[tuple[WhatsAppMessage, str]] = []
        for entry in self.entry:
            for change in entry.changes:
                if change.field != "messages":
                    continue
                display_phone = change.value.metadata.get("display_phone_number", "")
                for msg in change.value.messages or []:
                    results.append((msg, display_phone))
        return results


# ─────────────────────────────────────────────────────────────────────────────
# OUTBOUND  (messages we send via the Cloud API)
# ─────────────────────────────────────────────────────────────────────────────

class OutboundTextMessage(BaseModel):
    """Send a plain text message."""
    messaging_product: str = "whatsapp"
    recipient_type: str = "individual"
    to: str
    type: Literal["text"] = "text"
    text: dict[str, Any]

    @classmethod
    def build(cls, to: str, body: str, preview_url: bool = False) -> "OutboundTextMessage":
        return cls(to=to, text={"body": body, "preview_url": preview_url})


class OutboundTemplateComponent(BaseModel):
    type: Literal["header", "body", "button"]
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    sub_type: Optional[str] = None
    index: Optional[str] = None


class OutboundTemplateMessage(BaseModel):
    """Send a pre-approved WhatsApp template message."""
    messaging_product: str = "whatsapp"
    recipient_type: str = "individual"
    to: str
    type: Literal["template"] = "template"
    template: dict[str, Any]

    @classmethod
    def build(
        cls,
        to: str,
        template_name: str,
        language_code: str = "en",
        components: Optional[list[dict[str, Any]]] = None,
    ) -> "OutboundTemplateMessage":
        return cls(
            to=to,
            template={
                "name": template_name,
                "language": {"code": language_code},
                "components": components or [],
            },
        )


class OutboundButtonAction(BaseModel):
    type: Literal["reply"] = "reply"
    reply: dict[str, str]  # {"id": "...", "title": "..."}


class OutboundInteractiveMessage(BaseModel):
    """Send an interactive message with reply buttons (max 3)."""
    messaging_product: str = "whatsapp"
    recipient_type: str = "individual"
    to: str
    type: Literal["interactive"] = "interactive"
    interactive: dict[str, Any]

    @classmethod
    def build_buttons(
        cls,
        to: str,
        body_text: str,
        buttons: list[tuple[str, str]],  # [(id, title), ...]
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
    ) -> "OutboundInteractiveMessage":
        """Build an interactive button message. Max 3 buttons per WhatsApp spec."""
        if len(buttons) > 3:
            raise ValueError("WhatsApp interactive messages support at most 3 reply buttons.")
        payload: dict[str, Any] = {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": bid, "title": title}}
                    for bid, title in buttons
                ]
            },
        }
        if header_text:
            payload["header"] = {"type": "text", "text": header_text}
        if footer_text:
            payload["footer"] = {"text": footer_text}
        return cls(to=to, interactive=payload)
