# Generic OpenWithWidget tempui keyword (TODO 3b6de01) (COMPLETED)

## Summary

`OpenMarkdown`/`OpenImage` are each a one-keyword-per-widget special
case: a fixed target widget kind, a file-loading path baked into
`desk.shell.window.DeskWindow`'s own dispatch. Any *other* widget that
implements `set_file` (Sheet, TODO `5928ae6`) -- or, since TODO
`83427f4`, any `kind: "html"` widget via `self.getOpenedFile()` -- has
no tempui route to be placed with a file pre-loaded at all. Cites
`../FEEDBACK/FEEDBACK-DESK-sheet-widget-no-programmatic-open-2026-08-07-0302.md`
(suggestion 2). Depends on TODO `83427f4` (done).

## Approach

`OpenWithWidget<TAB>widget_id<TAB>path` -- tab-separated (a path may
contain spaces; matches `DefineWidget`'s own convention, not
`OpenMarkdown`/`OpenImage`'s simpler single-space-split shape, which
only ever needs one field). Dispatch mirrors the existing `custom:
<keyword>` pattern `detect_temp_ui_kind` already uses for
`DefineWidget`-defined widgets -- a dynamic suffix
(`open_with_widget:<widget_id>`) carrying the target widget id, rather
than a new fixed kind-to-widget-id mapping entry the way `OpenMarkdown`/
`OpenImage` each have. An unknown `widget_id` is a silent no-op
(`self._widgets.get(widget_id) is None`), the same tolerance every
other kind already has for a malformed/stale file.

The one real design wrinkle: `open_widget_content`'s own `path=`
handling (TODO `83427f4`) already covers *both* `kind: "python"`
(`set_file`) and `kind: "html"` (`_html_widget_opened_file`) uniformly
-- but the existing `_bind_temp_ui_content`/`_bind_temp_ui_widget`
machinery `OpenMarkdown`/`OpenImage`/etc. all share is Python-only by
construction (`_bind_temp_ui_widget`'s own hard `isinstance(frame
.content, PythonWidgetHost)` gate, `_bind_temp_ui_content` only ever
receiving a `PythonWidgetHost.current`). Two different call shapes,
handled accordingly:

- **Fresh placement** (`_activate_temp_ui`): for this one kind,
  resolves the target path directly and calls `open_widget_content(...,
  path=target)` itself, skipping `_bind_temp_ui_content` entirely --
  `path=` already does the right thing for either content type.
- **Restore** (`_bind_temp_ui_widget`): a `ChromiumWidget` instance
  needs its own new branch (there was none before -- restore used to
  just return immediately for non-Python content) that re-applies the
  target straight into `_html_widget_opened_file` (mirrors what a fresh
  html placement's `path=` does, since there's no Python method to call
  on restore either); a `PythonWidgetHost` instance falls through to the
  existing `_bind_temp_ui_content` path, which gains its own new
  `open_with_widget:` branch (`set_file`, matching `open_markdown`/
  `open_image`'s exact shape) so a *restored* python-kind instance's
  file gets re-applied the same way theirs already do.

## Affected files

- `src/desk/temp_ui.py` -- `OPEN_WITH_WIDGET_KEYWORD`,
  `RESERVED_TEMPUI_KEYWORDS`, `parse_open_with_widget`,
  `detect_temp_ui_kind`, new `_OPEN_WITH_WIDGET_DOC` split file +
  `SPLIT_DOC_CONTENT` entry, `DOC_TEMPLATE`'s own keyword bullet list,
  tag + `_NEW_FEATURES`.
- `src/desk/shell/window.py` -- `_temp_ui_widget_id_for`,
  `_notify_temp_ui`, `_activate_temp_ui`, `_bind_temp_ui_widget`,
  `_bind_temp_ui_content`, `_resolve_open_with_widget_target`.
- `tests/verify/verify_open_with_widget.py` -- new.

## Verification

Real `DeskWindow`/frames, no mocks: `detect_temp_ui_kind` returns
`open_with_widget:<id>` for a well-formed file and `question` for a
missing widget_id/path or an unknown keyword; `parse_open_with_widget`
round-trips widget_id+path, tolerates a path containing spaces (the
whole reason this is tab-, not space-, separated); a fresh placement
targeting a `kind: "python"` widget (Sheet) actually loads the file via
`set_file`; a fresh placement targeting a `kind: "html"`
(`DefineWidget`) widget records it in `_html_widget_opened_file`,
reachable via `get_opened_file_for_instance`; an unknown `widget_id` is
a silent no-op, not an error; restore re-applies the target for both
content kinds (a real Desk-reload-shaped restore call, not just the
fresh-placement path); a relative path resolves against the current
Desk's own directory, an absolute one is used as-is (matching
`OpenMarkdown`/`OpenImage`'s own precedent). Doc/tag checks. Re-run
`verify_html_widget_opened_file.py`, `verify_sheet_widget_set_file.py`,
and any existing `tempui`/`OpenMarkdown`/`OpenImage`-related scripts for
regressions. Full `tests/verify/` sweep. No browser launch needed.

## Status

Implemented as planned, no deviations. The "one real design wrinkle"
called out up front (fresh placement vs. restore needing genuinely
different code shapes for a kind:"html" instance) held up exactly as
anticipated -- both paths, plus the Python-restore path through
`_bind_temp_ui_content`'s new branch, are covered directly.

Verified: the new `verify_open_with_widget.py` (26 checks, real
`DeskWindow`/`ChromiumWidget`/`PythonWidgetHost` instances, no mocks --
parsing/detection including the tab-separation-tolerates-spaces case and
the missing-field/unknown-keyword fallback to "question"; fresh
placement for both content kinds, a relative path resolved against the
current Desk's own directory, an unknown widget_id as a silent no-op, a
repeat click re-centering rather than replacing; restore re-applying the
target for both content kinds, and confirming an unrelated tempui kind's
own restore leaves a kind:"html" instance's opened file untouched; doc/
tag checks), run 3x for flakiness, `os._exit()` ending for the same
WebEngine-teardown-segfault reason established elsewhere. Full
`tests/verify/` sweep (164 scripts) passes. Browser launch not needed.

This was the last open TODO citing
`../FEEDBACK/FEEDBACK-DESK-sheet-widget-no-programmatic-open-2026-08-07-0302.md`
-- moved to `../FEEDBACK/implemented/`.
