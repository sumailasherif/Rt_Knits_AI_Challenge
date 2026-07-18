"""
requester — factory floor workers who submit maintenance tickets via WhatsApp.
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Requester(Base):
    __tablename__ = "requester"

    requester_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # WhatsApp-normalized E.164 format: +2307XXXXXXX
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    # Preferred language for outgoing messages
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    dept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("department.dept_id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    department: Mapped["Department"] = relationship(  # noqa: F821
        "Department", back_populates="requesters", lazy="select"
    )
    task_requests: Mapped[list["TaskRequest"]] = relationship(  # noqa: F821
        "TaskRequest", back_populates="requester", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Requester {self.name!r} phone={self.phone_number}>"
