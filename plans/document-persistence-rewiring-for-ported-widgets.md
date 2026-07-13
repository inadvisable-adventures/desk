# Document that porting a widget requires re-wiring its persistence to the Bridge API (COMPLETED)

TODO `411d0e0`, from a `DESK_FEEDBACK-2026-07-13T012144.md`
(TODO `4ab5875`) tempui-widget-feature suggestion.

## Summary

`hex_flower`'s own state layer was ported verbatim from `hexsheet`'s
`RegisterSignalSender`/`RegisterDatastore` custom-event protocol,
expecting a "sheet" parent controller that doesn't exist in Desk --
those events are simply never handled, so the widget's persistence
silently does nothing once its (separate) blank-page bug is fixed.
Nothing in either place that documents `self.getLocalStorage`/
`setLocalStorage` currently warns that porting a widget doesn't carry
its old persistence mechanism along for free -- it has to be
explicitly re-wired to those two calls.

## Fix

Added a short paragraph making this explicit, in both places an agent
building or porting a `kind: "html"` widget's persistence would
actually read:

- `src/desk/temp_ui.py`'s `_CUSTOM_WIDGETS_DOC` (rendered as
  `tempui-custom-widgets.md`, one of the docs Desk provides in
  `.desk_temp` to an agent building a `DefineWidget` custom widget) --
  appended right after the `setLocalStorage` bullet, since that's
  exactly where an agent deciding how to persist state would be
  reading.
- `design-docs/architecture.md`'s Bridge API section (read by a
  contributor working directly in the Desk repo under `widgets/`,
  which is how `hex_flower` itself was actually built, per the
  TODO `4ab5875` investigation).

Bumped `TEMPUI_DOC_VERSION` (3 -> 4) since the split doc content
changed.

## Affected files

- `src/desk/temp_ui.py` -- `_CUSTOM_WIDGETS_DOC` text, `TEMPUI_DOC_VERSION`.
- `design-docs/architecture.md` -- Bridge API section.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`): extended
`verify_tempui_doc_versioning.py`-style checks confirming
`_CUSTOM_WIDGETS_DOC`/the rendered `tempui-custom-widgets.md` contains
the new re-wiring guidance and `TEMPUI_DOC_VERSION` is `4`; re-ran the
full existing scratchpad regression suite (same pre-existing,
unrelated failures as every prior TODO this session, none touching
the files edited here).

## Status

Implemented. No `LEARNINGS.md` entry -- a documentation addition
following an already-identified gap, not a new surprising discovery.
