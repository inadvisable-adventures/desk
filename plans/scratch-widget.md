# Scratch Widget (COMPLETED)

## Summary

TODO 43845be: a new `kind: "python"` widget (`widgets/scratch/`) — a
simple multi-line textbox for jotting/pasting arbitrary text, with an
internal title row reading `Scratch: [label]` where `[label]` is
inline-editable.

## Design

- `python`-kind, following the same "plain PyQt6 widget" pattern as the
  TODO/Editor/Browser widgets.
- The `WidgetFrame` chrome titlebar (`src/desk/shell/widget_frame.py`)
  is a single static string per widget kind, set once from
  `widget.json`'s `"name"` — it has no per-instance update mechanism.
  Since each Scratch instance needs its own independently-editable
  label, this widget renders its own internal title row inside its
  content area (below the chrome titlebar, like the TODO widget's own
  internal toolbar), not by trying to repurpose the chrome titlebar.
- Title row: a `QLabel` reading `Scratch: {label}` (label defaults to
  `"untitled"`). Double-clicking the label swaps it for a `QLineEdit`
  pre-filled with the current label; `Enter` or losing focus commits
  the edited text back to the `QLabel` display (empty input falls back
  to `"untitled"` rather than leaving a blank label). This is a plain
  label/edit-swap, not a popup dialog — the smallest UI that satisfies
  "inline-editable."
- Body: a single `QPlainTextEdit`, expanding to fill remaining space,
  no placeholder text needed (a blank scratch pad is self-explanatory).
- No persistence/file-backing: this item only asks for the widget
  itself. (TODO d25e557, later in the file, plans to reuse a Scratch
  widget as a place to dump conflicting TODO text — that's a separate
  item and will drive whatever "create with an initial label/content"
  hook it needs; not building that hook speculatively here.)

## Affected files

- `widgets/scratch/widget.json`, `widgets/scratch/widget.py` (new).

## Verification

Entirely headless (`QApplication(sys.argv)`):

1. Confirm the widget constructs with the title row reading
   `Scratch: untitled` and an empty, editable text body.
2. Double-click (or directly call the label's edit-entry handler) to
   enter edit mode, confirm a `QLineEdit` pre-filled with `untitled`
   appears.
3. Type a new label and commit (Enter), confirm the title row now
   reads `Scratch: {new label}` and the `QLineEdit` is gone.
4. Enter edit mode again, clear the field, commit — confirm it falls
   back to `Scratch: untitled` rather than `Scratch: ` (blank).
5. Type text into the body `QPlainTextEdit`, confirm `toPlainText()`
   reflects it (plain widget behavior, but confirms the layout wiring
   didn't swallow the body).
6. Regression: confirm `discover_widgets` picks up the new
   `widgets/scratch` manifest, and a real `DeskWindow.open_widget
   ("scratch")` correctly builds and places a working `ScratchWidget`.

## Status

Implemented and verified, entirely headlessly (`QApplication(sys.argv)`):

1. Confirmed the widget starts with the title row reading
   `Scratch: untitled` and an empty body.
2. Confirmed double-clicking (via a `start_editing()` hook exposed for
   headless testing, avoiding a synthetic `QMouseEvent`) swaps in a
   `QLineEdit` prefilled with `untitled`.
3. Confirmed committing a new label (`returnPressed`) updates the title
   row and swaps back to the display label.
4. Confirmed committing a blank/whitespace-only edit falls back to
   `Scratch: untitled` rather than leaving it blank.
5. Confirmed the body `QPlainTextEdit` holds typed text correctly.
6. Regression: confirmed `discover_widgets` picks up the new
   `widgets/scratch` manifest, and a real `PythonWidgetHost` correctly
   builds a working `ScratchWidget` from it.
