"""
Requester Resolver

get_or_create_requester() is injected into the Orchestrator.
It looks up a requester by phone number, auto-creating one if this is
their first message (self-registration via WhatsApp).
"""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Requester

log = structlog.get_logger(__name__)


async def get_or_create_requester(phone: str, db: AsyncSession) -> str:
    """
    Return requester_id for the given E.164 phone number.
    Auto-creates a new Requester row if this number has never messaged before.
    """
    # Normalise: ensure leading +
    if not phone.startswith("+"):
        phone = "+" + phone

    result = await db.execute(
        select(Requester).where(Requester.phone_number == phone)
    )
    requester = result.scalar_one_or_none()

    if requester:
        return requester.requester_id

    # First contact — create a placeholder requester
    new_id = str(uuid.uuid4())
    requester = Requester(
        requester_id=new_id,
        name=f"Worker ({phone[-4:]})",  # placeholder until they provide their name
        phone_number=phone,
        language="en",
        is_active=True,
    )
    db.add(requester)
    await db.flush()

    log.info("requester_auto_created", phone=phone, requester_id=new_id)
    return new_id
