"""Reservation and timezone edge cases."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.hospitable_stays.models import (
    Property,
    arriving,
    current_and_next,
    normalize_time,
    parse_reservation,
)


@pytest.mark.parametrize(
    "category",
    ["cancelled", "request", "checkpoint", "not_accepted", "pending", "unknown"],
)
def test_non_confirmed_excluded(reservation_data, property_data, category):
    reservation_data["reservation_status"]["current"]["category"] = category
    assert parse_reservation(reservation_data, Property(**property_data), False) is None


def test_owner_stay_excluded(reservation_data, property_data):
    reservation_data["stay_type"] = "owner_stay"
    assert parse_reservation(reservation_data, Property(**property_data), False) is None


def test_back_to_back_and_same_day_turnover(reservation_data, property_data):
    prop = Property(**property_data)
    first = parse_reservation(reservation_data, prop, False)
    second_data = {
        **reservation_data,
        "id": "fake-second",
        "check_in": reservation_data["check_out"],
        "check_out": "2026-11-09T11:00:00-05:00",
    }
    second = parse_reservation(second_data, prop, False)
    assert current_and_next([first, second], datetime(2026, 11, 7, 16, tzinfo=UTC)) == (
        second,
        None,
    )
    second_data["check_in"] = "2026-11-07T15:00:00-05:00"
    second = parse_reservation(second_data, prop, False)
    assert current_and_next([first, second], datetime(2026, 11, 7, 17, tzinfo=UTC)) == (
        None,
        second,
    )
    assert arriving(second, datetime(2026, 11, 6, 20, tzinfo=UTC), 24)
    assert not arriving(second, second.check_in, 24)


def test_privacy_allowlist(reservation_data, property_data):
    reservation_data["guest"] = {
        "first_name": "Synthetic",
        "last_name": "Guest",
        "email": "guest@example.invalid",
        "phone_numbers": [],
        "other": "discard",
    }
    private = parse_reservation(reservation_data, Property(**property_data), False)
    assert private.guest == {}
    opted_in = parse_reservation(reservation_data, Property(**property_data), True)
    assert "other" not in opted_in.guest
    assert "email" not in opted_in.attributes(False)
    assert opted_in.attributes(True)["email"] == "guest@example.invalid"


@pytest.mark.parametrize(
    ("value", "platform", "expected_hour"),
    [
        ("2026-07-01T15:00:00-05:00", "booking", 15),
        ("2026-07-01T15:00:00-05:00", "airbnb", 16),
        ("2026-07-01T15:00:00Z", "booking", 11),
        ("2026-07-01T15:00:00-04:00", "booking", 15),
    ],
)
def test_offset_repair(value, platform, expected_hour):
    result = normalize_time(value, ZoneInfo("America/New_York"), platform)
    assert result.hour == expected_hour
    assert result.utcoffset().total_seconds() == -14400


def test_dst_folds_and_nonexistent_time():
    zone = ZoneInfo("America/New_York")
    assert normalize_time("2026-11-01T01:30:00-05:00", zone, "booking").fold == 1
    with pytest.raises(ValueError, match="Nonexistent"):
        normalize_time("2026-03-08T02:30:00", zone, "booking")
