# Promoted-widget staleness follows shared tsconfig files (TODO 8a65056) (COMPLETED)

## Summary

The feedback (explicitly unconfirmed -- the author read only the docs) asked whether editing a shared file a widget
lists in its `tsconfig.json` `"files"` (e.g. `desk_widgets/_shared/x.ts`) marks the dependent widgets `[STALE]`.
Checked the source: it does not. `PromotedWidgetSourceWatcher.watch` (TODO 4eb3d9e) watches only the widget's own
directory, while `build_from_source` compiles and concatenates the listed external files into the widget. So an edit to
shared code left every dependent widget silently running its pre-edit JS until the next registration (Desk start/switch).
Cites `../FEEDBACK/FEEDBACK-DESK-shared-widget-file-edits-may-not-mark-dependents-stale-2026-10-21-0038.md`.

## Affected files

- `src/desk/custom_widgets.py`: new `external_source_files(widget_dir)`.
- `src/desk/shell/promoted_widget_source_watcher.py`: watches those files too; re-arms on a `tsconfig.json` edit.
- `src/desk/temp_ui.py`: tag, changelog entry, "Authoring from real source" note (the "that directory itself" wording).
- `tests/verify/verify_shared_file_staleness.py` (new).

## Approach

- `external_source_files`: `tsconfig.json` `"files"` entries that resolve (lexically, `normpath`) outside the widget
  directory; best-effort like `source_watch_exclusions` (missing/malformed tsconfig, non-string entries -> fewer paths).
- The watcher keeps a *list* of handles per keyword: the existing recursive watch of the widget dir, plus one
  non-recursive watch per distinct parent directory of a shared file (watchdog can't watch a single file), with the
  callback filtered to the listed files only -- an unlisted sibling in `_shared/` does not mark anything stale.
  One shared file listed by several widgets marks all of them (each has its own subscription).
- A `tsconfig.json` edit re-arms the watch (calls `watch` again) when its debounce fires, so a newly listed shared
  file is followed without waiting for a re-registration. The re-arm flag is sticky across debounce restarts: a tsconfig
  save usually comes with other writes that restart the timer (found by the test -- the first version lost the flag).
- Scope: promoted (source-backed, `source="desk"`) widgets only, same as the existing watcher. A still-`.desk_temp`
  widget is made stale by its regenerated `DefineWidget` file, which is `build_widget.py`'s job, not a watch.

## Verification

`verify_shared_file_staleness.py` (13 checks, real file watching in a temp tree): external-entry resolution, a shared
edit marking every widget listing it and no other, unlisted sibling ignored, own-dir edits still work, tsconfig re-arm,
re-watch idempotence, `stop_watching`/`stop_all`. `verify_promoted_widget_source_staleness.py` still passes (35).

## Status

Implemented; headless-verified. The `[STALE]` click -> rebuild path was untouched. Not exercised in the live app.
