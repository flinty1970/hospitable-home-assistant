"""Diagnostics contain operational counts only, never raw state or config."""

from typing import Any

from homeassistant.core import HomeAssistant

from . import HospitableEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HospitableEntry
) -> dict[str, Any]:
    c = entry.runtime_data.coordinator
    return {
        "version": 1,
        "webhook_id": "**REDACTED**",
        "webhook_secret": "**REDACTED**",
        "cloudhook_url": "**REDACTED**",
        "last_webhook_received": entry.runtime_data.webhooks.last_received.isoformat()
        if entry.runtime_data.webhooks.last_received
        else None,
        "last_webhook_event": entry.runtime_data.webhooks.last_event,
        "polling_fallback_active": entry.runtime_data.webhooks.fallback_active,
        "property_count": len(c.properties),
        "reservation_count": sum(len(rows) for rows in (c.data or {}).values()),
        "last_update_success": c.last_update_success,
        "last_successful_poll": c.last_successful_poll.isoformat()
        if c.last_successful_poll
        else None,
        "access_token": "**REDACTED**",
        "properties": "**REDACTED**",
        "reservations": "**REDACTED**",
        "guest_data": "**REDACTED**",
    }
