"""Shared property entity metadata."""

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HospitableCoordinator
from .models import Property


class HospitableEntity(CoordinatorEntity[HospitableCoordinator]):
    """An entity attached to a single property device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: HospitableCoordinator, prop: Property, key: str
    ) -> None:
        super().__init__(coordinator)
        self.prop = prop
        self._attr_unique_id = f"{prop.id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, prop.id)},
            name=prop.name,
            manufacturer="Hospitable",
            model="Rental property",
            entry_type=DeviceEntryType.SERVICE,
        )
