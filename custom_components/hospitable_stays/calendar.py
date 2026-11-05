"""Read-only calendar of accepted guest stays."""

from datetime import UTC, datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HospitableEntry
from .entity import HospitableEntity
from .models import Reservation, current_and_next


async def async_setup_entry(
    hass: HomeAssistant, entry: HospitableEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        ReservationCalendar(coordinator, prop, "reservations")
        for prop in coordinator.properties.values()
    )


class ReservationCalendar(HospitableEntity, CalendarEntity):
    """A bounded cached calendar. Never fetch additional data per entity."""

    def _event(self, reservation: Reservation) -> CalendarEvent:
        return CalendarEvent(
            start=reservation.check_in,
            end=reservation.check_out,
            summary=f"Reservation {reservation.code}",
            uid=reservation.id,
            description=f"{reservation.platform}; {reservation.guest_count} guests",
        )

    @property
    def event(self) -> CalendarEvent | None:
        current, upcoming = current_and_next(
            self.coordinator.reservations_for(self.prop.id), dt_util.utcnow()
        )
        return (
            self._event(reservation) if (reservation := current or upcoming) else None
        )

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            self._event(r)
            for r in sorted(
                self.coordinator.reservations_for(self.prop.id),
                key=lambda r: r.check_in.astimezone(UTC),
            )
            if r.check_in.astimezone(UTC) < end_date
            and r.check_out.astimezone(UTC) > start_date
        ]
