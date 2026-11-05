"""Cloud-only signed webhook hints; authenticated polling remains authoritative."""

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.aiohttp import MockRequest

from .cloud_helpers import cloud_active, cloud_connected, delete_hook, get_hook
from .const import CONF_CLOUDHOOK_URL, CONF_WEBHOOK_ID, CONF_WEBHOOK_SECRET, DOMAIN
from .coordinator import HospitableCoordinator

MAX_BODY = 262144
REPLAY_WINDOW = timedelta(hours=24)
MAX_DELIVERIES = 4096
ACTIONS = frozenset({"reservation.created", "reservation.changed"})


def host_secret(email: str) -> str:
    """Implement Hospitable's documented host secret, without altering case."""
    return base64.b64encode(email.strip().encode("utf-8")).decode("ascii")


def signature(body: bytes, secret: str) -> str:
    """Sign the exact bytes, with the base64 text as the HMAC key."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class WebhookManager:
    """Manage the webhook lifecycle and persistent bounded replay protection."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: HospitableCoordinator,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.last_received: datetime | None = None
        self.last_event: str | None = None
        self.last_test: datetime | None = None
        self._seen: dict[str, str] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}.webhooks", private=True
        )
        self._lock = asyncio.Lock()
        self._registered = False

    async def async_setup(self) -> None:
        """Register only when a previously enabled cloud hook exists."""
        if saved := await self._store.async_load():
            self._seen = saved.get("seen", {})
            self.last_received = dt_util.parse_datetime(
                saved.get("last_received") or ""
            )
            self.last_event = saved.get("last_event")
        if hook_id := self.entry.data.get(CONF_WEBHOOK_ID):
            webhook.async_register(
                self.hass,
                DOMAIN,
                "Hospitable Stays",
                hook_id,
                self.async_handle,
                allowed_methods=["POST"],
                local_only=False,
            )
            self._registered = True

    def unload(self) -> None:
        """Retain the cloud URL for reloads, but remove its local handler."""
        if self._registered:
            webhook.async_unregister(self.hass, self.entry.data[CONF_WEBHOOK_ID])
            self._registered = False

    async def async_enable(self, email: str) -> str:
        """Create a Nabu Casa hook only with an active connected subscription."""
        if not cloud_active(self.hass) or not cloud_connected(self.hass):
            raise HomeAssistantError("Home Assistant Cloud is unavailable")
        hook_id = self.entry.data.get(CONF_WEBHOOK_ID) or webhook.async_generate_id()
        url = await get_hook(self.hass, hook_id)
        # Persist immediately, so closing the options dialog does not orphan a hook.
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={
                **self.entry.data,
                CONF_WEBHOOK_ID: hook_id,
                CONF_WEBHOOK_SECRET: host_secret(email),
                CONF_CLOUDHOOK_URL: url,
            },
        )
        if not self._registered:
            webhook.async_register(
                self.hass,
                DOMAIN,
                "Hospitable Stays",
                hook_id,
                self.async_handle,
                allowed_methods=["POST"],
                local_only=False,
            )
            self._registered = True
        return url

    async def async_disable(self) -> None:
        """Delete the remote hook before discarding the local identifiers."""
        if hook_id := self.entry.data.get(CONF_WEBHOOK_ID):
            await delete_hook(self.hass, hook_id)
            self.unload()
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={
                    k: v
                    for k, v in self.entry.data.items()
                    if k
                    not in {CONF_WEBHOOK_ID, CONF_WEBHOOK_SECRET, CONF_CLOUDHOOK_URL}
                },
            )
        await self._store.async_remove()

    @property
    def fallback_active(self) -> bool:
        """Silence is a status heuristic, never used to turn polling off."""
        interval = self.coordinator.update_interval or timedelta(minutes=10)
        return (
            not self.entry.data.get(CONF_WEBHOOK_ID)
            or not cloud_active(self.hass)
            or not cloud_connected(self.hass)
            or self.last_received is None
            or dt_util.utcnow() - self.last_received
            > max(timedelta(minutes=30), interval * 3)
        )

    async def async_handle(
        self, hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response:
        """Reject direct HTTP and WebSocket calls: cloud relay or local test only."""
        if not isinstance(request, MockRequest) or request.mock_source not in {
            "cloud",
            f"{DOMAIN}_selftest",
        }:
            return web.Response(status=403)
        is_test = request.mock_source == f"{DOMAIN}_selftest"
        if not cloud_active(hass):
            return web.Response(status=403)
        stream = request.content
        body = bytearray()
        while chunk := await stream.read(min(65536, MAX_BODY + 1 - len(body))):
            body.extend(chunk)
            if len(body) > MAX_BODY:
                return web.Response(status=413)
        return await self.async_process(
            bytes(body), request.headers.get("Signature", ""), is_test=is_test
        )

    async def async_process(
        self, body: bytes, supplied_signature: str, *, is_test: bool = False
    ) -> web.Response:
        """Verify before parsing. Retain delivery metadata only, never raw data."""
        secret = self.entry.data.get(CONF_WEBHOOK_SECRET)
        if (
            not supplied_signature.isascii()
            or not secret
            or not hmac.compare_digest(signature(body, secret), supplied_signature)
        ):
            return web.Response(status=401)
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError
            delivery_id, action = payload["id"], payload["action"]
            if not isinstance(delivery_id, str) or not 1 <= len(delivery_id) <= 128:
                raise ValueError
            if action not in ACTIONS or not isinstance(payload["data"], (dict, list)):
                raise ValueError
            if not isinstance(payload["version"], str):
                raise ValueError
            created = datetime.fromisoformat(payload["created"])
            if created.tzinfo is None:
                raise ValueError
            created = created.astimezone(UTC)
        except (ValueError, KeyError, TypeError, RecursionError):
            return web.Response(status=400)
        now = dt_util.utcnow()
        if now - created > REPLAY_WINDOW or created - now > timedelta(minutes=5):
            return web.Response(status=400)
        async with self._lock:
            # Hash the opaque delivery ID as it is untrusted arbitrary input.
            key = hashlib.sha256(delivery_id.encode()).hexdigest()
            self._seen = {
                k: v
                for k, v in self._seen.items()
                if (stamp := dt_util.parse_datetime(v)) and now - stamp < REPLAY_WINDOW
            }
            if key in self._seen:
                return web.Response(status=200, text="duplicate")
            if len(self._seen) >= MAX_DELIVERIES:
                return web.Response(status=503)
            self._seen[key] = now.isoformat()
            if is_test:
                self.last_test = now
            else:
                self.last_received, self.last_event = now, action
            await self._store.async_save(
                {
                    "seen": self._seen,
                    "last_received": self.last_received.isoformat()
                    if self.last_received
                    else None,
                    "last_event": self.last_event,
                }
            )
        # Debounced by HA, obeys API backoff; no webhook data enters entity state.
        self.hass.async_create_task(self.coordinator.async_request_refresh())
        return web.Response(status=200, text="processed")

    async def async_test(self) -> bool:
        """Send a signed fake event through HA's registered local dispatcher."""
        if not self._registered:
            return False
        body = json.dumps(
            {
                "id": f"synthetic-test-{secrets.token_hex(16)}",
                "action": "reservation.changed",
                "created": dt_util.utcnow().isoformat(),
                "version": "2.0",
                "data": {},
            },
            separators=(",", ":"),
        ).encode()
        request = MockRequest(
            content=body,
            mock_source=f"{DOMAIN}_selftest",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Signature": signature(body, self.entry.data[CONF_WEBHOOK_SECRET]),
            },
        )
        response = await webhook.async_handle_webhook(
            self.hass, self.entry.data[CONF_WEBHOOK_ID], request
        )
        return response.status == 200 and response.text == "processed"
