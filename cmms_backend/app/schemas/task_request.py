from datetime import datetime
from typing import Any, Optional
from pydantic import Field
from app.schemas.base import CMMSBase


class TaskRequestCreate(CMMSBase):
    requester_id: str
    asset_id: Optional[str] = None
    raw_text: Optional[str] = None
    photo_url: Optional[str] = Field(None, max_length=500)
    audio_transcription: Optional[str] = None
    structured_fault: Optional[str] = None
    whatsapp_message_id: Optional[str] = Field(None, max_length=200)


class TaskRequestRead(CMMSBase):
    request_id: str
    requester_id: str
    asset_id: Optional[str] = None
    raw_text: Optional[str] = None
    photo_url: Optional[str] = None
    audio_transcription: Optional[str] = None
    structured_fault: Optional[Any] = None   # parsed JSON for API consumers
    whatsapp_message_id: Optional[str] = None
    created_at: datetime
