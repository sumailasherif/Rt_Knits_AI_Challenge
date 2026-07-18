from datetime import date, datetime
from typing import Any, Optional
from pydantic import Field
from app.schemas.base import CMMSBase


class DailyPlanCreate(CMMSBase):
    tech_id: str
    plan_date: date
    items: list[str] = Field(default_factory=list, description="Ordered list of wo_ids")


class DailyPlanUpdate(CMMSBase):
    items: Optional[list[str]] = None
    confirmed: Optional[bool] = None
    conflict_note: Optional[str] = Field(None, max_length=500)
    sent_at: Optional[datetime] = None


class DailyPlanRead(CMMSBase):
    plan_id: str
    tech_id: str
    plan_date: date
    items: list[Any] = []
    sent_at: Optional[datetime] = None
    confirmed: bool = False
    conflict_note: Optional[str] = None
    created_at: datetime
