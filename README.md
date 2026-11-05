# Hospitable Stays for Home Assistant

Read-only reservation sensors and calendars for occupancy-based heating, lighting,
cleaning reminders and other Home Assistant automations. Works with any supported
`climate` entity; no thermostat brand dependency.

**Push updates require Home Assistant Cloud. Without it, the integration polls.**

Domain: `hospitable_stays`, to avoid the existing third-party `hospitable` domain.
This is an independent community integration, not an official Hospitable product.

## Install through HACS

Requires Home Assistant **2026.10.0+**, HACS and a Hospitable account with API access.
The integration source uses Python 3.12-compatible syntax; current HA runs Python 3.14.

1. HACS → menu → Custom repositories.
2. Add `https://github.com/flinty1970/hospitable-home-assistant`, category **Integration**.
3. Find **Hospitable Stays**, download the release, and restart Home Assistant.
4. Settings → Devices & services → Add integration → **Hospitable Stays**.
5. Enter a read-only PAT, select one or more properties and confirm each property's
   **IANA timezone** (for example `America/New_York`). This is the property's
   timezone, which can differ from Home Assistant's or your browser's.

The repository must be published before HACS can download it. It is a custom
repository; inclusion in the HACS default catalogue is a separate process.

## Create a Personal Access Token

In Hospitable go to Apps (or Settings → Integrations) → API access → Access tokens
→ **+ Add new**. Name it “My Home Assistant” and grant **Read** only. Paste it
into your own Home Assistant; do not share it with this project's maintainers.
PAT creation requires an account owner/full-access admin and a connected listing.
Essentials does not include API access. PATs expire after a year.

## Entities (one device per selected property)

| Entity | State / attributes |
|---|---|
| Reservation status sensor | `none`, `checked_in`, `upcoming`; current stay, or next when empty |
| Next reservation sensor | Next reservation code, or `none`; `hours_until_check_in` |
| Occupied binary sensor | On during an accepted guest stay; check-in inclusive, checkout exclusive |
| Arrival within threshold binary sensor | Next check-in within N hours (default 24; options 1–168) |
| Reservations calendar | Accepted guest stays, with property-local start/end times |

Reservation attributes: `check_in`, `check_out`, `nights`, `platform`, `guest_count`,
`reservation_code`. Sensors also identify `property_id` and `timezone`.
Guest counts and codes can be missing or inaccurate upstream. “Checked in” and
“occupied” mean **booked**, not a detected arrival or an occupied room.

Events: `hospitable_guest_arriving_soon`, `hospitable_guest_checked_in`,
`hospitable_guest_checked_out`. Payload: `property_id`, `property` (name),
`reservation_code`. Boundaries update every 30 seconds without network calls;
polling discovers changes at the selected interval (default 10 minutes).
Startup baselines current occupancy without inventing check-in/check-out events.
Upcoming-arrival notifications can re-fire after an integration reload; automations
that need exactly-once notifications should persist their last notified code.
Cancelled, pending/request, checkpoint, rejected and owner stays are excluded.
Cancellation does not manufacture a checkout event. Owner calendar blocks do not
indicate guest occupancy. Calendar event UIDs are reservation UUIDs.

The shared cache covers reservations with checkout from yesterday through 366 days
ahead in property-local dates, including long stays already in progress. The
calendar is read-only and bounded; it does not fetch arbitrary historic ranges.

## Privacy and permissions

Guest names and contact details are **off by default**. Timing and privacy options
can enable available `first_name`, `last_name`, `email`, `phone_numbers` attributes.
Platforms may omit or mask these fields. Home Assistant Recorder may retain them:
disabling the option stops future exposure but does not purge old history/backups.
Calendars and bus events never include guest contacts or names.

The integration calls only GET `/v2/properties` and GET `/v2/reservations`.
It retains property `id`, `name`, `timezone`, and reservation `id`, `platform`,
`platform_id`, `check_in`, `check_out`, `nights`,
`reservation_status.current.category`, `guests.total`, `stay_type`, `properties[].id`.
It requests `include=properties`; `guest` is added only when opted in.
Read PATs allow property, reservation and calendar access; additional relationships
and account features have their own scope/data restrictions. See the complete
[schema and permissions review](docs/RESEARCH.md) for documented fields and limits.

It never requests, inspects, stores or exposes smart-lock/door codes. It does not
request messaging, finances, property details, agreement contents or smart devices.
Unknown response fields are discarded. Diagnostic downloads contain counts/times,
with credentials, hook identifiers, property identities and reservation/guest data
redacted by omission. Credentials live in HA's private config-entry storage, which
is **not encrypted at rest**; protect your HA storage and backups.

## Optional Nabu Casa push updates

Settings → Devices & services → Hospitable Stays → Configure → **Webhooks**.
With no active subscription, only the polling-mode notice is shown.
With an active connected subscription:

1. Select **Enable push updates**, enter the **primary Hospitable account email**,
   and submit to create a Cloud hook. Use its exact spelling/case in Hospitable.
2. Open **Webhook status and URL**, and copy the private `https://hooks.nabu.casa/…`
   URL from the read-only field, or open **Hospitable Stays** in the sidebar and
   click **Copy URL**. The sidebar status panel is restricted to administrators.
3. In Hospitable: **Apps → Webhooks (under Tools) → Webhooks tab → + Add new**.
4. Give it a name, paste the URL, select **Reservations**, then **Save**.
5. Click **Test** in Hospitable; reopen HA's status screen to check receipt.

Hospitable signs the **exact raw body** with HMAC-SHA256 in the `Signature` header.
For hosts its secret is the primary user's email encoded in base64. This key is
email-derived, not random; base64 is not encryption. Anyone with the URL can post
to it, which is why signature verification matters. Protect both the URL and email.
No full webhook URL, body, token or signing key is logged by this integration.
Home Assistant's own webhook debug logging can include IDs: avoid enabling it or
sharing its raw logs. Invalid signatures, malformed envelopes and deliveries older
than 24 hours or over five minutes ahead are rejected. Duplicate delivery IDs are
persisted for 24 hours (bounded to 4096; excess receives 503).

Only the Nabu Casa cloud relay path is accepted. Direct HTTP and WebSocket webhook
calls are rejected. Payloads are refresh hints; entity state always comes from an
authenticated API poll. Polled data is shared across all entities and all pages
must succeed before a new snapshot is published. 429/5xx responses back off with
exponential delays and honor Retry-After. Webhook refreshes use the same throttle.
No numeric per-minute limit is claimed because these two endpoint docs do not
publish one. Requests are serialized and conservatively paced.

The status screen shows last received time/type, polling fallback and last poll.
Fallback is “active” before the first delivery, without cloud connectivity, or
once silence exceeds the greater of 30 minutes and three poll intervals. Silence
can be normal; there is no documented heartbeat. **Polling continues at the chosen
interval even when webhooks arrive**, so missing deliveries cannot stop updates.

**Send test event** submits a signed synthetic sample through the registered local
HA receiver. It confirms processing, not internet reachability or Hospitable setup.
It records a separate self-test timestamp and does not claim a cloud delivery.
Use Hospitable's **Test** button for the end-to-end check.

Disable push in options to delete the cloud hook, then remove the webhook in
Hospitable. If Cloud is unavailable, reconnect it before deleting the hook.
Polling still works during outages, account logout or subscription expiry.

Tunnels and your own domain may be considered in a later version.
Port forwarding, reverse proxies and external-URL setup are not supported here.

## Property timezone normalization

Confirm an IANA zone during setup because the API may return only a fixed offset.
For Booking.com (`platform=booking`) timestamps with a conflicting **non-Z** offset,
the local clock time is authoritative and gets the property's IANA zone. UTC `Z`
values are converted as instants, and other platforms keep their reported instant.
DST folds use the reported matching offset where possible, otherwise the first
fold. Nonexistent local times fail the refresh rather than silently moving a stay.
This is a defensive heuristic, not proof the upstream offset was wrong. Tests cover
summer/winter offsets, folds, DST gaps, back-to-back and same-day turnover.

## Automations

Import the [Occupancy-based heating blueprint](blueprints/automation/occupancy_heating.yaml).
Choose the property's Occupied and Next reservation entities and any climate entity.
Set comfort/empty temperatures in **the climate entity's temperature unit**, and
choose how many hours before arrival to preheat. Keep the thermostat in a mode
that accepts a single target temperature. The blueprint does not change HVAC mode.
Unknown/unavailable inputs preserve the existing setpoint; built-in frost protection
and the thermostat's own limits remain your responsibility.

[Two short examples](examples/automations.yaml): pre-arrival notification and a
post-checkout routine to turn off selected lights/switches. Replace example entity
IDs and the fake property ID before creating them in HA's automation UI.

## Troubleshooting

- **Invalid/expired token:** a Repairs issue and reauth flow ask for a new Read PAT.
  The replacement must still read all selected properties. Check IP restrictions
  on the token and whether your account plan includes API access.
- **Unavailable entities:** API failures, malformed data and rate limits mark the
  shared coordinator unavailable. Existing cached data is not treated as a fresh
  empty property. Retry after the backoff interval; don't repeatedly reload.
- **No upcoming bookings:** check confirmed status, property selection and the
  calendar window. Owner stays and iCal calendar blocks are not guest reservations.
- **Wrong times:** confirm property timezone and inspect Booking.com values. To
  change selected properties/zones in this initial version, remove and re-add the
  config entry; entity unique IDs remain based on property IDs.
- **No push:** ensure Cloud is active/connected, email matches the primary account,
  and the exact private URL and Reservations subscription are saved in Hospitable.
  The local test alone cannot validate that setup. Polling continues.
- **Diagnostics:** use the integration menu → Download diagnostics. Do not attach
  config-entry files, raw API responses, guest data or webhook URLs to issues.

## Development and validation

Use Python 3.14 for the pinned HA 2026.10.4 test runtime:

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy custom_components
```

Tests use synthetic fixtures and mocked HTTP with external sockets disabled.
GitHub Actions also run hassfest and HACS validation. See
[validation notes](docs/VALIDATION.md) for what has actually been verified, and
[research](docs/RESEARCH.md) for links to current official contracts.
