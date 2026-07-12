# Stack widget (COMPLETED)

TODO `ac212bc`.

## Summary

"Create a 'stack' widget to keep track of nested discussions, with the
data stored in the widget-local storage, but with a button to copy the
stack as an md into a project file called STACK-[timestamp].md, and
the ability to load from an appropriately-formatted stack md file."

A new `kind: "python"` widget, `widgets/stack/`, modeling a literal
LIFO stack of "frames" (title + free-form notes) — a lightweight
breadcrumb trail for "I was looking into X, then a sub-question Y came
up, then within Y a sub-sub-question Z came up," navigable by push
(go one level deeper) / pop (finish the current nested thread, back to
the parent). Persists via widget-local storage (TODO fb76057, the only
consumer of that capability so far). Export/import through a new small
file-format module, `desk.stack_file`, mirroring `desk.todo_file`'s
existing shape for a different, simpler format.

## Key decisions

- **A literal stack, operated only from the top** — one global Push
  button (inserts a new, empty, immediately-editable frame) and one
  global Pop button (removes the current top frame), not a delete
  button per-frame. Keeps the UI and the mental model dead simple and
  honest to the "nested discussions" metaphor: you can go one level
  deeper or step back out, not reach into the middle and delete an
  arbitrary frame.
- **All frames visible and editable at once, most-recent (top) frame
  shown at the top of the widget** — not a collapse/expand-only-the
  -top scheme. Simpler to build (no expand-state machinery), and lets
  you glance back at an earlier frame's notes without popping out of
  the current one first.
- **No confirmation on Pop** — matches this codebase's generally low
  -friction interaction style elsewhere (e.g. editing/reprioritizing a
  TODO item has none either), and the frame about to be removed is
  fully visible on screen right before clicking, so it's not a hidden
  or surprising action.
- **Confirmation *is* asked before Load** (`QMessageBox.question`,
  same established pattern as Desk-switching/widget-close) — unlike
  Pop (removes one visible frame), Load silently discards the *entire*
  current stack, a much bigger, easy-to-not-notice loss.
- **"Save as Markdown" writes immediately, no dialog** — the target
  filename is already fully specified by the TODO's own wording
  (`STACK-[timestamp].md`, no content-derived naming ambiguity the way
  TODO 9743419's "save a copy" button had), so there's nothing for a
  dialog to usefully ask; a status label reports where it was saved,
  mirroring the TODO widget's own status-label pattern. "the root of
  the project directory" (TODO 9743419's phrasing) / "a project file"
  (this TODO's phrasing) both point at the same place:
  `current_context.get_current_desk_directory()`, falling back to
  `Path.cwd()` if none is set yet (matches `crash_handler`'s and
  `_doc_path()`'s existing fallback shape).
- **New `desk.stack_file` module, not inline in the widget** — matches
  the established convention (`desk.todo_file`, `desk.temp_ui`) of
  keeping a parse/render file-format pair as shared, widget
  -independent, easily unit-testable code. Format: `# Stack` title line,
  then one `## <title>` heading per frame followed by its notes,
  **bottom-of-stack (oldest, pushed first) to top (current) reading
  top-to-bottom in the file** — narrates the nesting in the order it
  actually happened, like a written log, rather than most-recent-first.
  `parse_stack_file` is the literal inverse, splitting on `## `
  headings.
- **Timestamp format matches `crash_handler`'s**: `%Y-%m-%dT%H-%M-%S`
  (filesystem-safe, sortable, consistent with `DESK-CRASH-<timestamp>
  .log`, TODO 95f7ce9).

## Affected files

- `src/desk/stack_file.py` (new) — `StackFrame`, `render_stack_file`,
  `parse_stack_file`.
- `widgets/stack/widget.json` (new), `widgets/stack/widget.py` (new) —
  `StackWidget`: toolbar (Push/Pop/Save as Markdown/Load), a
  `QScrollArea` of frame rows (title `QLineEdit` + notes
  `QPlainTextEdit`), `get_widget_local_storage`/`set_widget_local_storage`
  (TODO fb76057) for persistence.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks):

- `render_stack_file`/`parse_stack_file` round-trip: a multi-frame
  stack (including a frame with empty notes, and notes containing
  their own `##`-looking text to confirm the split logic isn't
  fooled) survives render-then-parse unchanged.
- Real `StackWidget`: Push adds a new frame at the top and it's
  immediately editable; Pop removes the current top frame and the
  next one down becomes the visible top; the widget's own
  `get_widget_local_storage()`/`set_widget_local_storage()` round-trip
  a real multi-frame stack correctly (title + notes preserved, stack
  order preserved).
- "Save as Markdown": clicking it with a real current-Desk directory
  set writes a real `STACK-<timestamp>.md` file there, whose content
  matches `render_stack_file`'s own output for that stack.
- "Load": choosing a real, well-formed stack markdown file replaces the
  current stack with its parsed frames; declining the confirmation
  prompt leaves the current stack untouched.
- A widget-local-storage round trip through a *real* Desk save/load
  cycle (matching TODO fb76057's own verification shape): place a
  `StackWidget`, push a couple of frames, save the Desk, reload it, and
  confirm the frames are still there in the right order.

## Status

Implemented as planned: `src/desk/stack_file.py` (`StackFrame`,
`render_stack_file`, `parse_stack_file`); `widgets/stack/widget.json` +
`widgets/stack/widget.py` (`StackWidget`, `_FrameRow`).

All headless verification steps above passed: render/parse round-trip
(including a case with an empty-notes frame); render order is
bottom-of-stack-first; parse ignores any preamble before the first `##`
heading; Push/Pop maintain correct stack order in both the internal
list and the visual layout (top of stack always visually first);
`get_widget_local_storage`/`set_widget_local_storage` round-trip a
real multi-frame stack, order preserved; "Save as Markdown" writes a
real file whose content matches `render_stack_file`'s own output;
"Load" replaces the stack after confirmation and leaves it untouched
if declined; and a full real `Desk` save/load round trip (via
`desk.desks.save_desk`/`load_desk`, not reimplemented logic) preserves
a pushed multi-frame stack correctly -- the Stack widget is
widget-local storage's (TODO fb76057) first real consumer.

Confirmed `discover_widgets` picks up the new widget correctly
(`id="stack"`, `deprecated=False`).

No `LEARNINGS.md` entry needed -- nothing surprising turned up; the one
real subtlety (reconstructing `_replace_frames`'s visual insertion
order to match what sequential `_push()` calls would have produced)
was caught and fixed during implementation, not discovered as a
surprising runtime behavior during verification.
