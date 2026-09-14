# Multi-line, word-wrapping prompt input for the Claude (Desk) widget (TODO `8df6797`) (COMPLETED)

## Summary

`widgets/claude_desk/widget.py`'s `_prompt_input` is currently a
single-line `QLineEdit`: a long prompt scrolls off-screen horizontally
instead of wrapping, and the box can never show more than one line at
a time. Replace it with a small `QPlainTextEdit` subclass
(`_PromptInput`) that word-wraps by default (`QPlainTextEdit`'s own
default `lineWrapMode` is `WidgetWidth`) and re-creates the
`QLineEdit.returnPressed` affordance this widget already relies on:
plain Enter sends the message, Shift+Enter inserts a newline instead
of sending.

## Affected files

- `widgets/claude_desk/widget.py` -- new `_PromptInput(QPlainTextEdit)`
  class with a `send_requested` signal; `ClaudeDeskWidget.__init__`
  swaps it in for the old `QLineEdit` and fixes its height so it
  doesn't grow to fill the row; every other `_prompt_input` call site
  (`_on_send_clicked`, the mic-dictation slot) updated from
  `QLineEdit`'s `text()`/`setText()`/`clear()` API to
  `QPlainTextEdit`'s `toPlainText()`/`setPlainText()`/`clear()`
  (`clear()` itself is unchanged -- both classes have it).
- `tests/verify/verify_claude_desk_widget.py` -- new coverage for
  `_PromptInput`'s key handling and the updated send/mic call sites.
- `tests/verify/disabled_verify_claude_desk_widget_mic.py`,
  `tests/verify/disabled_verify_claude_desk_widget_claude_api.py` --
  both reference `_prompt_input.text()`/`.setText()` directly; updated
  to the new `toPlainText()`/`setPlainText()` API so they stay correct
  for whenever someone runs them by hand (they're disabled for
  unrelated reasons -- real mic hardware / real API calls -- not
  drift), per `development-process.md`'s "fix what your own change
  made stale" expectation.

## Design decisions

- **`QPlainTextEdit`, not a rich-text `QTextEdit`.** Keeps this a
  plain-text box with no formatting/paste-as-rich-text concerns to
  handle -- matches `_history`'s own existing use of `QPlainTextEdit`
  elsewhere in this same widget.
- **Enter-to-send via a small subclass**, not an event filter on the
  plain `QPlainTextEdit` -- `QPlainTextEdit` has no `returnPressed`-
  style signal (that's `QLineEdit`-only, per the TODO item's own
  description), so `_PromptInput` overrides `keyPressEvent`: a bare
  Return/Enter (no Shift) emits a new `send_requested` signal instead
  of calling `super()` (so no newline is inserted); Shift+Enter (or
  any other key) falls through to the default `QPlainTextEdit`
  behavior, which inserts the newline. `ClaudeDeskWidget.__init__`
  connects `send_requested` to `_on_send_clicked`, the same slot
  `returnPressed` used to drive.
- **Fixed height, not auto-growing with content.** Matches this file's
  own existing `TASKS_PANEL_HEIGHT` precedent (a flat pixel constant,
  not `sizeHint`-driven) rather than inventing a new auto-resize
  mechanism -- a new `PROMPT_INPUT_HEIGHT = 60` constant (~3 lines at
  the default font size) keeps the box multi-line without letting an
  arbitrarily long prompt push the history area off the bottom of the
  widget. The box still scrolls vertically past that height (a
  `QPlainTextEdit` does this natively), so nothing is ever lost --
  only the *visible* height is capped.
- **Bottom-aligned mic/send buttons.** `prompt_row` is a
  `QHBoxLayout` shared with `_mic_button`/`_send_button`; explicitly
  setting `Qt.AlignmentFlag.AlignBottom` for both buttons in that
  layout keeps them pinned to the bottom edge of the now-taller
  `_prompt_input` (the usual chat-input convention) instead of Qt's
  default vertical centering.
- **No change to the queueing/busy behavior (TODO `e1f6391`).**
  `_prompt_input` still stays enabled while a turn is in flight; only
  the widget class and its text-access API change.

## Verification

`tests/verify/verify_claude_desk_widget.py` (extended):

- Plain Enter on `_PromptInput` emits `send_requested` and does not
  insert a newline into the box.
- Shift+Enter on `_PromptInput` does *not* emit `send_requested` and
  does insert a newline (the box's `toPlainText()` grows by one line).
- `_on_send_clicked` reads/clears `_prompt_input` via the new
  `toPlainText()`/`clear()` API and still queues/sends exactly as
  before (reuses the existing `_FakeSession` pattern already in this
  file).
- The mic-dictation slot (`_on_mic_transcription_finished`) sets the
  dictated text into `_prompt_input` via `setPlainText`, confirmed by
  reading it back with `toPlainText()`.

Run the full `tests/verify/` suite and compare the failing set against
the pre-existing baseline (`git stash`) to confirm nothing else
regressed.

## Verification results

Implemented as designed: `_PromptInput(QPlainTextEdit)` with a
`send_requested` signal, `PROMPT_INPUT_HEIGHT = 60`, bottom-aligned
mic/send buttons. Extended `tests/verify/verify_claude_desk_widget.py`
with the five tests described above (26 checks total in that file, 0
failures). Also updated the two disabled-but-still-real scripts that
reference `_prompt_input.text()`/`.setText()` directly
(`tests/verify/disabled_verify_claude_desk_widget_claude_api.py`,
`tests/verify/disabled_verify_claude_desk_widget_mic.py`) to the new
`toPlainText()`/`setPlainText()` API so they stay correct if run by
hand.

Full `tests/verify/` suite run (138 non-disabled scripts): only
`tests/verify/verify_relocate_promoted_widget_source.py` fails --
confirmed pre-existing via `git stash` (fails identically,
with the same segfault, on unmodified `main`; its own traceback shows
it's importing `desk.shell.window` from a hardcoded sibling checkout
path rather than this repo, the same class of bug TODO `224fbc9`'s own
write-up already flags), not caused by this change. No browser launch
was needed for this widget's own verification (offscreen Qt platform,
matching every other `verify_claude_desk_widget.py` test).
