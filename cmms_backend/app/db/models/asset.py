"""
asset — physical machines/equipment on the factory floor.
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Asset(Base):
    __tablename__ = "asset"

    asset_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # e.g. Knitting Machine, Dyeing Vat, Compressor, Electrical Panel
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    model_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("department.dept_id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Required trade to work on this asset: Mechanical, Electrical, Civil, etc.
    required_trade: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    department: Mapped["Department"] = relationship(  # noqa: F821
        "Department", back_populates="assets", lazy="select"
    )
    knowledge_docs: Mapped[list["KnowledgeDoc"]] = relationship(  # noqa: F821
        "KnowledgeDoc", back_populates="asset", lazy="select"
    )
    task_requests: Mapped[list["TaskRequest"]] = relationship(  # noqa: F821
        "TaskRequest", back_populates="asset", lazy="select"
    )
    work_orders: Mapped[list["WorkOrder"]] = relationship(  # noqa: F821
        "WorkOrder", back_populates="asset", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Asset {self.name!r} category={self.category}>"
