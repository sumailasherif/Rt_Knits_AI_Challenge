"""
feedback — requester's 1-5 star rating after work_order is Completed.
Blocks new requests if absent (Rating Gate).
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_feedback_rating_range"),
    )

    feedback_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    wo_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("work_order.wo_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # one feedback per work order
        index=True,
    )
    # FK to the requester who submitted feedback
    requester_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("requester.requester_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    work_order: Mapped["WorkOrder"] = relationship(  # noqa: F821
        "WorkOrder", back_populates="feedback", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Feedback wo={self.wo_id} rating={self.rating}>"
