"""
Test 8 — Analytics API endpoints (Fix #4).
Verifies KPI, technician performance, and asset failure endpoints
return correct shape and respect query filters.
"""
import pytest


@pytest.mark.asyncio
async def test_kpi_summary_empty(async_client):
    resp = await async_client.get("/api/v1/analytics/kpi")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "kpi_summary"
    assert "kpi" in data
    assert "generated_at" in data


@pytest.mark.asyncio
async def test_kpi_summary_with_seed(async_client, seed_db):
    resp = await async_client.get("/api/v1/analytics/kpi")
    assert resp.status_code == 200
    kpi = resp.json()["kpi"]
    assert kpi["total_work_orders"] >= 1
    assert kpi["p1_count"] >= 1


@pytest.mark.asyncio
async def test_technician_performance_endpoint(async_client, seed_db):
    resp = await async_client.get("/api/v1/analytics/technicians")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "technician_performance"


@pytest.mark.asyncio
async def test_asset_failures_endpoint(async_client, seed_db):
    resp = await async_client.get("/api/v1/analytics/assets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "asset_failures"


@pytest.mark.asyncio
async def test_sla_compliance_endpoint(async_client, seed_db):
    resp = await async_client.get("/api/v1/analytics/sla")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "sla_compliance"
    assert "kpi" in data


@pytest.mark.asyncio
async def test_kpi_date_filter(async_client, seed_db):
    """date_from / date_to filters must be accepted without 422 error."""
    resp = await async_client.get(
        "/api/v1/analytics/kpi",
        params={"date_from": "2020-01-01", "date_to": "2030-12-31"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_asset_failures_dept_filter(async_client, seed_db):
    """dept_id filter must be applied before .limit() — no crash."""
    resp = await async_client.get(
        "/api/v1/analytics/assets",
        params={"dept_id": seed_db["dept_id"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "asset_failures"
