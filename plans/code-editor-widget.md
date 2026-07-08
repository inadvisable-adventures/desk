# Code editor widget (COMPLETED)

## Summary

A new `kind: "python"` widget (`widgets/editor/`) providing a real text/code
editor backed by `QScintilla` (native Qt, via the `PyQt6-QScintilla`
bindings) — per direct instruction, resolving item 21's previously-open
implementation choice in favor of native Qt over Chromium/Monaco. Supports
opening, editing, and saving a file from disk, with syntax highlighting
based on the file's extension.

## Affected files

- `pyproject.toml` (edit) — add `PyQt6-QScintilla` to dependencies.
- `widgets/editor/widget.json` (new) — manifest (`kind: "python"`).
- `widgets/editor/widget.py` (new) — the widget itself.
- `TODO.md` (edit) — mark item 18 (Code editor widget, prioritized ahead of
  hot reload) `COMPLETED` once verified.
- `design-docs/architecture.md` (edit) — add a Code Editor Widget component
  entry, matching the existing Console Widget entry's level of detail.

## Design

### Self-contained widget, same shape as `console`/`demo`

`widget.py` exposes `build() -> QWidget`, loaded the same way every other
`python` widget is (`PythonWidgetHost`, no special-case wiring). No changes
needed to `desk.shell.python_widget`, `canvas.py`, or `window.py`.

### Editor surface: `QsciScintilla` with a small toolbar

- `QsciScintilla` as the main text-editing surface: line numbers margin,
  monospace font, current-line highlighting.
- A slim top toolbar (`QToolBar` or a plain `QHBoxLayout` of `QPushButton`s
  — matching this project's preference for bespoke, no extra Qt Designer/
  resource-file machinery) with **Open**, **Save**, **Save As** actions,
  plus a small label showing the currently open file's name (or
  "*(untitled)*").
- Standard shortcuts: `Cmd+O` open, `Cmd+S` save, `Cmd+Shift+S` save as
  (via `QShortcut`/`QKeySequence.StandardKey`).

### Syntax highlighting: lexer selected by file extension

A small `EXTENSION_LEXERS` dict maps common extensions (`.py`, `.json`,
`.js`/`.ts`, `.html`, `.md`, `.sh`, `.yaml`/`.yml`, `.c`/`.cpp`/`.h`) to the
matching `PyQt6.Qsci` lexer class (`QsciLexerPython`, `QsciLexerJSON`, ...).
Unknown/no extension: no lexer (plain text, still fully editable). The
lexer is (re)applied via `QsciScintilla.setLexer(...)` whenever a file is
opened.

### File I/O: plain `QFileDialog`, no automatic Desk-directory context

`QFileDialog.getOpenFileName`/`getSaveFileName`, defaulting to the editor's
own last-used directory (an instance variable, starting from the user's
home directory) — **not** automatically defaulted to the current Desk's
associated directory. Wiring that through would require `PythonWidgetHost`/
`window.py` to pass Desk context into `build()`, which no `python` widget
does today and which is really the Desk Bridge API's job (item 20) to solve
generally, not something to bolt on ad hoc for just this widget. Explicitly
out of scope here — noted as a natural follow-up once item 20 exists.

### Unsaved-changes handling

Track modification state via `QsciScintilla.isModified()`
(`modificationChanged` signal updates the toolbar's file-name label with a
"•" marker, a common editor convention). Opening a different file or
closing the widget with unsaved changes prompts via `QMessageBox` (Save /
Discard / Cancel) before proceeding — reusing the same
confirm-before-losing-state pattern already established for Desk switching
(`desk.shell.window.DeskWindow.switch_desk`).

## Verification

1. Headless: construct the widget, call `_load_file(path)` directly with a
   real temp file containing distinctive content, confirm
   `editor.text()` matches, and confirm the lexer selected matches the
   file's extension (e.g. `.py` → `QsciLexerPython` instance).
2. Headless: edit the loaded text, confirm `isModified()` becomes `True`
   and the toolbar label reflects the unsaved marker; call `_save_file()`,
   confirm the file on disk now matches the edited text and `isModified()`
   resets to `False`.
3. Headless: confirm opening a *different* file while the current one has
   unsaved changes triggers the confirm dialog (inject a fake `confirm`
   callable the same way `DeskWindow` does, rather than driving a real
   `QMessageBox`).
4. Full-app: launch the real app, add an Editor widget via the right-click
   spawn menu (item 14), open a real `.py` file from this repo, confirm
   syntax highlighting renders and the file's content displays correctly.

## Key design decisions / tradeoffs

- **`QScintilla`, not Monaco/Chromium** — direct instruction, also
  consistent with this project's established preference for native Qt
  widgets over Chromium ones wherever practical (see `CLAUDE.md`, and the
  Console widget's same resolution in `plans/console-widget.md`).
- **No automatic Desk-directory awareness yet.** The TODO item's "project/
  workspace awareness" aspiration needs a real way for a `python` widget to
  learn the current Desk's directory, which doesn't exist for any widget
  today. Building one-off plumbing just for this widget would preempt and
  likely conflict with item 20's (Desk Bridge API) general solution to the
  same problem — better to ship a fully-functional standalone editor now
  and wire in Desk-awareness generally later.
- **Lexer-by-extension, not a language picker.** Simple and sufficient for
  a first version; `QScintilla` supports many more lexers than are wired up
  here, so extending `EXTENSION_LEXERS` later is a small, additive change.

## Status

Implemented and verified:

1. Headless: loaded a real `.py` temp file via `_load_file`, confirmed
   `editor.text()` matches and `QsciLexerPython` was selected; confirmed a
   freshly-constructed editor with no file loaded shows the `(untitled)`
   label.
2. Headless: edited loaded text, confirmed `isModified()` became `True` and
   the label showed the "•" marker; called `_save_file()`, confirmed the
   file on disk was updated and `isModified()`/the label reset.
3. Headless: confirmed all three branches of the unsaved-changes confirm
   path via an injected `confirm_unsaved` callable — `"save"` (writes to
   disk, returns `True`), `"discard"` (returns `True` without writing),
   and `"cancel"` (returns `False`) — without driving a real `QMessageBox`.
4. Full-app: confirmed `discover_widgets` picks up the new `widgets/editor`
   manifest, `PythonWidgetHost` builds an `EditorWidget` through the normal
   widget-loading path (no special-casing needed), and opening a real file
   from this repo (`widgets/console/widget.py`) through `_load_file`
   displays its content with `QsciLexerPython` applied. Did not drive the
   real right-click spawn menu or `QFileDialog` interactively (no way to
   drive real mouse/keyboard interaction in this environment, consistent
   with prior widgets' verification notes) — the underlying code paths
   (`discover_widgets`, `PythonWidgetHost`, `_load_file`) are exactly what
   those UI actions call into.
