# Project python widgets go `[STALE]` instead of auto-reloading (TODO f143ce4) (COMPLETED)

## Summary

Investigation of `../FEEDBACK/FEEDBACK-DESK-a-placed-instance-of-a-kind-python-project-widget-desk-widge-2026-11-20-1706.md`
showed a placed `kind: "python"` project widget (`desk_widgets/<name>/`) was already hot-reloaded in place on every save
(`PythonWidgetHost` listens to `HotReloadBroker.widget_changed`) -- silently, discarding the instance's in-memory state,
and with no hash, so no `[STALE]`. This item gives project python widgets the promoted-widget experience instead: detect
by content hash, show `[STALE]`, rebuild only on the user's click; and disconnects the auto-reload for them.

## Affected files

- `src/desk/widgets.py`: `project_widget_content_hash(widget_dir)`.
- `src/desk/shell/python_widget.py`: `auto_reload` keyword (default `True`), public `rebuild()`.
- `src/desk/shell/window.py`: project hosts built with `auto_reload=False`; `_load_project_widgets` stores the hash in
  `_custom_widget_content_hash` and refreshes `[STALE]`; restore adopts the current hash when none was saved;
  `[STALE]` click, "reload all stale" and `_reload_stale_frame` handle `PythonWidgetHost`.
- `src/desk/temp_ui.py` (doc wording), `src/desk/tempui_content/` changelog entry (breaking, `#937578`).
- `tests/verify/verify_project_python_widget_staleness.py` (new); `verify_project_python_widgets.py` fake updated.

## Approach

- Hash = sha256 over sorted relative path + bytes of every file in the widget directory, excluding `__pycache__`, `.pyc`
  and dot-entries; first 12 hex digits. Reusing `_custom_widget_content_hash`/`placed_content_hash` gives persistence
  across restarts and the existing `[STALE]` plumbing for free.
- `_load_project_widgets` already re-runs on every debounced `widget_changed`, so it is the one place the hash refreshes.
- A fresh placement takes the current hash (existing path); a restored instance saved before this change adopts the
  current source as its baseline.
- Accepting `[STALE]` calls `PythonWidgetHost.rebuild()` (same failure behaviour as a hot reload: keep the old widget,
  surface `[ERROR]`).
- Built-in widgets keep live reload. Docked (sidebar) project widgets also keep it: they have no titlebar to carry
  `[STALE]`.

## Not done / known limits

- Only the widget's own directory is hashed; an edit to a module it imports from elsewhere is neither detected nor
  reloaded (`sys.modules` caches it). Worth a follow-up.
- No `[RELOAD]` button for project python widgets.

## Verification

`verify_project_python_widget_staleness.py`. Headless only.
