"""
Test 4 — Technicians REST API + shift toggle endpoints.
"""
import pytest


@pytest.mark.asyncio
async def test_list_technicians(async_client, seed_db):
    resp = await async_client.get("/api/v1/technicians")
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["tech_id"] == seed_db["tech_id"] for t in data)


@pytest.mark.asyncio
async def test_get_technician_by_id(async_client, seed_db):
    resp = await async_client.get(f"/api/v1/technicians/{seed_db['tech_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Tech One"
    assert data["trade"] == "Mechanical"
    assert data["on_shift"] is True


@pytest.mark.asyncio
async def test_get_technician_not_found(async_client):
    resp = await async_client.get("/api/v1/technicians/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_technician(async_client):
    payload = {
        "name":         "New Tech",
        "trade":        "Electrical",
        "pool":         "General",
        "phone_number": "+23099990099",
        "on_shift":     False,
    }
    resp = await async_client.post("/api/v1/technicians", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["trade"] == "Electrical"
    assert data["reward_score"] == 0.0


@pytest.mark.asyncio
async def test_shift_off(async_client, seed_db):
    tech_id = seed_db["tech_id"]
    resp = await async_client.post(f"/api/v1/technicians/{tech_id}/shift-off")
    assert resp.status_code == 200
    assert resp.json()["on_shift"] is False


@pytest.mark.asyncio
async def test_shift_on(async_client, seed_db):
    tech_id = seed_db["tech_id"]
    resp = await async_client.post(f"/api/v1/technicians/{tech_id}/shift-on")
    assert resp.status_code == 200
    assert resp.json()["on_shift"] is True


@pytest.mark.asyncio
async def test_filter_on_shift(async_client, seed_db):
    resp = await async_client.get("/api/v1/technicians", params={"on_shift": "true"})
    assert resp.status_code == 200
    for t in resp.json():
        assert t["on_shift"] is True


@pytest.mark.asyncio
async def test_filter_by_trade(async_client, seed_db):
    resp = await async_client.get("/api/v1/technicians", params={"trade": "Mechanical"})
    assert resp.status_code == 200
    for t in resp.json():
        assert t["trade"] == "Mechanical"
