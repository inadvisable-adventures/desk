# Desk Proc mechanism (TODO `97bd090`)

## Summary

A new tempui DSL keyword, `DeskProc`, lets an agent drop a one-time
Python script into `.desk_temp` that runs with real, in-process access
to Desk's own live shell state -- not just a `kind: "html"` widget's
capability-scoped Bridge API. The motivating example: reveal a
specific already-placed widget instance (the same action as clicking
its titlebar eye button) and then take a real pixel screenshot of it,
saving a PNG to disk. Close sibling of the existing `Job` mechanism
(TODO `d7e66f6`) -- reuses its tempui-file -> notification -> placed
one-shot-runner-widget -> Start-button -> background-thread-exec shape
and its `.desk_temp`-cache-subdir materialization convention -- but is
its own keyword and widget kind, because (a) it needs a real,
documented, thread-safe way to touch GUI-thread-owned Qt state, which a
generic `Job` has no reason to grow, and (b) its notification must look
clearly different from an ordinary tempui placement notification and
be clearly labelled "Desk Proc," per direct user request -- today every
tempui kind (`Job` included) renders through the same plain-text
banner.

## Affected files

- `src/desk/temp_ui.py` -- `DESK_PROC_KEYWORD`, `DeskProcDefinition`,
  `parse_desk_proc`, `detect_temp_ui_kind`'s new `"desk_proc"` branch,
  `RESERVED_TEMPUI_KEYWORDS`, a new split doc (`tempui-desk-proc.md`) +
  `TEMPUI_DOC_VERSION` bump + `_NEW_FEATURES_DOC` entry +
  `DOC_TEMPLATE`'s file-type list (nine -> ten).
- `src/desk/desk_proc.py` (new) -- materializes a `DeskProcDefinition`'s
  script to a real file, mirroring `desk.jobs` exactly but under its
  own `desk_procs/` cache subdir.
- `src/desk/shell/current_context.py` -- one new hook,
  `set_gui_thread_caller`/`get_gui_thread_caller`.
- `src/desk/shell/window.py` -- `DESK_PROC_RUNNER_WIDGET_ID`, added to
  `TEMP_UI_WIDGET_IDS`; `_temp_ui_widget_id_for`/`_notify_temp_ui` gain
  a `"desk_proc"` branch (the latter now also picks a `banner_style`);
  wires `current_context.set_gui_thread_caller(self._handle.gui_bridge.call)`
  in `__init__`; two new methods, `screenshot_widget_instance(instance_id,
  path) -> bool` and `screenshot_desk(path) -> bool`.
- `src/desk/shell/canvas.py` -- `WorkspaceView.notify_temp_ui` gains a
  `banner_style` passthrough parameter.
- `src/desk/shell/temp_ui_notifications.py` -- `_NotificationBanner`/
  `TempUiNotificationStack.notify` gain a `banner_style` parameter
  (`"default"` | `"desk_proc"`) that changes both the border color and
  adds a bold, non-selectable "DESK PROC" caption line.
- `widgets/desk_proc_runner/` (new) -- `widget.json` + `widget.py`.
- `tests/verify/` -- new coverage.

## Design decisions

- **Tempui file format is a simplified `Job`**: first line
  `DeskProc<TAB>summary`, one or more `Script<TAB>base64-chunk` lines
  (concatenated in file order, same chunking convention `Job`'s own
  `Script` lines and `DefineWidget`'s own `Html` lines already use). No
  `kind`/`Capability` lines at all -- unlike `Job`, there is no
  `html`-kind variant: the entire point of `DeskProc` is direct,
  unsandboxed access to the live Desk shell, which a `kind: "html"`
  page structurally cannot have. If a script genuinely only needs
  capability-scoped Bridge API access, `Job` already covers that case;
  reach for `DeskProc` specifically when the script needs to act on
  Desk's own shell (reveal/screenshot a widget, and whatever else this
  grows to need later).
- **Same one-file-one-instance shape as `Job`/Scratch/Question**, bound
  via the existing `_bind_temp_ui_content` fallback
  (`elif hasattr(content, "set_source_file")`) with zero changes to
  that function -- the Desk Proc Runner widget re-parses its own source
  file directly via `desk.temp_ui.parse_desk_proc`, exactly like
  `widgets/job_runner/widget.py` already does for `parse_job`.
- **Execution is the same background-thread direct-exec `Job`'s
  `python`-kind already established** (a fresh module namespace,
  `desk` importable, stdout/stderr/exceptions captured via a
  `pyqtSignal` relay) -- copied, not reused via import, since
  `_run_python_job` is a private module-level function in
  `widgets/job_runner/widget.py`, and `widgets/<id>/` modules aren't
  meant to import each other. The one addition: the exec namespace also
  gets a `deskproc` global (see below), which a `Job` script's
  namespace has no reason to carry.
- **`deskproc` is a small, curated, documented object, not "you get the
  same raw process access, good luck"** -- unlike a `Job`, whose docs
  explicitly say "no sandboxing, same access any other code already
  running in this process has," a `DeskProc` script's *documented*
  interaction surface is this object (nothing stops a script from also
  `import`-ing internals directly, same trust level as a `Job` -- this
  doesn't add a new capability boundary, just a safe, ergonomic,
  discoverable front door for the two motivating actions):
  - `deskproc.reveal_widget(instance_id: str) -> bool` -- thin wrapper
    over the already-existing `zoom_to_widget_by_instance_id` (TODO
    `7505703`), just called safely from a background thread.
  - `deskproc.screenshot_widget(instance_id: str, path: str) -> bool`
    -- new `DeskWindow.screenshot_widget_instance`.
  - `deskproc.screenshot_desk(path: str) -> bool` -- new
    `DeskWindow.screenshot_desk`.
  - `deskproc.list_widget_instances() -> list[dict]` -- thin wrapper
    over the already-existing `DeskWindow.get_state_dict()` (the same
    data `desk.workspace.getState()` already exposes to `kind: "html"`
    widgets), so a script has a real way to discover instance ids
    rather than needing them handed in externally.
  All four route through the new `current_context.get_gui_thread_caller()`
  hook for thread safety (see below) -- none of them touch a Qt object
  directly from the calling (background) thread.
- **Thread safety reuses the exact primitive the Local Web Server
  already relies on for this same problem**, rather than inventing a
  second one: `desk.shell.bridge.GuiBridge.call(fn)` is already
  documented as callable "from any other thread" (see its own
  docstring) -- it's constructed on the GUI thread and attached to the
  live `DeskWindow` once, at `src/desk/app.py:50`
  (`handle.gui_bridge.attach(window)`), and every existing Bridge API
  route already synchronously calls into `DeskWindow` methods through
  it (`app.py`'s own `run_on_gui`). The only gap is that nothing before
  now let *in-process* Python code (as opposed to an HTTP request
  handler) reach it -- `set_gui_thread_caller`/`get_gui_thread_caller`
  closes that gap, the same minimal get/set-pair shape every other
  `current_context` hook already uses. `DeskWindow.__init__` sets it to
  `self._handle.gui_bridge.call` directly -- no new object, no new
  threading primitive.
- **`screenshot_widget_instance` grabs the target `WidgetFrame` itself**
  (titlebar + content, `frame.grab()`) rather than just its inner
  `.content` -- a truer "what you'd see on the canvas" screenshot,
  useful for confirming which widget it is at a glance. **`screenshot_desk`
  grabs `self.view` (the `WorkspaceView`/canvas viewport), not `self`
  (the whole `QMainWindow`)** -- deliberately different from
  `widgets/feedback/widget.py`'s existing `_take_screenshot` (which
  grabs the whole main window, `.grab()` on `current_context
  .get_main_window()`, useful there for a bug report that might need to
  show a dialog or other window chrome) -- for a Desk Proc, the canvas
  content is what an agent actually wants to see; native window chrome
  (menu bar, etc.) is noise. Both use the exact `.grab()` -> `QPixmap`
  -> `.save(path, "PNG")` idiom the Feedback widget already established
  as this codebase's one existing screenshot precedent.
- **Both screenshot methods resolve `path` the same way `desk.fs.*`
  already does**: an absolute path is used as-is; a relative one
  resolves against `self.current_desk.directory`. Parent directories
  are created (`mkdir(parents=True, exist_ok=True)`) before saving,
  mirroring `desk.fs.writeFile`'s own "never silently reject a write to
  a not-yet-existing directory" fix (TODO `ad20867`). Both return
  `False` on any failure (frame not found, `QPixmap.save` returning
  `False`) rather than raising -- a script can check the return value
  without needing to catch a Desk-internal exception type.
- **The notification's visual distinction is a threaded parameter, not
  a parallel notification widget.** `_NotificationBanner` gains
  `banner_style: str = "default"`; `"desk_proc"` selects a distinct
  border color (amber, `#e0a030`, vs. the existing blue `#3daee9`) and
  adds a bold, separate "DESK PROC" caption `QLabel` above the summary
  text -- two structurally different things (a badge line plus a color
  change), not just a color tweak, so it reads as clearly different at
  a glance even before the text is read. The caption label is
  non-selectable (`Qt.TextInteractionFlag.NoTextInteraction`), matching
  this project's own "labels aren't user-selectable" convention
  (`CLAUDE.md`) -- the existing summary/close-button labels in this
  same file already follow it. `TempUiNotificationStack.notify` and
  `WorkspaceView.notify_temp_ui` just thread the same parameter through
  unchanged otherwise.

## Step-by-step implementation

1. `temp_ui.py`: `DESK_PROC_KEYWORD = "DeskProc"`, add to
   `RESERVED_TEMPUI_KEYWORDS`; `DeskProcDefinition` dataclass
   (`summary`, `script_b64`); `parse_desk_proc(text)` mirroring
   `parse_job` minus the `kind`/`Capability` handling; `detect_temp_ui_kind`
   gains a `"desk_proc"` branch.
2. `desk_proc.py` (new): `DESK_PROC_CACHE_DIRNAME = "desk_procs"`,
   `desk_proc_dir(desk_temp_dir, proc_id)`,
   `PYTHON_DESK_PROC_ENTRY_FILENAME = "script.py"`,
   `SOURCE_VIEW_FILENAME = "desk_proc_source.py"`, `materialize`,
   `materialize_script_body` -- same shape/tolerance as `desk.jobs`'s
   equivalents (malformed base64/UTF-8 logged and returns `None`, never
   raises).
3. `current_context.py`: `set_gui_thread_caller`/`get_gui_thread_caller`
   hook pair, matching `set_html_job_starter`'s shape (a plain
   `Callable[[Callable[[], Any]], Any] | None`).
4. `window.py`: wire `current_context.set_gui_thread_caller(self._handle
   .gui_bridge.call)` in `__init__` alongside the other hooks;
   `screenshot_widget_instance(self, instance_id: str, path: str) ->
   bool` and `screenshot_desk(self, path: str) -> bool` per the Design
   decisions above; `DESK_PROC_RUNNER_WIDGET_ID = "desk_proc_runner"`,
   added to `TEMP_UI_WIDGET_IDS`; `_temp_ui_widget_id_for` gains a
   `"desk_proc"` branch; `_notify_temp_ui` gains a `"desk_proc"` branch
   (`text = f"Desk Proc: {summary}"`) and its final `self.view
   .notify_temp_ui(...)` call gains a `banner_style="desk_proc" if kind
   == "desk_proc" else "default"` argument.
5. `canvas.py`: `WorkspaceView.notify_temp_ui(self, path, text,
   on_clicked, banner_style="default")` passes `banner_style` through
   to `self.temp_ui_notifications.notify(...)`.
6. `temp_ui_notifications.py`: add `DESK_PROC_BANNER_STYLE` (same shape
   as `BANNER_STYLE`, amber border); `_NotificationBanner.__init__(self,
   text, banner_style="default", parent=None)` picks the stylesheet and
   conditionally adds the "DESK PROC" caption label;
   `TempUiNotificationStack.notify(self, path, text, on_clicked,
   banner_style="default")` threads it through to the banner
   constructor.
7. `widgets/desk_proc_runner/widget.json` + `widget.py`: near-copy of
   `widgets/job_runner/`'s summary/View-Code/Start/status shape, minus
   the `kind` branch (always the background-thread-exec path);
   `_DeskProcApi` (or equivalent small class/closure set) builds the
   `deskproc` global from `current_context.get_gui_thread_caller()` +
   `current_context.get_main_window()`, injected into the exec globals
   dict alongside `desk`'s own ambient importability.
8. `temp_ui.py` doc work: `_DESK_PROC_DOC` (new split doc,
   `tempui-desk-proc.md`, modeled on `_JOBS_DOC`'s shape -- format, an
   example file, the `deskproc.*` API surface, and an explicit note
   that this is Python-only/no sandboxing, same trust level as `Job`);
   add to `SPLIT_DOC_CONTENT`; `DOC_TEMPLATE`'s file-type list gains a
   `DeskProc` bullet (nine -> ten built-in file types) linking to it;
   bump `TEMPUI_DOC_VERSION` (matching comment block) and add a
   `_NEW_FEATURES_DOC` entry.
9. New/extended verify coverage (see below); run the full
   `tests/verify/` suite.

## Key tradeoffs

- No `html`-kind variant, by design (see Design decisions) -- a
  `DeskProc` that only needs Bridge API access should use `Job`
  instead.
- `deskproc.*` is a curated convenience surface, not a real sandbox --
  a script can still `import` internal `desk.*` modules directly and
  bypass it entirely, the same "View Code is the only review step"
  trust level this project already accepted for `Job`. This is a
  deliberate non-goal, not an oversight: building a real sandbox is a
  much bigger, separate concern this lightweight mechanism doesn't
  attempt.
- `deskproc.list_widget_instances()` only exposes what `desk.workspace
  .getState()` already exposes to any `kind: "html"` widget with the
  `workspace` capability -- no new information is surfaced that wasn't
  already reachable some other way.
- Like `Job`, a run `DeskProc` file/its `desk_procs/<id>/` cache
  directory is never cleaned up automatically, and once started, Start
  stays disabled forever (a fresh `DeskProc` file is needed for a
  second run) -- consistent with the "a run Job file is kept, not
  deleted" precedent.

## Verification

New checks, real (no mocking):
- `tests/verify/verify_desk_proc_tempui_parsing.py` (new):
  `parse_desk_proc` round-trips summary/script through the real DSL
  text shape (single- and multi-chunk `Script` lines); rejects garbage
  (no keyword, no `Script` lines); `detect_temp_ui_kind` returns
  `"desk_proc"`; `DESK_PROC_KEYWORD` is in `RESERVED_TEMPUI_KEYWORDS`.
- `tests/verify/verify_desk_proc_materialize.py` (new):
  `desk_proc.materialize` writes a real `script.py` under
  `desk_procs/<id>/`, and returns `None` (logged) for malformed
  base64; `materialize_script_body` writes a real, distinctly-named
  plain-text file.
- `tests/verify/verify_desk_proc_runner_widget.py` (new, real `QWidget`
  construction): `set_source_file` against a real `DeskProc` tempui
  file updates the summary display; Start actually runs a real script
  on a background thread (pumped via `app.processEvents()`) and the
  status display reaches "done" with captured stdout, or "errored"
  with a captured traceback for a script that raises; the injected
  `deskproc` global's four methods are real callables in the executed
  script's namespace and route through a fake
  `current_context.get_gui_thread_caller()` (recording calls, since a
  full Qt canvas isn't needed to prove the wiring); persisted status/
  interrupted-on-reload/`has_unsaved_local_edits`/View Code all mirror
  `verify_job_runner_widget.py`'s equivalent checks.
- `tests/verify/verify_desk_proc_notification_routing.py` (new, mirrors
  `verify_job_notification_routing.py`): `DESK_PROC_RUNNER_WIDGET_ID` is
  in `TEMP_UI_WIDGET_IDS`; `_temp_ui_widget_id_for` resolves a real
  `DeskProc` file to it; `_notify_temp_ui` composes the `"Desk Proc:
  ..."` text and passes `banner_style="desk_proc"` (a fake `view
  .notify_temp_ui` records its args) -- contrasted with an ordinary
  `Question`/`Scratch` file passing `banner_style="default"`.
- `tests/verify/verify_desk_proc_notification_banner.py` (new, real
  `QWidget` construction): a `banner_style="desk_proc"` banner shows a
  real, non-selectable "DESK PROC" caption label and a different
  stylesheet than `banner_style="default"`'s.
- `tests/verify/verify_desk_proc_screenshot.py` (new, real `WidgetFrame`
  placement via the same `_FakeWindow`/`_place_widget`-binding harness
  `verify_widget_error_indicator.py` already establishes):
  `screenshot_widget_instance` saves a real, non-empty PNG file for a
  real placed frame and returns `False` for an unknown instance id;
  `screenshot_desk` saves a real PNG of the canvas viewport; both
  resolve a relative path against `current_desk.directory` and create
  missing parent directories, mirroring `desk.fs.writeFile`'s own
  fix.
- `tests/verify/verify_tempui_desk_proc_doc.py` (new, mirrors
  `verify_tempui_jobs_doc.py`): `TEMPUI_DOC_VERSION` bumped;
  `tempui-desk-proc.md` covers the file format and the `deskproc.*` API
  surface; `DOC_TEMPLATE`'s file-type list references it; `_NEW_FEATURES_DOC`
  has a matching entry.
- Full `tests/verify/` regression suite.
