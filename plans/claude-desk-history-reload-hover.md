# Hover-triggered "reload" control over user lines in the Claude (Desk) widget's history (TODO `a4c3dec`)

## Summary

`widgets/claude_desk/widget.py`'s `_history` (a read-only `QPlainTextEdit`)
already visually distinguishes user-authored lines from everything else
(TODO `78d6207`, via `setExtraSelections()` + `_history_user_selections`).
This item adds a small floating "reload" button that appears only when
hovering over one of those user lines, and, when clicked, loads that
line's original prompt text back into `_prompt_input` so it can be
edited and resent — without disturbing normal click-drag text
selection/copy-paste anywhere in `_history`, and without touching
`_prompt_input`'s own behavior while the user is typing in it.

## Affected files

- `widgets/claude_desk/widget.py`:
  - `_append_history` gains a `reload_text: str | None = None` keyword
    (defaults to `text` itself when omitted, so the one existing
    direct-call test site with no reload text keeps working
    unchanged). Every `is_user=True` call site is updated to pass the
    *bare* prompt text (no `"> "`/`"[queued] "` display prefix) as
    `reload_text`.
  - A new `self._history_user_entries: list[tuple[int, int, str]]`
    list is grown alongside `self._history_user_selections` — one
    `(start, end, reload_text)` tuple per user line, reusing the exact
    same `start`/`end` character offsets already computed for the
    extra-selection highlight.
  - `__init__` wires hover detection on `self._history.viewport()` and
    a single floating `QPushButton` reload control, following the
    existing `widgets/todo/widget.py` "open plan" button precedent
    (`_plan_button`/`_on_item_entered`/`eventFilter`/
    `_hide_plan_button`, see `plans/todo-open-plan-button.md`) as
    closely as `QPlainTextEdit` (no built-in per-row hover signal like
    `QListWidget.itemEntered`) allows:
    - `self._history.viewport().installEventFilter(self)` catches
      `QEvent.Type.MouseMove` (recompute/show the button) and
      `QEvent.Type.Leave` (hide it) — the widget observes these
      events but never consumes them, so `_history`'s own
      click-drag text selection is completely untouched.
    - `self._history.verticalScrollBar().valueChanged` also hides the
      button (matches `_hide_plan_button`'s own scroll-triggered
      hide), so it never lingers over content that scrolled out from
      under it.
    - The button is a single reused `QPushButton(self._history.viewport())`,
      not one per line — mirrors the todo widget's own documented
      reason for that choice (a per-line child widget would be
      fragile to keep in sync as more history is appended).
  - New handlers: `eventFilter`, `_update_reload_button(pos)`,
    `_hide_reload_button`, `_on_reload_clicked`.
- `tests/verify/verify_claude_desk_widget.py` — new coverage.

## Design decisions

- **Hover detection via `cursorForPosition` + a tracked entry list,
  not per-line child widgets.** `QPlainTextEdit` has no per-row hover
  signal the way `QListWidget.itemEntered` gives `widgets/todo/widget.py`'s
  existing plan-button precedent. `QTextEdit.cursorForPosition(pos)`
  (viewport-relative coordinates, matching what an event filter on
  `viewport()` receives) maps the mouse position to a document
  character offset; a linear scan of `_history_user_entries` (small —
  one entry per user-sent message in a session) finds which, if any,
  covers that offset. This deliberately reuses the same `(start, end)`
  offsets `_append_history` already computes for the extra-selection
  highlight, so the two features can never disagree about which text
  counts as "the user line."
- **`reload_text` stores the bare prompt, not the displayed line.**
  The three `is_user=True` call sites each add their own display
  prefix (`"> "` for a sent message, `"[queued] "` for a
  not-yet-sent one) that is not part of what the user actually typed.
  Reloading must hand back exactly the original words, not
  `"> hello"` — so `reload_text` is threaded through separately from
  `text`, the same distinction the call sites already have to make
  today (they format `text` themselves before calling
  `_append_history`).
- **Positioning: right edge of the entry's first line, via
  `cursorRect()`.** Matches `_on_item_entered`'s own
  `rect.right() - size.width() - 6` convention for the todo widget's
  plan button, adapted from `visualItemRect(list_item)` (list-row
  rect) to `cursorRect(cursor)` (text-line rect) — the nearest
  `QPlainTextEdit` equivalent. For a multi-line user entry (e.g. the
  bootstrap prompt), the button anchors to the *first* line of the
  entry, not every line, since one control per entry (not per line)
  is all the feature needs.
- **Never consume the event.** The event filter only *observes*
  `MouseMove`/`Leave` on `_history.viewport()` and always falls
  through to `super().eventFilter(...)` — it never calls
  `event.accept()` or returns `True` for these types, so Qt's own
  built-in click-drag text selection inside `_history` keeps working
  exactly as it does today. `_prompt_input` is untouched by any of
  this — the event filter is installed only on `_history`'s viewport,
  never `_prompt_input`'s — so normal typing/selection there is
  unaffected regardless of what the mouse is doing over `_history`.
- **Clicking loads via `setPlainText`, replacing (not appending to)
  the box.** Matches the existing `_on_mic_transcription_finished`
  precedent (TODO `fe7d8f2`) of setting rather than sending — the
  user reviews/edits before anything goes to Claude, and reload is a
  deliberate "start over from this earlier prompt" action, not an
  append.

## Verification

New coverage in `tests/verify/verify_claude_desk_widget.py`:

- `_append_history(..., is_user=True, reload_text=...)` records a
  matching `(start, end, reload_text)` triple in
  `_history_user_entries`, using the bare text, not the displayed
  `"> "`/`"[queued] "`-prefixed line.
- The existing no-`reload_text`-argument call site
  (`test_multiline_user_text_gets_a_single_selection`'s direct
  `_append_history(..., is_user=True)` call) still works, falling back
  to `text` itself.
- `_send_now`/`_on_send_clicked`'s real call sites store the bare
  prompt (no prefix) as `reload_text`.
- `_update_reload_button` (called directly with a synthetic viewport
  position, not a simulated real mouse event — matches this suite's
  existing style of calling private handlers directly rather than
  driving real `QTest` mouse events) shows the button and records the
  hovered entry when the position falls inside a user entry's
  character range, and hides it otherwise.
- `_on_reload_clicked` sets `_prompt_input`'s text to the hovered
  entry's `reload_text` (not the displayed line) and hides the
  button afterward.
- Non-user lines (assistant/tool/error) never register a hover entry.
- The event filter is installed on `_history.viewport()` specifically
  (not on `_prompt_input` or the widget itself), confirming the two
  boxes' event handling stays independent.

Run the full `tests/verify/` suite and compare the failing set against
the pre-existing baseline (`git stash` the change, rerun, diff which
scripts fail) to confirm nothing else regressed. No browser launch
needed — offscreen Qt platform, matching every other
`verify_claude_desk_widget.py` test. Real mouse-hover behavior
(the button actually appearing under a live cursor) is not
exercised by the headless suite; if a real Desk launch is available
this session, do a manual sanity check, and if not, note in this
plan's "Verification results" that the manual check was skipped.
