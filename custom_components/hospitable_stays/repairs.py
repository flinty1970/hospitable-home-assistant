"""Route expired-token Repairs issues into Home Assistant reauthentication."""

from typing import Any

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant


class TokenRepairFlow(ConfirmRepairFlow):
    """Start reauth without accepting a token in the Repairs dialog."""

    def __init__(self, entry_id: str) -> None:
        super().__init__()
        self.entry_id = entry_id

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        if user_input is not None:
            if entry := self.hass.config_entries.async_get_entry(self.entry_id):
                entry.async_start_reauth(self.hass)
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="confirm")


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> TokenRepairFlow | None:
    if data and (entry_id := data.get("entry_id")):
        return TokenRepairFlow(entry_id)
    return None
