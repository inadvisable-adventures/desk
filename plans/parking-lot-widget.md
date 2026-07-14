# New widget: Parking Lot (COMPLETED)

TODO `a48e968`.

## Summary

A new "Parking Lot" widget that reads the nearest `PARKINGLOT.md` and
displays each item's title in a scrollable list. Each row has a
"Discuss" button on its right; double-clicking a row's title instead
opens just that one item in a Markdown widget, via the tempui
mechanism. Mirrors `widgets/questions/` and `widgets/todo/` in overall
shape (file watching, external-path indicator), adapted for
`PARKINGLOT.md`'s own structure and read-only nature (this widget
never edits `PARKINGLOT.md` itself).

## Design

### 1. `src/desk/parking_lot_file.py` (new)

A parser for `PARKINGLOT.md`, mirroring `desk.questions_file`'s shape
(dataclass + regex-based parser), adapted for `PARKINGLOT.md`'s actual
structure: each item is a top-level `- **<title>**` bullet (the title
itself can wrap across multiple source lines for long titles, e.g. the
existing `WidgetSpawnMenu._activate_item` entry), followed by
free-form body prose up to the next top-level bullet or EOF.

```python
@dataclass
class ParkingLotEntry:
    title: str        # collapsed to one line (wrapped titles joined with spaces)
    line_number: int  # 1-indexed line, in the file just read, where this item's "- **Title**" bullet starts
    raw_text: str      # this item's own text, heading bullet through body, trailing whitespace trimmed

def find_nearest_parking_lot_file(start_dir: Path) -> Path | None: ...
def parse_parking_lot_file(path: Path) -> tuple[str, list[ParkingLotEntry]]: ...
```

`line_number` uses the exact same definition already established by
the tempui `DiscussParkingLotItem` keyword's own doc (TODO 624ff3a):
"the line number ... where the item ... starts (its leading
`- **Title**` bullet)" — so an entry's `line_number` is always safe to
hand to `_place_discuss_claude_widget`'s existing `parking_lot_line`
parameter without any new convention to keep in sync.

No render/write-back function is needed (unlike `questions_file.py`'s
`render_questions_file`) — this widget only ever reads `PARKINGLOT.md`,
never rewrites it.

### 2. `widgets/parking_lot/` (new widget)

`widget.json`:

```json
{
  "name": "Parking Lot",
  "kind": "python",
  "entry": "widget.py",
  "capabilities": [],
  "default_size": { "width": 560, "height": 600 }
}
```

`widget.py`, modeled on `widgets/questions/widget.py`'s overall shape
(a plain-dict `_state`, `SingleFileWatcher` for live external-edit
reload, `external_path_changed` signal, status/timestamp labels) but
simpler: read-only, no dialogs, no git-commit-backed writes.

- `QListWidget` of items, one row per `ParkingLotEntry`, each row using
  `setItemWidget` with a small `QWidget` containing a `QLabel` (title,
  stretched, non-selectable per this project's UI-label convention)
  and a fixed-width `QPushButton("Discuss")` on the right — a literal
  "column" of Discuss buttons down the right edge, per the request
  (distinct from the Questions widget's single floating hover button,
  which doesn't fit "a button in a column on the right").
- `itemDoubleClicked` (fires from clicks landing on the row's own
  label area, which doesn't grab the mouse, same as a plain
  `QListWidgetItem`'s default text would) opens just that item:
  builds a `Markdown <title>\n<raw_text>` tempui file (the format
  already defined by `parse_markdown_tempui` /
  `_MARKDOWN_KEYWORD`) and writes it to a new UUID-named file under
  `<current desk directory>/.desk_temp/`, creating that directory
  first if it doesn't exist yet. This reuses the *existing* `Markdown`
  tempui keyword and Desk's existing directory-watch/notification flow
  verbatim — no new DSL keyword, no doc changes needed. Matches "loads
  ... as tempui" from the request: the item is handed to the Markdown
  widget exclusively through the tempui mechanism, the same way an
  agent would hand it a `Markdown`-keyword file by hand.
- Each row's Discuss button calls
  `current_context.get_discuss_starter()("PARKINGLOT.md",
  parking_lot_line=entry.line_number)` — the same reliable
  line-number-reference path TODO 624ff3a introduced for
  `DiscussParkingLotItem`, not the full-text path (avoids
  reintroducing the exact launch-prompt-length problem that TODO
  fixed, now that this widget has an easy, always-correct line number
  for every item it lists).
- `reload()`/`_on_external_change()`/watcher wiring mirror
  `QuestionsWidget` exactly, adapted to
  `find_nearest_parking_lot_file`/`parse_parking_lot_file`.
- `external_path_changed` signal + `refresh_external_path_status()`
  method, same shape as `QuestionsWidget`/`TodoWidget` — `DeskWindow
  .open_widget_content` already wires this generically via `hasattr`,
  no `window.py` change needed for this part.

### 3. `src/desk/shell/window.py`: let `start_discussion` take a line number too

`DeskWindow.start_discussion` (the `current_context` "discuss starter"
hook, TODO 46e1b42) currently only forwards `(source_label,
item_text)` to `_place_discuss_claude_widget`, which already supports
an optional `parking_lot_line` (added by TODO 624ff3a) but
`start_discussion` never exposes it. Widen it:

```python
def start_discussion(
    self, source_label: str, item_text: str = "", parking_lot_line: int | None = None
) -> None:
    self._place_discuss_claude_widget(source_label, item_text, parking_lot_line)
```

`item_text` gains a default so the new widget can call this passing
only `parking_lot_line`. The existing Questions-widget call site
(`starter("QUESTIONS.md", entry.raw_text)`) is untouched and keeps
working exactly as before.

### 4. `src/desk/shell/current_context.py`: update the hook's docstring

`set_discuss_starter`/`get_discuss_starter`'s type hint and the
module docstring's "Also holds a 'discuss starter' hook" paragraph get
a short addition noting the new optional line-number form and the
Parking Lot widget as its second caller. No behavior change here (the
hook is still just `DeskWindow.start_discussion` itself) — Python's
default-arg semantics mean the wider signature is already
call-compatible with the existing single-caller.

## Affected files

- `src/desk/parking_lot_file.py` (new)
- `widgets/parking_lot/widget.json` (new)
- `widgets/parking_lot/widget.py` (new)
- `src/desk/shell/window.py`
- `src/desk/shell/current_context.py`

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`):

- `parse_parking_lot_file` against this project's own real
  `PARKINGLOT.md`: item count, first item's title/line_number/raw_text
  match expectations, and a wrapped-title item (e.g. the
  `WidgetSpawnMenu._activate_item` entry) collapses to one line
  correctly.
- Constructing `ParkingLotWidget` directly (real `QApplication`,
  offscreen platform) against a temp directory with a small synthetic
  `PARKINGLOT.md`: the list shows the right number of rows with the
  right titles; double-clicking a row writes a UUID-named file under
  `.desk_temp/` whose content round-trips through
  `parse_markdown_tempui` back to `(title, raw_text)`; clicking a row's
  Discuss button, with a fake `discuss_starter` hook installed via
  `current_context.set_discuss_starter`, calls it with
  `("PARKINGLOT.md", parking_lot_line=<that item's line number>)`.
- `DeskWindow.start_discussion`'s widened signature: called with only
  `parking_lot_line` still reaches `_place_discuss_claude_widget`
  correctly (unbound-method-on-a-double pattern, same as TODO
  624ff3a's own verification); called the old two-positional-arg way
  (mirroring the Questions widget's call site) is unaffected.

Not exercised (same limitation noted in every prior widget TODO in
this project): actually right-clicking the canvas / dragging the
Parking Lot widget out of the spawn menu in a live GUI session, and a
real `claude` binary launch from the Discuss button.

## Status

Implemented as designed above.
