# (COMPLETED) "Send scratch to agent" button on the Scratch widget (TODO `2016312`)

## Summary

A button on `widgets/scratch/widget.py` opens a new Claude (Desk) widget just right of the Scratch, as the
`[CHAT]` titlebar button does (`DeskWindow._place_widget_chat_about`), but with no widget-chat
instructions: the session's first user turn is Desk's normal starting prompt (`_PROMPT_INTRO` +
`_PROMPT_ORIENTATION_ONLY` + `_PROMPT_TOOLS` + the development-process pointer, exactly what
`ClaudeDeskWidget.start_session` builds) followed by the Scratch's complete text, verbatim.

## Decisions

- **Placement:** the Scratch has only a title row and a body (no Open/Save buttons; those live in the
  editor/markdown/sheet/svg_editor widgets), so add a button row between them: `[Send to agent]` at the left
  with a stretch after it. If Scratch ever gains file buttons they go first, with this one after them and
  12px of layout spacing (the row's own spacing is 4px) separating the groups.
- **Hook:** `current_context.set_scratch_agent_sender(sender)` with `sender(source: QWidget, label: str,
  text: str) -> str | None` (an error message, or `None` on success). `source` is the Scratch widget itself;
  the shell finds its `WidgetFrame` by scanning `view._frames` for the frame whose `content.current` is it
  (the Scratch doesn't know its instance id). Positional-only parameters, no optional ones, so a plain
  `Callable` alias is enough (`development-process.md`); the real method `DeskWindow.send_text_to_agent`
  is exercised positionally in the verify script.
- **Text goes in the turn directly,** not via `_write_claude_instructions_file` (that is a "read this file"
  pointer): `claude_extra_instructions = "\n\nThe user's message (the complete text of their Scratch
  widget, verbatim):\n\n" + text`. `start_session` already appends `extra_instructions` last.
- **Size:** `_MAX_BUFFER_SIZE` and `verify_claude_session_oversized_message.py` concern *incoming* NDJSON
  lines from the CLI, not what we send, so they don't bound this. The practical limit is the model's context;
  cap at `MAX_SCRATCH_SEND_CHARS = 400_000` (~100k tokens) and, above it, refuse with a popup saying how
  large it is and the limit, sending nothing.
- **Empty Scratch** (whitespace only): popup "The Scratch is empty -- nothing to send.", nothing placed.
- **Errors/popups** use `current_context.get_popup_opener()` (blocking; same as other python widgets).
- Button label is a plain `QPushButton` (a push button's own text isn't selectable); the title label already
  uses `NoTextInteraction`. No new `QLabel`s.
- Not agent-visible: no tempui changelog entry.

## Affected files

- `widgets/scratch/widget.py` -- button row, `_send_to_agent`.
- `src/desk/shell/current_context.py` -- `set_/get_scratch_agent_sender`.
- `src/desk/shell/window.py` -- `send_text_to_agent`, registration, shared "beside frame" position helper
  factored out of `_place_widget_chat_about`.
- `tests/verify/verify_scratch_send_to_agent.py` (new).

## Verification

Headless script: real `DeskWindow`-free checks of the widget (empty -> popup and sender not called; over cap
-> popup, not called; normal -> sender called with label and exact text) plus a `DeskWindow` check that
`send_text_to_agent` places a claude_desk frame right of the source frame whose recorded extra instructions
end with the verbatim text and contain no widget-chat instructions. Live check in Desk skipped unless noted
below.

## Status

Completed 2026-10-21. All verify steps ran headless (offscreen); the live-app check was skipped.
