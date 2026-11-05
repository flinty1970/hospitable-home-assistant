"""Exercise real HA flow management with mocked Hospitable responses."""

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hospitable_stays.api import AuthenticationError
from custom_components.hospitable_stays.const import DOMAIN


async def test_setup_flow(hass, property_data):
    with (
        patch(
            "custom_components.hospitable_stays.api.HospitableApi.properties",
            return_value=[property_data],
        ),
        patch(
            "custom_components.hospitable_stays.async_setup_entry",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"access_token": "FAKE-TEST-TOKEN"}
        )
        assert result["step_id"] == "properties"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"properties": [property_data["id"]]}
        )
        assert result["step_id"] == "timezone"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"timezone": "America/New_York"}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["properties"][0]["timezone"] == "America/New_York"


async def test_invalid_token(hass):
    with patch(
        "custom_components.hospitable_stays.api.HospitableApi.properties",
        side_effect=AuthenticationError,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={"access_token": "FAKE-EXPIRED-TOKEN"},
        )
        assert result["errors"] == {"base": "invalid_auth"}


async def test_options(hass, entry):
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"poll_minutes": 15, "arrival_hours": 12, "guest_details": False},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["poll_minutes"] == 15
