"""
Test 5 — Assets REST API.
"""
import pytest


@pytest.mark.asyncio
async def test_list_assets(async_client, seed_db):
    resp = await async_client.get("/api/v1/assets")
    assert resp.status_code == 200
    data = resp.json()
    assert any(a["asset_id"] == seed_db["asset_id"] for a in data)


@pytest.mark.asyncio
async def test_get_asset_by_id(async_client, seed_db):
    resp = await async_client.get(f"/api/v1/assets/{seed_db['asset_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Knitting Machine 1"
    assert data["is_critical"] is True


@pytest.mark.asyncio
async def test_get_asset_not_found(async_client):
    resp = await async_client.get("/api/v1/assets/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_asset(async_client, seed_db):
    payload = {
        "name":           "Dyeing Vat 3",
        "category":       "Dyeing Equipment",
        "dept_id":        seed_db["dept_id"],
        "required_trade": "Mechanical",
        "is_critical":    False,
    }
    resp = await async_client.post("/api/v1/assets", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Dyeing Vat 3"
    assert "asset_id" in data


@pytest.mark.asyncio
async def test_update_asset(async_client, seed_db):
    asset_id = seed_db["asset_id"]
    resp = await async_client.patch(
        f"/api/v1/assets/{asset_id}",
        json={"location": "Hall B, Row 2"},
    )
    assert resp.status_code == 200
    assert resp.json()["location"] == "Hall B, Row 2"


@pytest.mark.asyncio
async def test_filter_assets_by_dept(async_client, seed_db):
    resp = await async_client.get(
        "/api/v1/assets", params={"dept_id": seed_db["dept_id"]}
    )
    assert resp.status_code == 200
    for a in resp.json():
        assert a["dept_id"] == seed_db["dept_id"]
