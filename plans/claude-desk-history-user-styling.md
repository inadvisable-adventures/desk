# Visually differentiate user prompts in the Claude (Desk) widget's history (TODO `78d6207`) (COMPLETED)

## Summary

`widgets/claude_desk/widget.py`'s `_history` (a `QPlainTextEdit`)
appends every kind of line -- user-typed prompts (`"> {text}"`),
queued-but-not-yet-sent prompts (`"[queued] {text}"`), Claude's own
assistant text, and system/tool/permission/error markers -- through
one `_append_history(text)` helper with no visual distinction beyond
the existing textual prefixes, making it hard to scan who said what.

Add a `setExtraSelections()`-based highlight for every user-authored
line (color + bold), reusing the exact technique
`widgets/voice_input/widget.py`'s `_highlight_low_confidence_words`
already established in this codebase for colorizing text inside a
`QPlainTextEdit` without touching the document's own character
format. `setExtraSelections()` is a pure rendering overlay -- it is
never part of the document, never included in `toPlainText()`, and
(confirmed directly, matching `voice_input`'s own documented reason
for using it) never included in what gets copied to the clipboard --
so this adds visual differentiation with zero risk of altering
today's plain-text selection/copy output. No change to the existing
textual prefixes (`"> "`, `"[queued] "`, ...) -- those stay exactly as
they are; only a presentation layer is added on top.

## Affected files

- `widgets/claude_desk/widget.py` -- `_append_history` gains an
  `is_user: bool = False` keyword; every user-authored call site
  passes it; a new `_history_user_selections` list accumulates one
  `QTextEdit.ExtraSelection` per user line and is re-applied via
  `self._history.setExtraSelections(...)` after each one (the API
  replaces the whole list on every call, so the widget must keep its
  own running list rather than appending to Qt's).
- `tests/verify/verify_claude_desk_widget.py` -- new coverage.

## Design decisions

- **Which lines count as "user-authored."** The three call sites that
  emit text the user actually typed: `start_session`'s initial
  bootstrap-prompt line, `_send_now`'s `"> {text}"` line, and
  `_on_send_clicked`'s `"[queued] {text}"` line (queued content is
  still the user's own words, just not sent yet). Assistant text,
  tool use/result, permission, and error lines are left unstyled --
  matches the TODO's own framing of "user-entered prompts" vs.
  "everything else."
- **Color: this app's established accent blue (`#3daee9`)**, the same
  hex `widgets/editor/widget.py`'s own `CARET_COLOR` names as "this
  app's established accent blue" -- reuses an existing convention
  rather than inventing a new color. Paired with
  `QFont.Weight.DemiBold` for a chat-message-like visual weight
  without full bold's shoutiness.
- **`setExtraSelections`, not `QTextCursor.insertText(text, format)`.**
  The latter would mutate the *document's own* character format for
  that range -- on a `QPlainTextEdit`, whose backing store is still a
  real `QTextDocument`, a mutated char format can leak into copied
  rich-text mime data (`text/html`) alongside the plain text, which is
  exactly the "no stray markup ... when copying" failure mode the TODO
  calls out. `setExtraSelections` never touches the document at all --
  it's a separate, render-only overlay list the view consults only for
  painting -- so it can't leak into copy/paste under any code path.
- **A widget-owned list of selections, not one-shot.** Unlike
  `voice_input`'s single `_highlight_low_confidence_words()` call (one
  transcription result, one selection list, done),
  `ClaudeDeskWidget._history` accumulates lines indefinitely across a
  whole session, and `setExtraSelections()` always replaces its
  argument wholesale -- so each new user line's selection is appended
  to `self._history_user_selections` and the *whole* list is re-passed
  every time, or every earlier highlight would be wiped out by the
  next call.
- **Character offsets computed from `text`'s own length, not block
  counting.** `end = document().characterCount() - 1` (the position
  right after the just-appended content) and `start = end - len(text)`
  -- correct regardless of whether `appendPlainText` needed to insert
  a leading block separator before this content (irrelevant to the
  math, since that separator isn't part of `text`) or whether `text`
  itself contains embedded newlines (each becomes a block boundary
  that still consumes exactly one character position, identical to a
  literal `"\n"` for this arithmetic) -- covers `start_session`'s
  multi-line bootstrap prompt correctly, not just single-line prompts.

## Verification

New coverage in `tests/verify/verify_claude_desk_widget.py`:

- `_send_now`'s `"> {text}"` line ends up covered by exactly one
  extra selection spanning that line's own text (start/end offsets
  match, format has the accent color and demi-bold weight).
- `_on_send_clicked`'s queued-message line is styled the same way.
- `_on_assistant_text`/tool-use/tool-result/permission/error lines add
  *no* new extra selection.
- A multi-line `start_session` bootstrap prompt (containing embedded
  `"\n"`) is covered by a single selection spanning its *entire* text,
  not just its first line.
- `_history.toPlainText()` is byte-for-byte unchanged from before this
  change for a representative mixed transcript (user + queued +
  assistant + tool + error lines) -- confirms no textual/whitespace
  change, only the added overlay.

Run the full `tests/verify/` suite and compare the failing set against
the pre-existing baseline (`git stash`) to confirm nothing else
regressed. No browser launch needed (offscreen Qt platform, matching
every other `verify_claude_desk_widget.py` test).

## Verification results

Implemented as designed: `_append_history(text, *, is_user=False)`;
`USER_MESSAGE_COLOR = QColor("#3daee9")`; a widget-owned
`_history_user_selections` list re-applied via `setExtraSelections()`
on every user line. `start_session`'s bootstrap-prompt line,
`_send_now`'s `"> {text}"` line, and `_on_send_clicked`'s
`"[queued] {text}"` line all pass `is_user=True`; every other call
site unchanged.

Extended `tests/verify/verify_claude_desk_widget.py` with the five
tests described above (36 checks total in that file, 0 failures),
including a direct check that `_history.toPlainText()` for a
representative mixed transcript matches exactly what the pre-change
code would have produced (byte-for-byte), and that
`QTextCursor.selectedText()`'s own U+2029 paragraph-separator
substitution for a multi-block selection round-trips back to the
original `"\n"`-joined text for the multi-line-prompt case.

Full `tests/verify/` suite (138 non-disabled scripts) run: only the
same pre-existing, unrelated `verify_relocate_promoted_widget_source.py`
failure from TODO `8df6797`'s own verification remains -- no new
failures introduced by this change.
