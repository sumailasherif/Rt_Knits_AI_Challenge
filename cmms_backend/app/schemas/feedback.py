from datetime import datetime
from typing import Optional
from pydantic import Field
from app.schemas.base import CMMSBase


class FeedbackCreate(CMMSBase):
    wo_id: str
    requester_id: Optional[str] = None
    rating: int = Field(..., ge=1, le=5, description="1 (worst) to 5 (best)")
    comment: Optional[str] = Field(None, max_length=1000)


class FeedbackRead(CMMSBase):
    feedback_id: str
    wo_id: str
    requester_id: Optional[str] = None
    rating: int
    comment: Optional[str] = None
    created_at: datetime
