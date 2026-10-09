# Promoted widget rebuild re-syncs `widget.json` (TODO `8bbc484`) (COMPLETED)

Cites `../FEEDBACK/FEEDBACK-DESK-hmsvc-discovery-friction-and-promoted-widget-capabilities-2026-10-09-1351.md`
(finding 2).

## Summary

A promoted widget's `capabilities`/`state_schema` live in the `.desk`
file's `custom_widgets[]` entry, written at promotion and never re-read, so
the documented "edit `desk_widgets/<name>/` and save" workflow reloaded
cleanly and then 403'd. The `[STALE]` rebuild now re-reads `widget.json`.

## Affected files

- `src/desk/custom_widgets.py` -- `read_source_manifest`.
- `src/desk/shell/window.py` -- `_rebuild_promoted_widget` (used by both
  `_on_promoted_widget_stale_clicked` and `reload_all_stale_widgets`),
  `_sync_definition_from_manifest`, `_confirm_added_capabilities`,
  `_notify_widget_manifest_synced`.
- `src/desk/temp_ui.py` -- docs + changelog tag.
- `tests/verify/verify_promoted_widget_manifest_sync.py`.

## Design decisions

- The definition is mutated in place; it is the same object the saved Desk
  holds in `custom_widgets`, so the next save persists it.
- Added capability -> confirmation dialog (decided with the user); declining
  keeps the old list but still applies removals and `state_schema`.
- Malformed/missing `widget.json` -> keep stored values (a half-written
  file mid-edit must never strip capabilities).
- Notification whenever anything changed.

## Verification

Headless script (22 checks); existing stale/staleness scripts still pass.
Real-dialog/browser run skipped.
