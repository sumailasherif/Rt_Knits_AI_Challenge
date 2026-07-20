"""
Shared pytest fixtures for the RT Knits CMMS test suite.

Provides:
  - async_client  — AsyncClient wired to the FastAPI app with an in-memory
                    SQLite database (no Postgres/Docker required for CI).
  - db_session    — raw AsyncSession against the same SQLite engine.
  - seed_db       — pre-populated tables (one of each entity type).

SQLite is used instead of PostgreSQL for tests because:
  1. No external service needed in CI.
  2. SQLAlchemy async works identically on both for the queries we test.
  3. pgvector / JSON columns are emulated adequately for unit tests.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# ── Override DATABASE_URL before importing anything from app ─────────────────
import os
os.environ.setdefault("DATABASE_URL",      "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")
os.environ.setdefault("OPENAI_API_KEY",           "sk-test-placeholder")
os.environ.setdefault("WHATSAPP_VERIFY_TOKEN",     "test-verify-token")
os.environ.setdefault("WHATSAPP_ACCESS_TOKEN",     "test-access-token")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID",  "000000000000")
os.environ.setdefault("APP_ENV",                   "development")

from app.db.base_class import Base
from app.db.session import get_db
from app.main import app

# ── In-memory async SQLite engine ────────────────────────────────────────────
TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)
TestSessionLocal = async_sessionmaker(
    bind=TEST_ENGINE,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create all ORM tables once per test session."""
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh DB session, roll back after every test."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture()
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient wired to the FastAPI app.
    Overrides the get_db dependency to use the test session.
    """
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()


# ── Seed helpers ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def seed_db(db_session: AsyncSession):
    """Insert one of each entity type and return a dict of IDs."""
    from app.db.models import (
        Asset, Assignment, Department, DailyPlan,
        Feedback, Requester, TaskRequest, Technician, WorkOrder,
    )
    from datetime import date, datetime, timezone

    dept_id      = str(uuid.uuid4())
    requester_id = str(uuid.uuid4())
    asset_id     = str(uuid.uuid4())
    tech_id      = str(uuid.uuid4())
    request_id   = str(uuid.uuid4())
    wo_id        = str(uuid.uuid4())
    assign_id    = str(uuid.uuid4())
    fb_id        = str(uuid.uuid4())
    plan_id      = str(uuid.uuid4())

    dept = Department(dept_id=dept_id, name="Test Dept", location="Floor 1")
    req  = Requester(
        requester_id=requester_id, name="Test Worker",
        phone_number="+23099990001", dept_id=dept_id,
    )
    asset = Asset(
        asset_id=asset_id, name="Knitting Machine 1",
        category="Knitting Machine", dept_id=dept_id,
        required_trade="Mechanical", is_critical=True,
    )
    tech = Technician(
        tech_id=tech_id, name="Tech One", trade="Mechanical",
        pool="LTKTech", phone_number="+23099990002",
        on_shift=True, is_active=True, reward_score=5.0,
    )
    tr = TaskRequest(
        request_id=request_id, requester_id=requester_id,
        asset_id=asset_id, raw_text="Machine is making loud noise",
    )
    wo = WorkOrder(
        wo_id=wo_id, request_id=request_id, asset_id=asset_id,
        priority="P1", status="Assigned",
        description="Loud noise from knitting machine",
        required_trade="Mechanical", estimated_minutes=90,
        assigned_techs=[tech_id],
    )
    assign = Assignment(
        assignment_id=assign_id, wo_id=wo_id, tech_id=tech_id,
    )
    plan = DailyPlan(
        plan_id=plan_id, tech_id=tech_id,
        plan_date=date.today(), items=[wo_id],
    )

    for obj in [dept, req, asset, tech, tr, wo, assign, plan]:
        db_session.add(obj)
    await db_session.flush()

    return {
        "dept_id": dept_id, "requester_id": requester_id,
        "asset_id": asset_id, "tech_id": tech_id,
        "request_id": request_id, "wo_id": wo_id,
        "assign_id": assign_id, "plan_id": plan_id,
    }
