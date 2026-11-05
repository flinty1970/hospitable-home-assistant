Unofficial community integration for Hospitable. Not affiliated with or endorsed by Hospitable.

# Hospitable Stays for Home Assistant

Read-only reservation sensors and calendars for occupancy-based heating, lighting,
cleaning reminders and other Home Assistant automations. Works with any supported
`climate` entity; no thermostat brand dependency.

This integration works only with Hospitable accounts that have API access.

Early release (0.1.x): [feedback and bug reports welcome](https://github.com/flinty1970/hospitable-home-assistant/issues).

**Push updates require Home Assistant Cloud. Without it, the integration polls.**

Domain: `hospitable_stays`, to avoid the existing third-party `hospitable` domain.
This is an independent community integration, not an official Hospitable product.

## Which integration should I use?

**Hospitable Stays** is built on the Hospitable Public API and works only for
Hospitable hosts with API access. A read-only token connects the account. It
provides reservation status, booking platform, guest count and property-timezone
handling, with optional push updates through Home Assistant Cloud. It is read-only
and does not manage door codes.

[Rental Control](https://github.com/tykeal/homeassistant-rental-control) reads iCal
(ICS) calendar feeds over HTTPS. It can work with any provider offering a compatible
feed, including Airbnb, VRBO, Booking.com and Guesty. It polls the calendar and can
manage lock slots through Keymaster. Its documentation also describes using
its generated codes in custom lock automations without Keymaster.

| | Hospitable Stays | Rental Control |
|---|---|---|
| Data source | Hospitable Public API v2 | HTTPS iCal/ICS calendar feed |
| Supported platforms | Reservations available through a Hospitable account with API access | Providers that supply a compatible HTTPS calendar feed |
| Update method | Configurable polling (default 10 minutes), plus optional Nabu Casa webhooks; polling continues | Configurable calendar polling (documented default 2 minutes) |
| Door code management | None; does not request or expose lock codes | Optional Keymaster lock-slot management; generated codes are also available to custom automations |
| Setup | Read-only Hospitable PAT, property selection and property timezone; optional Cloud hook setup | Calendar name and ICS URL in HA's setup flow; optional Keymaster configuration |

Rental Control is the appropriate choice if you do not use Hospitable, or want
Home Assistant to manage door codes. Choose Hospitable Stays if you want a
Hospitable API connection for reservation-driven automations. The two can be
installed side by side for different roles. This comparison is based on this
project's [API review](docs/RESEARCH.md) and
[Rental Control's own documentation](https://github.com/tykeal/homeassistant-rental-control#features).
Calendar-feed fields depend on what each provider includes; this comparison does
not assume that Rental Control lacks reservation details or timezone support.

## Install through HACS

Requires Home Assistant **2026.10.0+**, HACS and a Hospitable account with API access.
The integration source uses Python 3.12-compatible syntax; current HA runs Python 3.14.

1. HACS → menu → Custom repositories.
2. Add `https://github.com/flinty1970/hospitable-home-assistant`, category **Integration**.
3. Find **Hospitable Stays**, download the release, and restart Home Assistant.
4. Settings → Devices & services → Add integration → **Hospitable Stays**.
5. Enter a read-only PAT, select one or more properties and choose each property's
   **IANA timezone** from the searchable menu (for example `America/New_York`). This is the property's
   timezone, which can differ from Home Assistant's or your browser's.

This is a custom repository; inclusion in the HACS default catalogue is a separate process.

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

## What do the options mean?

Open Settings → Devices & services → Hospitable Stays → Configure.

| Option | What it does | Starting setting |
|---|---|---|
| **Polling interval (minutes)** | How often HA asks Hospitable for reservation changes. A value of 10 means a new, changed or cancelled booking may take up to about 10 minutes to appear under normal conditions. Polling continues when push is enabled. API backoff/outages can extend this. Allowed range: 1–1440 minutes. | **10 minutes** |
| **Arrival threshold (hours)** | How far before the next check-in the Arrival within threshold binary sensor turns on and `hospitable_guest_arriving_soon` is fired. At 24 hours, a 16:00 check-in enters the window at 16:00 the previous day. It does not switch heating on by itself. Allowed range: 1–168 hours. | **24 hours** |
| **Expose guest names and contact details** | Adds available guest names, email and phone numbers to reservation-sensor attributes. Platforms may omit/mask them. They may then enter HA history, backups and dashboards. Turning this off stops future exposure but does not delete existing history. Occupancy and heating work without it. | **Off** |
| **Property timezones** | Searchable region/city menu for each property's own timezone. It controls booking calculations and offset correction, independently of the HA server's timezone. Numeric API offsets do not preselect HA's timezone. | For a UK property: **Europe/London (United Kingdom)** |
| **Webhooks → Enable push updates** | Optional faster updates for booking changes, delivered through Home Assistant Cloud. Requires an active Nabu Casa subscription and manual registration of the generated URL in Hospitable. Polling remains the fallback. | Optional; polling works on its own |
| **Primary Hospitable account email** | The account owner's email, used to verify Hospitable webhook signatures. It is not a guest email, notification recipient or HA login field. Hospitable derives host signing keys from this address; the integration stores the derived signing key. Enter it only when enabling push. | Exact primary Hospitable account email |
| **Webhook status and URL** | Shows the private URL, last received event, last successful poll and fallback status. The admin sidebar panel also has a Copy URL button. | Inspect after setup |
| **Send test event** | Sends a signed synthetic sample through the local receiver. It tests processing, not whether Hospitable can reach the Cloud URL. Use Hospitable's Test button for that. | Run when troubleshooting |
| **Disable push updates** | Deletes the Nabu Casa hook and leaves polling running. Also remove the corresponding webhook in Hospitable. | Use to return to polling only |

**The arrival threshold and heating blueprint's preheat hours are separate.** You
can receive an arrival reminder 24 hours ahead while starting heating only 4 hours
ahead. Both use the scheduled check-in time, not a detected physical arrival.
Changing options saves them and reloads this integration automatically; it does
not require a full Home Assistant restart.

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

## Example automations

These examples are documentation; installing the integration does not create or
enable them. Start with notifications so you can observe the timing before adding
controls. Booked occupancy is not physical presence: a guest may leave late.

For the YAML examples below, open Settings → Automations & scenes → Create
automation → Create new automation, then its menu → **Edit in YAML**. Paste one
complete example at a time. Replace every `example_*` entity with your own.
Copy the property's UUID from the `property_id` attribute on its Reservation status
sensor (Tools → States, or the entity's state attributes) and replace
`fake-property-replace-me`. The UUID is different from the property's name.

### 1. Pre-arrival reminder

Creates a notification inside HA when the next stay enters the arrival threshold.
It does not send a phone notification or guest message. To notify a phone instead,
replace the notification action with your own configured mobile-app notify action.

```yaml
alias: Hospitable pre-arrival reminder
triggers:
  - trigger: event
    event_type: hospitable_guest_arriving_soon
    event_data:
      property_id: "fake-property-replace-me"
actions:
  - action: persistent_notification.create
    data:
      title: Guest arrival approaching
      message: >-
        {{ trigger.event.data.property }}: reservation
        {{ trigger.event.data.reservation_code }} is arriving soon.
mode: single
```

The integration's **Arrival threshold** sets this reminder's lead time. An upcoming
arrival can be announced again after an integration reload; add persistent
last-notified-code tracking if your notification workflow needs exactly-once delivery.

### 2. Post-checkout lights and appliances off

Runs after the scheduled checkout. The occupancy condition prevents the routine
from switching things off when another booked stay has already begun. Choose only
devices that are appropriate to switch off automatically; keep essentials such as
refrigeration and network equipment out of the target list.

```yaml
alias: Hospitable post-checkout turn things off
triggers:
  - trigger: event
    event_type: hospitable_guest_checked_out
    event_data:
      property_id: "fake-property-replace-me"
conditions:
  - condition: state
    entity_id: binary_sensor.example_cottage_occupied
    state: "off"
actions:
  - action: light.turn_off
    target:
      entity_id: light.example_guest_lights
  - action: switch.turn_off
    target:
      entity_id: switch.example_guest_appliances
mode: single
```

A cancellation is not treated as checkout. Startup also does not replay checkout
events missed while HA was stopped. The entity condition uses the same property's
Occupied entity as the event's property UUID.

### 3. Cleaning reminder after checkout

Creates a reminder in HA, including on a same-day turnover. This is a reminder to
you; it does not contact a cleaner or change a Hospitable task.

```yaml
alias: Hospitable cleaning reminder
triggers:
  - trigger: event
    event_type: hospitable_guest_checked_out
    event_data:
      property_id: "fake-property-replace-me"
actions:
  - action: persistent_notification.create
    data:
      title: Cleaning due
      message: >-
        Scheduled checkout has passed at {{ trigger.event.data.property }}
        for reservation {{ trigger.event.data.reservation_code }}.
        Check departure and the next arrival before arranging access.
mode: single
```

### 4. Occupancy-based heating with preheating

Use the included [Occupancy-based heating blueprint](blueprints/automation/occupancy_heating.yaml).

1. Settings → Automations & scenes → Blueprints → Import blueprint.
2. Paste `https://github.com/flinty1970/hospitable-home-assistant/blob/main/blueprints/automation/occupancy_heating.yaml`.
3. Create an automation from it.
4. Choose the **Occupied** and **Next reservation** entities from the same property,
   then choose the climate entity you want to control.
5. Choose comfort and empty-property temperatures in **that climate entity's unit**.
   For example, on a Celsius thermostat you might choose 21°C and 16°C; choose
   suitable Fahrenheit values if the entity uses °F.
6. Set **Hours before arrival to return to comfort**, for example 4 hours.

The behavior is:

| Booking state | Target temperature |
|---|---|
| Accepted guest stay currently in progress | Comfort |
| Empty, with next arrival inside the blueprint's preheat window | Comfort |
| Empty, with no arrival inside that window | Empty-property setpoint |
| Booking inputs unknown/unavailable | Preserve the existing setpoint |

The blueprint works with a chosen climate entity rather than a thermostat brand.
Keep the thermostat in a mode that accepts a single target temperature: the
blueprint does not change HVAC mode. It reevaluates on booking/occupancy changes,
at HA startup and every five minutes. It will reapply its chosen setpoint on that
schedule while enabled; disable the automation when you want manual control.
Keep the thermostat's own frost protection and temperature limits enabled.

The [standalone example file](examples/automations.yaml) contains the first two
patterns as well. Guest names and contact details can stay **off** for all examples.

## Troubleshooting

- **Invalid/expired token:** a Repairs issue and reauth flow ask for a new Read PAT.
  The replacement must still read all selected properties. Check IP restrictions
  on the token and whether your account plan includes API access.
- **Unavailable entities:** API failures, malformed data and rate limits mark the
  shared coordinator unavailable. Existing cached data is not treated as a fresh
  empty property. Retry after the backoff interval; don't repeatedly reload.
- **No upcoming bookings:** check confirmed status, property selection and the
  calendar window. Owner stays and iCal calendar blocks are not guest reservations.
- **Wrong times:** confirm property timezone and inspect Booking.com values. Use Configure → Property timezones to correct a zone without re-entering
  your PAT. A UK property uses Europe/London even on a US Home Assistant instance.
  Changing selected properties still requires removing and re-adding the entry.
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
