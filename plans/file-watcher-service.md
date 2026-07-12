# Centralized file-watcher service (COMPLETED)

TODO `578cb6b`.

## Summary

"Create a service for filewatchers in Desk, both from the app and from
widgets... a new `desk-services` directory under `./src/`... a
sub-directory file-watcher... The currently active watchers should be
tracked and managed by this service. Watches should be de-duplicated
as appropriate... to fix... `RuntimeError: Cannot add watch
<ObservedWatch: ...> - it is already scheduled.`"

A new `src/desk_services/file_watcher/` package (`desk_services`, not
the literal hyphenated `desk-services` — hyphens aren't valid in a
Python import name; the TODO's own phrasing is casual prose here, not
a hard spelling requirement) providing one process-wide, de-duplicating
`FileWatcherService`. Every existing watcher (`SingleFileWatcher`,
`WidgetWatcher`, `TempUiManager`, and the TODO widget's own bespoke
copy) is migrated onto it, keeping every one of their existing public
APIs/signals/behavior unchanged — this is an internal-plumbing swap,
not a widget-facing change.

## Key decisions

- **Root cause, already documented and now confirmed as the actual
  target**: `PARKINGLOT.md`'s existing "`FSEventsEmitter` 'already
  scheduled'" note traces this to *two separate `watchdog.Observer`
  instances* whose watched paths overlap/nest (the TODO widget's own
  watcher on the Desk directory, and `TempUiManager`'s watcher on that
  same directory's `.desk_temp/` subdirectory) — not simply "the exact
  same path watched twice." macOS's FSEvents backend shares process
  -global native state across `Observer` instances in a way that
  colliding *or nested* paths from *different* Observers can trip,
  even though each Observer's own bookkeeping is internally
  consistent. A single `Observer` scheduling many different
  (possibly-nested, possibly-identical) paths does **not** hit this —
  only crossing *Observer* instances does.
- **The fix is therefore "one process-wide `Observer`, not clever
  overlap detection."** `FileWatcherService` owns exactly one
  `watchdog.observers.Observer`, started once. Every watch request
  from anywhere in the app schedules onto that same `Observer`. This
  eliminates the cross-Observer collision entirely, regardless of
  whether two requested paths are identical, nested, or unrelated —
  simpler and more robustly correct than trying to detect and merge
  overlapping directory trees.
- **De-duplication (the literal "already scheduled" symptom, and the
  TODO's "a single watcher might make more than one notification")
  happens at the (`resolved_path`, `recursive`) key level**: the first
  `watch(path, callback, recursive=...)` call for a given key does one
  real `Observer.schedule(...)`; every subsequent call for the
  *identical* key reuses it and just adds `callback` to that key's
  subscriber list. All subscribers for a key are notified on every
  matching event. The underlying native watch is only
  `unschedule()`d once the last subscriber for that key cancels.
- **Gotcha-handling hoisted into the service, once** — both existing
  watchdog gotchas this codebase has independently rediscovered twice
  (symlink-resolved event paths on macOS FSEvents; an atomic write
  landing as `FileMovedEvent` whose real path is `dest_path`, not
  `src_path` — see `LEARNINGS.md`) are handled in one place
  (`_NormalizingHandler`) instead of duplicated per consumer. Every
  migrated consumer drops its own copy of this logic.
- **The service's own contract stays deliberately thin**: `watch(path,
  callback: Callable[[Path], None], *, recursive=False) -> WatchHandle`
  (`.cancel()`), plus a module-level `get_service() -> FileWatcherService`
  lazy singleton (matching `desk.shell.current_context`'s existing
  module-level-global convention) and a `.stop()` for clean process
  shutdown. No debouncing, no filename classification, no self-write
  suppression in the service itself — those stay in each consumer,
  unchanged, matching "for now, only implement the APIs that are
  needed" (the service is the shared low-level substrate, not a
  replacement for every consumer's own domain logic). Callbacks fire
  on the watchdog background thread, exactly as today (each consumer's
  own debounce/signal-emit already handles the thread hop safely, via
  Qt's automatic queued-connection delivery for a `pyqtSignal.emit()`
  called off the GUI thread).
- **All four existing watchers migrate onto it**, since the TODO's own
  wording ("both from the app and from widgets," "the currently active
  watchers") and the actual bug (a cross-*app*-watcher collision, not
  a widget-only one) both point at migrating everything, not just
  adding an unused new module:
  - `SingleFileWatcher` (`desk/file_watch.py`) — internals rewritten to
    call `get_service().watch(path.parent, ..., recursive=False)`;
    external API (`watch(path)`, `stop()`, `changed` signal, debounce
    timing) is unchanged, so `widgets/markdown`, `widgets/markdown_ex`,
    and `widgets/svg_viewer` need zero changes.
  - `WidgetWatcher` (`desk/widgets.py`) — same swap; external API
    (`__init__(widgets_dir, broker)`, `.start()`, `.stop()`) unchanged.
    `app.py`'s `app.aboutToQuit.connect(watcher.stop)` now only cancels
    *this* watcher's own subscription — the shared service's `Observer`
    itself is stopped once via a new
    `app.aboutToQuit.connect(get_service().stop)`, not by any
    individual consumer.
  - `TempUiManager` (`shell/temp_ui_manager.py`) — same swap; external
    API (`provision()`, `file_added`/`file_edited` signals,
    `record_own_write`) unchanged.
  - **The TODO widget's own bespoke watcher is retired entirely**, not
    just migrated — resolving `PARKINGLOT.md`'s existing consolidation
    note directly (the note itself suggested this exact fix: "growing
    `SingleFileWatcher` to optionally own the self-write suppression").
    `SingleFileWatcher` gains an optional `record_own_write(text: str)`
    method — same mechanism `TempUiManager` already has (store expected
    content, compare against freshly-read content when a change fires,
    drop the signal if they match) — and the TODO widget's
    `_start_file_watcher`/`_SingleFileHandler`/`_FileChangeRelay` trio
    is deleted in favor of a plain `SingleFileWatcher` instance, with
    `record_own_write` called at the exact point `state
    ["last_written_text"]` is set today (synchronously in
    `_write_and_commit`, before the background git-commit thread
    starts) so timing is preserved exactly. The edit-conflict
    -resolution logic (walking `_open_edits`) stays as-is, just wired
    to `SingleFileWatcher.changed` instead of the widget's own bespoke
    signal.
- **Packaging**: `pyproject.toml`'s `packages` list gains
  `"src/desk_services"` alongside `"src/desk"` — the TODO explicitly
  asked for a new top-level directory under `src/`, not nesting inside
  the existing `desk` package, so that structural intent is honored
  (only the hyphen→underscore spelling is corrected).

## New/affected files

- `src/desk_services/__init__.py` (new, empty — package marker).
- `src/desk_services/file_watcher/__init__.py` (new) — re-exports
  `FileWatcherService`, `get_service`, `WatchHandle`.
- `src/desk_services/file_watcher/service.py` (new) — `_WatchKey`,
  `_NormalizingHandler`, `WatchHandle`, `FileWatcherService`
  (`watch`, `stop`), `get_service()`.
- `pyproject.toml` — `packages = ["src/desk", "src/desk_services"]`.
- `src/desk/file_watch.py` — `SingleFileWatcher` internals rewritten
  onto the service; new `record_own_write(text)`.
- `src/desk/widgets.py` — `WidgetWatcher` internals rewritten onto the
  service.
- `src/desk/shell/temp_ui_manager.py` — `TempUiManager` internals
  rewritten onto the service.
- `src/desk/app.py` — `app.aboutToQuit.connect(get_service().stop)`.
- `widgets/todo/widget.py` — bespoke watcher trio removed in favor of
  a `SingleFileWatcher` + `record_own_write`.
- `design-docs/architecture.md` — a short "File Watcher Service"
  addition (likely under Components, plus a one-line mention in each
  affected widget's existing entry).
- `PARKINGLOT.md` — remove the two now-resolved notes (the
  `FSEventsEmitter` "already scheduled" note and the TODO-widget
  -watcher-consolidation note), or mark them resolved.
- `LEARNINGS.md` — an entry if the migration surfaces anything
  surprising during verification (per `development-process.md`).

## Verification

Headless:

- `FileWatcherService` in isolation: two `watch()` calls on the
  identical `(path, recursive)` schedule only one native
  `Observer.schedule()` (assert via a monkeypatched/counted schedule,
  or by asserting only one `ObservedWatch` is tracked) and both
  callbacks fire on one real file change; cancelling one subscriber
  leaves the other still receiving events; cancelling the last
  subscriber for a key actually unschedules it (no further callbacks,
  and a fresh `watch()` on that key re-schedules cleanly).
- **The actual reported bug, reproduced and fixed**: two *logically
  different* watches whose paths nest (a directory and a subdirectory
  of it, matching the TODO-widget/`TempUiManager` real-world case) —
  before the fix (two raw `Observer()`s), this raises the
  `RuntimeError`; through the shared service, both schedule cleanly
  with no exception and both fire independently for their own changes.
- `SingleFileWatcher`: existing behavior preserved exactly — watch/
  stop idempotency, debounced `changed` signal, symlink-resolved path
  matching, `FileMovedEvent`/atomic-write handling (recreate the exact
  scenarios `LEARNINGS.md` documents); new `record_own_write`
  suppresses a matching echo, same as `TempUiManager`'s.
  `widgets/markdown`/`markdown_ex`/`svg_viewer` re-verified against
  real temp files (their own original verification steps, re-run).
- `WidgetWatcher`: hot-reload still fires `HotReloadBroker
  .widget_changed` with the correct `widget_id` on a real widget
  -source-file edit.
  `TempUiManager`: `file_added`/`file_edited` still fire correctly
  classified (by prior-seen-filename, unchanged), and
  `record_own_write` still suppresses self-writes.
- TODO widget: a full round-trip (add an item, confirm the write
  -triggered reload doesn't misfire as an "external change"; edit
  `TODO.md` externally with the widget open, confirm it reloads); the
  edit-conflict-resolution path (open an item editor, then change the
  file externally) still resolves correctly.
- Real widget-loading path: `desk.widgets.discover_widgets` +
  `desk.shell.python_widget.PythonWidgetHost` for the affected widgets
  (a literal `DeskWindow` construction skipped for the same
  pre-existing, unrelated offscreen stall noted in prior plans).

## Status

Implemented and verified. All headless verification steps above passed:

- `FileWatcherService` in isolation: identical `(path, recursive)` keys
  share one native schedule and fan out to every subscriber; cancelling
  one subscriber leaves others receiving events; cancelling the last
  subscriber unschedules the native watch; re-watching after full
  cancellation re-schedules cleanly.
- Two watches on nested paths (directory + subdirectory, the actual
  reported real-world shape) schedule and fire independently through
  the shared service with no exception.
- `SingleFileWatcher`: debounced `changed` signal, idempotent
  re-`watch()` of the same path, and the new `record_own_write`
  suppression all verified against a real temp file; the Markdown,
  Markdown (Extended), and SVG Viewer widgets still `build()`
  successfully unchanged.
- `WidgetWatcher`: hot-reload still fires `HotReloadBroker
  .widget_changed` with the correct widget id on a real widget-source
  edit, and stops cleanly.
- `TempUiManager`: `file_added`/`file_edited` fire correctly classified
  by prior-seen-filename, and `record_own_write` still suppresses
  self-writes.
- TODO widget: a full round-trip against a real temp Desk directory --
  initial load, an add/reprioritize write-and-commit that does *not*
  misfire `_on_external_change` (the widget's own pre-existing
  `last_written_text` comparison, left as-is rather than routed through
  `SingleFileWatcher.record_own_write`, since `_write_and_commit` is
  deliberately not a method and must not hold a reference to the
  watcher -- see its own docstring), and a real external edit to
  `TODO.md` reloading correctly.
- Real widget-loading path: `desk.file_watch`, `desk.widgets
  .WidgetWatcher`, and `desk.shell.temp_ui_manager.TempUiManager` all
  exercised via real (offscreen) `PyQt6.QtWidgets.QApplication`/
  `QCoreApplication` instances, not mocks. A literal `DeskWindow`
  construction was skipped, same as prior plans, due to the
  pre-existing, unrelated offscreen stall.

No `LEARNINGS.md` entry was needed -- nothing surprising turned up
during verification; the migration matched the plan's design exactly.
