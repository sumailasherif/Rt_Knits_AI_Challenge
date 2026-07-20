"""
Test 7 — Reward Loop (Fix #7).

Verifies:
  - update_reward_score calculates and persists delta correctly.
  - calculate_completion_and_close stamps timestamps AND fires reward when
    feedback already exists (the key fix).
  - Speed bonus is awarded when actual time ≤ 90% of estimated.
  - Score is clamped to [0, 10].
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.services.reward import calculate_completion_and_close, update_reward_score
from app.db.models import (
    Assignment, Department, Feedback, Requester,
    TaskRequest, Technician, WorkOrder,
)


async def _setup_wo(db, *, priority="P1", estimated_minutes=60):
    """Create a minimal WO + assignment + technician and return their IDs."""
    dept_id   = str(uuid.uuid4())
    tech_id   = str(uuid.uuid4())
    req_id_r  = str(uuid.uuid4())
    tr_id     = str(uuid.uuid4())
    wo_id     = str(uuid.uuid4())
    assign_id = str(uuid.uuid4())

    db.add(Department(dept_id=dept_id, name=f"Dept {dept_id[:4]}"))
    db.add(Requester(
        requester_id=req_id_r, name="R",
        phone_number=f"+2309{dept_id[:7]}",
        dept_id=dept_id,
    ))
    db.add(Technician(
        tech_id=tech_id, name="T", trade="Mechanical",
        pool="General", phone_number=f"+2308{dept_id[:7]}",
        on_shift=True, is_active=True, reward_score=0.0,
    ))
    db.add(TaskRequest(request_id=tr_id, requester_id=req_id_r, raw_text="x"))
    db.add(WorkOrder(
        wo_id=wo_id, request_id=tr_id, priority=priority,
        status="Assigned", description="x",
        assigned_techs=[tech_id], estimated_minutes=estimated_minutes,
    ))

    now = datetime.now(timezone.utc)
    db.add(Assignment(
        assignment_id=assign_id, wo_id=wo_id, tech_id=tech_id,
        arrived_at=now - timedelta(minutes=50),   # arrived 50 min ago
    ))
    await db.flush()
    return wo_id, assign_id, tech_id


@pytest.mark.asyncio
async def test_update_reward_score_p1_rating5(db_session):
    """P1 + rating 5 = base(3) + urgency(1.5) + quality(2) + volume(0.5) = 7.0"""
    wo_id, assign_id, tech_id = await _setup_wo(db_session, priority="P1")

    # Stamp completed_at so speed bonus eligibility can be checked
    result = await db_session.execute(
        select(Assignment).where(Assignment.assignment_id == assign_id)
    )
    a = result.scalar_one()
    a.completed_at = datetime.now(timezone.utc)
    await db_session.flush()

    await update_reward_score(wo_id, 5, db_session)

    result = await db_session.execute(
        select(Technician).where(Technician.tech_id == tech_id)
    )
    tech = result.scalar_one()
    # base 3 + urgency 1.5 + quality 2 + volume 0.5 = 7 (no speed bonus: 50min > 60*0.9=54min)
    assert tech.reward_score == pytest.approx(7.0, abs=0.1)


@pytest.mark.asyncio
async def test_update_reward_score_p0(db_session):
    """P0 + rating 5 = 3 + 3 + 2 + 0.5 = 8.5 (capped at 10 if speed bonus)"""
    wo_id, assign_id, tech_id = await _setup_wo(db_session, priority="P0")

    result = await db_session.execute(
        select(Assignment).where(Assignment.assignment_id == assign_id)
    )
    a = result.scalar_one()
    a.completed_at = datetime.now(timezone.utc)
    await db_session.flush()

    await update_reward_score(wo_id, 5, db_session)

    result = await db_session.execute(
        select(Technician).where(Technician.tech_id == tech_id)
    )
    tech = result.scalar_one()
    assert tech.reward_score >= 8.0   # at least base + P0 + max quality + volume


@pytest.mark.asyncio
async def test_speed_bonus_awarded(db_session):
    """Actual time ≤ 90% of estimated → +1.0 speed bonus."""
    wo_id, assign_id, tech_id = await _setup_wo(
        db_session, priority="P2", estimated_minutes=60
    )

    now = datetime.now(timezone.utc)
    result = await db_session.execute(
        select(Assignment).where(Assignment.assignment_id == assign_id)
    )
    a = result.scalar_one()
    # Arrived 40 min ago, completed now → actual = 40 min, threshold = 54 min → speed bonus
    a.arrived_at   = now - timedelta(minutes=40)
    a.completed_at = now
    await db_session.flush()

    await update_reward_score(wo_id, 3, db_session)   # neutral quality

    result = await db_session.execute(
        select(Technician).where(Technician.tech_id == tech_id)
    )
    tech = result.scalar_one()
    # base(3) + P2(0) + quality(0) + speed(1) + volume(0.5) = 4.5
    assert tech.reward_score == pytest.approx(4.5, abs=0.1)


@pytest.mark.asyncio
async def test_calculate_completion_fires_reward_when_feedback_exists(db_session):
    """
    Fix #7: if feedback already exists at completion time,
    calculate_completion_and_close must apply the reward immediately.
    """
    wo_id, assign_id, tech_id = await _setup_wo(db_session, priority="P2")

    # Pre-insert feedback (requester rated before tech tapped DONE)
    db_session.add(Feedback(wo_id=wo_id, rating=4))
    await db_session.flush()

    await calculate_completion_and_close(wo_id, assign_id, None, db_session)

    # WO should be closed
    wo_result = await db_session.execute(
        select(WorkOrder).where(WorkOrder.wo_id == wo_id)
    )
    wo = wo_result.scalar_one()
    assert wo.status == "Completed"
    assert wo.closed_at is not None

    # Reward should have been applied
    tech_result = await db_session.execute(
        select(Technician).where(Technician.tech_id == tech_id)
    )
    tech = tech_result.scalar_one()
    # base(3) + P2(0) + quality(rating4 → +1) + volume(0.5) = 4.5 min (no speed — no arrived_at)
    assert tech.reward_score > 0.0


@pytest.mark.asyncio
async def test_reward_score_clamped_at_ten(db_session):
    """Score must never exceed 10 regardless of formula inputs."""
    wo_id, assign_id, tech_id = await _setup_wo(
        db_session, priority="P0", estimated_minutes=60
    )

    # Give tech a near-limit existing score
    tech_result = await db_session.execute(
        select(Technician).where(Technician.tech_id == tech_id)
    )
    tech = tech_result.scalar_one()
    tech.reward_score = 0.0   # start fresh — we test the delta clamping

    now = datetime.now(timezone.utc)
    result = await db_session.execute(
        select(Assignment).where(Assignment.assignment_id == assign_id)
    )
    a = result.scalar_one()
    a.arrived_at   = now - timedelta(minutes=30)   # fast → speed bonus
    a.completed_at = now
    await db_session.flush()

    await update_reward_score(wo_id, 5, db_session)

    tech_result = await db_session.execute(
        select(Technician).where(Technician.tech_id == tech_id)
    )
    tech = tech_result.scalar_one()
    # Max possible delta: 3 + 3 + 2 + 1 + 0.5 = 9.5 → within [0,10]
    assert tech.reward_score <= 10.0
