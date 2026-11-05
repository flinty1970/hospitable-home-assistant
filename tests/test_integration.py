"""Load actual HA platforms and inspect registry/state and diagnostics."""

import json
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hospitable_stays.const import DOMAIN
from custom_components.hospitable_stays.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_full_setup_and_unload(hass, entry, reservation_data, freezer):
    freezer.move_to("2026-11-05T22:00:00Z")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.hospitable_stays.api.HospitableApi.reservations",
        return_value=[reservation_data],
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        states = [
            s
            for s in hass.states.async_all()
            if s.entity_id.startswith(
                (
                    "sensor.example_cottage",
                    "binary_sensor.example_cottage",
                    "calendar.example_cottage",
                )
            )
        ]
        assert len(states) == 5
        assert hass.states.get("binary_sensor.example_cottage_occupied").state == "on"
        assert (
            hass.states.get("sensor.example_cottage_reservation_status").state
            == "checked_in"
        )
        data = await async_get_config_entry_diagnostics(hass, entry)
        serialized = json.dumps(data)
        assert "FAKE-TEST-TOKEN" not in serialized
        assert "FAKE-BOOKING" not in serialized
        assert "fake-property" not in serialized
        assert data["property_count"] == 1
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert (
            hass.states.get("binary_sensor.example_cottage_occupied").state
            == "unavailable"
        )


async def test_reauth_wrong_account_and_success(hass, entry, property_data):
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.hospitable_stays.api.HospitableApi.properties",
            return_value=[],
        ) as validate,
        patch(
            "homeassistant.config_entries.ConfigEntries.async_reload",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"access_token": "FAKE-NEW-TOKEN"}
        )
        assert result["errors"] == {"base": "wrong_account"}
        validate.return_value = [property_data]
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"access_token": "FAKE-NEW-TOKEN"}
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reauth_successful"
        assert entry.data["access_token"] == "FAKE-NEW-TOKEN"


async def test_cloud_required_options(hass, entry):
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "webhooks"}
    )
    assert result["step_id"] == "cloud_required"
    assert result["description_placeholders"]["minutes"] == "10"
    assert not result["data_schema"].schema


async def test_save_timezone_options_on_loaded_entry(
    hass, entry, reservation_data, freezer
):
    freezer.move_to("2026-11-05T22:00:00Z")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.hospitable_stays.api.HospitableApi.reservations",
        return_value=[reservation_data],
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        flow = await hass.config_entries.options.async_init(entry.entry_id)
        flow = await hass.config_entries.options.async_configure(
            flow["flow_id"], {"next_step_id": "timezones"}
        )
        result = await hass.config_entries.options.async_configure(
            flow["flow_id"], {"timezone": "Europe/London"}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        assert (
            entry.runtime_data.coordinator.properties["fake-property"].timezone
            == "Europe/London"
        )
        assert (
            hass.states.get("sensor.example_cottage_reservation_status").attributes[
                "timezone"
            ]
            == "Europe/London"
        )
        flow = await hass.config_entries.options.async_init(entry.entry_id)
        flow = await hass.config_entries.options.async_configure(
            flow["flow_id"], {"next_step_id": "settings"}
        )
        result = await hass.config_entries.options.async_configure(
            flow["flow_id"],
            {"poll_minutes": 15, "arrival_hours": 12, "guest_details": False},
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        assert entry.runtime_data.coordinator.arrival_hours == 12
        assert (
            entry.runtime_data.coordinator.properties["fake-property"].timezone
            == "Europe/London"
        )
        assert await hass.config_entries.async_unload(entry.entry_id)
