"""
Test 1 — Health & startup checks.
Validates the FastAPI app mounts correctly and the /health endpoint responds.
"""
import pytest


@pytest.mark.asyncio
async def test_root(async_client):
    resp = await async_client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "RT Knits Agentic CMMS"
    assert "docs" in data


@pytest.mark.asyncio
async def test_health_endpoint_ok(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    # DB may be "error: ..." in test env (SQLite vs asyncpg URL) — just check key exists
    assert "db" in data


@pytest.mark.asyncio
async def test_docs_reachable(async_client):
    resp = await async_client.get("/docs")
    # FastAPI Swagger UI returns 200
    assert resp.status_code == 200
