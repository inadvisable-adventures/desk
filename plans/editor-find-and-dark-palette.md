# Editor: find and dark-mode palette (TODO d5744c8) (COMPLETED)

## Summary
(a) Lexer token colors are lexer defaults (black, dark grey, blue) and unreadable on `EDITOR_BACKGROUND`.
(b) Add substring find: search box right of "Save As", then Previous/Next buttons; Cmd/Ctrl+F focuses it.

## Affected files
- `widgets/editor/widget.py`
- `tests/verify/verify_editor_find.py` (new)

## Approach
- (a) After creating a lexer, set its paper to the editor background and, for every style 0..127 that
  the lexer defines, remap its color: keep hue, force HSL lightness >= 0.68 (and cap too-pale
  values), so syntax distinctions survive but legibility doesn't depend on lexer defaults.
- (b) `QLineEdit` + two buttons in the toolbar. `textChanged` -> search forward from the selection
  start (the caret position, so typing more characters keeps the same match), wrapping. Next searches
  from the selection end; Previous from the selection start backwards. Enter/Shift+Enter in the box
  = next/previous. Case-insensitive literal (non-regex). Not-found state tints the box red-ish.
  Uses `QsciScintilla.findFirst(expr, re=False, cs=False, wo=False, wrap=True, forward, line, index)`.
  Search origin is the editor's caret via `getCursorPosition()`, which stays the "most recent
  position" because focus leaves the editor without moving the caret.

## Verification
Headless script `tests/verify/verify_editor_find.py`; browser/visual check skipped.
