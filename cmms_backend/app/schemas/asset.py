from typing import Optional
from pydantic import Field
from app.schemas.base import CMMSBase


class AssetBase(CMMSBase):
    name: str = Field(..., min_length=1, max_length=200, examples=["Circular Knitting Machine #12"])
    category: Optional[str] = Field(None, max_length=100, examples=["Knitting Machine"])
    model_number: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=200, examples=["Hall B, Row 3"])
    dept_id: Optional[str] = None
    required_trade: Optional[str] = Field(
        None, max_length=80, examples=["Mechanical", "Electrical"]
    )
    is_critical: bool = False
    notes: Optional[str] = None


class AssetCreate(AssetBase):
    pass


class AssetUpdate(CMMSBase):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=200)
    required_trade: Optional[str] = Field(None, max_length=80)
    is_critical: Optional[bool] = None
    notes: Optional[str] = None


class AssetRead(AssetBase):
    asset_id: str
    department_name: Optional[str] = None
