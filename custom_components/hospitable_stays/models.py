"""Allowlisted reservation models and property-local time handling."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Property:
    """A selected property; timezone must be an IANA identifier."""

    id: str
    name: str
    timezone: str


def normalize_time(value: str, zone: ZoneInfo, platform: str) -> datetime:
    """Repair Booking.com's conflicting non-Z offset; preserve true UTC instants."""
    parsed = datetime.fromisoformat(value)
    wall = parsed.replace(tzinfo=None)
    local = wall.replace(tzinfo=zone)
    alternate = local.replace(fold=1)
    if parsed.tzinfo is not None and parsed.utcoffset() == alternate.utcoffset():
        local = alternate
    repair = (
        platform == "booking"
        and not value.endswith("Z")
        and parsed.utcoffset() != local.utcoffset()
    )
    if (
        parsed.tzinfo is None
        or repair
        or (platform == "booking" and not value.endswith("Z"))
    ):
        if local.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != wall:
            raise ValueError("Nonexistent property-local time")
        return local
    return parsed.astimezone(zone)


@dataclass(frozen=True)
class Reservation:
    """Only data approved for entity exposure; no raw payload retained."""

    id: str
    property_id: str
    code: str
    check_in: datetime
    check_out: datetime
    nights: int
    platform: str
    guest_count: int
    guest: dict[str, Any] = field(default_factory=dict, repr=False)

    def attributes(self, include_guest: bool = False) -> dict[str, Any]:
        """Return state attributes with privacy controlled at exposure time too."""
        result = {
            "check_in": self.check_in.isoformat(),
            "check_out": self.check_out.isoformat(),
            "nights": self.nights,
            "platform": self.platform,
            "guest_count": self.guest_count,
            "reservation_code": self.code,
        }
        if include_guest:
            result.update(self.guest)
        return result


def parse_reservation(
    raw: dict[str, Any], prop: Property, include_guest: bool
) -> Reservation | None:
    """Parse only accepted guest stays; fail closed on unknown status."""
    category = raw.get("reservation_status", {}).get("current", {}).get("category")
    if category != "accepted" or raw.get("stay_type") == "owner_stay":
        return None
    zone = ZoneInfo(prop.timezone)
    platform = str(raw["platform"])
    start = normalize_time(raw["check_in"], zone, platform)
    end = normalize_time(raw["check_out"], zone, platform)
    if end.astimezone(UTC) <= start.astimezone(UTC):
        raise ValueError("Reservation checkout must follow checkin")
    guest: dict[str, Any] = {}
    if include_guest and isinstance(details := raw.get("guest"), dict):
        guest = {
            key: details[key]
            for key in ("first_name", "last_name", "email", "phone_numbers")
            if key in details
        }
    return Reservation(
        id=str(raw["id"]),
        property_id=prop.id,
        code=str(raw["platform_id"]),
        check_in=start,
        check_out=end,
        nights=int(raw["nights"]),
        platform=platform,
        guest_count=int(raw.get("guests", {}).get("total", 0)),
        guest=guest,
    )


def current_and_next(
    reservations: list[Reservation], now: datetime
) -> tuple[Reservation | None, Reservation | None]:
    """Use half-open intervals so back-to-back stays turn over correctly."""
    instant = now.astimezone(UTC)
    ordered = sorted(reservations, key=lambda item: item.check_in.astimezone(UTC))
    current = next(
        (
            r
            for r in ordered
            if r.check_in.astimezone(UTC) <= instant < r.check_out.astimezone(UTC)
        ),
        None,
    )
    upcoming = next((r for r in ordered if r.check_in.astimezone(UTC) > instant), None)
    return current, upcoming


def arriving(reservation: Reservation | None, now: datetime, hours: int) -> bool:
    """Return whether the next stay begins inside the configured lead time."""
    return reservation is not None and timedelta(0) < reservation.check_in.astimezone(
        UTC
    ) - now.astimezone(UTC) <= timedelta(hours=hours)
