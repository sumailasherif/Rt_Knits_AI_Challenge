from typing import Optional
from pydantic import Field
from app.schemas.base import CMMSBase


class DepartmentBase(CMMSBase):
    name: str = Field(..., min_length=1, max_length=120, examples=["Knitting"])
    location: Optional[str] = Field(None, max_length=200, examples=["Block A, Floor 1"])
    description: Optional[str] = Field(None, examples=["Main knitting production floor"])


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(CMMSBase):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    location: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None


class DepartmentRead(DepartmentBase):
    dept_id: str
