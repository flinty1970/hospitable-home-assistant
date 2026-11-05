"""UI setup, reauthentication and options."""

from typing import Any
from zoneinfo import ZoneInfoNotFoundError, available_timezones

import probatio as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import ApiError, AuthenticationError, HospitableApi
from .cloud_helpers import cloud_active
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


async def timezone_schema(
    hass: HomeAssistant, default: str | None = None
) -> vol.Schema:
    """Offer a searchable IANA menu; a numeric offset must not suggest HA's zone."""
    zones = sorted(await hass.async_add_executor_job(available_timezones))
    key = (
        vol.Required("timezone", default=default)
        if default in zones
        else vol.Required("timezone")
    )
    return vol.Schema(
        {
            key: selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=zone,
                            label="Europe/London (United Kingdom)"
                            if zone == "Europe/London"
                            else zone,
                        )
                        for zone in zones
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=False,
                )
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
        return self.async_show_form(
            step_id="timezone",
            data_schema=await timezone_schema(self.hass, prop["timezone"]),
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
            step_id="init", menu_options=["settings", "timezones", "webhooks"]
        )

    async def async_step_timezones(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Correct property zones without removing entries or re-entering a PAT."""
        if not hasattr(self, "_timezone_index"):
            self._timezone_index = 0
            self._timezones: dict[str, str] = dict(
                self.config_entry.options.get("timezones", {})
            )
        prop = self.config_entry.data[CONF_PROPERTIES][self._timezone_index]
        errors: dict[str, str] = {}
        if user_input is not None:
            zone = user_input["timezone"]
            if zone not in await self.hass.async_add_executor_job(available_timezones):
                errors["base"] = "invalid_timezone"
            else:
                self._timezones[prop["id"]] = zone
                self._timezone_index += 1
                if self._timezone_index == len(self.config_entry.data[CONF_PROPERTIES]):
                    return self.async_create_entry(
                        title="",
                        data={
                            **self.config_entry.options,
                            "timezones": self._timezones,
                        },
                    )
                return await self.async_step_timezones()
        return self.async_show_form(
            step_id="timezones",
            data_schema=await timezone_schema(
                self.hass, self._timezones.get(prop["id"], prop["timezone"])
            ),
            errors=errors,
            description_placeholders={"property": prop["name"]},
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

    async def async_step_webhooks(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show Cloud subscription gating before offering any setup steps."""
        from .const import CONF_WEBHOOK_ID

        if not cloud_active(self.hass):
            return self.async_show_form(
                step_id="cloud_required",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "minutes": str(
                        self.config_entry.options.get(
                            CONF_POLL_MINUTES, DEFAULT_POLL_MINUTES
                        )
                    )
                },
            )
        if self.config_entry.data.get(CONF_WEBHOOK_ID):
            return self.async_show_menu(
                step_id="webhooks",
                menu_options=["webhook_status", "test_event", "disable_push"],
            )
        return self.async_show_menu(step_id="webhooks", menu_options=["enable_push"])

    async def async_step_cloud_required(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    async def async_step_enable_push(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        if not cloud_active(self.hass):
            return await self.async_step_webhooks()
        if user_input is not None:
            email = user_input["primary_email"].strip()
            if "@" not in email or len(email) > 254:
                errors["base"] = "invalid_email"
            else:
                try:
                    await self.config_entry.runtime_data.webhooks.async_enable(email)
                except HomeAssistantError:
                    errors["base"] = "cloud_unavailable"
                else:
                    return await self.async_step_webhook_status()
        return self.async_show_form(
            step_id="enable_push",
            data_schema=vol.Schema(
                {
                    vol.Required(vol.Secret("primary_email")): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.EMAIL
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_webhook_status(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        from .const import CONF_CLOUDHOOK_URL

        if user_input is not None:
            return self.async_create_entry(
                title="", data=dict(self.config_entry.options)
            )
        manager = self.config_entry.runtime_data.webhooks
        poll = manager.coordinator.last_successful_poll
        received = manager.last_received
        return self.async_show_form(
            step_id="webhook_status",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "cloudhook_url",
                        default=self.config_entry.data.get(CONF_CLOUDHOOK_URL, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.URL, read_only=True
                        )
                    )
                }
            ),
            description_placeholders={
                "received": received.isoformat() if received else "Never",
                "event": manager.last_event or "None",
                "fallback": "Active"
                if manager.fallback_active
                else "Standby (periodic polling continues)",
                "poll": poll.isoformat() if poll else "Never",
            },
        )

    async def async_step_test_event(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            success = await self.config_entry.runtime_data.webhooks.async_test()
            return self.async_show_form(
                step_id="test_result",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "result": "Signed sample processed successfully"
                    if success
                    else "Test failed; check Cloud connection and webhook configuration"
                },
            )
        return self.async_show_form(step_id="test_event", data_schema=vol.Schema({}))

    async def async_step_test_result(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    async def async_step_disable_push(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                await self.config_entry.runtime_data.webhooks.async_disable()
            except HomeAssistantError:
                errors["base"] = "cloud_unavailable"
            else:
                return self.async_create_entry(
                    title="", data=dict(self.config_entry.options)
                )
        return self.async_show_form(
            step_id="disable_push", data_schema=vol.Schema({}), errors=errors
        )
