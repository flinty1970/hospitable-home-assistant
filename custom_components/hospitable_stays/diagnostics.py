"""Privacy-safe operational diagnostics."""
from typing import Any
from homeassistant.core import HomeAssistant
from . import HospitableEntry
async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: HospitableEntry) -> dict[str, Any]:
    c = entry.runtime_data.coordinator
    return {"property_count": len(c.properties), "reservation_count": sum(map(len, (c.data or {}).values())), "last_update_success": c.last_update_success, "access_token": "**REDACTED**", "guest_data": "**REDACTED**"}
