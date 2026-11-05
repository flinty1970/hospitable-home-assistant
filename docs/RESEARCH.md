# Contract review — 5 November 2026

## Decisions before implementation

Use domain `hospitable_stays`: no core integration or HACS default entry was found,
but [tykeal/homeassistant-hospitable](https://github.com/tykeal/homeassistant-hospitable)
already uses `custom_components/hospitable`. Another repository is
[peluke/hospitableIntegration](https://github.com/peluke/hospitableIntegration).
Default-list absence does not prove absence of all custom HACS repositories.

Implement polling, then optional Cloud hooks. Preserve `hospitable_guest_*` event names.
Booked occupancy is not physical occupancy. Exclude owner stays and non-accepted
reservations. Keep periodic polling even while push works. Quiet webhooks are not
proof of failure: there is no documented heartbeat.

## Hospitable contract and permissions

Primary sources inspected:

- [PAT guide](https://help.hospitable.com/en/articles/8609392-accessing-the-public-api-with-a-personal-access-token-pat): Apps (or Settings → Integrations) → API access → Access tokens → Add new; Read permission; account owner/admin and connected listing required. Essentials does not include API access. PATs expire after one year. Bearer Authorization header.
- [Introduction](https://developer.hospitable.com/docs/public-api-docs/d862b3ee512e6-introduction): HTTPS JSON, v2. Rate limits are endpoint-specific. No numeric limit is published on the property/reservation endpoints inspected; do not invent one. Honor 429 and Retry-After; serialize calls and back off on transient errors.
- [Properties](https://developer.hospitable.com/docs/public-api-docs/qc4x36uhxinx3-get-properties): GET `https://public.api.hospitable.com/v2/properties`. `page`, `per_page` (maximum 100).
- [Reservations](https://developer.hospitable.com/docs/public-api-docs/ih7nc1ovefrcs-get-reservations): GET `/reservations`, mandatory repeated `properties[]`; date_query `checkin`, `checkout`, `booked_at`; start_date/end_date; include; page/per_page ≤100. Without explicit dates results default to the next two weeks. Query checkout from yesterday through one year ahead, so long current stays are included. This is a documented bounded calendar, not unlimited history.
- [Pagination](https://developer.hospitable.com/docs/public-api-docs/dbc4b7ed7eb1b-pagination): `data`, `meta.current_page`, `meta.last_page`; never follow server-provided URLs with the bearer token.

Ordinary Read PATs can read properties, reservations and calendar information.
The exact **integration field allowlist** is:

| Resource | Fields read and retained |
|---|---|
| Property | `id`, `name`, `timezone` |
| Reservation | `id`, `platform`, `platform_id`, `check_in`, `check_out`, `nights`, `reservation_status.current.category`, `guests.total`, `stay_type`, `properties[].id` |
| Guest, opt-in only (`include=guest`) | `first_name`, `last_name`, `email`, `phone_numbers` |

The reservation schema also documents conversation IDs/languages, booking_date,
arrival_date, departure_date, last_message_at, deprecated status/status_history,
issue_alert, owner_stay, notes and site_id. These are not exposed by this integration.
Properties additionally document public_name, picture, address, listed, amenities,
description, summary, check-in/check-out defaults, currency, capacity, room_details,
house_rules, listings, tags, property_type, room_type, calendar_restricted and
parent_child. Optional relationships include user, listings, details, bookings,
owners. These are deliberately not retained. Field presence still depends on the
booking platform and account data; contact information can be absent or masked.

The API documents optional financials/financialsV2, listings, properties, review,
tasks, agreements, user and smartlock_code includes. Scope requirements differ;
PAT access is broad but does not guarantee populated data. We request only
`properties`, plus `guest` if enabled. No messaging, financial, lock or agreement
access is needed or promised. Never request `smartlock_code`, property details,
shortcodes or smart-device endpoints. Unrequested extra fields are discarded.

## Webhooks

[Host setup](https://help.hospitable.com/en/articles/10008203-webhooks-for-reservations-properties-messages-and-reviews): Apps → Webhooks under Tools → Webhooks tab → Add new; supply name/URL, choose Reservations, Save, Test. Newer navigation may call Apps “Integrations”. There is no documented host webhook-subscription API used here.

[Signing and envelope](https://developer.hospitable.com/docs/public-api-docs/webhooks-docs):
`Signature` is hexadecimal HMAC-SHA256 of the exact body bytes. Host secret is
base64 of the **primary user's email address**, not a new random signing secret.
Vendor secrets come from the partner portal. Do not present base64 as encryption
or the email-derived key as a strong random secret. Keep the hook URL secret too.
Envelope: id, action, data (object or array), created (UTC ISO8601), version;
reservation.changed includes triggers. Reservation actions: reservation.created,
reservation.changed. Property actions include created/changed/deleted/merged;
message.created and review.created exist but are not subscribed to here.
Retries: expect 200; five retries with delays 1s, 5s, 10s, 1h, 6h. Sender range
38.80.170.0/24; do not trust forwarded source IPs through a cloud relay.

Verify signature, validate envelope, reject deliveries over 24h old or more than
5 minutes in the future, deduplicate bounded delivery IDs for 24h, then request an
authenticated API refresh. Never use guest or lock contents in webhook data.
Replay state survives reloads through HA Store. The local signed self-test uses the
registered webhook dispatcher and a synthetic payload; it does not prove cloud
routing or Hospitable registration. Use Hospitable's Test button for end-to-end QA.

## Home Assistant sources reviewed

- [Config flows and reauth](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/)
- [Options flows](https://developers.home-assistant.io/docs/config_entries_options_flow_handler/)
- [DataUpdateCoordinator](https://developers.home-assistant.io/docs/integration_fetching_data/)
- [Calendar entities](https://developers.home-assistant.io/docs/core/entity/calendar/)
- [Diagnostics](https://developers.home-assistant.io/docs/core/integration/diagnostics/)
- [Repairs](https://developers.home-assistant.io/docs/core/platform/repairs/)
- [Webhook implementation](https://github.com/home-assistant/core/blob/dev/homeassistant/components/webhook/__init__.py)
- [Cloud helpers](https://github.com/home-assistant/core/blob/dev/homeassistant/components/cloud/__init__.py): async_active_subscription, async_get_or_create_cloudhook, async_delete_cloudhook.

Use ConfigEntry runtime_data, async platform forwarding, coordinator availability,
reauth via ConfigEntryAuthFailed, issue registry and reauth repairs. Cloud is an
after_dependency so polling remains available without Cloud setup; http/webhook
are dependencies. Standard options forms cannot supply an arbitrary clipboard
button: show the URL in a read-only selector and provide a local admin-only custom
sidebar panel with a Copy URL button. Status WebSocket handlers require admin
authorization independently of panel visibility.

API property timezone examples are fixed offsets, not guaranteed IANA names.
Require host confirmation of an IANA timezone per property. For Booking.com
(`platform=booking`) only, if the timestamp's non-Z offset disagrees with the IANA
zone at that local wall time, retain the wall time and attach the IANA zone.
UTC Z timestamps represent instants and are converted normally. No broad offset
rewrite for other platforms. Reject nonexistent local times; choose the matching
fold when an offset disambiguates DST, otherwise fold=0. This is a defensive
heuristic, not a vendor guarantee; check affected stays before enabling heating.

Signing documentation rechecked on 5 November 2026 using the rendered official
Webhooks → Signature section. It explicitly distinguishes host email-derived
secrets from vendor secrets managed in the Partner Portal and specifies HMAC-SHA256.
