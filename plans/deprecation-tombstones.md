# Deprecations by tombstone (TODO `df8138a`) (COMPLETED)

## Summary
Replace the warn-then-remove idea with tombstones: the old API name stays, with only a
report to Desk and an error that says what to use now and carries an agent command.

## Affected files
`src/desk/deprecations.py` (new), `src/desk/server/{app,bridge_client,runner}.py`,
`src/desk/{temp_ui,widgets,hmsvc}.py`, `src/desk/shell/window.py`,
`design-docs/{deprecation-process,architecture,isolation}.md`,
`deprecated-docs/` (README checklist, DEPR-001 status), `TODO.md`, ~12 verify scripts
migrated to per-instance credentials, new `verify_deprecations.py`.

## Decisions
- The registry carries `detector`/`rewriter` for the deferred scan and rewrite items;
  nothing runs them in this slice.
- Reporting is once per (deprecation, instance), listeners run outside the lock and a
  broken listener cannot break the tombstone.
- The identity of a report comes from the bound credential, except for DEPR-001 itself,
  where the claimed headers are all there is and are recorded for diagnosis only.
- A manifest tombstone is a `ValueError` subclass so loaders that already skip-and-log a
  bad manifest cope; for `service.json` the service is listed inert (message as
  description, no capabilities, no autostart) rather than dropped or run with defaults.
- A tempui tombstone is its own kind (`deprecated:<id>`), handled before the existing
  DefineWidget/notification flow, so it is never silently a Question.
- DEPR-001 conversion removes `allow_legacy_identity`, the env var and the warning; the
  shared token stays valid for routes that need no identity.
- Scan, rewriters and the UI handoff are separate TODOs (`284bfbd`, `cc78e9d`, `18fa45f`).

## Verification
`verify_deprecations.py` (registry, messages, python/manifest/tempui/JS-stub surfaces,
DeskWindow handling), the credentials test (DEPR-001 tombstone, report route), a real
Chromium end-to-end scenario for a Bridge JS tombstone, and the isolation test.
