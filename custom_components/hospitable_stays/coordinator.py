"""Shared polling and local reservation boundary updates."""

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
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
from .models import Property, Reservation, arriving, current_and_next, parse_reservation

_LOGGER = logging.getLogger(__name__)


class HospitableCoordinator(DataUpdateCoordinator[dict[str, list[Reservation]]]):
    """One snapshot shared by every entity, with no partial poll publication."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: HospitableApi
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=entry.options.get(CONF_POLL_MINUTES, DEFAULT_POLL_MINUTES)
            ),
        )
        self.entry = entry
        self.api = api
        self.properties = {
            p["id"]: Property(
                **{
                    **p,
                    "timezone": entry.options.get("timezones", {}).get(
                        p["id"], p["timezone"]
                    ),
                }
            )
            for p in entry.data[CONF_PROPERTIES]
        }
        self.include_guest: bool = entry.options.get(CONF_GUEST_DETAILS, False)
        self.arrival_hours: int = entry.options.get(
            CONF_ARRIVAL_HOURS, DEFAULT_ARRIVAL_HOURS
        )
        self.last_successful_poll: datetime | None = None
        self._active: dict[str, Reservation] | None = None
        self._announced: set[tuple[str, str, str]] = set()

    async def _async_update_data(self) -> dict[str, list[Reservation]]:
        now = dt_util.utcnow()
        # Include all in-progress stays regardless of when they checked in.
        dates = [
            now.astimezone(ZoneInfo(p.timezone)).date()
            for p in self.properties.values()
        ]
        start = (min(dates) - timedelta(days=1)).isoformat()
        end = (max(dates) + timedelta(days=366)).isoformat()
        try:
            raw = await self.api.reservations(
                list(self.properties), start, end, self.include_guest
            )
            result: dict[str, list[Reservation]] = {pid: [] for pid in self.properties}
            seen: set[tuple[str, str]] = set()
            for row in raw:
                for related in row["properties"]:
                    pid = related["id"]
                    if pid in self.properties and (pid, row["id"]) not in seen:
                        seen.add((pid, row["id"]))
                        if reservation := parse_reservation(
                            row, self.properties[pid], self.include_guest
                        ):
                            result[pid].append(reservation)
        except AuthenticationError as err:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"auth_{self.entry.entry_id}",
                is_fixable=True,
                severity=ir.IssueSeverity.ERROR,
                translation_key="invalid_auth",
                data={"entry_id": self.entry.entry_id},
            )
            raise ConfigEntryAuthFailed("Hospitable token needs renewal") from err
        except (ApiError, ValueError, KeyError, TypeError) as err:
            raise UpdateFailed("Could not refresh Hospitable reservation data") from err
        self.last_successful_poll = now
        ir.async_delete_issue(self.hass, DOMAIN, f"auth_{self.entry.entry_id}")
        self._evaluate(result, now)
        return result

    def reservations_for(self, property_id: str) -> list[Reservation]:
        """Return the cached property snapshot."""
        return self.data.get(property_id, []) if self.data else []

    @callback
    def tick(self, now: datetime) -> None:
        """Refresh time-derived entities without making any network requests."""
        if self.last_update_success and self.data:
            self._evaluate(self.data, now)
            self.async_update_listeners()

    @callback
    def _evaluate(self, data: dict[str, list[Reservation]], now: datetime) -> None:
        active: dict[str, Reservation] = {}
        live_keys = {
            (pid, r.id, r.check_in.isoformat())
            for pid, rows in data.items()
            for r in rows
        }
        self._announced.intersection_update(live_keys)
        for pid, rows in data.items():
            current, upcoming = current_and_next(rows, now)
            if current:
                active[pid] = current
            if self._active is not None:
                previous = self._active.get(pid)
                # Cancellations/removals are not real checkouts.
                if previous and (not current or current.id != previous.id):
                    updated = next((r for r in rows if r.id == previous.id), None)
                    if updated and updated.check_out.astimezone(UTC) <= now:
                        self._fire("checked_out", updated)
                if current and (not previous or current.id != previous.id):
                    self._fire("checked_in", current)
            if arriving(upcoming, now, self.arrival_hours) and upcoming:
                key = (pid, upcoming.id, upcoming.check_in.isoformat())
                if key not in self._announced:
                    self._announced.add(key)
                    self._fire("arriving_soon", upcoming)
        self._active = active

    @callback
    def _fire(self, event: str, reservation: Reservation) -> None:
        self.hass.bus.async_fire(
            f"hospitable_guest_{event}",
            {
                "property_id": reservation.property_id,
                "property": self.properties[reservation.property_id].name,
                "reservation_code": reservation.code,
            },
        )
