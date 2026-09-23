# Sheet widget: set_file(path) + drag-and-drop (TODO 5928ae6) (COMPLETED)

## Summary

`SheetWidget` never implements `set_file` -- its `Open` button pops a
native `QFileDialog` directly, with no method any external caller (the
file-type-registry's `hasattr(widget, "set_file")` dispatch, drag-and
-drop) could call instead. Every other built-in viewer/editor
(Markdown, Image Viewer, Editor) already exposes `set_file`; Sheet is
the one exception, and it's a `kind: "python"` widget where nothing
else blocks the fix (contrast the `kind: "html"` gap TODO 83427f4 just
closed differently, since there's no Python method to call there at
all). Cites
`../FEEDBACK/FEEDBACK-DESK-sheet-widget-no-programmatic-open-2026-08-07-0302.md`
(suggestion 1; suggestion 2 -- a generic `OpenWithWidget` tempui
keyword -- is TODO `3b6de01`, next in the queue, not this one).

## Approach

1. `SheetWidget.set_file(path)` -- delegates to `_load_file`, the exact
   one-line convention `EditorWidget.set_file` already uses.
2. `_load_file` gains the same read-error guard `EditorWidget._load_file`
   already has (TODO 810a5d6) and `Sheet` currently lacks entirely:
   `path.read_text()` wrapped in try/except, a popup on failure (not an
   inline message -- Sheet, like Editor and unlike read-only Markdown/
   Image Viewer, is editable, so a fake "could not read" message
   embedded in the grid itself risks the user then hitting Save and
   overwriting the real file with it; Editor's own docstring gives this
   exact reasoning), state left untouched. Bringing Sheet up to its
   peers' own established robustness, not just adding the bare method
   -- it's about to be wired into the same dispatch surface they are.
3. `EXTERNAL_DROP_WIDGET_BY_SUFFIX` (`src/desk/shell/window.py`) gains
   `.tsv`/`.tab` -> `SHEET_WIDGET_ID`. Deliberately **not** `.txt`,
   despite `TSV_FILTER`'s own dialog filter listing it as browsable --
   `.txt` is generic plain text (already reasonably handled by the
   Editor fallback every other unmapped suffix gets), and mapping it to
   Sheet for *drag-and-drop* specifically would make dropping an
   ordinary text file open it as a mostly-empty one-row spreadsheet
   instead of readable text, a real UX regression for the far more
   common case. Not `.csv` either -- `Sheet.load_tsv`/`to_tsv` only
   ever split/join on a literal tab, so a comma-separated file wouldn't
   actually parse as a table; `TSV_FILTER`'s own glob agrees (`*.tsv
   *.tab *.txt`, no `.csv`).
4. No tempui changelog tag -- `set_file` is internal `kind: "python"`
   widget-to-widget plumbing (the file-type-registry dispatch, drag
   -and-drop), not part of the tempui DSL/Bridge API surface any of
   Markdown/Editor/Image Viewer's own `set_file` methods are documented
   there either.

## Affected files

- `widgets/sheet/widget.py`
- `src/desk/shell/window.py` -- `EXTERNAL_DROP_WIDGET_BY_SUFFIX`
- `tests/verify/verify_sheet_widget.py` (if it exists) or a new
  dedicated verify script.

## Verification

Real `SheetWidget`, no mocks: `set_file(path)` loads a real TSV file's
content into the table, matching `_open_file`'s own dialog-driven
result; a missing/unreadable path leaves the grid and `_current_path`
untouched and shows a popup (via a fake `current_context` popup opener,
matching `verify_segfault_fix.py`'s own established pattern for this
exact property on Editor), not a crash; `hasattr(SheetWidget(),
"set_file")` is `True` (the actual file-type-registry dispatch
precondition). `EXTERNAL_DROP_WIDGET_BY_SUFFIX` maps `.tsv`/`.tab` to
`SHEET_WIDGET_ID` and leaves `.txt`/`.csv` unmapped (regression: still
falls through to the Editor default). Full `tests/verify/` sweep. No
browser launch needed.

## Status

Implemented as planned, no deviations. Also brought `_load_file` up to
`EditorWidget._load_file`'s own read-error robustness (a popup, state
left untouched) -- Sheet had none at all before this, and it's about to
be reached from paths (the file-type-registry dispatch, the new drop
mapping) with no other safety net around it.

Verified: the new `verify_sheet_widget_set_file.py` (15 checks -- real
`SheetWidget`, no mocks -- `hasattr(widget, "set_file")` is the actual
dispatch precondition; `set_file` produces byte-identical grid content
to the dialog-driven `_open_file` path for the same file; an unreadable
path shows a popup and leaves the grid/`_current_path` untouched, both
with and without a popup opener registered; the drop-suffix map has
`.tsv`/`.tab` but deliberately not `.txt`/`.csv`, with the two
pre-existing mappings unchanged), run 3x for flakiness. Full
`tests/verify/` sweep (163 scripts) passes. Browser launch not needed.

`../FEEDBACK/FEEDBACK-DESK-sheet-widget-no-programmatic-open-2026-08-07-0302.md`
stays in place -- its suggestion 2 (a generic `OpenWithWidget` tempui
keyword) is TODO `3b6de01`, still open and next in the queue.
