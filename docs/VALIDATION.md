# Validation

Local runtime: Home Assistant 2026.10.4, Python 3.14.7, matching US Home Assistant
2026.10.4. Source is Python 3.12-compatible; HA itself requires its bundled Python.

- 55 pytest tests pass with external sockets disabled and mocked Hospitable HTTP.
- Real HA config/options/reauth flows and full platform setup/unload exercised.
- One property device and five entity states checked under an accepted synthetic stay.
- Cancellation/pending/owner stays, same-day turnover, back-to-back boundaries,
  privacy projection, timezone offsets, DST folds/gaps, pagination, 429/5xx backoff,
  credential boundaries, signed cloud dispatch, invalid signatures, replay age,
  duplicate delivery persistence, malformed payloads, local self-test and fallback.
- Blueprint expansion and both automation examples validate against HA schemas.
- Ruff lint/format and mypy checks pass for the integration source.

The restricted execution sandbox blocks asyncio self-pipe traffic; tests therefore
ran outside that sandbox while pytest still disabled external network sockets.

GitHub hassfest/HACS validation and live US HACS installation are checked separately
below. Mocked tests do not establish real account field availability or cloud routing.
Live comparison must use the selected property's real timezone and confirm upcoming
and current stay data, counts, platform, codes and the calendar. Guest contacts stay
disabled unless explicitly requested. No heating or turn-off automation is installed
as part of data validation.

The first GitHub test job passed. Initial hassfest/HACS failures identified a
Repairs translation schema conflict and missing repository topics; both were
corrected. Added an admin-only sidebar panel with Copy URL and local self-test
buttons, plus authorization and Cloud gating tests. Final workflow results and
live installation status are recorded after publication.

## Published release and HACS installation

- Release: [v0.1.0](https://github.com/flinty1970/hospitable-home-assistant/releases/tag/v0.1.0).
- [Workflow 42060472602](https://github.com/flinty1970/hospitable-home-assistant/actions/runs/42060472602): **tests, hassfest and HACS all passed** for release code `1feabec`.
- US HA's HACS registered the custom repository and successfully installed
  **v0.1.0**, with installed and available versions matching.
- Home Assistant restart scheduled through its supported restart tool.
- Live account field comparison remains pending host setup: enter the PAT directly
  in HA, select properties, confirm IANA timezones, then compare entity attributes
  and calendar events with Hospitable. No PAT was requested through chat.
- No climate, light, switch or lock automation was installed or run by this test.
