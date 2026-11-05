"""UI setup, reauthentication and options."""

from typing import Any
from zoneinfo import ZoneInfoNotFoundError

import probatio as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import ApiError, AuthenticationError, HospitableApi
from .const import (
    CONF_ARRIVAL_HOURS,
    CONF_GUEST_DETAILS,
    CONF_POLL_MINUTES,
    CONF_PROPERTIES,
    DEFAULT_ARRIVAL_HOURS,
    DEFAULT_POLL_MINUTES,
    DOMAIN,
)

TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(vol.Secret(CONF_ACCESS_TOKEN)): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )
    }
)


class HospitableConfigFlow(ConfigFlow, domain=DOMAIN):
    """Validate a read PAT before property selection."""

    VERSION = 1

    def __init__(self) -> None:
        self._token = ""
        self._properties: list[dict[str, Any]] = []
        self._selected: list[dict[str, Any]] = []
        self._zone_index = 0

    async def _validate(self, token: str) -> list[dict[str, Any]]:
        return await HospitableApi(
            async_get_clientsession(self.hass), token
        ).properties()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._token = user_input[CONF_ACCESS_TOKEN].strip()
                self._properties = await self._validate(self._token)
                if not self._properties:
                    return self.async_abort(reason="no_properties")
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except (ApiError, KeyError, ValueError, TypeError):
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_properties()
        return self.async_show_form(
            step_id="user", data_schema=TOKEN_SCHEMA, errors=errors
        )

    async def async_step_properties(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        owned = {
            p["id"]
            for entry in self._async_current_entries()
            for p in entry.data[CONF_PROPERTIES]
        }
        choices = {p["id"]: p["name"] for p in self._properties if p["id"] not in owned}
        if not choices:
            return self.async_abort(reason="already_configured")
        if user_input is not None:
            ids = user_input[CONF_PROPERTIES]
            if not ids or not set(ids) <= choices.keys():
                errors["base"] = "select_properties"
            else:
                self._selected = [dict(p) for p in self._properties if p["id"] in ids]
                self._zone_index = 0
                return await self.async_step_timezone()
        return self.async_show_form(
            step_id="properties",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROPERTIES): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=pid, label=name)
                                for pid, name in choices.items()
                            ],
                            multiple=True,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_timezone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        prop = self._selected[self._zone_index]
        errors = {}
        if user_input is not None:
            try:
                if await dt_util.async_get_time_zone(user_input["timezone"]) is None:
                    raise ValueError("Invalid IANA timezone")
            except (ZoneInfoNotFoundError, ValueError, TypeError):
                errors["base"] = "invalid_timezone"
            else:
                prop["timezone"] = user_input["timezone"]
                self._zone_index += 1
                if self._zone_index == len(self._selected):
                    return self.async_create_entry(
                        title="Hospitable Stays",
                        data={
                            CONF_ACCESS_TOKEN: self._token,
                            CONF_PROPERTIES: self._selected,
                        },
                    )
                return await self.async_step_timezone()
        try:
            if await dt_util.async_get_time_zone(prop["timezone"]) is None:
                raise ValueError("Invalid IANA timezone")
            default = prop["timezone"]
        except (ZoneInfoNotFoundError, ValueError):
            default = self.hass.config.time_zone
        return self.async_show_form(
            step_id="timezone",
            data_schema=vol.Schema(
                {vol.Required("timezone", default=default): selector.TextSelector()}
            ),
            errors=errors,
            description_placeholders={
                "property": prop["name"],
                "reported_timezone": prop["timezone"],
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            entry = self._get_reauth_entry()
            try:
                token = user_input[CONF_ACCESS_TOKEN].strip()
                properties = await self._validate(token)
                if not {p["id"] for p in entry.data[CONF_PROPERTIES]} <= {
                    p["id"] for p in properties
                }:
                    errors["base"] = "wrong_account"
                else:
                    ir.async_delete_issue(self.hass, DOMAIN, f"auth_{entry.entry_id}")
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_ACCESS_TOKEN: token}
                    )
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except (ApiError, ValueError, KeyError, TypeError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=TOKEN_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        return HospitableOptionsFlow()


class HospitableOptionsFlow(OptionsFlowWithReload):
    """Configure timing and guest privacy."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["settings"]
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self.config_entry.options, **user_input}
            )
        options = self.config_entry.options
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_MINUTES,
                        default=options.get(CONF_POLL_MINUTES, DEFAULT_POLL_MINUTES),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Required(
                        CONF_ARRIVAL_HOURS,
                        default=options.get(CONF_ARRIVAL_HOURS, DEFAULT_ARRIVAL_HOURS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=168)),
                    vol.Required(
                        CONF_GUEST_DETAILS,
                        default=options.get(CONF_GUEST_DETAILS, False),
                    ): bool,
                }
            ),
        )

