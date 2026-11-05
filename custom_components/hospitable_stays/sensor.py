"""Reservation status and next-stay sensors."""

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HospitableEntry
from .coordinator import HospitableCoordinator
from .entity import HospitableEntity
from .models import Property, current_and_next


async def async_setup_entry(
    hass: HomeAssistant, entry: HospitableEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        ReservationSensor(coordinator, prop, key)
        for prop in coordinator.properties.values()
        for key in ("reservation_status", "next_reservation")
    )


class ReservationSensor(HospitableEntity, SensorEntity):
    """State and safe attributes from the shared snapshot."""

    _attr_icon = "mdi:calendar-account"

    def __init__(
        self, coordinator: HospitableCoordinator, prop: Property, key: str
    ) -> None:
        super().__init__(coordinator, prop, key)
        self._key = key
        if key == "reservation_status":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = ["none", "checked_in", "upcoming"]

    @property
    def native_value(self) -> str:
        current, upcoming = current_and_next(
            self.coordinator.reservations_for(self.prop.id), dt_util.utcnow()
        )
        if self._key == "next_reservation":
            return upcoming.code if upcoming else "none"
        return "checked_in" if current else "upcoming" if upcoming else "none"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        current, upcoming = current_and_next(
            self.coordinator.reservations_for(self.prop.id), now
        )
        reservation = (
            upcoming if self._key == "next_reservation" else current or upcoming
        )
        attrs: dict[str, Any] = {
            "property_id": self.prop.id,
            "timezone": self.prop.timezone,
        }
        if reservation:
            attrs.update(reservation.attributes(self.coordinator.include_guest))
        if self._key == "next_reservation":
            attrs["hours_until_check_in"] = (
                (upcoming.check_in - now).total_seconds() / 3600 if upcoming else None
            )
        return attrs
