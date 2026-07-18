from datetime import datetime
from typing import Literal, Optional
from pydantic import Field
from app.schemas.base import CMMSBase


class KnowledgeDocCreate(CMMSBase):
    asset_id: Optional[str] = None
    source_type: Literal["manual", "SOP", "history"] = Field(
        ..., examples=["manual"]
    )
    title: str = Field(..., min_length=1, max_length=300)
    raw_content: Optional[str] = None


class KnowledgeDocRead(CMMSBase):
    doc_id: str
    asset_id: Optional[str] = None
    source_type: str
    title: str
    embedding_ref: Optional[str] = None
    created_at: datetime
