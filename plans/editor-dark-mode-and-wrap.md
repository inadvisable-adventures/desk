# Editor: visible caret, dark-mode-friendly line numbers, line wrap

TODOs `cbbb661` (caret color), `17a2720` (line-number margin), and
`1d6777f` (line wrap) -- implemented together since all three are
small changes to the same file (`widgets/editor/widget.py`'s
`QsciScintilla` setup).

## Summary

- `cbbb661`: the editor's caret currently renders black (QScintilla's
  own default), which is invisible against a dark background --
  confirmed the underlying cause isn't unique to the caret: this
  editor's `QsciScintilla` never explicitly set its own base
  text/background colors at all, so what actually renders depends on
  Qt's palette-derived defaults, which follow the OS appearance.
  Explicitly committing the widget to this app's own established dark
  palette (matching `terminal_widget.py`'s `DEFAULT_FOREGROUND`/
  `DEFAULT_BACKGROUND`) fixes the caret's invisibility at its root,
  not just band-aids the caret's own color in isolation, and gives the
  other two items below a well-defined background to work against.
- `17a2720`: the line-number margin defaults to a *white* background
  regardless of the main editor's own paper color -- a separate,
  independent default in Scintilla (`STYLE_LINENUMBER`), not something
  that already followed the base editor color. Replaced with a
  background matching the editor's own, numbers drawn in a muted gray
  (a dimmer shade of the main text color, not identical), and a thin
  colored divider margin between the numbers and the text.
- `1d6777f`: long lines currently run off the right edge instead of
  wrapping. Word-wrap turned on; Scintilla's own default wrapped-line
  numbering (show the number once, on the *first* visual sub-line of a
  wrapped logical line) already matches "keep the line number aligned
  with the top line" without extra configuration -- confirmed by
  reading Scintilla's own margin-numbering behavior, not assumed.

## Key decisions

- **Explicit base colors, not just the caret.** `editor.setColor`/
  `setPaper` set to `#e8e8e8`/`#1e1e1e` (this app's own established
  dark palette, already reused by this same file's
  `setCaretLineBackgroundColor`). Scoped deliberately: this only fixes
  the *base* style (used for plain-text files, and as `STYLE_DEFAULT`'s
  fallback) and the margin -- it does **not** touch any individual
  lexer's own token colors (`QsciLexerPython` etc., applied in
  `_apply_lexer`), which is a materially bigger "make syntax
  highlighting dark-theme-aware" task nobody asked for here. Noted
  explicitly as a scope boundary, not an oversight.
- **Caret color**: `setCaretForegroundColor(#3daee9)` -- this
  codebase's established accent blue (TODO widget's checked filter
  buttons, notification banners), guaranteed visible against the new
  dark paper and consistent with the rest of the app's own branding,
  rather than an arbitrary new color.
- **Line-number margin (margin 0)**: `setMarginsBackgroundColor(#1e1e1e)`
  (matches the editor's own new paper -- no more white block) and
  `setMarginsForegroundColor` a muted gray (`#7a7f85`, dimmer than the
  main `#e8e8e8` text, per "a slightly different color than the
  default text").
- **Divider (a second, new margin, index 1)**: Scintilla's own
  documented mechanism for this exact look -- `setMarginType(1,
  QsciScintilla.MarginType.SymbolMarginColor)` (a solid-color margin,
  no symbols/numbers), `setMarginWidth(1, 2)`, `setMarginBackgroundColor
  (1, "#3a3d41")` (this app's own titlebar/chrome divider color,
  already used elsewhere for exactly this "separates two chrome
  regions" purpose). `setMarginBackgroundColor`/`marginBackgroundColor`
  are real, verifiable per-margin QsciScintilla methods (confirmed
  directly in the installed PyQt6-QScintilla version) -- not a raw
  `SendScintilla` message needed.
- **Wrap**: `setWrapMode(QsciScintilla.WrapMode.WrapWord)`. No further
  wrap-visual-flag/indent configuration -- not asked for, and
  Scintilla's default wrapped-sub-line numbering already does what was
  asked (checked directly against Scintilla's own documented
  behavior, not assumed to need extra config).

## Affected files

- `widgets/editor/widget.py` -- `EditorWidget.__init__`'s `QsciScintilla`
  setup: base color, caret color, margin 0/1 setup, wrap mode.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, a real
`EditorWidget`):

- `editor.color()`/`editor.paper()` return the new dark palette;
  `editor.caretForegroundColor()` returns the accent blue.
- `editor.marginsForegroundColor()` (margin 0's text color) differs
  from `editor.color()` (the main text color) -- "a slightly different
  color than the default text," checked as an actual inequality, not
  just "was set to something."
- `editor.marginBackgroundColor(0)` matches `editor.paper()` (no more
  white block); `editor.marginType(1)` is `SymbolMarginColor`,
  `editor.marginWidth(1) > 0`, and `editor.marginBackgroundColor(1)`
  differs from both margin 0's and the editor's own background (a
  genuinely distinct divider color).
- `editor.wrapMode()` is `WrapWord` after construction.
- Regression: opening/lexing a real file (extension-based lexer
  selection) still works with all of the above set; existing
  behaviors (`setCaretLineVisible`, save/load, etc.) untouched.

## Status

Not yet implemented.
