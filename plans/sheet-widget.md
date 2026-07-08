# Sheet widget (basic TSV spreadsheet) (COMPLETED)

TODO `c758ddf`.

## Summary

"A 'sheet' widget which implements a basic spreadsheet (resizable rows
and columns, wordwrap or clip for overflow, all entries are
left-aligned and vertically centered) which serializes/saves as TSV
files." A new `kind: "python"` widget (`widgets/sheet/`) built on
`QTableWidget`, which provides all four requirements natively.

## Key decisions

- **`QTableWidget`** covers every stated requirement out of the box —
  no third-party spreadsheet dependency (per `CLAUDE.md`):
  - **Resizable rows/columns**: both headers'
    `setSectionResizeMode(Interactive)` (user-draggable section
    borders; this is already the default, set explicitly for clarity).
  - **Wordwrap or clip for overflow**: `setWordWrap(True)` — text wraps
    within the cell and is clipped beyond the row's height (cells never
    spill into neighbors). Rows are user-resizable to reveal more.
  - **Left-aligned + vertically centered entries**: every cell item's
    `textAlignment` is `Qt.AlignLeft | Qt.AlignVCenter`. Applied to
    pre-created cells directly, and — crucially — via
    `setItemPrototype(...)` so cells the user creates by typing into an
    empty cell (which `QTableWidget` clones from the prototype) inherit
    the alignment too (confirmed the clone preserves it).
- **File I/O: TSV**, via an editor/markdown-widget-style toolbar (Open /
  Save / Save As), with the dialogs seeded from the current Desk
  directory (`desk.shell.current_context`, falling back to home).
  - **Serialize**: join each row's cell texts with `\t`, rows with `\n`,
    trailing newline. Empty cells → empty strings.
  - **Parse**: `splitlines()`, split each line on `\t`; column count =
    the widest row (ragged rows are padded with empty cells).
  - New/empty sheet: a default empty grid (e.g. 12 rows × 6 cols) so
    it's usable immediately; loading a file resizes to fit it.
- **Row/column editing**: Add Row, Add Column, and Delete Row / Delete
  Column (operating on the current selection) buttons — the minimum to
  be an actual editable sheet rather than a fixed grid.
- **No cross-reload persistence of the open file** (same as the editor
  and markdown widgets — the widget contract has no per-instance state
  payload; already parked in `PARKINGLOT.md`). A dirty-marker in the
  filename label (like the editor's `•`) indicates unsaved edits.

## New/affected files

- `widgets/sheet/widget.json` (new) — `{name: "Sheet", kind: "python",
  entry: "widget.py", capabilities: [], default_size: 640x480}`.
- `widgets/sheet/widget.py` (new) — `SheetWidget(QWidget)`:
  - A `QTableWidget` configured as above (word wrap, interactive
    resize, item prototype with the alignment).
  - Toolbar: `Open`, `Save`, `Save As`, `Add Row`, `Add Column`,
    `Delete Row`, `Delete Column`, a stretch, and a filename/dirty
    label.
  - `_load_file`/`_save_file`/`_save_file_as`/`_open_file` (TSV
    round-trip, dialogs seeded from `_last_dir`), `_new_item()`
    (an empty `QTableWidgetItem` with the alignment, used when building
    grids), add/delete row/column handlers, `_mark_dirty`/`_update_label`
    (via `QTableWidget.itemChanged`), `build() -> SheetWidget()`.
- `design-docs/architecture.md` — new Sheet Widget component entry.

## Verification

Headless, against real temp TSV files:
- Round-trip: build a sheet, set some cells (including an empty one and
  one with a tab-free multiword string), `_save_file` to a temp path,
  read the file back and assert exact TSV (`\t`-joined columns,
  `\n`-joined rows); then `_load_file` a hand-written TSV (including a
  ragged row) and assert the table's dimensions and cell texts, with
  short rows padded.
- Alignment: every populated cell item — and a cell created via the
  item prototype (simulating a user-typed cell) — reports
  `Qt.AlignLeft | Qt.AlignVCenter`.
- Config: `wordWrap()` is True; both headers are in Interactive resize
  mode.
- Add/Delete row/column change the table dimensions as expected and
  preserve surrounding cell contents.
- Dirty marker: editing a cell sets the unsaved marker; saving clears
  it.
- A full-app `DeskWindow` regression: place a real `sheet` widget and
  round-trip a file through it.

## Status

**Completed.** Implemented and verified headlessly as described above:
config (word wrap, interactive resize), alignment (pre-filled cells +
prototype-cloned user cells), TSV save round-trip, ragged-file load with
padding, add/delete row & column, and the dirty marker; plus a full-app
`DeskWindow` placement + TSV round-trip. `design-docs/architecture.md`
gained a Sheet Widget entry.
