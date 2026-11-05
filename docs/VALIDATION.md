# Validation

Documentation review: 5 November 2026. Local runtime: Home Assistant 2026.10.4,
Python 3.14.7. The declared minimum is HA 2026.10.0; this review did not run that
exact version. See [release and installation checks](RELEASE_CHECK.md).

## Existing checks

- All 59 pytest tests pass with external sockets disabled and mocked Hospitable HTTP.
- Real HA config/options/reauth flows and full platform setup/unload are exercised.
- Synthetic fixtures cover entity projection, cancellation, pending/owner stays,
  same-day turnover, back-to-back boundaries, privacy, timezone offsets, DST,
  pagination, backoff, credential boundaries and signed cloud dispatch.
- Webhook coverage includes invalid signatures, replay age, persistent
  deduplication, malformed payloads, local self-test and fallback.
- Blueprint expansion and automation examples validate against HA schemas.
- Ruff lint passes; format checking reports 28 files already formatted.
- Mypy passes for all 15 integration source files.

The restricted execution sandbox blocks asyncio self-pipe traffic; pytest ran
outside that sandbox while its fixtures still disabled external network sockets.

## Published release and workflow checks

The existing [v0.1.2 release](https://github.com/flinty1970/hospitable-home-assistant/releases/tag/v0.1.2)
points to tag commit `af3a77b8cc7e094d76bf05d2e2f6e03a143b65a8`.
[Workflow 42065395095](https://github.com/flinty1970/hospitable-home-assistant/actions/runs/42065395095)
passed tests, hassfest and HACS for that release code. The final documentation
commit also triggers these checks; its result is reported with the review handoff.

## Documentation and scope

Every README link was checked: four relative file targets exist, seven unique
web targets return HTTP 200, and the Rental Control features anchor exists.
The illustrative Nabu Casa URL placeholder is not a live link and was excluded.
The comparison uses Rental Control's own current README; no live interoperability
test was performed.

This review changes documentation only. Integration source, entities, options,
API calls, blueprint, manifests and version remain unchanged. No live account
field comparison, installation, restart or cloud-routing test was repeated.
Mocked tests do not establish real account field availability or cloud routing.
