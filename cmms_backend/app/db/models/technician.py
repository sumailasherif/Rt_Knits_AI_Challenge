"""
technician — maintenance staff member with trade, pool, and reward score.
"""
import uuid

from sqlalchemy import Boolean, Enum, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

TradeEnum = Enum(
    "Mechanical", "Electrical", "Civil", "Plumbing", "IT", "General",
    name="trade_enum",
)
PoolEnum = Enum("LTKTech", "DyeTech", "General", name="pool_enum")


class Technician(Base):
    __tablename__ = "technician"

    tech_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    trade: Mapped[str] = mapped_column(TradeEnum, nullable=False, index=True)
    pool: Mapped[str] = mapped_column(PoolEnum, nullable=False, default="General", index=True)
    # WhatsApp E.164 phone number
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    on_shift: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Gamification score — updated on each work_order completion
    reward_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Max concurrent jobs this technician can handle
    max_concurrent_jobs: Mapped[int] = mapped_column(nullable=False, default=2)

    # ── Relationships ──────────────────────────────────────────────────────────
    assignments: Mapped[list["Assignment"]] = relationship(  # noqa: F821
        "Assignment", back_populates="technician", lazy="select"
    )
    daily_plans: Mapped[list["DailyPlan"]] = relationship(  # noqa: F821
        "DailyPlan", back_populates="technician", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Technician {self.name!r} trade={self.trade} on_shift={self.on_shift}>"
