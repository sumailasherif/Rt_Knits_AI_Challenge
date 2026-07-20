"""
Async SQLAlchemy upsert writers.

Each function receives a list of plain dicts (from loaders.py) and writes
them using INSERT ... ON CONFLICT DO NOTHING so the seed is idempotent.

All writes are batched in chunks of 500 rows to avoid parameter-limit errors
on large datasets.
"""
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Asset,
    Department,
    Requester,
    TaskRequest,
    Technician,
    WorkOrder,
)

log = structlog.get_logger(__name__)

CHUNK_SIZE = 500


async def _bulk_upsert(
    db: AsyncSession,
    model,
    rows: list[dict[str, Any]],
    conflict_column: str,
) -> int:
    """
    Generic PostgreSQL INSERT ... ON CONFLICT (conflict_column) DO NOTHING.
    Returns number of rows processed.
    """
    if not rows:
        return 0

    table = model.__table__

    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i : i + CHUNK_SIZE]
        stmt = pg_insert(table).values(chunk)
        stmt = stmt.on_conflict_do_nothing(index_elements=[conflict_column])
        await db.execute(stmt)

    await db.flush()
    return len(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Individual entity writers
# ─────────────────────────────────────────────────────────────────────────────

async def upsert_departments(db: AsyncSession, rows: list[dict]) -> None:
    n = await _bulk_upsert(db, Department, rows, "dept_id")
    log.info("upserted_departments", count=n)


async def upsert_assets(db: AsyncSession, rows: list[dict]) -> None:
    # Remove serial_number duplicates — keep first occurrence
    seen_serials: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        sn = row.get("serial_number")
        if sn and sn in seen_serials:
            continue
        if sn:
            seen_serials.add(sn)
        deduped.append(row)
    n = await _bulk_upsert(db, Asset, deduped, "asset_id")
    log.info("upserted_assets", count=n)


async def upsert_technicians(db: AsyncSession, rows: list[dict]) -> None:
    # Deduplicate by phone_number
    seen_phones: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        ph = row.get("phone_number", "")
        if ph in seen_phones:
            continue
        seen_phones.add(ph)
        deduped.append(row)
    n = await _bulk_upsert(db, Technician, deduped, "tech_id")
    log.info("upserted_technicians", count=n)


async def upsert_requesters(db: AsyncSession, rows: list[dict]) -> None:
    # Deduplicate by phone_number
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        ph = row.get("phone_number", "")
        if ph in seen:
            continue
        seen.add(ph)
        deduped.append(row)
    n = await _bulk_upsert(db, Requester, deduped, "requester_id")
    log.info("upserted_requesters", count=n)


async def upsert_task_requests(db: AsyncSession, rows: list[dict]) -> None:
    n = await _bulk_upsert(db, TaskRequest, rows, "request_id")
    log.info("upserted_task_requests", count=n)


async def upsert_work_orders(db: AsyncSession, rows: list[dict]) -> None:
    n = await _bulk_upsert(db, WorkOrder, rows, "wo_id")
    log.info("upserted_work_orders", count=n)


# ─────────────────────────────────────────────────────────────────────────────
# Reset (used with --reset flag)
# ─────────────────────────────────────────────────────────────────────────────

async def reset_seed_tables(db: AsyncSession) -> None:
    """
    Truncate all seed-populated tables in reverse FK order.
    Uses TRUNCATE ... CASCADE for speed; safe because this is dev/demo data.
    """
    await db.execute(text("TRUNCATE TABLE feedback RESTART IDENTITY CASCADE"))
    await db.execute(text("TRUNCATE TABLE assignment RESTART IDENTITY CASCADE"))
    await db.execute(text("TRUNCATE TABLE daily_plan RESTART IDENTITY CASCADE"))
    await db.execute(text("TRUNCATE TABLE work_order RESTART IDENTITY CASCADE"))
    await db.execute(text("TRUNCATE TABLE task_request RESTART IDENTITY CASCADE"))
    await db.execute(text("TRUNCATE TABLE knowledge_doc RESTART IDENTITY CASCADE"))
    await db.execute(text("TRUNCATE TABLE asset RESTART IDENTITY CASCADE"))
    await db.execute(text("TRUNCATE TABLE requester RESTART IDENTITY CASCADE"))
    await db.execute(text("TRUNCATE TABLE technician RESTART IDENTITY CASCADE"))
    await db.execute(text("TRUNCATE TABLE department RESTART IDENTITY CASCADE"))
    await db.flush()
    log.warning("all_seed_tables_truncated")
