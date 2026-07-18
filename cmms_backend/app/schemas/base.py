"""
Shared base schema configuration.
All schemas inherit from CMMSBase which sets:
  - model_config with from_attributes=True (ORM mode)
  - populate_by_name=True (allow field aliases)
  - str_strip_whitespace=True
"""
from pydantic import BaseModel, ConfigDict


class CMMSBase(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=True,
    )
