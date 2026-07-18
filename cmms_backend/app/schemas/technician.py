from typing import Literal, Optional
from pydantic import Field, field_validator
from app.schemas.base import CMMSBase

TradeType = Literal["Mechanical", "Electrical", "Civil", "Plumbing", "IT", "General"]
PoolType = Literal["LTKTech", "DyeTech", "General"]


class TechnicianBase(CMMSBase):
    name: str = Field(..., min_length=1, max_length=150)
    trade: TradeType
    pool: PoolType = "General"
    phone_number: str = Field(
        ..., pattern=r"^\+[1-9]\d{7,14}$", description="E.164 WhatsApp number"
    )
    on_shift: bool = False
    is_active: bool = True
    max_concurrent_jobs: int = Field(2, ge=1, le=10)

    @field_validator("phone_number")
    @classmethod
    def normalise_phone(cls, v: str) -> str:
        return v.strip().replace(" ", "")


class TechnicianCreate(TechnicianBase):
    pass


class TechnicianUpdate(CMMSBase):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    trade: Optional[TradeType] = None
    pool: Optional[PoolType] = None
    on_shift: Optional[bool] = None
    is_active: Optional[bool] = None
    max_concurrent_jobs: Optional[int] = Field(None, ge=1, le=10)


class TechnicianRead(TechnicianBase):
    tech_id: str
    reward_score: float = 0.0
    # Populated on demand — count of active assignments
    active_jobs: Optional[int] = None
