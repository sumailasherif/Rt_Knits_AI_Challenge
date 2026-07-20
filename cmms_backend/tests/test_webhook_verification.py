"""
Test 2 — WhatsApp webhook GET verification (Fix #2).

Verifies that:
  - hub.mode / hub.verify_token / hub.challenge dot-notation query params
    are parsed correctly by FastAPI.
  - Correct token returns 200 with challenge echoed as plain text.
  - Wrong token returns 403.
"""
import pytest


@pytest.mark.asyncio
async def test_webhook_verify_success(async_client):
    resp = await async_client.get(
        "/webhook",
        params={
            "hub.mode":         "subscribe",
            "hub.verify_token": "test-verify-token",   # matches conftest env
            "hub.challenge":    "challenge_abc123",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "challenge_abc123"
    assert resp.headers["content-type"].startswith("text/plain")


@pytest.mark.asyncio
async def test_webhook_verify_wrong_token(async_client):
    resp = await async_client.get(
        "/webhook",
        params={
            "hub.mode":         "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge":    "challenge_abc123",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_verify_missing_mode(async_client):
    resp = await async_client.get(
        "/webhook",
        params={
            "hub.verify_token": "test-verify-token",
            "hub.challenge":    "challenge_abc123",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_post_bad_json(async_client):
    """POST with malformed JSON must return 200 (Meta retries on non-200)."""
    resp = await async_client.post(
        "/webhook",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_webhook_post_status_update_ignored(async_client):
    """Delivery / read receipts (no messages key) must return 200 silently."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry1",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "+230123", "phone_number_id": "000"},
                            "statuses": [{"id": "msg1", "status": "delivered"}],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    resp = await async_client.post("/webhook", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
