# Claude/Console widgets default to the active project directory

TODO `f447303`.

## Summary

`TerminalWidget` (`src/desk/terminal_widget.py`, shared by the Console
and Claude widgets) spawns its `bash` via `subprocess.Popen` with no
`cwd=` argument at all, so the shell simply inherits whatever working
directory the Desk *process itself* was launched from -- not the
currently-open Desk's own directory. Confirmed by reading the actual
`Popen` call (no `cwd`, no `os.chdir()`, no `pty.fork()` anywhere in
the file) and both widget files (neither passes anything either).

## Key decisions

- **`TerminalWidget.__init__` gains an optional `cwd: Path | None =
  None` parameter**, passed straight through to `subprocess.Popen`'s
  own `cwd=` (which already accepts a path-like object directly, no
  `str()` needed). `None` keeps today's exact fallback behavior
  (inherit the Desk process's own cwd) -- correct for the one edge
  case where `current_context.get_current_desk_directory()` is itself
  `None` (no Desk directory known yet), not a bug to work around.
  `desk.terminal_widget` stays Desk-context-agnostic otherwise (no
  `current_context` import there) -- `cwd`, like `command`, is just a
  plain parameter the *caller* decides, matching how `command` itself
  already works.
- **Both widgets pass `current_context.get_current_desk_directory()`
  as `cwd`** at construction time. Confirmed this is reliably
  available and already-set by the time either widget's `build()`
  runs: `DeskWindow._place_widget` (which constructs the widget
  synchronously via `PythonWidgetHost.__init__` -> `build()`) is only
  ever called after `current_context.set_current_desk_directory()` has
  already run, both at boot (`__init__`) and on every desk switch
  (`switch_desk`, TODO 4716585 additionally moved this even earlier,
  before `_load_desk_widgets`). Both widget files already import
  `current_context` (Claude does; Console needs the import added).
- **Set once, at `bash`'s own spawn** -- not re-applied for the Claude
  widget's later `exec claude ...`, since `exec` replaces the process
  image in place without forking, keeping the same cwd `bash` itself
  started with. One point of control, not two.

## Affected files

- `src/desk/terminal_widget.py` -- `TerminalWidget.__init__(self,
  parent=None, command=None, cwd=None)`.
- `widgets/console/widget.py` -- `build()` passes
  `cwd=current_context.get_current_desk_directory()`.
- `widgets/claude/widget.py` -- `ClaudeWidget.__init__` passes the same
  through to `super().__init__`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, a real
spawned `bash` process): construct a `TerminalWidget` with `cwd=`some
temp directory, have the shell print its own working directory (`pwd`)
via `type_into_shell`, read the PTY output back, confirm it matches
the given directory -- not wherever the test process itself runs from.
Also confirms the existing `cwd=None` default still behaves as before
(inherits the test process's own cwd). Then confirms both
`widgets/console/widget.py:build()` and `widgets/claude/widget.py`'s
`ClaudeWidget()` construction actually pass `current_context
.get_current_desk_directory()` through, via a patched `current_context`
returning a known directory.

## Status

Not yet implemented.
