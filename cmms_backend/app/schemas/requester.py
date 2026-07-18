from typing import Optional
from pydantic import Field, field_validator
from app.schemas.base import CMMSBase


class RequesterBase(CMMSBase):
    name: str = Field(..., min_length=1, max_length=150, examples=["Ravi Kumar"])
    phone_number: str = Field(
        ..., pattern=r"^\+[1-9]\d{7,14}$", examples=["+23052345678"],
        description="E.164 WhatsApp number"
    )
    language: str = Field("en", max_length=10, examples=["en", "fr", "hi", "bn"])
    dept_id: Optional[str] = None
    is_active: bool = True

    @field_validator("phone_number")
    @classmethod
    def normalise_phone(cls, v: str) -> str:
        return v.strip().replace(" ", "")


class RequesterCreate(RequesterBase):
    pass


class RequesterUpdate(CMMSBase):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    language: Optional[str] = Field(None, max_length=10)
    dept_id: Optional[str] = None
    is_active: Optional[bool] = None


class RequesterRead(RequesterBase):
    requester_id: str
    department_name: Optional[str] = None  # flattened for convenience
