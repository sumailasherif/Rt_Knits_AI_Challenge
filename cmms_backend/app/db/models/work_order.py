"""
work_order — the authoritative maintenance job entity.
Tracks priority, status lifecycle, and assigned technicians.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

PriorityEnum = Enum("P0", "P1", "P2", name="priority_enum")
WOStatusEnum = Enum(
    "Open", "Queued", "Assigned", "InProgress", "Paused", "Completed", "Cancelled",
    name="wo_status_enum",
)


class WorkOrder(Base):
    __tablename__ = "work_order"

    wo_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    request_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("task_request.request_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("asset.asset_id", ondelete="SET NULL"), nullable=True, index=True
    )
    # P0=Immediate/Safety, P1=Scheduled, P2=Anytime
    priority: Mapped[str] = mapped_column(PriorityEnum, nullable=False, default="P2", index=True)
    status: Mapped[str] = mapped_column(
        WOStatusEnum, nullable=False, default="Open", index=True
    )
    # Structured description of the fault / work to be done
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Required trade: Mechanical | Electrical | Civil | Plumbing | IT
    required_trade: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # JSON array of tech_ids currently assigned
    assigned_techs: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    # Estimated duration in minutes (set by Triage / Planning Agent)
    estimated_minutes: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # SLA deadline (auto-calculated from priority)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    task_request: Mapped["TaskRequest | None"] = relationship(  # noqa: F821
        "TaskRequest", back_populates="work_order", lazy="select"
    )
    asset: Mapped["Asset | None"] = relationship(  # noqa: F821
        "Asset", back_populates="work_orders", lazy="select"
    )
    assignments: Mapped[list["Assignment"]] = relationship(  # noqa: F821
        "Assignment", back_populates="work_order", lazy="select"
    )
    feedback: Mapped["Feedback | None"] = relationship(  # noqa: F821
        "Feedback", back_populates="work_order", lazy="select", uselist=False
    )

    def __repr__(self) -> str:
        return f"<WorkOrder {self.wo_id} priority={self.priority} status={self.status}>"
