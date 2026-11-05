"""Lifecycle boundaries, failure handling and entity behavior."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.hospitable_stays.api import ApiError, AuthenticationError
from custom_components.hospitable_stays.binary_sensor import OccupancySensor
from custom_components.hospitable_stays.calendar import ReservationCalendar
from custom_components.hospitable_stays.const import DOMAIN
from custom_components.hospitable_stays.coordinator import HospitableCoordinator
from custom_components.hospitable_stays.models import Property, parse_reservation
from custom_components.hospitable_stays.sensor import ReservationSensor


async def test_boundary_events_without_network(
    hass, entry, reservation_data, property_data
):
    entry.add_to_hass(hass)
    api = AsyncMock()
    c = HospitableCoordinator(hass, entry, api)
    r = parse_reservation(reservation_data, Property(**property_data), False)
    events = []
    for name in ("arriving_soon", "checked_in", "checked_out"):
        hass.bus.async_listen(f"hospitable_guest_{name}", lambda e: events.append(e))
    c.data = {r.property_id: [r]}
    c._evaluate(c.data, r.check_in - timedelta(hours=25))
    c.tick(r.check_in - timedelta(hours=24))
    c.tick(r.check_in - timedelta(hours=23))
    c.tick(r.check_in)
    c.tick(r.check_out)
    await hass.async_block_till_done()
    assert [e.event_type for e in events] == [
        "hospitable_guest_arriving_soon",
        "hospitable_guest_checked_in",
        "hospitable_guest_checked_out",
    ]
    assert all(e.data["reservation_code"] == "FAKE-BOOKING" for e in events)
    api.reservations.assert_not_called()


async def test_cancelled_stay_does_not_emit_checkout(
    hass, entry, reservation_data, property_data
):
    c = HospitableCoordinator(hass, entry, AsyncMock())
    r = parse_reservation(reservation_data, Property(**property_data), False)
    events = []
    hass.bus.async_listen("hospitable_guest_checked_out", lambda e: events.append(e))
    c._evaluate({r.property_id: [r]}, r.check_in)
    c._evaluate({r.property_id: []}, r.check_out)
    await hass.async_block_till_done()
    assert events == []


async def test_poll_and_auth_repairs(hass, entry, reservation_data):
    entry.add_to_hass(hass)
    api = AsyncMock()
    api.reservations.return_value = [reservation_data]
    c = HospitableCoordinator(hass, entry, api)
    result = await c._async_update_data()
    assert len(result["fake-property"]) == 1
    assert c.last_successful_poll
    api.reservations.side_effect = AuthenticationError()
    with pytest.raises(ConfigEntryAuthFailed):
        await c._async_update_data()
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, f"auth_{entry.entry_id}")
    api.reservations.side_effect = None
    await c._async_update_data()
    assert not registry.async_get_issue(DOMAIN, f"auth_{entry.entry_id}")
    api.reservations.side_effect = ApiError()
    with pytest.raises(UpdateFailed):
        await c._async_update_data()


async def test_entities_and_calendar(hass, entry, property_data, reservation_data):
    prop = Property(**property_data)
    r = parse_reservation(reservation_data, prop, False)
    c = HospitableCoordinator(hass, entry, AsyncMock())
    c.data = {prop.id: [r]}
    with patch("homeassistant.util.dt.utcnow", return_value=r.check_in):
        occupied = OccupancySensor(c, prop, "occupied")
        assert occupied.is_on
        status = ReservationSensor(c, prop, "reservation_status")
        assert status.native_value == "checked_in"
        assert status.extra_state_attributes["guest_count"] == 2
        calendar = ReservationCalendar(c, prop, "reservations")
        assert calendar.event.uid == r.id
        assert await calendar.async_get_events(hass, r.check_in, r.check_out) == [
            calendar.event
        ]
        assert (
            await calendar.async_get_events(
                hass, r.check_out, r.check_out + timedelta(days=1)
            )
            == []
        )
        c.last_update_success = False
        assert not status.available


async def test_property_zone_override_normalizes_booking_offset(
    hass, entry, reservation_data
):
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={"timezones": {"fake-property": "Europe/London"}}
    )
    reservation_data["platform"] = "booking"
    api = AsyncMock()
    api.reservations.return_value = [reservation_data]
    c = HospitableCoordinator(hass, entry, api)
    result = await c._async_update_data()
    stay = result["fake-property"][0]
    assert c.properties["fake-property"].timezone == "Europe/London"
    assert stay.check_in.hour == 15
    assert stay.check_in.utcoffset().total_seconds() == 0
