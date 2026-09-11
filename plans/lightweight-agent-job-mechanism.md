# Lightweight one-shot agent Job mechanism (TODO `d7e66f6`) (COMPLETED)

## Summary

A new tempui DSL keyword, `Job`, lets an agent drop a one-time script
into `.desk_temp` and run it with real widget-context capabilities --
notably Bridge API access for an `html`-kind job -- without building a
full `DefineWidget`/`widgets/<id>/` registration. Follows this
project's established tempui-file-drop conventions end to end: a new
`Job Runner` widget (`kind: "python"`) binds to the file the same way
Scratch/Question already do, shows the declared summary, a "View Code"
button, and a "Start" button; on Start, a `python`-kind job runs
in-process on a background thread, an `html`-kind job is materialized
and placed as a real, capability-scoped `kind: "html"` widget instance
reusing the exact auth/profile-isolation machinery TODO `a5f66cc`
already built.

## Affected files

- `src/desk/temp_ui.py` -- `JOB_KEYWORD`, `JobDefinition`, `parse_job`,
  `detect_temp_ui_kind`'s new `"job"` branch, `RESERVED_TEMPUI_KEYWORDS`,
  a new split doc (`tempui-jobs.md`) + `TEMPUI_DOC_VERSION` bump +
  `_NEW_FEATURES_DOC` entry + `DOC_TEMPLATE`'s file-type list.
- `src/desk/jobs.py` (new) -- materializes a `JobDefinition`'s script
  to a real file, mirroring `desk.custom_widgets.materialize`.
- `src/desk/shell/current_context.py` -- one new hook,
  `set_html_job_starter`/`get_html_job_starter`.
- `src/desk/shell/window.py` -- `JOB_RUNNER_WIDGET_ID`;
  `_temp_ui_widget_id_for`/`_notify_temp_ui` gain a `"job"` branch (no
  other change needed -- Job is a Scratch/Question-shaped single-file
  -to-single-instance binding, not DefineWidget's two-step
  type-then-instance shape); new `start_html_job(job_id, definition,
  on_status)`.
- `widgets/job_runner/` (new) -- `widget.json` + `widget.py`.
- `tests/verify/` -- new coverage.

## Design decisions

- **Tempui file format mirrors `DefineWidget` exactly**: first line
  `Job<TAB>kind<TAB>summary` (`kind` is `python` or `html`), zero or
  more `Capability<TAB>name` lines, one or more `Script<TAB>base64
  -chunk` lines (concatenated in file order, same chunking convention
  `Html` already uses) -- base64 because a script's own content will
  routinely contain tabs/newlines this TAB-delimited-lines format
  can't otherwise carry safely. `Capability` lines are collected
  regardless of `kind` (unused for `python`, meaningful for `html`) --
  simpler than branching the parser on `kind` for a field that's
  harmless to just ignore.
- **Not a two-step type-then-instance DSL like `DefineWidget`.** A
  `Job` file is Scratch/Question-shaped: one file, one instance, bound
  via the *existing* `_bind_temp_ui_content` fallback branch
  (`elif hasattr(content, "set_source_file")`) with zero changes to
  that function -- the Job Runner widget re-parses its own source file
  directly via `desk.temp_ui.parse_job`, the same established pattern
  `widgets/question/widget.py`/`widgets/lightning_round/widget.py`
  already use for their own tempui parsing.
- **`python`-kind execution needs no `DeskWindow` involvement at all.**
  Direct-exec (a fresh module namespace, `desk` importable,
  stdout/stderr/exceptions captured) is a pure, self-contained
  operation the widget can run entirely on a background thread +
  `pyqtSignal` relay -- the exact same shape `widgets/git_diff/widget.py`
  already establishes for background work reporting back to the GUI
  thread. No new `current_context` hook needed for this path.
- **`html`-kind execution needs exactly one new `current_context`
  hook** (`set_html_job_starter`/`get_html_job_starter`, mirroring
  `set_discuss_starter`'s shape), since only `DeskWindow` can
  materialize + mount on the running `ServerHandle` + place a real
  `ChromiumWidget`. `DeskWindow.start_html_job`:
  1. `desk.jobs.materialize` writes the decoded script to
     `.desk_temp/jobs/<job_id>/index.html` (mirroring
     `custom_widgets.materialize`'s directory convention, under its own
     `jobs/` cache subdir rather than reusing `custom_widgets/`, since
     a Job is never a reusable widget *kind* the way a `DefineWidget`
     is).
  2. Builds a `WidgetInfo(id=job_id, kind="html",
     capabilities=definition.capabilities, tempui_only=True, ...)` and
     adds it to `self._widgets[job_id]` directly -- *not* through
     `_register_custom_widget` (that method's conflict-checking/
     spawn-menu-catalog/stale-hash bookkeeping is all about a
     reusable, promotable widget *kind*; a Job is neither). This is
     what makes the Bridge API's `require_caller` dependency (`app.py`)
     resolve real, scoped capabilities for the job's own JS the moment
     it calls `window.desk.*` -- no new auth/injection mechanism, just
     a new source feeding an existing lookup.
  3. `self._handle.mount_html_widget(job_id, directory, info)` serves
     the content; `self._place_widget(job_id, info, pos, size,
     instance_id=job_id)` places a real, visible `ChromiumWidget` on
     the canvas, centered in the current view (mirroring
     `_place_discuss_claude_widget`'s centered convention) -- visible
     on purpose: placing a real widget instance the user can see is
     the transparency mechanism here, not an incidental side effect.
     `job_id` doubles as both the widget id and the instance id (a Job
     only ever has one execution/instance, unlike a `DefineWidget`
     keyword, which can have many placed instances).
  4. Status reporting reuses `ChromiumWidget`'s own existing signals --
     no new ones needed: `loadFinished(bool)` (native to
     `QWebEngineView`, which `ChromiumWidget` already subclasses) as
     "done" (`True`) or "errored" (`False`), and
     `error_state_changed(bool, str)` (TODO `d4d6c71`, already wired
     for the `[ERROR]` titlebar button) as a second, more specific
     "errored" signal carrying the actual console-error/uncaught
     -exception text. Both connect to the `on_status` callback the
     Job Runner widget passed in.
- **"Done" for an `html`-kind job means "the page finished loading,"
  not "every async Bridge call it kicked off has resolved."** There's
  no universal, protocol-level way to know an arbitrary web page's own
  async work is finished (that's exactly the "generic progress
  protocol" gap the sibling FEEDBACK item's own heavier concept would
  solve) -- accepted as a known, documented MVP limitation (see Key
  tradeoffs), not something this deliberately-lightweight mechanism
  tries to solve.
- **Persisting "has this Job already run" across a Desk reload reuses
  the existing generic python-widget persisted-state hook**
  (`get_widget_local_storage`/`set_widget_local_storage`, the same
  pull-based mechanism `desk.self.getLocalStorage/setLocalStorage`
  generalizes for `kind: "html"` widgets) -- not a write-back to the
  Job tempui file itself. The widget persists `{"status": ...,
  "detail": ...}`; a restored `"executing"` status (Desk closed mid
  -run) is treated as interrupted/stale on load -- shown distinctly,
  with Start re-enabled -- rather than a permanently stuck widget with
  no way forward.
- **Re-running is blocked the same way the earlier "Job cleanup"
  decision specified**: once status leaves `"not_started"`, `Start`
  becomes disabled and stays disabled (persisted, so this survives a
  reload) -- except the interrupted-on-reload case above, which is a
  deliberate, narrow exception (nothing to be "kept a record of" for a
  run that never actually finished).
- **`has_unsaved_local_edits()` doubles as the "don't live-refresh an
  already-started Job out from under itself" guard** -- returns
  `True` whenever status is not `"not_started"`, reusing
  `_refresh_live_temp_ui`'s *existing* opt-out mechanism (the Scratch
  widget's own established precedent, TODO `9ee505f`) instead of
  adding new logic to `window.py`.
- **`View Code` needs a real file on disk** (`desk.editor
  .openOrScrap`/`open_editor_or_scrap`, reached via the existing
  `current_context.get_editor_or_scrap_opener()` hook, resolves a
  real `Path`) -- the widget materializes the script body to a plain
  file itself (`desk.jobs.materialize_script_only`, no `DeskWindow`
  involvement needed, a pure filesystem write under
  `.desk_temp/jobs/<job_id>/`) the first time View Code is clicked (or
  eagerly in `set_source_file`), independent of the separate `html`
  -kind materialize-to-`index.html` step `start_html_job` does at
  Start time -- View Code always writes a plain-text script file
  (`.py`/`.html` by kind) since the point is showing the *source*, not
  the browser-ready wrapped-for-execution form.

## Step-by-step implementation

1. `temp_ui.py`: `JOB_KEYWORD = "Job"`, add to
   `RESERVED_TEMPUI_KEYWORDS`; `JobDefinition` dataclass (`kind`,
   `summary`, `script_b64`, `capabilities`); `parse_job(text)`
   mirroring `parse_define_widget`; `detect_temp_ui_kind` gains a
   `"job"` branch.
2. `jobs.py` (new): `materialize(desk_temp_dir, job_id, definition) ->
   Path | None` (writes `index.html` for `html`, `script.py` for
   `python`, under `jobs/<job_id>/`, malformed-base64 tolerant same as
   `custom_widgets.materialize`); `materialize_script_body(desk_temp_dir,
   job_id, definition) -> Path | None` (View Code's own plain-text
   copy, named `job_source.py`/`job_source.html` to avoid ever
   colliding with the `html`-kind `index.html` the server actually
   serves).
3. `current_context.py`: `set_html_job_starter`/`get_html_job_starter`
   hook pair, matching `set_discuss_starter`'s shape.
4. `window.py`: `JOB_RUNNER_WIDGET_ID = "job_runner"`;
   `_temp_ui_widget_id_for`/`_notify_temp_ui` gain a `"job"` branch
   (`text = f"Job: {summary}"`); `start_html_job(self, job_id: str,
   definition: JobDefinition, on_status: Callable[[str, str], None])
   -> None` per the Design decisions above; wire
   `current_context.set_html_job_starter(self.start_html_job)` in
   `__init__` alongside the other hooks.
5. `widgets/job_runner/widget.json` + `widget.py`: summary/kind
   labels, View Code button (`current_context
   .get_editor_or_scrap_opener()`), Start button, status display;
   `python`-kind background-thread direct-exec (module-level function
   + `_Relay(QObject)`, mirroring `git_diff/widget.py`); `html`-kind
   dispatch via `current_context.get_html_job_starter()`;
   `get_widget_local_storage`/`set_widget_local_storage`;
   `set_source_file`; `has_unsaved_local_edits`.
6. `temp_ui.py` doc work: `_JOBS_DOC` (new split doc, `tempui-jobs.md`,
   modeled on `_SCRATCH_DOC`'s length/shape -- format, an example file,
   the `python`/`html` execution split, and the capability list `html`
   jobs can declare, reusing the exact capability-name list `app.py`'s
   `require_caller` already enforces); add to `SPLIT_DOC_CONTENT`;
   `DOC_TEMPLATE`'s file-type list gains a `Job` bullet (eight -> nine
   built-in file types) linking to it; bump `TEMPUI_DOC_VERSION`
   (matching comment block) and add a `_NEW_FEATURES_DOC` entry.
7. New/extended verify coverage (see below); run the full
   `tests/verify/` suite.

## Key tradeoffs

- No progress protocol, run history, checkpointing, or resumability --
  deliberately out of scope per the earlier design-questions round;
  that's the sibling FEEDBACK item's own heavier concept.
- An `html`-kind job's "done" status reflects page-load completion,
  not completion of whatever async Bridge calls its own script kicked
  off -- a script that fires-and-forgets a Bridge call and returns
  immediately will show "done" before that call's effect is actually
  visible elsewhere. Documented explicitly in `tempui-jobs.md` so an
  agent authoring a Job knows not to rely on "done" as a strict
  completion signal for async work.
- `python`-kind direct-exec has no capability/sandboxing story at all
  (full `desk` package access, same as any `kind: "python"` widget's
  own code already has) -- consistent with the "View Code is the only
  review step" decision already made; not a new, separate exposure.
- The Job's own placed `html` widget instance is never cleaned up
  (mounted route, materialized directory, `self._widgets` entry all
  persist for the process's lifetime) -- consistent with "a run Job
  file is kept, not deleted" and every other `.desk_temp`-scoped
  registration this codebase already never tears down mid-session
  (e.g. `_register_custom_widget`'s own entries).

## Verification

New checks, real (no mocking):
- `tests/verify/verify_job_tempui_parsing.py` (new): `parse_job`
  round-trips kind/summary/capabilities/script through the real DSL
  text shape (single- and multi-chunk `Script` lines); rejects garbage
  (no keyword, bad `kind`, no `Script` lines); `detect_temp_ui_kind`
  returns `"job"`; `JOB_KEYWORD` is in `RESERVED_TEMPUI_KEYWORDS`.
- `tests/verify/verify_jobs_materialize.py` (new): `jobs.materialize`
  writes a real `index.html`/`script.py` under `jobs/<job_id>/` by
  kind, and returns `None` (logged) for malformed base64;
  `materialize_script_body` writes a real plain-text file.
- `tests/verify/verify_job_runner_widget.py` (new, real `QWidget`
  construction, no Chromium/WebEngine needed for the `python`-kind
  half): `set_source_file` against a real `Job` tempui file updates
  the summary/kind display; `python`-kind Start actually runs a real
  script on a background thread (pumped via `app.processEvents()`,
  same pattern `verify_bridge_api_editor_or_scrap.py` already uses)
  and the status display reaches "done" with captured stdout, or
  "errored" with a captured traceback for a script that raises;
  `get_widget_local_storage`/`set_widget_local_storage` round-trip a
  real status, and a restored `"executing"` status is shown as
  interrupted with Start re-enabled; `has_unsaved_local_edits()` is
  `False` before Start and `True` after; View Code calls the real
  `current_context.get_editor_or_scrap_opener()` hook with a real,
  materialized file path.
- `tests/verify/verify_html_job_execution.py` (new, real
  `start_server` + real `DeskWindow`-shaped fake, same
  `_FakeWindowWithView`-style harness `verify_html_widget_local_storage.py`
  already establishes): `DeskWindow.start_html_job` materializes,
  mounts, registers `self._widgets[job_id]`, and places a real,
  visible `ChromiumWidget`; a real HTTP round trip confirms the
  placed instance's Bridge API calls are scoped to exactly the
  declared `Capability` lines (a call to a namespace it didn't declare
  gets a real 403); `on_status` fires "done" on a real
  `loadFinished(True)` and "errored" on a real captured console error.
  Uses `os._exit()` at the end (TODO `a5f66cc`'s established pattern
  for any script placing a real `ChromiumWidget`/`QWebEngineProfile`).
- `tests/verify/verify_tempui_jobs_doc.py` (new): `TEMPUI_DOC_VERSION`
  bumped; `tempui-jobs.md` covers the file format, the capability
  list, and the "done" caveat; `DOC_TEMPLATE`'s file-type list
  references it (the established "every split file must be linked"
  invariant); `_NEW_FEATURES_DOC` has a matching entry.
- Full `tests/verify/` regression suite.
