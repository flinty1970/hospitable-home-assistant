"""Minimal asynchronous read-only Hospitable v2 client."""

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import API_URL


class ApiError(Exception):
    """A sanitized API error, never including response bodies or credentials."""


class AuthenticationError(ApiError):
    """Token invalid, expired, or missing the required read permission."""


class RetryLater(ApiError):
    """Requests suspended until the server-directed or exponential deadline."""


def retry_seconds(value: str | None, now: datetime) -> float:
    """Accept Retry-After seconds or an HTTP date."""
    if value is None:
        return 0
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(
                0, (parsedate_to_datetime(value).astimezone(UTC) - now).total_seconds()
            )
        except (ValueError, TypeError, OverflowError):
            return 0


class HospitableApi:
    """Serialize requests and back off without sleeping inside HA's event loop."""

    def __init__(self, session: ClientSession, token: str) -> None:
        self._session = session
        self._token = token
        self._lock = asyncio.Lock()
        self._not_before = 0.0
        self._failures = 0
        self._last_request = 0.0

    async def _get(self, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        async with self._lock:
            if time.monotonic() < self._not_before:
                raise RetryLater("API backoff active")
            # Conservative pacing; no numeric provider quota is documented here.
            await asyncio.sleep(max(0, 0.25 - (time.monotonic() - self._last_request)))
            self._last_request = time.monotonic()
            try:
                async with self._session.get(
                    API_URL + path,
                    params=params,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Accept": "application/json",
                    },
                    timeout=ClientTimeout(total=30),
                    allow_redirects=False,
                ) as response:
                    if response.status in (401, 403):
                        raise AuthenticationError("Check the token and Read permission")
                    if response.status == 429 or response.status >= 500:
                        self._failures += 1
                        delay = max(
                            60 * 2 ** min(self._failures - 1, 6),
                            retry_seconds(
                                response.headers.get("Retry-After"), datetime.now(UTC)
                            ),
                        )
                        self._not_before = time.monotonic() + delay
                        raise RetryLater("API temporarily unavailable")
                    if response.status != 200:
                        raise ApiError(f"Unexpected API HTTP status {response.status}")
                    payload = await response.json()
            except (ClientError, TimeoutError, ValueError) as err:
                self._failures += 1
                self._not_before = time.monotonic() + min(
                    3600, 60 * 2 ** min(self._failures - 1, 6)
                )
                raise ApiError("Unable to read API response") from err
            if not isinstance(payload, dict):
                raise ApiError("Invalid API response structure")
            self._failures = 0
            self._not_before = 0
            return payload

    async def _pages(
        self,
        path: str,
        params: list[tuple[str, str]],
        select: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = await self._get(
                path, [*params, ("page", str(page)), ("per_page", "100")]
            )
            rows = payload.get("data")
            meta = payload.get("meta")
            if not isinstance(rows, list) or not isinstance(meta, dict):
                raise ApiError("Missing pagination metadata")
            if not all(isinstance(row, dict) for row in rows):
                raise ApiError("Invalid resource data")
            result.extend(select(row) for row in rows)
            try:
                current, last = int(meta["current_page"]), int(meta["last_page"])
            except (KeyError, TypeError, ValueError) as err:
                raise ApiError("Invalid pagination metadata") from err
            if current != page or not 1 <= last <= 10000:
                raise ApiError("Inconsistent pagination metadata")
            if page >= last:
                return result
            page += 1

    async def properties(self) -> list[dict[str, Any]]:
        """Validate the token and return only property identifiers, names, zones."""
        return await self._pages(
            "/properties",
            [],
            lambda row: {k: row[k] for k in ("id", "name", "timezone")},
        )

    async def reservations(
        self,
        property_ids: list[str],
        start: str,
        end: str,
        include_guest: bool = False,
    ) -> list[dict[str, Any]]:
        """Read a bounded checkout window, all statuses (including cancellations)."""
        fields = (
            "id",
            "platform",
            "platform_id",
            "check_in",
            "check_out",
            "nights",
            "reservation_status",
            "guests",
            "stay_type",
        )

        def select(row: dict[str, Any]) -> dict[str, Any]:
            chosen = {k: row[k] for k in fields if k in row}
            chosen["reservation_status"] = {
                "current": {
                    "category": row.get("reservation_status", {})
                    .get("current", {})
                    .get("category")
                }
            }
            chosen["guests"] = {"total": row.get("guests", {}).get("total", 0)}
            if not isinstance(row.get("properties"), list) or not row["properties"]:
                raise ApiError("Reservation property relationship is missing")
            chosen["properties"] = [{"id": p["id"]} for p in row.get("properties", [])]
            if include_guest and isinstance(guest := row.get("guest"), dict):
                chosen["guest"] = {
                    k: guest[k]
                    for k in ("first_name", "last_name", "email", "phone_numbers")
                    if k in guest
                }
            return chosen

        params = [("properties[]", pid) for pid in property_ids]
        params.extend(
            [
                ("date_query", "checkout"),
                ("start_date", start),
                ("end_date", end),
                ("include", "properties,guest" if include_guest else "properties"),
            ]
        )
        return await self._pages("/reservations", params, select)
