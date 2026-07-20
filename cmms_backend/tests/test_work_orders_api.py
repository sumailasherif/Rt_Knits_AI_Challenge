"""
Test 3 — Work Orders REST API.

Verifies CRUD operations, list filtering, and assignment retrieval.
"""
import pytest


@pytest.mark.asyncio
async def test_list_work_orders_empty(async_client):
    resp = await async_client.get("/api/v1/work-orders")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_work_orders_with_seed(async_client, seed_db):
    resp = await async_client.get("/api/v1/work-orders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    wo = next((w for w in data if w["wo_id"] == seed_db["wo_id"]), None)
    assert wo is not None
    assert wo["priority"] == "P1"
    assert wo["status"] == "Assigned"


@pytest.mark.asyncio
async def test_get_work_order_by_id(async_client, seed_db):
    wo_id = seed_db["wo_id"]
    resp = await async_client.get(f"/api/v1/work-orders/{wo_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["wo_id"] == wo_id
    assert data["required_trade"] == "Mechanical"


@pytest.mark.asyncio
async def test_get_work_order_not_found(async_client):
    resp = await async_client.get("/api/v1/work-orders/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_work_order(async_client, seed_db):
    payload = {
        "asset_id":           seed_db["asset_id"],
        "priority":           "P2",
        "description":        "Routine check",
        "required_trade":     "Electrical",
        "estimated_minutes":  60,
    }
    resp = await async_client.post("/api/v1/work-orders", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["priority"] == "P2"
    assert data["status"] == "Open"
    assert "wo_id" in data


@pytest.mark.asyncio
async def test_update_work_order_status(async_client, seed_db):
    wo_id = seed_db["wo_id"]
    resp = await async_client.patch(
        f"/api/v1/work-orders/{wo_id}",
        json={"status": "InProgress"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "InProgress"


@pytest.mark.asyncio
async def test_filter_work_orders_by_priority(async_client, seed_db):
    resp = await async_client.get("/api/v1/work-orders", params={"priority": "P1"})
    assert resp.status_code == 200
    for wo in resp.json():
        assert wo["priority"] == "P1"


@pytest.mark.asyncio
async def test_get_assignments_for_wo(async_client, seed_db):
    wo_id = seed_db["wo_id"]
    resp = await async_client.get(f"/api/v1/work-orders/{wo_id}/assignments")
    assert resp.status_code == 200
    assigns = resp.json()
    assert len(assigns) >= 1
    assert assigns[0]["wo_id"] == wo_id
