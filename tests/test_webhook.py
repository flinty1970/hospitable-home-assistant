"""Verify signing, replay handling, cloud gating and fallback without live data."""

import json
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.util import dt as dt_util
from homeassistant.util.aiohttp import MockRequest

from custom_components.hospitable_stays.coordinator import HospitableCoordinator
from custom_components.hospitable_stays.webhook import (
    WebhookManager,
    host_secret,
    signature,
)


@pytest.fixture
def manager(hass, entry):
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            "webhook_secret": host_secret("primary@example.invalid"),
            "webhook_id": "FAKE-HOOK-ID-FOR-TESTS",
        },
    )
    c = HospitableCoordinator(hass, entry, AsyncMock())
    c.async_request_refresh = AsyncMock()
    return WebhookManager(hass, entry, c)


def body(**updates):
    return json.dumps(
        {
            "id": "fake-delivery",
            "action": "reservation.changed",
            "created": dt_util.utcnow().isoformat(),
            "version": "2.0",
            "data": {},
            **updates,
        }
    ).encode()


async def send(manager, payload, valid=True):
    return await manager.async_process(
        payload,
        signature(payload, manager.entry.data["webhook_secret"]) if valid else "0" * 64,
    )


async def test_valid_signature_and_duplicate(hass, manager):
    payload = body()
    assert (await send(manager, payload)).status == 200
    assert (await send(manager, payload)).text == "duplicate"
    await hass.async_block_till_done()
    manager.coordinator.async_request_refresh.assert_awaited_once()
    assert manager.last_event == "reservation.changed"
    assert manager.last_received


async def test_invalid_signature(manager):
    assert (await send(manager, body(), valid=False)).status == 401
    assert manager.last_received is None
    manager.coordinator.async_request_refresh.assert_not_called()


@pytest.mark.parametrize(
    "updates",
    [
        {"created": "2020-01-01T00:00:00Z"},
        {"created": "2999-01-01T00:00:00Z"},
        {"created": "2026-11-05T12:00:00"},
        {"action": "unsupported"},
        {"data": "invalid"},
        {"id": 1},
        {"version": None},
    ],
)
async def test_stale_future_and_malformed(manager, updates):
    assert (await send(manager, body(**updates))).status == 400
    manager.coordinator.async_request_refresh.assert_not_called()


@pytest.mark.parametrize("payload", [b"{", b"null", b"[]", b"{}"])
async def test_malformed_json(manager, payload):
    assert (await send(manager, payload)).status == 400


async def test_persisted_deduplication(hass, manager):
    payload = body()
    await send(manager, payload)
    second = WebhookManager(hass, manager.entry, manager.coordinator)
    await second.async_setup()
    try:
        assert (await send(second, payload)).text == "duplicate"
    finally:
        second.unload()


async def test_fallback_when_quiet(manager):
    with (
        patch(
            "custom_components.hospitable_stays.webhook.cloud_active", return_value=True
        ),
        patch(
            "custom_components.hospitable_stays.webhook.cloud_connected",
            return_value=True,
        ),
    ):
        assert manager.fallback_active
        manager.last_received = dt_util.utcnow()
        assert not manager.fallback_active
        manager.last_received -= timedelta(hours=1)
        assert manager.fallback_active
        assert manager.coordinator.update_interval == timedelta(minutes=10)


async def test_registered_signed_local_test(hass, manager):
    with patch(
        "custom_components.hospitable_stays.webhook.cloud_active", return_value=True
    ):
        await manager.async_setup()
        try:
            assert await manager.async_test()
            assert manager.last_test
            assert manager.last_received is None
        finally:
            manager.unload()


async def test_reject_direct_http_and_ws(hass, manager):
    request = MockRequest(content=body(), mock_source="webhook/ws", method="POST")
    assert (
        await manager.async_handle(hass, "FAKE-HOOK-ID-FOR-TESTS", request)
    ).status == 403


async def test_cloud_dispatch_path(hass, manager):
    payload = body()
    request = MockRequest(
        content=payload,
        mock_source="cloud",
        method="POST",
        headers={"Signature": signature(payload, manager.entry.data["webhook_secret"])},
    )
    with patch(
        "custom_components.hospitable_stays.webhook.cloud_active", return_value=True
    ):
        assert (
            await manager.async_handle(hass, "FAKE-HOOK-ID-FOR-TESTS", request)
        ).status == 200
