# Claude widget: quitting claude closes the widget (not drop to a shell) (COMPLETED)

TODO `5ddbef0`.

## Answers to the questions

- *Does claude need to run in the context of a shell?* Not strictly, but
  running it via a shell is deliberate (TODO 6907120): a real login/
  interactive `bash` loads the user's profile (`PATH`, `nvm`, aliases,
  etc.) first, so `claude` is found and runs the same way it would from a
  real terminal. Keeping that is worthwhile.
- *Is there a way to force the shell to exit when claude exits?* Yes —
  `exec`. Typing `exec claude …` makes bash **replace itself** with
  claude in the same PTY process once its profile has loaded, so when
  claude quits the PTY ends (there's no shell to fall back to). Bonus:
  if `claude` isn't found, bash's `exec` fails and the interactive shell
  *stays* (bash prints "not found" and continues), so the existing
  "shell stays usable if claude is missing" safety is preserved.

So this is two changes: launch claude with `exec`, and make the widget
actually close when its PTY process exits.

## Fix

1. **`widgets/claude/widget.py`** — prefix both `start_session`
   commands with `exec ` (`exec claude --session-id … --permission-mode
   auto "<prompt>"` and `exec claude --resume … --permission-mode
   auto`).
2. **`src/desk/terminal_widget.py`** — add a `process_exited =
   pyqtSignal()` and emit it in `_on_readable` when the PTY read returns
   EOF (empty), alongside the existing `[process exited]` text (harmless
   for the Console widget, which nobody connects it for).
3. **`src/desk/shell/window.py`** — in `_bind_claude_widget`, connect the
   claude widget's `process_exited` to close its own frame:
   `close_widget_by_instance_id(frame.instance_id)` (no confirmation,
   removes + saves), **deferred** via `QTimer.singleShot(0, …)` so the
   removal doesn't happen synchronously inside the `QSocketNotifier`
   callback that detected EOF (deleting the widget out from under its own
   running notifier). Only the claude widget wires this up; the Console
   widget keeps its current "show `[process exited]`, stay put" behavior.

## Scope

- Only the claude widget auto-closes; the Console widget is unchanged
  (exiting its bash just shows `[process exited]`).
- The hot-reload caveat (post-build binding, incl. this signal
  connection, is lost when `widgets/claude/widget.py` is itself
  hot-reloaded) already applies and is parked in `PARKINGLOT.md`.

## Affected files

- `widgets/claude/widget.py`, `src/desk/terminal_widget.py`,
  `src/desk/shell/window.py`.
- `design-docs/architecture.md` — update the Claude Widget entry (exec +
  close-on-exit; the "shell stays usable" note now refers specifically
  to the claude-not-found case).

## Verification

Headless:
- `start_session` (fresh and resume) types an `exec claude …` command
  (still containing `--session-id`/`--resume`, `--permission-mode auto`,
  and — fresh only — the prompt).
- `TerminalWidget` emits `process_exited` when its child process exits
  (run a short-lived command, e.g. `["true"]`, and confirm the signal
  fires once the PTY hits EOF).
- Full-app: place a claude widget in a real `DeskWindow` (with a fake,
  immediately-exiting `claude`/PTY), and confirm that when the process
  exits the widget's frame is removed from the canvas (and the desk
  saved) rather than left showing a shell.

## Status

**Completed.** Implemented and verified headlessly: `start_session`
types `exec claude …` (fresh and resume); `TerminalWidget` emits
`process_exited` when its child exits (PTY EOF); and, in a full-app
`DeskWindow`, a claude widget's frame is removed when its process exits.
(A test-only `wait_for` bug initially masked check 3 — the production
close path was correct throughout, confirmed by repeated runs.)
`design-docs/architecture.md`'s Claude Widget entry updated.
