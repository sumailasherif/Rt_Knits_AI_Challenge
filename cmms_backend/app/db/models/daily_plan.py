"""
daily_plan — the nightly-generated ordered task list pushed to each technician.
"""
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class DailyPlan(Base):
    __tablename__ = "daily_plan"

    plan_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tech_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("technician.tech_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Ordered list of wo_ids the technician should tackle tomorrow
    items: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    # Timestamp when WhatsApp message was dispatched
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # True once technician replies "CONFIRM" or accepts via WhatsApp
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Free-text conflict note if technician requested changes
    conflict_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    technician: Mapped["Technician"] = relationship(  # noqa: F821
        "Technician", back_populates="daily_plans", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<DailyPlan tech={self.tech_id} date={self.plan_date} confirmed={self.confirmed}>"
