# kind:"html" widget learns which file it was opened for (TODO 83427f4) (COMPLETED)

## Summary

The file type registry's view/edit-handler open flow (`DeskWindow
.open_editor_or_scrap`/`open_git_diff`, `widgets/project_files/widget.py`'s
`_open_file`) all gate on `hasattr(widget, "set_file")` -- a plain
Python method that only exists on a handful of built-in `kind:"python"`
viewers' content objects. A `kind:"html"` (`DefineWidget`/promoted)
widget registered as a file type's handler gets placed correctly but is
never told which file to load -- it opens empty, with no error and no
Bridge API equivalent to ask for the same information. Confirmed:
`find_view_handler`'s exactly two call sites (plus `open_git_diff`) all
funnel through the identical `hasattr` gate. Cites
`../FEEDBACK/FEEDBACK-DESK-html-widget-view-handler-no-file-path-2026-08-06-2353.md`.

## Approach

A new `desk.self.getOpenedFile()` Bridge call (mirrors `getManifest`/
`getLocalStorage`'s shape -- self-scoped via `require_instance_id`, no
capability declaration needed), backed by a new per-instance dict on
`DeskWindow` (`_html_widget_opened_file`, same shape as
`_html_widget_local_storage`), rather than merging an `_openedFile` key
into the widget's persisted `getLocalStorage` state (the report's own
"either closes the gap" option) -- explicitly not chosen, since that
state gets written to the `.desk` file, and "which file was I opened
for" is a one-shot fact about placement, not something meaningful to
persist and restore across a reload days later (the file may have moved
or the registry entry may have changed by then).

Centralized in `open_widget_content`/`open_widget_content_centered`
(both gain an optional `path: Path | None = None` parameter) rather
than duplicated at each of the three call sites: when given, a
`kind:"python"` instance's `set_file(path)` is called (the existing
behavior, moved in from each caller, including the existing
broken-`set_file`-must-not-propagate safety wrap); a `kind:"html"`
instance instead gets `path` recorded in `_html_widget_opened_file`,
keyed by instance id. This also removes three duplicated hasattr/
try-except blocks at the call sites, which now just pass `path=path`.
`current_context`'s `centered_widget_opener` hook (used by
`ProjectFilesWidget._open_in_widget`) gains the same parameter.

## Affected files

- `src/desk/shell/window.py` -- `_html_widget_opened_file`,
  `open_widget_content`/`open_widget_content_centered`,
  `get_opened_file_for_instance`, `open_editor_or_scrap`/
  `open_git_diff` simplified, cleared alongside
  `_html_widget_local_storage` on Desk switch.
- `src/desk/shell/current_context.py` -- `centered_widget_opener`'s
  type hint/docstring.
- `widgets/project_files/widget.py` -- `_open_in_widget` simplified
  (dropped its own now-dead `logging` import/`logger`).
- `src/desk/server/app.py` -- `GET /api/bridge/self/getOpenedFile`.
- `src/desk/server/bridge_client.py` -- `self.getOpenedFile()`.
- `src/desk/temp_ui.py` -- Bridge API doc entry, tag, `_NEW_FEATURES`.
- `tests/verify/verify_html_widget_opened_file.py` -- new.

## Verification

Real `DeskWindow`/`ChromiumWidget`/`PythonWidgetHost` instances, no
mocks: `open_widget_content(..., path=...)` sets `_html_widget_opened_file`
for a placed `kind:"html"` instance and calls `set_file` for a
`kind:"python"` one (unchanged behavior, now centralized);
`get_opened_file_for_instance` returns `None` for an instance never
given a path; a broken `set_file()` is caught, not propagated (the
existing safety property, now exercised through the shared path);
omitting `path` entirely reproduces every existing caller's behavior
unchanged (regression -- README seeding, drag-and-drop, tempui binding,
none of which pass it). `open_editor_or_scrap`/`open_git_diff`
end-to-end with an html widget registered as the handler. Doc/tag
checks. Re-run `verify_file_explorer_fallback_chain.py` and any other
script touching `open_editor_or_scrap`/`open_git_diff`/`ProjectFilesWidget
._open_in_widget`. Full `tests/verify/` sweep. No browser launch
needed.

## Status

Implemented as planned. The centralization (moving set_file/getOpenedFile
handling into `open_widget_content` itself, rather than duplicating it at
each caller) had a real cost worth recording: four existing verify
scripts' fake stand-ins for `open_widget_content_centered`/the
`centered_widget_opener` hook had baked in the *old* division of labor
(the caller calls set_file itself) and needed updating to match the new
one (the caller passes `path=`, the callee handles it) --
`verify_file_explorer_fallback_chain.py`, `verify_viewer_widgets_edit_button.py`,
`verify_segfault_fix.py`, `verify_new_desk_flow.py` (the last for an
unrelated reason: a new `_html_widget_opened_file` dict now cleared
alongside `_html_widget_local_storage` on Desk switch, which its
`_OrderTrackingWindow` fake didn't have). Found and fixed via the full
sweep, not assumed -- exactly the kind of regression a centralizing
refactor risks, confirmed real rather than theoretical.

Verified: the new `verify_html_widget_opened_file.py` (14 checks, real
`ChromiumWidget`/`PythonWidgetHost` instances via real widget.py files on
disk, no fake content swapped in post-placement -- a kind:"html" instance
records its opened file, `get_opened_file_for_instance` returns `None`
for an unknown/never-opened instance, a kind:"python" instance still gets
`set_file` called exactly as before this TODO, a broken `set_file()`
doesn't propagate, a widget with no `set_file` at all is a harmless
no-op, omitting `path` entirely reproduces every existing caller
unchanged, doc/tag checks), run 3x for flakiness, `os._exit()` ending
for the same WebEngine-teardown-segfault reason
`verify_relocate_promoted_widget_source.py` already established.
Re-ran and fixed the four scripts above, plus a clean pass of
`verify_bridge_api_editor_or_scrap.py`, `verify_git_diff_widget.py`,
`verify_rename_project_files.py`, `verify_double_click_empty_canvas_scratch.py`,
`verify_new_scratch_button.py`, `verify_stale_build_widget_script_fix.py`.
Full `tests/verify/` sweep (162 scripts) passes. Browser launch not
needed.

This was the only TODO citing
`../FEEDBACK/FEEDBACK-DESK-html-widget-view-handler-no-file-path-2026-08-06-2353.md`
-- moved to `../FEEDBACK/implemented/`.
