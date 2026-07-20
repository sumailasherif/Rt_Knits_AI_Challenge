"""
Test 6 — Rating Gate Service (Fix #5).

Verifies:
  - Requester with no completed WOs → not blocked.
  - Requester with completed WO but no feedback → blocked.
  - After feedback submitted → no longer blocked.
  - parse_and_save_feedback correctly saves a rating.
  - Duplicate rating submission → idempotent.
"""
import uuid
import pytest
from sqlalchemy import select

from app.services.rating_gate import check_rating_gate, parse_and_save_feedback
from app.db.models import Department, Requester, TaskRequest, WorkOrder, Feedback


async def _make_completed_wo(db, requester_id, dept_id):
    """Helper: insert a Completed WO linked to the requester."""
    req_id = str(uuid.uuid4())
    wo_id  = str(uuid.uuid4())

    db.add(TaskRequest(
        request_id=req_id, requester_id=requester_id,
        raw_text="Test fault",
    ))
    db.add(WorkOrder(
        wo_id=wo_id, request_id=req_id,
        priority="P2", status="Completed",
        description="Test WO", assigned_techs=[],
    ))
    await db.flush()
    return wo_id


@pytest.mark.asyncio
async def test_gate_not_blocked_no_wos(db_session, seed_db):
    """A requester with no completed WOs should pass."""
    fresh_id = str(uuid.uuid4())
    db_session.add(Requester(
        requester_id=fresh_id, name="Fresh Worker",
        phone_number="+23099990010", dept_id=seed_db["dept_id"],
    ))
    await db_session.flush()

    gate = await check_rating_gate(fresh_id, db_session)
    assert gate.blocked is False
    assert gate.pending_wo_ids == []


@pytest.mark.asyncio
async def test_gate_blocked_unrated_wo(db_session, seed_db):
    """Requester with a Completed WO and no Feedback → blocked."""
    req_id = str(uuid.uuid4())
    db_session.add(Requester(
        requester_id=req_id, name="Blocked Worker",
        phone_number="+23099990011", dept_id=seed_db["dept_id"],
    ))
    await db_session.flush()

    wo_id = await _make_completed_wo(db_session, req_id, seed_db["dept_id"])

    gate = await check_rating_gate(req_id, db_session)
    assert gate.blocked is True
    assert wo_id in gate.pending_wo_ids


@pytest.mark.asyncio
async def test_gate_not_blocked_after_rating(db_session, seed_db):
    """After feedback is saved the gate should clear."""
    req_id = str(uuid.uuid4())
    db_session.add(Requester(
        requester_id=req_id, name="Rated Worker",
        phone_number="+23099990012", dept_id=seed_db["dept_id"],
    ))
    await db_session.flush()

    wo_id = await _make_completed_wo(db_session, req_id, seed_db["dept_id"])

    # Manually insert feedback
    db_session.add(Feedback(
        wo_id=wo_id, requester_id=req_id, rating=4,
    ))
    await db_session.flush()

    gate = await check_rating_gate(req_id, db_session)
    assert gate.blocked is False


@pytest.mark.asyncio
async def test_parse_feedback_wo_id_and_rating(db_session, seed_db):
    """'WO<id> 5' pattern should save feedback successfully."""
    req_id = str(uuid.uuid4())
    db_session.add(Requester(
        requester_id=req_id, name="Rater",
        phone_number="+23099990013", dept_id=seed_db["dept_id"],
    ))
    await db_session.flush()

    wo_id = await _make_completed_wo(db_session, req_id, seed_db["dept_id"])

    text = f"WO {wo_id[:8]} 5"
    saved, msg = await parse_and_save_feedback(text, req_id, db_session)
    assert saved is True
    assert "5" in msg

    result = await db_session.execute(
        select(Feedback).where(Feedback.wo_id == wo_id)
    )
    fb = result.scalar_one_or_none()
    assert fb is not None
    assert fb.rating == 5


@pytest.mark.asyncio
async def test_parse_feedback_bare_digit(db_session, seed_db):
    """Bare digit '4' should apply to the oldest pending WO."""
    req_id = str(uuid.uuid4())
    db_session.add(Requester(
        requester_id=req_id, name="Bare Rater",
        phone_number="+23099990014", dept_id=seed_db["dept_id"],
    ))
    await db_session.flush()

    wo_id = await _make_completed_wo(db_session, req_id, seed_db["dept_id"])

    saved, msg = await parse_and_save_feedback("4", req_id, db_session)
    assert saved is True

    result = await db_session.execute(
        select(Feedback).where(Feedback.wo_id == wo_id)
    )
    fb = result.scalar_one_or_none()
    assert fb is not None
    assert fb.rating == 4


@pytest.mark.asyncio
async def test_parse_feedback_duplicate_idempotent(db_session, seed_db):
    """Submitting the same rating twice must not raise and returns graceful msg."""
    req_id = str(uuid.uuid4())
    db_session.add(Requester(
        requester_id=req_id, name="Double Rater",
        phone_number="+23099990015", dept_id=seed_db["dept_id"],
    ))
    await db_session.flush()

    wo_id = await _make_completed_wo(db_session, req_id, seed_db["dept_id"])

    text = f"{wo_id[:8]} 3"
    saved1, _ = await parse_and_save_feedback(text, req_id, db_session)
    saved2, msg2 = await parse_and_save_feedback(text, req_id, db_session)

    assert saved1 is True
    assert saved2 is True          # idempotent — no exception
    assert "already rated" in msg2.lower()
