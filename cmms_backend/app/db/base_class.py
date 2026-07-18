"""
Single declarative base used by all ORM models.
Separated from base.py to avoid circular imports during Alembic autogenerate.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
