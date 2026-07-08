# Fix invisible shell caret in the Console widget (TODO 1217380) (COMPLETED)

## Summary

TODO 1217380: the terminal's own caret is invisible inside the Console
widget (`widgets/console/widget.py`'s `TerminalWidget`), even though the
same shell, run outside the app, normally shows a solid, non-blinking
box-shaped cursor at the current position.

## Root cause

`TerminalWidget` tracks pyte's cursor purely through `QPlainTextEdit`'s
own *native* text cursor: `_redraw()` repositions `self.textCursor()` to
the pyte cursor's row/col and calls `self.setCursorWidth(0 if
self._screen.cursor.hidden else 2)`, relying on Qt's built-in blinking
-caret rendering to make it visible.

Confirmed directly: `TerminalWidget.__init__` calls
`self.setReadOnly(True)`. `QPlainTextEdit.setReadOnly(True)` doesn't just
block editing — it replaces `textInteractionFlags()` wholesale, from the
default `Qt.TextInteractionFlag.TextEditorInteraction` down to just
`Qt.TextInteractionFlag.TextSelectableByMouse`, which drops the
`Qt.TextInteractionFlag.TextEditable` bit entirely
(`w.textInteractionFlags()` before/after `setReadOnly(True)` confirms
this directly). Qt's internal text-cursor blink/paint logic only draws
the native cursor when that flag is present — so a read-only
`QPlainTextEdit` never renders its native cursor at all, regardless of
`setCursorWidth`, focus, or `cursorRect()` all being otherwise "correct"
(all three were individually confirmed non-broken in isolation — focus
is real, `cursorWidth()` is 2, `cursorRect()` returns a valid non-empty
rect). This is exactly "does not show up at all," not a blink-rate or
timing issue.

(Re-adding `Qt.TextInteractionFlag.TextEditable` to the flags was tried
and rejected — see Design below.)

## Affected files

- `widgets/console/widget.py` (edit).

## Design

Render the cursor explicitly, as part of the same per-character
formatting `_redraw()` already does for pyte's own SGR attributes (bold/
underline/reverse-video/colors), instead of depending on Qt's read-only
-widget-suppressed native cursor:

- `_char_format(char, invert=False)`: after resolving `fg`/`bg` (and
  applying `char.reverse` as today), swap them again if `invert` is
  true. This composes correctly with existing reverse-video text (`ESC
  [7m`): a reverse-video character sitting under the cursor renders as
  *plain* video, cursor-highlighted — exactly how real terminal emulators
  render this overlap, and exactly analogous to how `char.reverse` itself
  already works.
- In `_redraw()`'s per-column loop, pass `invert=True` for exactly the
  one cell at `(self._screen.cursor.x, self._screen.cursor.y)`, unless
  `self._screen.cursor.hidden` (respecting `ESC[?25l`/`ESC[?25h`, e.g.
  from a full-screen program like `claude` that manages its own cursor
  visibility) — same condition the old `setCursorWidth(0 if hidden else
  2)` call used, just applied to the new mechanism.
- Remove the now-pointless `target = self.textCursor(); ...;
  self.setTextCursor(target); self.setCursorWidth(...)` block at the end
  of `_redraw()` — Qt's native cursor was never visibly rendering
  anything (confirmed above), and nothing else reads `self.textCursor()`'s
  position (mouse-driven text selection, still wanted for copying
  terminal output, is entirely independent of this and untouched).

This renders a solid, non-blinking, reverse-video **box** covering the
full character cell — matching the "outside the app" reference
behavior described in the TODO — rather than attempting to resurrect
Qt's native thin blinking I-beam caret.

### Rejected alternative: re-add `Qt.TextInteractionFlag.TextEditable`

`w.setTextInteractionFlags(w.textInteractionFlags() |
Qt.TextInteractionFlag.TextEditable)` does make the native cursor
render again — but confirmed directly, it also flips `w.isReadOnly()`
back to `False`. `TerminalWidget.keyPressEvent` fully overrides key
handling and never calls `super()`, so keyboard-driven native editing
stays blocked either way, but *mouse*-driven native editing (drag-drop
of selected text, "Paste" from the standard context menu, etc.) would
newly be possible, letting the user directly mutate the read-only
display buffer in ways `_redraw()` doesn't expect. The per-character
custom-format approach above gets the same visible result without
touching read-only/editable semantics at all.

## Verification

Entirely headless (`QT_QPA_PLATFORM=offscreen`), driving a real PTY:

1. Confirm the bug directly against the unfixed code: `textCursor()`
   valid, `hasFocus()` true, `cursorWidth()` 2 — yet
   `textInteractionFlags()` lacks `TextEditable`, matching Qt's
   documented "no native cursor painted" condition.
2. After the fix: feed known output through the real PTY so the cursor
   lands at a known (row, col), then read back the character format at
   that exact document position (via a `QTextCursor` positioned there,
   `.charFormat()`) and confirm its foreground/background are swapped
   relative to an untouched neighboring cell with the same underlying
   pyte attributes.
3. Move the cursor (send more input) and confirm the inverted cell moves
   with it, and the previously-inverted cell reverts to its normal
   (non-inverted) format.
4. Confirm `cursor.hidden` (simulate `ESC[?25l`) suppresses the
   inversion entirely, and `ESC[?25h` restores it.
5. Regression: existing reverse-video (`ESC[7m`) rendering elsewhere in
   the buffer is unaffected, and a reverse-video character directly
   under the cursor renders as plain (double-inverted) video.

## Status

Implemented and verified headlessly, driving a real PTY through
`TerminalWidget`: printed known text, read back the resulting cell's
`QTextCharFormat` via a `QTextCursor` positioned at the exact pyte
cursor row/col, and confirmed its foreground/background are swapped
relative to the immediately-preceding (non-cursor) cell (`#1e1e1e`/
`#e8e8e8` vs. `#e8e8e8`/`#1e1e1e`). Sent a real `ESC[?25l`/`ESC[?25h`
pair through the PTY and confirmed the inversion disappears while
`self._screen.cursor.hidden` is true and reappears once shown again.
Confirmed the rejected `TextEditable`-flag alternative's downside
(`isReadOnly()` flips to `False`) directly before discarding that
approach.
