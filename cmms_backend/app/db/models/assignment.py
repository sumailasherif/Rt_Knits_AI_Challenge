"""
assignment — one technician attached to one work_order.
Timestamps track the full lifecycle: acknowledge → arrive → pause → complete.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Assignment(Base):
    __tablename__ = "assignment"

    assignment_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    wo_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("work_order.wo_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tech_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("technician.tech_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Set when technician taps "ACKNOWLEDGE" reply button on WhatsApp
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when technician taps "ON SITE" / "ARRIVED"
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when work is paused (P0 preemption or lunch break)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when technician marks job done
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Notes added at completion
    completion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True if this assignment was created via P0 preemption
    is_preempted: Mapped[bool] = mapped_column(nullable=False, default=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    work_order: Mapped["WorkOrder"] = relationship(  # noqa: F821
        "WorkOrder", back_populates="assignments", lazy="select"
    )
    technician: Mapped["Technician"] = relationship(  # noqa: F821
        "Technician", back_populates="assignments", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<Assignment {self.assignment_id} wo={self.wo_id} "
            f"tech={self.tech_id} acked={self.acknowledged_at}>"
        )
