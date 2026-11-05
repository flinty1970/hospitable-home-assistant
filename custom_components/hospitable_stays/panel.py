"""Admin-only webhook status and clipboard UI, without exposing guest data."""

from pathlib import Path
from typing import Any

import probatio
from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .cloud_helpers import cloud_active
from .const import CONF_CLOUDHOOK_URL, CONF_POLL_MINUTES, DEFAULT_POLL_MINUTES, DOMAIN


@websocket_api.websocket_command({probatio.Required("type"): f"{DOMAIN}/status"})
@websocket_api.require_admin
@callback
def websocket_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Only authenticated administrators may retrieve private cloud URLs."""
    enabled = cloud_active(hass)
    rows = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if not hasattr(entry, "runtime_data"):
            continue
        manager = entry.runtime_data.webhooks
        rows.append(
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "minutes": entry.options.get(CONF_POLL_MINUTES, DEFAULT_POLL_MINUTES),
                "cloud_active": enabled,
                "url": entry.data.get(CONF_CLOUDHOOK_URL) if enabled else None,
                "last_received": manager.last_received.isoformat()
                if manager.last_received
                else None,
                "last_event": manager.last_event,
                "last_poll": manager.coordinator.last_successful_poll.isoformat()
                if manager.coordinator.last_successful_poll
                else None,
                "fallback": manager.fallback_active,
            }
        )
    connection.send_result(msg["id"], rows)


@websocket_api.websocket_command(
    {probatio.Required("type"): f"{DOMAIN}/test", probatio.Required("entry_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_test(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Run the same signed local self-test exposed through options."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
        connection.send_error(msg["id"], "not_found", "Integration is not loaded")
        return
    if not cloud_active(hass):
        connection.send_error(
            msg["id"], "cloud_unavailable", "Home Assistant Cloud is unavailable"
        )
        return
    connection.send_result(
        msg["id"], {"processed": await entry.runtime_data.webhooks.async_test()}
    )


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Register endpoints once; serve a local module only when frontend is loaded."""
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("websocket_registered"):
        websocket_api.async_register_command(hass, websocket_status)
        websocket_api.async_register_command(hass, websocket_test)
        data["websocket_registered"] = True
    if "frontend" not in hass.config.components or data.get("panel_registered"):
        return
    from homeassistant.components import panel_custom

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                f"/api/{DOMAIN}/panel.js",
                str(Path(__file__).parent / "frontend" / "panel.js"),
                False,
            )
        ]
    )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=DOMAIN,
        webcomponent_name="hospitable-stays-panel",
        sidebar_title="Hospitable Stays",
        sidebar_icon="mdi:calendar-home",
        module_url=f"/api/{DOMAIN}/panel.js?v=0.1.1",
        require_admin=True,
    )
    data["panel_registered"] = True
