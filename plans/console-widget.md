# Console widget (COMPLETED)

## Summary

Implement the Console widget: a built-in, shipped widget (`widgets/console/`,
discovered through the same catalog mechanism as any other widget — no
special-casing in `DeskWindow`/`WorkspaceView`) that runs a real `bash`
shell in a real PTY, so the user can run anything a terminal can,
including `claude`.

Resolves the open question from `design-docs/architecture.md` (Chromium
-hosted `xterm.js`+PTY vs. native-Qt): **native-Qt**, per the rationale
below.

## Resolving the Chromium-vs-native-Qt open question

**Native-Qt** (a `QPlainTextEdit`-based terminal), not `xterm.js` in a
`ChromiumWidget`:

- The project's established direction (TODO 8/9's "prefer Python,
  no build step" pivot) is specifically about not needing Node/npm/tsc for
  Desk's own built-in, shipped experience — pulling in `xterm.js` for a
  *core, always-present* widget would reintroduce exactly the dependency
  this project deliberately moved away from. (A user's own *custom*
  `kind: "html"` widget can still use `xterm.js` if they want — that door
  stays open — but the built-in Console shouldn't require it.)
- A `kind: "python"` widget is just a `widget.py` with `build() ->
  QWidget` — no new architecture needed at all; it slots into the exact
  same catalog/hot-reload/Desk-persistence machinery every other widget
  already uses.

## Design

### Scope: a real PTY, minimal ANSI handling (not a full terminal emulator)

A genuine VT100/xterm-compatible terminal emulator (cursor positioning,
alternate screen buffer, full SGR color support, etc.) is a large
undertaking, and the only real way to get one without writing it from
scratch is a third-party library (e.g. `pyte`) — which conflicts with
`CLAUDE.md`'s "avoid adding dependencies, prefer bespoke solutions" for
something this widget doesn't strictly need to satisfy its stated purpose
(run `bash`/`claude` and read/write text). This plan deliberately scopes
down to:

- A **real PTY** running `bash` (via the standard library's `pty` module —
  non-negotiable per `design-docs/architecture.md`'s existing "PTY-backed
  console, not a fake/emulated shell" decision).
- **Regex-stripped ANSI escape sequences** in the output (rendered as
  plain, uncolored text) rather than interpreted (no cursor repositioning,
  no color, no alternate-screen support). This means full-screen TUI
  programs (`vim`, `htop`, `less` in its default paging mode) will not
  render correctly — their cursor-positioning escape sequences get
  stripped rather than acted on, so redraws just appear as repeated lines
  of text. Ordinary linear CLI output (`bash` itself, most of what
  `claude` prints) is expected to work.
- **Basic key forwarding** (printable characters, Enter, Backspace, Tab,
  Ctrl-C, Ctrl-D) — not full keyboard/arrow-key/history support.

Noted explicitly as a real, current limitation (not silently glossed
over) in `design-docs/architecture.md` and this plan's Key Design
Decisions — a fuller VT100 emulator is real future work, not something
this item claims to deliver.

### PTY spawn (`widgets/console/widget.py`)

```python
master_fd, slave_fd = pty.openpty()
process = subprocess.Popen(
    ["bash"],
    stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
    preexec_fn=os.setsid,  # slave becomes the child's controlling terminal
    env={**os.environ, "TERM": "xterm-256color"},
    close_fds=True,
)
os.close(slave_fd)  # the child has its own copy; the parent doesn't need it
```

A fixed PTY window size (80×24) is set via `fcntl.ioctl(slave_fd,
termios.TIOCSWINSZ, ...)` before spawning, so interactive programs that
query terminal size get a sane answer — dynamically resizing it to match
the widget's actual size is future work, not needed for a first version.

### Output: `QSocketNotifier`, not a polling thread

`QSocketNotifier(master_fd, QSocketNotifier.Type.Read)` watches the
master fd for readability and fires a Qt signal on the GUI thread when
there's output — no background thread, no polling, fully integrated with
the Qt event loop (the same pattern this project already uses for
event-driven I/O rather than threads elsewhere). On the notifier firing:
`os.read(master_fd, 4096)`, decode (`utf-8`, `errors="replace"`), strip
ANSI escape sequences and lone `\r` characters via regex, append to the
`QPlainTextEdit`. An empty read (EOF) means the shell exited: disable the
notifier and append a `[process exited]` marker.

### Input: forward keystrokes to the PTY, don't let Qt echo locally

`QPlainTextEdit.setReadOnly(True)` (blocks the widget's own default text
-editing) plus a `keyPressEvent` override that translates the key to
bytes and `os.write()`s them straight to `master_fd`, **not** calling
`super().keyPressEvent(...)`. The *displayed* text comes entirely from
what the PTY echoes back through the master fd (the kernel's tty line
discipline, in canonical+echo mode, reflects typed characters back
through the same channel bash reads from) — letting Qt *also* locally
insert typed characters would double up (once from Qt, once from the
PTY's own echo arriving back through the reader).

Key translation for v1: printable text (`event.text()`), Enter (`\r`),
Backspace (`\x7f`), Tab (`\t`), Ctrl-C (`\x03`), Ctrl-D (`\x04`). Arrow
keys / bash history navigation are not forwarded yet — a known, noted gap
rather than a silent omission.

### Cleanup: terminate the child process when the widget is destroyed

Connect `self.destroyed.connect(self._cleanup)` in `__init__`.
`_cleanup` disables the socket notifier, closes `master_fd`, and
terminates the `bash` process (`process.terminate()`, with a short wait
then `process.kill()` if it doesn't exit). `destroyed` fires reliably
whenever the widget is actually torn down — including on hot reload
(`PythonWidgetHost._rebuild()` calls `deleteLater()` on the previous
widget before swapping in a new one) and on Desk switch
(`WorkspaceView.clear_widgets()`) — so a stray `bash` process is never
left running in the background after either of those.

## Affected files

- `widgets/console/widget.json` (new) — `{"name": "Console", "kind":
  "python", "entry": "widget.py", "default_size": {"width": 720, "height":
  420}}`.
- `widgets/console/widget.py` (new) — `TerminalWidget(QPlainTextEdit)` (PTY
  spawn, output reader, input forwarding, cleanup) and `build() ->
  QWidget`.
- `design-docs/architecture.md` (edit) — resolve the Console half of the
  Chromium-vs-native-Qt Open Question (leave the Code Editor half open,
  to resolve when that item is reached); update the Console Widget
  component description; add a Key Design Decisions entry for the
  ANSI-stripping/no-full-emulation scoping.

## Verification

1. Headless: spawn a `TerminalWidget`, write a known command's bytes
   followed by `\r` (e.g. `echo hello-from-pty\r`) via its `keyPressEvent`
   path (or directly via the same code path `os.write` uses), pump the Qt
   event loop briefly so the `QSocketNotifier` fires, and confirm
   `hello-from-pty` appears in the widget's `toPlainText()`.
2. Headless: confirm the child `bash` process is actually running
   (`process.poll() is None`) right after construction, and confirm it is
   no longer running (process exited) after the widget is destroyed —
   proving the `destroyed`-triggered cleanup actually terminates it,
   rather than leaking a background shell.
3. Headless: confirm ANSI escape sequences in a command's output (e.g.
   from `printf '\\033[31mred\\033[0m\\n'`) are stripped from the
   displayed text (the word appears, the raw escape bytes don't).
4. Headless: confirm ordinary key events (letters, Enter, Backspace,
   Ctrl-C) translate to the expected bytes without needing a full
   interactive session — test the key-to-bytes translation function
   directly against constructed `QKeyEvent`s.
5. Full-cycle: launch the real app (`python -m desk`); confirm the console
   widget is discovered and placed (or can be added via the item-14
   right-click menu) and that the app still starts/quits cleanly with a
   `bash` process now part of its process tree — and that quitting Desk
   doesn't leave that `bash` process running afterward.
6. Actually typing interactively into the widget and watching a real
   terminal session unfold is expected to be **skipped** for direct visual
   confirmation, per the precedent throughout this project (this
   environment can't drive real mouse/keyboard interaction) — the
   `os.write`/`QSocketNotifier` round-trip in steps 1–3 is the closest
   practical equivalent, driving the exact same code path a real
   keystroke would.

### Status (verification notes)

- Headless: confirmed the full PTY round-trip — simulated typing (via
  `keyPressEvent`) `echo hello-from-pty` + Enter, pumped the event loop,
  and confirmed `hello-from-pty` appeared in the widget's captured text
  shortly after, proving the whole path (keystroke → `os.write` →
  kernel PTY line discipline → `bash` executes → `bash` writes output →
  `QSocketNotifier` fires → `os.read` → display) works end to end.
- Headless: confirmed ANSI escape sequences are stripped — sent
  `printf '\033[31mred-marker\033[0m\n'`, confirmed `red-marker` appears
  in the displayed text with no raw escape byte (`\x1b`) present.
- Headless: confirmed the widget catalog correctly discovers
  `widgets/console/` (`kind: "python"`, `name: "Console"`,
  `default_size: (720, 420)`).
- **Found and fixed two real, non-obvious bugs during verification**
  (both recorded in `LEARNINGS.md`):
  1. `self.destroyed.connect(self._cleanup)` never actually fired —
     connecting an object's own `destroyed` signal to one of its own
     bound methods silently does nothing. Fixed by connecting to a
     lambda closing over plain captured values, calling a `@staticmethod`
     that never touches `self`.
  2. `subprocess.Popen(preexec_fn=os.setsid)` worked fine in isolated
     test scripts but **silently never spawned the child process at all**
     when run inside the real, running Desk app (confirmed directly by
     inspecting the process tree — no bash child ever appeared, no
     exception, nothing in the logs). Root cause: `preexec_fn` runs
     arbitrary Python between `fork()` and `exec()`, which is unsafe in a
     multi-threaded process — and a running PyQt app is exactly that.
     Fixed by switching to `start_new_session=True`, confirmed to
     correctly spawn `bash` as a real child process
     (`ps` showed the correct parent/child PID relationship) once fixed.
- Full-cycle, in the real running app: confirmed `bash` spawns as an
  actual child process of the Desk process on startup (both `console`
  and `demo` get auto-placed for a fresh Desk), and — critically —
  confirmed that quitting Desk terminates that `bash` child too (checked
  via `ps -p <pid>` before and after quitting), so no shell processes are
  left running in the background after Desk exits.
- Actually typing interactively into the widget and watching a real
  terminal session unfold remains **skipped** for direct visual
  confirmation — this environment can't drive real mouse/keyboard
  interaction — but the `keyPressEvent`-driven round-trip above exercises
  the exact same code path a real keystroke would, including the actual
  running app (not just a headless script) for the process-spawn and
  -cleanup checks specifically, since those two bugs only manifested
  under the real app's threading context.

## Key design decisions / tradeoffs

- **Native-Qt, not Chromium/`xterm.js`.** See the dedicated section above
  — keeps a core, always-present widget from requiring Node/npm/tsc,
  consistent with this project's established direction.
- **Regex-stripped ANSI, not a real terminal emulator.** A correct VT100
  emulator either needs real effort (out of scope for "a real PTY the
  user can run commands in") or a third-party library (`pyte`), which
  `CLAUDE.md` asks to avoid absent a strong reason. Accepting that
  full-screen TUI programs won't render correctly is the honest tradeoff
  for keeping this dependency-free and simple; noted as a real limitation,
  not hidden.
- **`QSocketNotifier`, not a reader thread.** Keeps PTY I/O fully
  integrated with the Qt event loop (no cross-thread signal marshalling
  needed to get bytes from a background thread onto the GUI thread) —
  simpler and more consistent with how this project already prefers
  event-driven I/O.
- **Cleanup via the `destroyed` signal, not a `closeEvent`/explicit
  "close" method.** `closeEvent` is for top-level windows, not arbitrary
  child widgets being destroyed (e.g. by hot reload or a Desk switch);
  `destroyed` is the one signal guaranteed to fire whenever the widget
  actually goes away, regardless of *why*.
