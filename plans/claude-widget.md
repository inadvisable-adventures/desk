# Claude widget (TODO 6907120) (COMPLETED)

## Summary

TODO 6907120: a new widget, `claude`, that runs the `claude` CLI in a
real shell (same underlying mechanism as the Console widget), passing an
initial prompt telling it it's running inside Desk and pointing it at
the `.desk_temp` doc that explains Temporary UI conventions.

## Design

### Extract the generic PTY/pyte terminal into a shared module

`widgets/console/widget.py`'s `TerminalWidget` is already fully generic
— nothing in it is Console-specific except the hardcoded
`subprocess.Popen(["bash"], ...)` call. Move the whole class (plus its
supporting `_ResilientStream`/`_PtyScreen`/color-map/char-format
machinery) into a new `src/desk/terminal_widget.py`, the same "shared
logic lives in `desk.`, thin `widgets/*/widget.py` entry points" pattern
already used for `desk.todo_file`/`desk.git_utils`/`desk.temp_ui`. Widget
directories can't import each other directly (each `widget.py` is loaded
via `importlib.util.spec_from_file_location` into its own throwaway
module namespace, not real package imports) — this is the reason a
shared *installed-package* module is the right home, not a
`widgets/console` → `widgets/claude` import.

`TerminalWidget.__init__` gains a `command: list[str] | None = None`
parameter (`self._command = command or ["bash"]` — keeps today's
behavior as the default rather than forcing every caller to spell out
`["bash"]`), used in place of the hardcoded `["bash"]` in the
`subprocess.Popen` call. Nothing else about the class changes — same PTY
setup, same `_redraw`/cursor-cell rendering (TODO 1217380), same cleanup.

`widgets/console/widget.py` becomes a thin shim:

```python
from desk.terminal_widget import TerminalWidget

def build() -> QWidget:
    return TerminalWidget()
```

### `widgets/claude/` widget

Same PTY mechanism, via the shared module, but immediately types the
`claude` invocation into the freshly-spawned shell — like a user
launching a normal terminal and then typing a command — rather than
`exec`-ing `claude` as the PTY's own process directly. This matters
because `claude`'s availability, `PATH`, and any shell customization
(`nvm`, aliases, etc.) are set up by the shell's own
startup/profile — the exact same reason the Console widget itself spawns
`bash`, not an arbitrary program, as the PTY's process. If `claude` isn't
found, the user sees the shell's own "command not found" — same
graceful behavior a real terminal gives, and the shell itself stays
usable afterward (not exited), unlike running `bash -c "claude ..."`
which would exit the whole pane once `claude` does.

The initial prompt text, matching the TODO's own example wording:

```python
CLAUDE_WIDGET_PROMPT = (
    "You are running inside of Desk. Please read this document to "
    "understand the implications of that: {doc_path}"
)
```

`doc_path` is `current_context.get_current_desk_directory() /
TEMP_UI_DIRNAME / DOC_FILENAME` (`desk.temp_ui`'s existing constants —
the same `desk-temporary-ui.md` the Temporary UI feature already
provisions) when the current Desk's directory is known; falls back to a
plain relative-path description (`.desk_temp/desk-temporary-ui.md`) if
`current_context` hasn't been set yet (an edge case, not the normal
path, but the widget must not crash if it is placed before that's
populated).

```python
def build() -> QWidget:
    directory = current_context.get_current_desk_directory()
    doc_path = (
        str(directory / TEMP_UI_DIRNAME / DOC_FILENAME)
        if directory is not None
        else f"{TEMP_UI_DIRNAME}/{DOC_FILENAME}"
    )
    prompt = CLAUDE_WIDGET_PROMPT.format(doc_path=doc_path)
    widget = TerminalWidget(command=["bash"])
    widget.type_into_shell(f"claude {shlex.quote(prompt)}\n")
    return widget
```

This needs one small, generically-useful addition to `TerminalWidget`
itself: a `type_into_shell(text: str) -> None` method (just
`os.write(self._master_fd, text.encode())`, wrapped the same way
`keyPressEvent` already writes to the pty) — a clean, explicit way for a
subclass/caller to feed the shell input programmatically, rather than
reaching into `widget._master_fd` directly from outside the class.

## Affected files

- `src/desk/terminal_widget.py` (new) — the extracted, parameterized
  `TerminalWidget` (moved from `widgets/console/widget.py`).
- `widgets/console/widget.py` (edit) — thin shim over the shared module.
- `widgets/claude/widget.json` (new), `widgets/claude/widget.py` (new).
- `design-docs/architecture.md` (edit) — a new Claude Widget component
  entry alongside the existing Console Widget one.

## Verification

Entirely headless (`QT_QPA_PLATFORM=offscreen`), driving real PTYs:

1. Regression: `widgets/console/widget.py`'s `build()` still produces a
   working `TerminalWidget` running `bash` (same behavior as before the
   extraction — send a known command through the real pty, confirm the
   rendered buffer reflects it).
2. `TerminalWidget(command=[...])`: confirm the PTY's process is what
   was actually requested (not always `bash`) — e.g. spawn with a
   command that immediately echoes something distinctive and confirm
   it's visible in the rendered buffer, without needing `type_into_shell`
   at all.
3. `type_into_shell`: confirm text written this way is delivered to the
   real PTY exactly like a `keyPressEvent`-driven keystroke would be.
4. Claude widget's `build()`: with `current_context
   .set_current_desk_directory` set to a real directory, confirm the
   constructed prompt contains the expected doc path; with no current
   Desk directory known, confirm it falls back to the relative-path
   description instead of crashing. Confirm the actual bytes written to
   the real PTY (via a fake/no-op `claude` on `PATH` for the test, since
   the real CLI isn't guaranteed to be installed in a test environment)
   match `claude <quoted prompt>\n`.

## Status

Implemented and verified headlessly, driving real PTYs:

1. Regression: `widgets/console/widget.py`'s `build()` (now a thin shim
   over `desk.terminal_widget.TerminalWidget()`) still spawns a real,
   working `bash` shell — sent a distinctive command through the real
   pty and confirmed it rendered correctly.
2. Confirmed `TerminalWidget(command=[...])` actually runs the requested
   command (not always `bash`) via a real, distinctive non-bash command.
3. Confirmed `type_into_shell` delivers text to the real PTY exactly
   like a `keyPressEvent`-driven keystroke would.
4. Claude widget: confirmed `_doc_path()` returns the real
   `.desk_temp/desk-temporary-ui.md` path when a current Desk directory
   is known, and the relative-path fallback when it isn't. End-to-end
   with a fake `claude` script on `PATH` (a clean `HOME` was needed for
   this specific test to avoid the real environment's own shell rc file
   clobbering `PATH` before the fake binary could be found — not a
   product behavior change, purely a test-environment concern):
   monkeypatched `type_into_shell` to capture the exact text `build()`
   sent (confirming it starts with `claude ` and contains the real doc
   path, independent of any terminal line-wrap rendering), and
   separately confirmed end-to-end that the fake `claude` binary
   actually received and echoed that same prompt back through the real
   PTY.
5. Updated `design-docs/architecture.md` with a new Claude Widget
   component entry.
