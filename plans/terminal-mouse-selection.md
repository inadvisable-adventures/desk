# Terminal widget: preserve mouse selection across redraws (and let it be copied) (COMPLETED)

TODO `846303c`.

## Investigation

`TerminalWidget` is a read-only `QPlainTextEdit`, whose `setReadOnly(True)`
keeps `TextSelectableByMouse` — so mouse selection *is* enabled and, in a
static terminal, works. The bug is that `_redraw()` (called on **every**
PTY read, in `_on_readable`) does `cursor.select(Document);
removeSelectedText()` and rebuilds the whole document from pyte's screen
buffer. Any active selection is wiped by that rebuild. A live TUI like
claude repaints near-continuously (cursor blink, spinners, streaming
output), so a selection is destroyed almost as soon as it's made —
"mouse-based selection doesn't work in claude".

A second, related gap: even with the selection preserved, copying it is
blocked. `keyPressEvent` turns Ctrl+C into `0x03` (SIGINT) unconditionally
(and on macOS Qt maps Cmd→Control, so the natural "Cmd+C to copy" also
lands here), so there's no way to copy the selection to the clipboard.

## Fix

1. **Preserve the selection across `_redraw()`**: the redraw always
   rebuilds the *same* fixed grid (`PTY_ROWS` blocks × `PTY_COLS` chars),
   so a character offset denotes the same screen cell before and after.
   Capture `anchor()`/`position()` (and `hasSelection()`) before wiping;
   after rebuilding, if there was a selection, restore a cursor with the
   same anchor/position (clamped to the document length defensively) via
   `setTextCursor`. When there's no selection, behavior is unchanged (the
   cursor is left where the rebuild ended, as today — the terminal cursor
   is drawn separately as an inverted cell).
2. **Copy on Ctrl/Cmd+C when there's a selection**: in `keyPressEvent`,
   if Ctrl (Qt `ControlModifier`) + `C` is pressed *and*
   `textCursor().hasSelection()`, call `self.copy()` and return (don't
   send to the PTY). With no selection, Ctrl+C still sends `0x03` (SIGINT)
   as before. This is the standard "Ctrl+C copies when text is selected,
   interrupts otherwise" terminal convention (e.g. Windows Terminal), and
   it sidesteps macOS Cmd/Ctrl modifier-mapping entirely — whichever
   physical key Qt reports as `ControlModifier`+C copies a live
   selection.

## Scope

- Not adding a right-click "Copy" context menu, mouse-reporting/SGR mouse
  passthrough, or paste — out of scope for this selection bug. The
  Ctrl+C-with-selection path covers "select text to copy it".

## Affected files

- `src/desk/terminal_widget.py` — `_redraw` (save/restore selection),
  `keyPressEvent` (copy-on-Ctrl+C-with-selection).

## Verification

Headless, against a real `TerminalWidget` (real PTY):
- Feed initial output, set a selection over a known cell range, then feed
  more data to trigger `_redraw()`; assert the selection survives (same
  `anchor`/`position`, `hasSelection()` still True) — and that without
  the fix it would be gone (demonstrated by the pre-fix wipe).
- Ctrl+C **with** a selection copies the selected text to
  `QApplication.clipboard()` and writes **nothing** to the PTY.
- Ctrl+C **without** a selection writes `0x03` to the PTY and leaves the
  clipboard unchanged.
- Regression: a plain selection with no redraw still works; other keys
  (arrows etc., TODO 3be392a) are unaffected.

## Status

**Completed.** Implemented and verified headlessly as described above:
a selection survives a `_redraw()` (anchor/position preserved); Ctrl+C
with a selection copies to the clipboard and sends nothing to the PTY;
Ctrl+C without a selection sends `0x03` (SIGINT) and leaves the clipboard
alone; and a redraw with no selection introduces none.
