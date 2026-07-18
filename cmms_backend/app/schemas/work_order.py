from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import Field, field_validator
from app.schemas.base import CMMSBase

PriorityType = Literal["P0", "P1", "P2"]
WOStatusType = Literal[
    "Open", "Queued", "Assigned", "InProgress", "Paused", "Completed", "Cancelled"
]


class WorkOrderCreate(CMMSBase):
    request_id: Optional[str] = None
    asset_id: Optional[str] = None
    priority: PriorityType = "P2"
    description: Optional[str] = None
    required_trade: Optional[str] = Field(None, max_length=80)
    estimated_minutes: Optional[int] = Field(None, ge=1)


class WorkOrderUpdate(CMMSBase):
    priority: Optional[PriorityType] = None
    status: Optional[WOStatusType] = None
    description: Optional[str] = None
    required_trade: Optional[str] = Field(None, max_length=80)
    assigned_techs: Optional[list[str]] = None
    estimated_minutes: Optional[int] = Field(None, ge=1)
    closed_at: Optional[datetime] = None


class WorkOrderRead(CMMSBase):
    wo_id: str
    request_id: Optional[str] = None
    asset_id: Optional[str] = None
    asset_name: Optional[str] = None
    priority: str
    status: str
    description: Optional[str] = None
    required_trade: Optional[str] = None
    assigned_techs: list[Any] = []
    estimated_minutes: Optional[int] = None
    created_at: datetime
    closed_at: Optional[datetime] = None
    sla_due_at: Optional[datetime] = None
    # Feedback summary (populated when status=Completed)
    feedback_rating: Optional[int] = None


class WorkOrderSummary(CMMSBase):
    """Lightweight read used in planning lists."""
    wo_id: str
    priority: str
    status: str
    description: Optional[str] = None
    required_trade: Optional[str] = None
    estimated_minutes: Optional[int] = None
