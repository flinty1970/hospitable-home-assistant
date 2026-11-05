"""Synthetic fixtures only. No live account data or credentials."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable_stays.const import DOMAIN


@pytest.fixture(autouse=True)
def custom_integration(enable_custom_integrations):
    yield


@pytest.fixture
def property_data():
    return {
        "id": "fake-property",
        "name": "Example Cottage",
        "timezone": "America/New_York",
    }


@pytest.fixture
def reservation_data():
    return {
        "id": "fake-reservation",
        "platform": "airbnb",
        "platform_id": "FAKE-BOOKING",
        "check_in": "2026-11-05T15:00:00-05:00",
        "check_out": "2026-11-07T11:00:00-05:00",
        "nights": 2,
        "reservation_status": {"current": {"category": "accepted"}},
        "guests": {"total": 2},
        "stay_type": "guest_stay",
        "properties": [{"id": "fake-property"}],
    }


@pytest.fixture
def entry(property_data):
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "access_token": "FAKE-TEST-TOKEN-NOT-A-CREDENTIAL",
            "properties": [property_data],
        },
    )
