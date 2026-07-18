"""
knowledge_doc — manuals, SOPs, and historical repair records
embedded into ChromaDB for the Knowledge Agent.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

SourceTypeEnum = Enum("manual", "SOP", "history", name="source_type_enum")


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_doc"

    doc_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("asset.asset_id", ondelete="SET NULL"), nullable=True, index=True
    )
    # manual | SOP | history
    source_type: Mapped[str] = mapped_column(SourceTypeEnum, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ChromaDB document ID — used to look up the vector
    embedding_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    asset: Mapped["Asset | None"] = relationship(  # noqa: F821
        "Asset", back_populates="knowledge_docs", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDoc {self.title!r} type={self.source_type}>"
