# Global crash-log handler (COMPLETED)

TODO `95f7ce9`.

## Summary

"Add a global error handler: on an uncaught exception anywhere in the
app, attempt to append the stack trace to a file called
`DESK-CRASH-[timestamp].log` in the project folder. Must not itself
"further crash" if writing that log fails for any reason."

A new `desk.crash_handler` module installs a custom `sys.excepthook`
(chained to whatever was previously installed, normally Python's own
default) from `desk.app.main()`, as early as possible. On any uncaught
exception, it formats the traceback and appends it to
`DESK-CRASH-<timestamp>.log` in "the project folder" -- the current
Desk's associated directory if one is known yet, else the process's
current working directory (the same fallback shape `_doc_path()`
already uses in `widgets/claude/widget.py`, and consistent with how
`desk.app.main()` already treats `Path.cwd()` as the default project
root before any Desk is loaded). Any failure while doing this (can't
resolve a directory, can't write, whatever) is swallowed silently --
this handler's own job is strictly additive logging, never a new
failure mode.

## Investigation

Confirmed directly (not assumed) that `sys.excepthook` is actually the
right, sufficient mechanism here, for both of the two ways an
"uncaught exception anywhere in the app" can arise in this codebase:

- A same-thread Qt slot (e.g. `QTreeView.doubleClicked` -> a connected
  Python method) that raises: reproduced with a real `QApplication` and
  a real `QPushButton.clicked` slot raising -- the custom hook fires
  with the real exception, and the process does not abort.
- A cross-thread, queued-connection signal (e.g. a background
  `watchdog`-thread callback emitting into a GUI-thread slot, matching
  `HotReloadBroker`'s own real shape) whose slot raises: reproduced with
  a real `QCoreApplication`, a background thread emitting into a
  queued-by-default cross-thread signal -- same result, hook fires, no
  abort.

(This doesn't contradict `plans/isolate-hot-reload-crash.md`'s own
documented, directly-confirmed real crash for the hot-reload case
specifically -- that finding stands for its own exact scenario. It just
establishes that `sys.excepthook` itself is a reliable enough general
mechanism to build this TODO's logging on, regardless of whether a
given uncaught exception happens to additionally destabilize the
process afterward.)

## Key decisions

- **`sys.excepthook`, not a `faulthandler`-based signal handler.** The
  TODO's own wording ("on an uncaught exception") describes a Python
  exception, which is exactly what `sys.excepthook` is for. A genuine
  OS-level fault with no Python exception involved at all (a true
  native segfault, no traceback -- see `PARKINGLOT.md`'s Desk Picker
  crash note) is a different, heavier mechanism (`faulthandler`,
  designed around one long-lived pre-opened file handle, not a fresh
  per-crash timestamped filename) that isn't what was asked for here --
  not pursued, to avoid solving a problem nobody described yet.
- **Chain to the previously-installed hook (normally `sys
  .__excepthook__`), don't replace it.** Preserves the existing
  stderr-traceback behavior every developer already relies on; this
  handler is purely additive (extra file logging), never a behavior
  regression.
- **"The project folder" = `current_context
  .get_current_desk_directory()`, falling back to `Path.cwd()`.**
  Mirrors the existing fallback shape in `widgets/claude/widget.py`'s
  `_doc_path()`, and matches `desk.app.main()`'s own existing use of
  `Path.cwd()` as the default project root before any Desk is loaded
  (exactly the situation where a startup-time crash, with no current
  Desk directory set yet, is otherwise most likely to have nowhere
  sensible to log to).
- **Append mode, not overwrite, despite the per-crash timestamped
  filename.** Each crash normally gets its own uniquely-named file, so
  there's usually nothing to append to -- but two exceptions in the
  same rounded second (rare, not impossible: a queued signal delivering
  a second bad callback moments after a first crash's hook is still
  running) would otherwise silently clobber one occurrence. Opening
  `"a"` costs nothing in the common case and avoids that edge case.
- **The entire body is one `try`/`except Exception: pass`.** Not
  `except OSError` or similar narrower catch -- literally anything going
  wrong while trying to log (a bad path, a permissions error, an
  encoding problem formatting the traceback itself) must never become a
  *second* uncaught exception inside the exception handler.
- **New module (`desk/crash_handler.py`), not inline in `app.py`.**
  Keeps it independently testable (a plain function, no `QApplication`
  needed to exercise it) and matches this codebase's convention of
  small, focused `desk.` modules for cross-cutting concerns
  (`desk.file_watch`, `desk.git_utils`, etc.).
- **Installed once, idempotently, from `desk.app.main()`** -- as early
  as possible (before constructing `QApplication`), so even a startup
  -time exception is covered.

## Affected files

- `src/desk/crash_handler.py` (new) -- `install()`, internal
  `_log_path()`/`_handle_exception()`.
- `src/desk/app.py` -- `main()` calls `crash_handler.install()` first
  thing.

## Verification

Headless, no `QApplication` needed for the core logic:

- `install()` is idempotent (calling it twice doesn't double-chain or
  lose the original hook).
- Triggering `sys.excepthook` (calling it directly with a real
  exception's `(type, value, traceback)`, the same way Python's runtime
  does) writes a `DESK-CRASH-<timestamp>.log` file containing the
  formatted traceback, in a temp directory stood in for "the project
  folder" via `current_context.set_current_desk_directory`.
- With no current Desk directory set, the log lands in `Path.cwd()`
  instead (temporarily `chdir`'d to a temp directory for the test).
- The previously-installed hook (a stand-in recording calls) still
  fires afterward, with the same exception info, confirming chaining
  works.
- Forcing the log-write step itself to raise (e.g. an unwritable
  directory) confirms `_handle_exception` swallows it and still calls
  through to the previous hook, rather than raising a second exception.
- Real end-to-end sanity check, matching the investigation above: a
  real `QApplication`/`QPushButton.clicked` slot that raises, with
  `crash_handler.install()` active, produces a real log file and the
  process keeps running.

## Status

Implemented as planned: `src/desk/crash_handler.py` (`install()`,
`_log_path()`, `_handle_exception()`), wired into `desk.app.main()` as
the very first thing it does.

All headless verification steps above passed: idempotent install;
writes `DESK-CRASH-<timestamp>.log` (containing the real formatted
traceback) into the current Desk directory when one is set; falls back
to `Path.cwd()` when none is set; chains to and still invokes the
previously-installed hook; survives the log-write step itself being
forced to raise, without losing the chained call. Also ran a real
end-to-end check with an actual `QApplication`/`QPushButton.clicked`
slot raising: a real log file was written and the process kept running
afterward.

No `LEARNINGS.md` entry needed -- the one non-obvious finding from this
work (that `sys.excepthook` reliably fires for both same-thread and
cross-thread-queued Qt slot exceptions, without the process necessarily
aborting) is recorded in this plan's own Investigation section, and
doesn't contradict or need to revise the existing, differently-scoped
"isolate-hot-reload-crash" finding.
