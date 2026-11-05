"""Mocked HTTP tests enforce endpoint, pagination and credential boundaries."""

import asyncio
import re
from datetime import UTC, datetime

import pytest

from custom_components.hospitable_stays.api import (
    ApiError,
    AuthenticationError,
    HospitableApi,
    RetryLater,
    retry_seconds,
)


async def test_pagination_and_projection(property_data, aioclient_mock):
    responses = aioclient_mock
    responses.get(
        re.compile(
            r"https://public.api.hospitable.com/v2/properties.*[?&]page=1(?:&|$)"
        ),
        json={
            "data": [{**property_data, "discard_me": "not retained"}],
            "meta": {"current_page": 1, "last_page": 2},
        },
    )
    responses.get(
        re.compile(
            r"https://public.api.hospitable.com/v2/properties.*[?&]page=2(?:&|$)"
        ),
        json={
            "data": [{**property_data, "id": "fake-second"}],
            "meta": {"current_page": 2, "last_page": 2},
        },
    )
    async with responses.create_session(asyncio.get_running_loop()) as session:
        rows = await HospitableApi(session, "FAKE-TEST-TOKEN").properties()
    assert len(rows) == 2
    assert "discard_me" not in rows[0]


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_failure(status, aioclient_mock):
    responses = aioclient_mock
    responses.get(
        re.compile(r"https://public.api.hospitable.com/v2/properties.*"),
        status=status,
    )
    async with responses.create_session(asyncio.get_running_loop()) as session:
        with pytest.raises(AuthenticationError):
            await HospitableApi(session, "FAKE-TEST-TOKEN").properties()


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_backoff_blocks_further_requests(status, aioclient_mock):
    responses = aioclient_mock
    responses.get(
        re.compile(r"https://public.api.hospitable.com/v2/properties.*"),
        status=status,
        headers={"Retry-After": "900"},
    )
    async with responses.create_session(asyncio.get_running_loop()) as session:
        api = HospitableApi(session, "FAKE-TEST-TOKEN")
        for _ in range(2):
            with pytest.raises(RetryLater):
                await api.properties()
    assert responses.call_count == 1
    assert len(responses.mock_calls) == 1


async def test_redirect_not_followed(aioclient_mock):
    responses = aioclient_mock
    responses.get(
        re.compile(r"https://public.api.hospitable.com/v2/properties.*"),
        status=302,
        headers={"Location": "https://example.invalid"},
    )
    async with responses.create_session(asyncio.get_running_loop()) as session:
        with pytest.raises(ApiError):
            await HospitableApi(session, "FAKE-TEST-TOKEN").properties()


async def test_reservation_includes_and_dates(reservation_data, aioclient_mock):
    responses = aioclient_mock
    responses.get(
        re.compile(r"https://public.api.hospitable.com/v2/reservations.*"),
        json={
            "data": [{**reservation_data, "unrelated": "discard"}],
            "meta": {"current_page": 1, "last_page": 1},
        },
    )
    async with responses.create_session(asyncio.get_running_loop()) as session:
        rows = await HospitableApi(session, "FAKE-TEST-TOKEN").reservations(
            ["fake-property"], "2026-11-04", "2027-11-06"
        )
    url = responses.mock_calls[0][1]
    assert url.query["date_query"] == "checkout"
    assert url.query["include"] == "properties"
    assert url.query["start_date"] == "2026-11-04"
    assert "unrelated" not in rows[0]


def test_retry_after_http_date():
    assert (
        retry_seconds(
            "Thu, 05 Nov 2026 12:10:00 GMT", datetime(2026, 11, 5, 12, tzinfo=UTC)
        )
        == 600
    )
    assert retry_seconds("invalid", datetime.now(UTC)) == 0
