from datetime import datetime
from typing import Optional
from pydantic import Field
from app.schemas.base import CMMSBase


class AssignmentCreate(CMMSBase):
    wo_id: str
    tech_id: str
    is_preempted: bool = False


class AssignmentUpdate(CMMSBase):
    acknowledged_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    completion_notes: Optional[str] = Field(None, max_length=2000)


class AssignmentRead(CMMSBase):
    assignment_id: str
    wo_id: str
    tech_id: str
    tech_name: Optional[str] = None
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    completion_notes: Optional[str] = None
    is_preempted: bool = False
    # Computed duration in minutes (completed_at - arrived_at)
    actual_duration_minutes: Optional[int] = None
