# LightningRound TempUI type + widget (TODO 11aeb43) (COMPLETED)

## Summary

TODO 11aeb43: a new TempUI file type, `LightningRound` — a shared set of
single-character-keyed options applied one at a time to a list of items
("lightning round items"), answerable by clicking a button or pressing
the corresponding key. A new widget kind renders it, alongside the
existing Question type.

## DSL

New keywords, alongside the existing `Question`/`Option`/`Answer`
(`desk.temp_ui.parse_temp_ui`'s keyword+rest-of-line shape is kept
as-is; a LightningRound file uses a **separate** parser, since its shape
is structurally different — one prompt, one shared option set, and a
*list* of items, not a single question/answer):

- `LightningRound\t[name]\t[prompt]` — first line, tab-separated (name
  and prompt can each contain spaces, so tab is the unambiguous
  delimiter here, unlike `Question`'s single free-text value).
- `Option [character]` — reused verbatim (same keyword, same
  keyword-then-rest-of-line shape as today); the value is a single
  character used both as the option's keyboard shortcut and its display.
  Repeat once per option; these options apply to every item in the file.
- `LRItem\t[description]\t[answer or "unanswered"]` — one lightning
  -round item, tab-separated for the same reason as the first line.
  `unanswered` is a literal placeholder written by whoever authors the
  file; Desk replaces it with the chosen option's character once
  answered.

Example, before any answers:

```
LightningRound	Vocab Drill	Is this word a noun, verb, or adjective?
Option N
Option V
Option A
LRItem	run	unanswered
LRItem	quick	unanswered
```

After answering "run" with "V":

```
LightningRound	Vocab Drill	Is this word a noun, verb, or adjective?
Option N
Option V
Option A
LRItem	run	V
LRItem	quick	unanswered
```

## Affected files

- `src/desk/temp_ui.py` (edit) — `LightningRoundItem`/
  `LightningRoundDocument` dataclasses, `parse_lightning_round`,
  `record_lightning_round_answer`, `detect_temp_ui_kind`, `DOC_TEMPLATE`
  updated to document the new type.
- `widgets/lightning_round/widget.json` (new), `widgets/lightning_round
  /widget.py` (new) — the widget itself.
- `src/desk/shell/window.py` (edit) — generalize the Question-only
  wiring (`QUESTION_WIDGET_ID`-specific checks in `_load_desk_widgets`,
  `_notify_temp_ui`, `_activate_temp_ui`) to route by the file's actual
  detected kind.
- `.desk_temp/desk-temporary-ui.md` (edit, this project's own already
  -provisioned copy) — regenerated from the new `DOC_TEMPLATE` by hand,
  since `TempUiManager.provision` only writes it if absent, not on every
  boot.

## Design

### Parsing (`desk/temp_ui.py`)

```python
@dataclass
class LightningRoundItem:
    description: str
    answer: str | None = None  # None means "unanswered"

@dataclass
class LightningRoundDocument:
    name: str = ""
    prompt: str = ""
    options: list[str] = field(default_factory=list)
    items: list[LightningRoundItem] = field(default_factory=list)

LIGHTNING_ROUND_KEYWORD = "LightningRound"
UNANSWERED = "unanswered"

def detect_temp_ui_kind(text: str) -> str:
    """"question" (default/existing type) or "lightning_round", from the
    first non-blank line's keyword -- so callers that see a temp-ui file
    for the first time (a notification, a saved Desk's widget state)
    know which widget kind to place without assuming "question"."""
    for line in text.splitlines():
        if line.strip():
            keyword = line.split(None, 1)[0]
            return "lightning_round" if keyword == LIGHTNING_ROUND_KEYWORD else "question"
    return "question"

def parse_lightning_round(text: str) -> LightningRoundDocument:
    doc = LightningRoundDocument()
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith(LIGHTNING_ROUND_KEYWORD + "\t") or line == LIGHTNING_ROUND_KEYWORD:
            parts = line.split("\t")
            doc.name = parts[1] if len(parts) > 1 else ""
            doc.prompt = parts[2] if len(parts) > 2 else ""
        elif line.startswith("Option"):
            parts = line.split(None, 1)
            if len(parts) > 1:
                doc.options.append(parts[1].strip())
        elif line.startswith("LRItem"):
            parts = line.split("\t")
            description = parts[1] if len(parts) > 1 else ""
            raw_answer = parts[2] if len(parts) > 2 else UNANSWERED
            answer = None if raw_answer == UNANSWERED else raw_answer
            doc.items.append(LightningRoundItem(description, answer))
    return doc

def record_lightning_round_answer(path: Path, item_index: int, character: str) -> str:
    """Rewrites the item_index-th LRItem line's answer field in place
    (item_index counts only LRItem lines, in file order -- matching
    parse_lightning_round's doc.items indexing) and returns the full
    resulting text, same self-write-suppression shape as append_answer."""
    lines = path.read_text().splitlines(keepends=True)
    seen = 0
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if not stripped.startswith("LRItem"):
            continue
        if seen == item_index:
            parts = stripped.split("\t")
            description = parts[1] if len(parts) > 1 else ""
            newline = "\n" if line.endswith("\n") else ""
            lines[i] = f"LRItem\t{description}\t{character}{newline}"
            break
        seen += 1
    text = "".join(lines)
    path.write_text(text)
    return text
```

`is_temp_ui_filename` (UUID check) is unchanged — it's about the
*filename*, not the content, and applies to every TempUI type equally.

### Widget (`widgets/lightning_round/`)

Same `build() -> QWidget` / `set_source_file(path)` shape as
`QuestionWidget` (`widgets/question/widget.py`), so it plugs into
`PythonWidgetHost`/`DeskWindow.open_widget_content` with zero special
-casing beyond widget-kind routing (below):

- A prompt label (`doc.prompt`, falling back to `doc.name`).
- A description label showing the **first unanswered item** (`next(i
  for i, item in enumerate(doc.items) if item.answer is None)`) — "skip
  those that already have an answer" per the TODO. If none remain: "All
  items answered!" (or "No items yet." if the file has no items at all).
- One button per option, labelled `f"Press {character}"` (per the TODO's
  own example wording) so the keyboard shortcut is discoverable without
  a separate legend.
- `keyPressEvent` (widget needs `Qt.FocusPolicy.StrongFocus` — a plain
  `QWidget` defaults to `NoFocus`, so it wouldn't receive key events
  otherwise) matches the typed character (case-insensitively — a typed
  key can arrive as either case depending on Shift) against the current
  option set and answers the same way a button click would.
- Answering calls `record_lightning_round_answer`, records the write via
  `current_context.get_temp_ui_write_recorder()` (same self-write
  -suppression as `QuestionWidget._choose`), then reloads — which
  naturally advances to the next unanswered item, or the "all answered"
  state.

### Routing by detected kind, not a fixed widget id (`window.py`)

Today, every TempUI file unconditionally becomes a `"question"` widget
(`QUESTION_WIDGET_ID`, hardcoded in three places). Generalize to a small
id-by-kind map and read the file's detected kind before choosing:

```python
LIGHTNING_ROUND_WIDGET_ID = "lightning_round"
TEMP_UI_WIDGET_IDS = {QUESTION_WIDGET_ID, LIGHTNING_ROUND_WIDGET_ID}

def _temp_ui_widget_id_for(self, path: Path) -> str:
    try:
        kind = detect_temp_ui_kind(path.read_text())
    except OSError:
        kind = "question"
    return LIGHTNING_ROUND_WIDGET_ID if kind == "lightning_round" else QUESTION_WIDGET_ID
```

- `_load_desk_widgets`: `if state.widget_id in TEMP_UI_WIDGET_IDS:` (was
  `== QUESTION_WIDGET_ID`) before calling the (renamed, but otherwise
  already fully generic) binder — `_bind_question_widget` becomes
  `_bind_temp_ui_widget`; its body already only calls
  `content.set_source_file(...)`, nothing Question-specific.
- `_activate_temp_ui`: look up `widget_id =
  self._temp_ui_widget_id_for(path)` instead of the hardcoded constant,
  and use it for both the catalog lookup and `open_widget_content`.
- `_notify_temp_ui`: branch on detected kind to pick the right parser
  for the notification's preview text — `doc.question` for a Question
  file (unchanged), `doc.prompt` (falling back to `doc.name`) for a
  LightningRound file.

### Docs (`DOC_TEMPLATE`, `.desk_temp/desk-temporary-ui.md`)

Add a `## LightningRound` section (mirroring the existing `## The TempUI
DSL` section's shape: keyword list, a before/after example) to
`DOC_TEMPLATE` in `desk/temp_ui.py` — this is the file agents (Claude
included) actually read to learn the DSL, so it's the primary "direction
to claude" the TODO calls out. Since `TempUiManager.provision` only
writes this file if it doesn't already exist, also manually refresh this
project's own already-provisioned `.desk_temp/desk-temporary-ui.md` copy
to the new template text, so this repo's own live behavior matches (not
required for the feature to work in a *fresh* directory, but this repo's
copy would otherwise silently drift out of date the moment this change
ships).

## Verification

Entirely headless (`QT_QPA_PLATFORM=offscreen`):

1. `parse_lightning_round`: round-trips a real example file (name,
   prompt, options, item descriptions/answers, including a mix of
   answered/unanswered items and the literal `unanswered` placeholder).
2. `detect_temp_ui_kind`: a `LightningRound`-first-line file → `
   "lightning_round"`; a `Question`-first-line file (and an empty file)
   → `"question"`.
3. `record_lightning_round_answer`: rewrites exactly the targeted
   `LRItem` line's answer field in place, leaves every other line
   (including other `LRItem` lines, `Option` lines, the first line)
   byte-for-byte untouched, and returns text matching the file's
   post-write content.
4. Widget: constructed with a real temp file, confirm it shows the first
   unanswered item's description and one button per option; clicking a
   button (and, separately, a synthesized matching keyPressEvent)
   records the answer and advances to the next unanswered item; confirm
   the "all answered" state once every item has an answer.
5. `window.py` routing: confirm `_temp_ui_widget_id_for` returns the
   right widget id for both a Question-shaped and a LightningRound
   -shaped file, and (full-app) that a `DeskWindow`'s
   `_load_desk_widgets`/`_activate_temp_ui` paths place the correct
   widget kind for each.

## Status

Implemented and verified headlessly:

1. `parse_lightning_round`/`detect_temp_ui_kind`: round-tripped a real
   example file (name, prompt, options, a mix of answered/unanswered
   items, including the literal `unanswered` placeholder); confirmed
   kind detection for both a `LightningRound`-first-line file and a
   `Question`-first-line/empty file.
2. `record_lightning_round_answer`: confirmed it rewrites exactly the
   targeted `LRItem` line's answer field, leaving the first line,
   `Option` lines, and every other `LRItem` line byte-for-byte
   untouched.
3. `LightningRoundWidget`: constructed against a real file, confirmed it
   shows the first unanswered item and one "Press X" button per option;
   confirmed both a button click and a synthesized matching
   `keyPressEvent` (including case-insensitive matching) record the
   answer, persist it to disk, and advance to the next unanswered item;
   confirmed the "All items answered!" state once every item has one.
4. `window.py` routing: confirmed `_temp_ui_widget_id_for` returns the
   right widget id for both file shapes; full-app regression (a real
   `DeskWindow`) confirmed a saved `lightning_round` widget state
   correctly reconnects to its source file via `_bind_temp_ui_widget`,
   and confirmed the existing `question` widget path still works
   unchanged after the `_bind_question_widget` → `_bind_temp_ui_widget`
   rename/generalization.
5. Refreshed this project's own already-provisioned
   `.desk_temp/desk-temporary-ui.md` from the updated `DOC_TEMPLATE` by
   hand (not committed — `.desk_temp/` is gitignored local state, same
   as always; the canonical, committed source is `DOC_TEMPLATE` itself).
