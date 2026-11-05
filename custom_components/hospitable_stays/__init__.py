"""Hospitable Stays custom integration."""

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import HospitableApi
from .coordinator import HospitableCoordinator
from .panel import async_setup_panel
from .webhook import WebhookManager

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR]


@dataclass
class RuntimeData:
    """Runtime resources belonging to one entry."""

    coordinator: HospitableCoordinator
    webhooks: WebhookManager


type HospitableEntry = ConfigEntry[RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: HospitableEntry) -> bool:
    """Set up UI-selected properties and platforms."""
    for prop in entry.data["properties"]:
        await dt_util.async_get_time_zone(
            entry.options.get("timezones", {}).get(prop["id"], prop["timezone"])
        )
    coordinator = HospitableCoordinator(
        hass,
        entry,
        HospitableApi(async_get_clientsession(hass), entry.data[CONF_ACCESS_TOKEN]),
    )
    await coordinator.async_config_entry_first_refresh()
    manager = WebhookManager(hass, entry, coordinator)
    await manager.async_setup()
    entry.runtime_data = RuntimeData(coordinator, manager)
    entry.async_on_unload(manager.unload)
    await async_setup_panel(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(
        async_track_time_interval(hass, coordinator.tick, timedelta(seconds=30))
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: HospitableEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HospitableEntry) -> bool:
    """Unload entity platforms and registered listeners."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: HospitableEntry) -> None:
    """Clean up the cloud hook when the configuration is removed."""
    from homeassistant.helpers.storage import Store

    from .cloud_helpers import delete_hook
    from .const import CONF_WEBHOOK_ID, DOMAIN

    if hook_id := entry.data.get(CONF_WEBHOOK_ID):
        await delete_hook(hass, hook_id)
    await Store(
        hass, 1, f"{DOMAIN}.{entry.entry_id}.webhooks", private=True
    ).async_remove()
