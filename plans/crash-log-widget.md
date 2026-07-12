# Crash logs move to .desk_temp/, auto-open as a Crash Log widget (COMPLETED)

TODO `7f51230`.

## Summary

Three parts:

1. `desk.crash_handler` (TODO `95f7ce9`) writes `DESK-CRASH-<timestamp>.log`
   into the current active project directory's `.desk_temp/` folder
   instead of the project directory itself.
2. On app startup, every existing crash log gets its own new "Crash
   Log" widget instance, opened automatically (not just left as a file
   sitting in a hidden directory).
3. The Crash Log widget reads a crash log's raw text and has a
   "Sanitize" button that strips OS/user-specific path prefixes down
   to (but keeping) the `src` or `.venv` directory a path contains --
   `/Users/alice/some-project/src/desk/foo.py` becomes
   `src/desk/foo.py`, making a log safe/convenient to paste elsewhere
   without leaking a local username or directory layout.

## Key decisions

- **Crash logs persist across restarts like any other placed widget,
  using the exact same "instance_id equals source filename"
  reconnection idea the tempui widgets already use** (TODO `a02b001`
  /`11aeb43`) -- `_load_desk_widgets` restores a saved `crash_log`
  -kind widget by re-binding it to `.desk_temp/<instance_id>` (its
  filename, not a DSL-detected uuid this time, since crash logs aren't
  tempui DSL content). This means: leaving a Crash Log widget open,
  saving, and restarting doesn't duplicate it -- it comes back via the
  normal restore path, not the startup-scan path.
- **Startup scan only opens a widget for a crash log that ISN'T
  already covered by a restored frame.** `_open_crash_log_widgets`
  (called once, after `_load_desk_widgets`/`_provision_temp_ui` in
  `__init__`) lists `.desk_temp/DESK-CRASH-*.log`, and for each one
  calls `find_frame_by_instance_id(path.name)` first -- only places a
  fresh widget if nothing already claimed that filename. Explicitly
  scoped to *app startup* only (matching the TODO's own wording), not
  re-run on every desk switch.
- **No auto-deletion or "seen" tracking beyond that.** If the user
  closes a Crash Log widget's frame (the normal titlebar ✕) without
  deleting the underlying file, it reopens on the *next* startup --
  deliberate, not a bug: the file's mere existence is the signal "this
  crash hasn't been triaged/cleared yet." A small "Delete Log File"
  button on the widget itself (confirmed via a dialog, mirroring
  existing confirm-before-destructive-action conventions in this file)
  is the actual way to make it stop reappearing -- deletes the file
  and closes the widget's own frame (wired the same way the Claude
  widget's `process_exited` signal already triggers
  `close_widget_by_instance_id`, not a new mechanism).
- **"Sanitize" transforms the widget's own displayed text, not the
  file on disk.** The original raw log stays untouched at all times --
  sanitizing produces a paste-safe *view*, not a destructive rewrite;
  clicking it more than once is a safe no-op past the first click
  (nothing left to strip a second time).
- **Path-stripping regex, not a stateful parser.** `/[^\s"']+` finds
  each absolute-path-looking run of text (stopping at whitespace or a
  quote, since traceback lines quote paths as `File "...", line N`);
  for each match, split on `/` and, scanning left to right, keep from
  the first segment that's exactly `src` or `.venv` onward -- a path
  containing neither is left unchanged (nothing safe to assume about
  it). `.venv`/`src` are a small, explicit, easily-extended list, not
  a general "look configurable" system -- this project only has these
  two.
- **Crash-log-directory creation is unconditional, no consent
  prompt.** `_provision_temp_ui`'s existing "create `.desk_temp`?"
  confirmation is for *agent-authored* temporary UI content; crash
  logging is a different, non-negotiable diagnostic concern that must
  never block or fail (see `crash_handler.py`'s own existing "must
  never itself introduce a new failure" contract) -- silently
  `mkdir`-ing `.desk_temp/` if it doesn't exist yet is the only
  approach consistent with that.

## Affected files

- `src/desk/crash_handler.py` -- `_log_path()` writes into
  `directory / TEMP_UI_DIRNAME`, creating that directory if needed.
- `widgets/crash_log/widget.py` (new) -- `CrashLogWidget`,
  `sanitize_crash_log(text) -> str`.
- `widgets/crash_log/widget.json` (new).
- `src/desk/shell/window.py` -- `CRASH_LOG_WIDGET_ID` constant;
  `_load_desk_widgets` restore handling for that widget id;
  `_bind_crash_log_widget`; `_open_crash_log_widgets` (called once in
  `__init__`).

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, real
files):

- `crash_handler._log_path()` resolves under `.desk_temp/`, and the
  directory is created if it didn't already exist.
- `sanitize_crash_log`: a path containing `src` is truncated to start
  there; a path containing `.venv` likewise; a path containing neither
  is left unchanged; a plain traceback line with a quoted path is
  handled correctly (no trailing quote/comma swallowed into the path).
- `CrashLogWidget`: `set_file` loads the log's raw text; clicking
  Sanitize updates the displayed text via the same function, without
  touching the file on disk; Delete Log File (confirmed) deletes the
  file and emits the dismiss signal.
- `DeskWindow._open_crash_log_widgets`/`_bind_crash_log_widget` (run
  unbound against a fake double, the established pattern for
  `DeskWindow`-dependent logic): a crash log file with no existing
  frame gets a fresh widget placed and bound; a crash log file whose
  instance_id already has a frame (simulating a desk-restore) is
  skipped, not duplicated.

## Status

Implemented as planned: `_log_path()` in `src/desk/crash_handler.py`
writes under `.desk_temp/`, creating it if needed; new
`widgets/crash_log/widget.py` (`CrashLogWidget`,
`sanitize_crash_log`) and `widgets/crash_log/widget.json`;
`CRASH_LOG_WIDGET_ID`/`CRASH_LOG_GLOB`, `_bind_crash_log_widget`,
`_open_crash_log_widgets` (called once in `__init__`, after
`_provision_temp_ui`), and a restore branch in `_load_desk_widgets`,
all in `src/desk/shell/window.py`. Also adds a new Crash Log Widget
entry (item 21) to `design-docs/architecture.md`.

Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real `QApplication`,
real files): `_log_path()` resolves under `.desk_temp/` and creates it;
`sanitize_crash_log` correctly truncates paths containing `src`/`.venv`
segments, leaves paths with neither unchanged, and is idempotent;
`CrashLogWidget.set_file` loads the raw text, Sanitize only changes
the displayed text (file on disk stays untouched), Delete Log File
(confirmed) deletes the file and emits `dismissed`, and a cancelled
confirmation does neither. `DeskWindow._open_crash_log_widgets`/
`_bind_crash_log_widget` (unbound methods on a fake double, the
established pattern for `DeskWindow`-dependent logic): a fresh crash
log gets a new widget bound to its file; a crash log already covered
by a restored frame (simulating a previous-session desk save) is not
duplicated; `_bind_crash_log_widget` wires `dismissed` to
`close_widget_by_instance_id` correctly.

Regression-checked: re-ran every other verification script from this
session (tempui-live-refresh, Questions-notification, drag-and-drop,
new-Desk-seeding, paste-clipboard-routing, `WidgetSpawnMenu`
grouping/keyboard-nav, MRU-file-existence) -- all still pass
unaffected.

No `LEARNINGS.md` entry needed -- nothing surprising here, just new
application logic built from already-established patterns (tempui
-style instance_id reconnection, the Claude widget's dismiss-signal
wiring, the fake-double `DeskWindow` test pattern).
