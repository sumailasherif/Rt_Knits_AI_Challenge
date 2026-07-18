"""
department — factory floor departments (Knitting, Dyeing, Finishing, etc.)
"""
import uuid

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Department(Base):
    __tablename__ = "department"

    dept_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    requesters: Mapped[list["Requester"]] = relationship(  # noqa: F821
        "Requester", back_populates="department", lazy="select"
    )
    assets: Mapped[list["Asset"]] = relationship(  # noqa: F821
        "Asset", back_populates="department", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Department {self.name!r} id={self.dept_id}>"
