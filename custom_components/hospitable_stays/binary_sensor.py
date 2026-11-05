"""Booked occupancy and arrival-window entities."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HospitableEntry
from .coordinator import HospitableCoordinator
from .entity import HospitableEntity
from .models import Property, arriving, current_and_next


async def async_setup_entry(
    hass: HomeAssistant, entry: HospitableEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        OccupancySensor(coordinator, prop, key)
        for prop in coordinator.properties.values()
        for key in ("occupied", "arrival")
    )


class OccupancySensor(HospitableEntity, BinarySensorEntity):
    """Booking-derived occupancy, independent of thermostat brand."""

    def __init__(
        self, coordinator: HospitableCoordinator, prop: Property, key: str
    ) -> None:
        super().__init__(coordinator, prop, key)
        self._key = key
        if key == "occupied":
            self._attr_device_class = BinarySensorDeviceClass.OCCUPANCY
        else:
            self._attr_icon = "mdi:airplane-clock"

    @property
    def is_on(self) -> bool:
        now = dt_util.utcnow()
        current, upcoming = current_and_next(
            self.coordinator.reservations_for(self.prop.id), now
        )
        return (
            current is not None
            if self._key == "occupied"
            else arriving(upcoming, now, self.coordinator.arrival_hours)
        )
