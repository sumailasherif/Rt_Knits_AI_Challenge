"""
task_request — raw inbound maintenance report from a requester via WhatsApp.
One task_request may spawn one work_order after triage.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class TaskRequest(Base):
    __tablename__ = "task_request"

    request_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    requester_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("requester.requester_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("asset.asset_id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Original message text (possibly translated/transcribed)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # URL to photo stored in object storage / WhatsApp media server
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Transcribed audio if voice message
    audio_transcription: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured fault extracted by Intake Agent (JSON stored as text)
    structured_fault: Mapped[str | None] = mapped_column(Text, nullable=True)
    # WhatsApp message ID for deduplication
    whatsapp_message_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    requester: Mapped["Requester"] = relationship(  # noqa: F821
        "Requester", back_populates="task_requests", lazy="select"
    )
    asset: Mapped["Asset | None"] = relationship(  # noqa: F821
        "Asset", back_populates="task_requests", lazy="select"
    )
    work_order: Mapped["WorkOrder | None"] = relationship(  # noqa: F821
        "WorkOrder", back_populates="task_request", lazy="select", uselist=False
    )

    def __repr__(self) -> str:
        return f"<TaskRequest {self.request_id} from={self.requester_id}>"
