# Scratch tempui capability (COMPLETED)

TODO `f8d9cec`.

## Summary

"Add a new (or existing?) tempui capability to allow agents to add
'scratch' text, and make it clear in the tempui instructions given to
claude that when the user refers to 'scratch,' that is what is meant,
unless there is a more pressing local meaning."

Checked: the Scratch widget (`widgets/scratch/`, `ScratchWidget`)
already exists -- a plain title-plus-`QPlainTextEdit` widget, today only
ever placed *programmatically* by another widget (the TODO widget's
edit-conflict handling, TODO d25e557, via `current_context
.get_widget_opener()` + `set_label()`). There is **no** existing tempui
-file-based way for an agent to place one with initial content -- that
capability doesn't exist yet and needs to be added, following the exact
shape the `OpenMarkdown` kind already established: a new, fourth
first-line keyword (`Scratch <label>`), fire-and-forget (no `Answer`
line, Desk never writes back), documented in `desk-temporary-ui.md`
(`DOC_TEMPLATE`) the same way the other three kinds already are.

## Key decisions

- **New keyword `Scratch <label>`, first line only; everything after it
  verbatim becomes the widget's initial body text.** Unlike `Question`/
  `OpenMarkdown` (whose single value is "everything after the first
  space, one line"), Scratch content is inherently multi-line free-form
  notes -- so only the *first* line is structured (`Scratch` + a short
  label matching `ScratchWidget.set_label`), and the rest of the file,
  completely unparsed, becomes the body. New `desk.temp_ui.parse_scratch
  (text) -> tuple[str, str] | None` (`(label, body)`, `None` if the file
  doesn't actually start with `Scratch`).
- **Fire-and-forget, exactly like `OpenMarkdown`** -- no `Answer` line,
  `ScratchWidget` never writes back to the tempui file (it has no file
  -writing capability at all today, and this doesn't add any -- adding
  live persistence of further user edits is a separate, much bigger
  question that overlaps with the not-yet-built general "widget-local
  storage" capability, TODO fb76057, not this one).
- **`detect_temp_ui_kind` gains a fourth return value, `"scratch"`**,
  and `window.py` wires it through the same places the other three
  kinds already go: `SCRATCH_WIDGET_ID = "scratch"` added to
  `TEMP_UI_WIDGET_IDS` (so a saved Desk reconnects a restored Scratch
  instance to its source file the same way, via `instance_id`-equals
  -uuid) and to `_temp_ui_widget_id_for`'s kind->widget_id mapping;
  `_bind_temp_ui_content` gains a `"scratch"` branch (`content
  .set_label(label)` + `content.body.setPlainText(body)`, duck-typed
  the same way `set_file`/`set_source_file` already are); `_notify_temp_ui`
  uses the label as the notification text (falling back to the
  existing generic "New question: <filename>" text if parsing fails,
  same defensive shape the other kinds already use).
- **No live refresh if the file is edited again after the widget is
  already open** -- clicking the notification a second time just
  re-centers on the existing widget, same limitation the existing
  Question/LightningRound kinds already have (their own live state
  changes come from the widget's *own* actions, not from re-reading the
  file). Not a new gap introduced here, and out of scope to fix
  generally.
- **The disambiguation instruction is added verbatim-in-spirit to
  `DOC_TEMPLATE`'s new "Scratch" section**: if the user says "scratch"
  in conversation, this capability is almost certainly what's meant --
  not some other, more generic sense of the word -- unless a clearly
  more pressing local meaning has already been established earlier in
  the same conversation. This is instructional text for claude reading
  `desk-temporary-ui.md` (per `CLAUDE_WIDGET_PROMPT`), not application
  logic.

## Affected files

- `src/desk/temp_ui.py` -- `SCRATCH_KEYWORD`, `parse_scratch()`,
  `detect_temp_ui_kind` gains `"scratch"`, `DOC_TEMPLATE` gains a new
  "## The TempUI DSL: Scratch" section (including the disambiguation
  note).
- `src/desk/shell/window.py` -- `SCRATCH_WIDGET_ID`, added to
  `TEMP_UI_WIDGET_IDS`; `_temp_ui_widget_id_for`, `_bind_temp_ui_content`,
  `_notify_temp_ui` each gain a `"scratch"` branch.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks):

- `detect_temp_ui_kind`: a file starting with `Scratch <label>` ->
  `"scratch"`; existing kinds unaffected.
- `parse_scratch`: `(label, body)` extracted correctly for a real
  multi-line file, including a label containing spaces and a
  multi-line body; `None` for a file not starting with `Scratch`.
- End-to-end via a real `DeskWindow`-style flow (`_temp_ui_widget_id_for`
  -> `_bind_temp_ui_content` against a real `ScratchWidget` instance):
  a real `.desk_temp/<uuid>` file with `Scratch <label>\n<body...>`
  resolves to `SCRATCH_WIDGET_ID`, and binding it sets the widget's
  label and body text to the parsed values.
- `_notify_temp_ui`'s derived notification text for a real Scratch
  file matches the label.

## Status

Implemented as planned: `SCRATCH_KEYWORD`, `parse_scratch()`,
`detect_temp_ui_kind`'s new `"scratch"` return, and the new
`DOC_TEMPLATE` section (with the disambiguation note) in `src/desk
/temp_ui.py`; `SCRATCH_WIDGET_ID`, `TEMP_UI_WIDGET_IDS`,
`_temp_ui_widget_id_for`, `_bind_temp_ui_content`, and `_notify_temp_ui`
in `src/desk/shell/window.py`.

All headless verification steps above passed, including exercising the
real (unbound, since neither touches `self`) `DeskWindow
._temp_ui_widget_id_for` and `DeskWindow._bind_temp_ui_content` methods
directly against a real `ScratchWidget` instance and a real temp file
-- not just the standalone `desk.temp_ui` parsing functions in
isolation.

No `LEARNINGS.md` entry needed -- this followed an existing, already
-documented pattern (`OpenMarkdown`'s shape) exactly, nothing
surprising turned up.
