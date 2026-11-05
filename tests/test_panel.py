"""Ensure private hook URLs are returned only to administrators with Cloud active."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import Unauthorized

from custom_components.hospitable_stays import RuntimeData
from custom_components.hospitable_stays.coordinator import HospitableCoordinator
from custom_components.hospitable_stays.panel import websocket_status
from custom_components.hospitable_stays.webhook import WebhookManager


async def test_non_admin_cannot_read_url(hass):
    connection = Mock(user=Mock(is_admin=False))
    with pytest.raises(Unauthorized):
        websocket_status(hass, connection, {"id": 1, "type": "hospitable_stays/status"})
    connection.send_result.assert_not_called()


async def test_admin_status_hides_url_without_cloud(hass, entry):
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, "cloudhook_url": "https://hooks.nabu.casa/FAKE-TEST-ONLY"},
    )
    c = HospitableCoordinator(hass, entry, AsyncMock())
    entry.runtime_data = RuntimeData(c, WebhookManager(hass, entry, c))
    connection = Mock(user=Mock(is_admin=True))
    with patch(
        "custom_components.hospitable_stays.panel.cloud_active", return_value=False
    ):
        websocket_status(hass, connection, {"id": 1})
        rows = connection.send_result.call_args.args[1]
        assert rows[0]["url"] is None
        assert not rows[0]["cloud_active"]
    with patch(
        "custom_components.hospitable_stays.panel.cloud_active", return_value=True
    ):
        websocket_status(hass, connection, {"id": 2})
        rows = connection.send_result.call_args.args[1]
        assert rows[0]["url"] == "https://hooks.nabu.casa/FAKE-TEST-ONLY"
        assert "access_token" not in rows[0]
