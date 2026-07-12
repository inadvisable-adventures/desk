# Consolidate self-write suppression; give the Editor widget external-change detection

TODO `cee6f74`.

## Summary

Two asks, bundled into one item because the second is only easy *because*
of the first (and both TODO 578cb6b) existing:

1. `TempUiManager` and the TODO widget currently each have their own,
   independently-written copy of "remember the text I just wrote myself,
   and suppress the next change notification if the file's fresh content
   matches it" (`TempUiManager._last_written`/`record_own_write` vs. the
   TODO widget's own `state["last_written_text"]` compared inline in
   `_on_external_change`). `SingleFileWatcher` *also* already grew its own
   third copy of this exact idea (`record_own_write`, added by TODO
   578cb6b) -- but the TODO widget was never actually switched onto it,
   so today there are three independent implementations of one concept,
   one of which (`SingleFileWatcher.record_own_write`) is dead code as
   far as its only intended caller goes.
2. The Editor widget (`widgets/editor/`, the "raw file editor") does not
   watch its open file at all today -- so if the TODO widget writes
   `TODO.md` while that same file happens to be open in an Editor widget
   instance, the Editor widget never finds out. Since every watcher in
   the app now schedules onto one shared, de-duplicating
   `desk_services.file_watcher` service (TODO 578cb6b), giving the Editor
   widget a `SingleFileWatcher` of its own on whatever file it has open
   costs nothing extra at the service level -- both watchers already
   share one native FSEvents schedule on that file's parent directory
   and each independently filters down to its own exact target path (this
   filtering already lives inside `SingleFileWatcher.watch`'s closure,
   see `desk/file_watch.py`) -- so this "just works" once the Editor
   widget adopts the same `SingleFileWatcher` pattern every other
   file-backed widget already uses.

## Key decisions

- **No "base widget class."** There isn't one today -- every widget
  (`EditorWidget`, `TodoWidget`, `MarkdownWidget`, ...) subclasses
  `QWidget` directly, and `TempUiManager` isn't a widget at all (it's a
  plain `QObject` owned once per `DeskWindow`, feeding the Question
  Widget via signals -- see `design-docs/architecture.md`). Retrofitting
  a shared widget base class just for this would be a much bigger,
  riskier change than the actual duplicated logic justifies, and
  wouldn't even help `TempUiManager`. Instead, following this codebase's
  existing convention for cross-widget-directory shared logic (widget
  directories can't import each other; shared code lives in `desk.`
  proper -- `desk.file_watch.SingleFileWatcher`,
  `desk.terminal_widget.TerminalWidget`, `desk.todo_file`,
  `desk.temp_ui`), the self-write bookkeeping itself gets a small shared
  helper in `desk/file_watch.py` (the existing home for watcher-adjacent
  shared logic), used internally by both `SingleFileWatcher` and
  `TempUiManager`.
- **New internal helper, not a new public API.** `desk/file_watch.py`
  gains a small `_SelfWriteMemory` class: `record(key, text)` /
  `is_own_write(key, text) -> bool`, wrapping a single `dict[Hashable,
  str]`. `SingleFileWatcher` uses it internally (keyed by its one
  resolved target path) in place of its current single `_expected_write`
  field; `TempUiManager` uses it internally (keyed by filename, matching
  its current dict) in place of its own `_last_written` dict. Both
  classes' existing public `record_own_write(...)` signatures are
  unchanged -- this is purely an internal de-duplication, not a new
  capability.
- **The TODO widget switches onto `SingleFileWatcher.record_own_write`
  instead of its own parallel check**, finally making that method a real,
  used piece of code rather than dead weight added-but-unused by TODO
  578cb6b. `_write_and_commit` (deliberately a module-level function, not
  a method -- see its own docstring: it must be safely callable from the
  `destroyed`-triggered teardown closure without touching `self` or any
  Qt child object) gains an optional `watcher: SingleFileWatcher | None`
  parameter; every call site passes `self._watcher` (the teardown
  closure already captures `watcher = self._watcher` as a local before
  teardown, so it can pass that captured reference without ever going
  through `self`). When given, `_write_and_commit` calls
  `watcher.record_own_write(text)` at the exact point
  `state["last_written_text"]` is set today (synchronously, right after
  `todo_path.write_text(text)`, before the background git-commit thread
  starts) -- same timing TODO 578cb6b's plan originally called for.
  `state["last_written_text"]` and the manual compare in
  `_on_external_change` are then deleted entirely: suppression happens
  once, inside `SingleFileWatcher`, before `changed` ever fires, so
  there's nothing left for the widget to re-check.
- **Editor widget gets a `SingleFileWatcher`**, same shape as the
  Markdown/Markdown (Extended)/SVG Viewer/TODO widgets' now-standard
  pattern (`self._watcher = SingleFileWatcher(self)`, watched/re-targeted
  inside `_load_file` -- which both `_open_file` and the public
  `set_file` already funnel through -- plus `_save_file_as`, which
  assigns `self._current_path` directly without going through
  `_load_file`). `_save_file` and `_save_file_as` both call
  `self._watcher.record_own_write(self.editor.text())` right after
  writing, so the echo of the Editor's own save is suppressed exactly
  like every other self-write case in the app.
- **Reacting to an external change respects unsaved local edits --
  no clobbering, no interruptive dialog.** On an (unsuppressed)
  `changed` signal:
  - If the buffer has no unsaved edits (`not self.editor.isModified()`):
    reload silently, identical to the Markdown widget's unconditional
    reload -- there's nothing of the user's to lose.
  - If it does have unsaved edits: don't touch the buffer. Set an
    internal `_external_change_pending` flag and reflect it in the
    existing title label (e.g. `"TODO.md • (changed on disk)"`) so the
    user finds out next time they look at the widget, without an
    interruptive prompt. Cleared on the next successful save (a plain
    Save always wins over an on-disk change the user hasn't looked at,
    same as most editors) or the next full reload. This is deliberately
    lighter-weight than the TODO widget's own dialog-based edit-conflict
    resolution (`_resolve_edit_conflict`, which spawns a Scratch widget)
    -- that machinery exists for TODO items' own structured
    add/edit/reprioritize flow specifically, not a general-purpose
    pattern worth reusing here for a single free-text buffer.
  - Known, accepted limitation: an auto-reload resets the caret/scroll
    position (`QsciScintilla.setText` behavior, same as every other
    `_load_file` call today). Not addressed here -- not requested, and
    not a new regression (already true of every existing reload path,
    e.g. re-opening the same file).
- **Explicitly out of scope, per direct instruction**: any debouncing/
  throttling for a pathologically-high-frequency writer hammering a
  single watched file. `SingleFileWatcher`'s existing 0.3s debounce
  already covers ordinary bursts (the same debounce every consumer
  already relies on); a dedicated fix for a much higher sustained write
  rate is deferred until it's an actual observed problem, not designed
  for speculatively.

## New/affected files

- `src/desk/file_watch.py` -- new internal `_SelfWriteMemory` helper;
  `SingleFileWatcher` internals rewritten onto it (public API
  unchanged).
- `src/desk/shell/temp_ui_manager.py` -- internals rewritten onto the
  same `_SelfWriteMemory` helper (public API unchanged).
- `widgets/todo/widget.py` -- `_write_and_commit` gains the optional
  `watcher` parameter and calls `record_own_write`; every call site
  updated to pass `self._watcher`/the teardown closure's captured
  `watcher`; `state["last_written_text"]` and the manual compare in
  `_on_external_change` removed.
- `widgets/editor/widget.py` -- new `SingleFileWatcher` instance, watch/
  re-watch wiring in `_load_file`/`_save_file_as`, `record_own_write`
  calls in `_save_file`/`_save_file_as`, new `_on_external_change`
  handler wired to `changed`, `_external_change_pending` flag reflected
  in `_update_label`, teardown wiring (`destroyed` -> captured
  `watcher.stop()`, matching every other file-backed widget).
- `design-docs/architecture.md` -- Editor Widget entry (component 9)
  gains a short mention of the new file-watching/conflict-flagging
  behavior; File Watcher Service entry (component 19) gains a short
  mention of the shared `_SelfWriteMemory` helper.
- `LEARNINGS.md` -- an entry if verification surfaces anything
  surprising.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`/
`QCoreApplication`, no mocks -- same approach TODO 578cb6b's
verification used):

- `_SelfWriteMemory` in isolation: `record`/`is_own_write` round-trip
  correctly for multiple independent keys.
- `SingleFileWatcher`: existing debounce/idempotent-watch/
  `record_own_write` behavior unchanged (re-run TODO 578cb6b's own
  verification for this class).
- `TempUiManager`: `file_added`/`file_edited` classification and
  `record_own_write` suppression still behave identically after the
  internal swap (re-run TODO 578cb6b's own verification for this
  class).
- TODO widget: the same round-trip TODO 578cb6b verified (own write via
  `_write_and_commit` doesn't misfire `_on_external_change`; a real
  external edit does reload) still passes with `state
  ["last_written_text"]` removed and suppression happening inside
  `SingleFileWatcher` instead.
- Editor widget, the actual new behavior: open a file, edit externally
  with no local unsaved changes -- confirm silent reload and updated
  buffer content; open a file, make a local unsaved edit, then edit the
  same file externally -- confirm the buffer is *not* clobbered, the
  label reflects the pending conflict, and saving afterward both
  overwrites the file with the local content and suppresses the
  resulting self-write notification (via `record_own_write`).
- **The actual motivating scenario**: an Editor widget and a TODO widget
  both pointed at the same real `TODO.md` in a temp Desk directory (two
  independent `SingleFileWatcher`s on the same parent directory, per TODO
  578cb6b's de-duplication) -- the TODO widget performs a write-and
  -commit, and the Editor widget (with no local unsaved edits) picks up
  and reloads the change on its own, with no additional wiring beyond
  each widget owning its own `SingleFileWatcher`.

## Status

Not yet implemented.
