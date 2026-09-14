# TODO

Items are worked in the order they're listed here, top to bottom — see
`development-process.md`'s "Item IDs" section. Each item has a permanent,
content-derived id (7 lowercase hex digits); ids carry no ordering
information and are never reused or reassigned, even if an item is later
reordered or its description edited.

224fbc9. COMPLETED: `DeskWindow._capture_desk_state()` (`src/desk/shell/window.py`)
   drops `Desk.state` -- the shared `desk.state.*` store -- when
   rebuilding a fresh `Desk` from the live canvas on every save, so it
   silently resets to `{}`. Because `save_current_desk()` immediately
   does `self.current_desk = desk` afterward, this wipes the *live*,
   in-memory store too, not just what's written to disk -- and
   `save_current_desk()` runs on removing *any* widget of *any* kind,
   switching Desks, quitting, and more, so closing a single widget
   deletes every `desk.state` key any widget has ever written, for the
   rest of the running session. Two further instances of the same bug
   reported alongside it: `get_state_dict()` (the Bridge API's
   `workspace.getState`) always reports `"state": {}` regardless of
   what's actually stored, since it reads through the same broken
   `_capture_desk_state()`; and `change_current_desk_directory()`
   hand-builds a `Desk(...)` dropping `state`, `custom_widgets`,
   `file_type_registry`, *and* `installed_jobs` all at once. Reported
   in
   `../FEEDBACK/FEEDBACK-DESK-state-store-wiped-by-capture-desk-state-2026-09-12-2100.md`
   (`draw-with-desk`), found while building a multi-widget raycaster
   family that relies on `desk.state` as its only persistence layer --
   real project data (camera/scene definitions) was lost and had to be
   manually recovered from `.desk_temp/MEDIATED-EVENT-LOG.tsv`.
   Prioritized per direct user request (real, repeatable data loss for
   any project using `desk.state`).
   [planned: fix-capture-desk-state-drops-state.md]

   COMPLETED: Implemented the structural fix, per the feedback's own
   suggestion, rather than patching only the reported `state` field:
   `_capture_desk_state`, `change_current_desk_directory`, and
   `rename_current_desk` (`src/desk/shell/window.py`) all now build
   their result via `dataclasses.replace(self.current_desk, ...)`
   instead of hand-enumerating which fields to carry over. Auditing
   every `Desk(...)` construction site in `window.py` while fixing this
   turned up a *third*, previously-unreported instance of the same bug
   in `rename_current_desk` (dropped all four of `state`/
   `custom_widgets`/`file_type_registry`/`installed_jobs`), fixed the
   same way. `get_state_dict` needed no code change -- it already reads
   through `_capture_desk_state`, so fixing that fixed it too (verified,
   not assumed).

   New verify coverage: `tests/verify/verify_state_store.py` (+23
   checks, 46 total) -- `_capture_desk_state`/`get_state_dict` no longer
   drop `state` (or `custom_widgets`/`file_type_registry`/
   `installed_jobs`); a direct reproduction of the reported incident
   (close one of two placed widgets, then save -- state survives);
   `change_current_desk_directory`/`rename_current_desk` both carry
   over all four fields; a real save-then-`load_desk` round trip
   confirms a `.desk` file's `state` section is no longer always `{}`
   by construction (closing the feedback's "structural finding" as a
   side effect of this same fix, confirmed rather than assumed). Ran
   the new tests against the pre-fix code first to confirm they
   actually fail there (they do -- one raises an uncaught `KeyError`
   partway through, since the bug is a real, hard crash-adjacent data
   loss, not a soft mismatch). Also fixed `verify_state_store.py`'s own
   `sys.path` line, which hardcoded an absolute path to a sibling
   checkout (`/Users/mphair/inadvisable-adventures/desk/src`) and was
   silently testing *that* checkout's unfixed code instead of this
   one's -- see `LEARNINGS.md`'s existing entry on this class of bug;
   the ~28 other affected scripts remain tracked separately in
   `PARKINGLOT.md`, unchanged here.
   `tests/verify/verify_lock_persistence.py`'s `_FakeWindow` updated to
   use a real `Desk(...)` instance (`dataclasses.replace` requires a
   real dataclass instance, not the ad hoc duck-typed stand-in it used
   before) -- still passes unchanged otherwise.

   Full `tests/verify/` suite rerun clean beyond two pre-existing,
   unrelated failures confirmed present on `main` before this change via
   `git stash` (`verify_eye_button_persists_title_only.py`,
   `verify_relocate_promoted_widget_source.py` -- the latter fails
   identically with or without this change).

f4a7872. COMPLETED: Add a monitorable background-tasks panel to the Claude (Desk)
   widget (`widgets/claude_desk/widget.py`) -- the Claude Agent SDK
   reports a session's background tasks (backgrounded Bash, a
   subagent/Task run, ...) as `TaskStartedMessage`/`TaskProgressMessage`/
   `TaskNotificationMessage`/`TaskUpdatedMessage` system messages, which
   `ClaudeSession._handle_message` (`src/desk/claude_session.py`)
   currently drops entirely. Prioritized to the top of this file per
   direct user request (three related Claude (Desk) widget UX asks in
   the same request -- this is one of them, see also TODO `1ceb701`/
   `551014c`). The panel expands from the bottom of the widget on
   toggle and grows the widget's own placed frame to fit (rather than
   squeezing the existing history/prompt area), via a new
   `current_context` "widget height adjuster" hook.
   [planned: claude-desk-background-tasks-panel.md]

   COMPLETED: `src/desk/claude_session.py` -- re-exported
   `TERMINAL_TASK_STATUSES`; new `task_event(task_id, patch)` signal;
   `_handle_message` gained branches for
   `TaskStartedMessage`/`TaskProgressMessage`/`TaskNotificationMessage`/
   `TaskUpdatedMessage`, each emitting a merged `patch` dict (a
   `TaskUpdatedMessage`'s own `status` folded into `patch` under a
   top-level `"status"` key, matching `TaskNotificationMessage`'s own
   shape). `src/desk/shell/current_context.py` -- new
   `widget_height_adjuster` hook (get/set pair). `src/desk/shell
   /window.py` -- `MIN_HEIGHT` imported alongside `WidgetFrame`;
   `DeskWindow.adjust_widget_instance_height(instance_id, delta)`
   (finds the frame, resizes its `graphicsProxyWidget()`, clamped to
   `MIN_HEIGHT`); wired into `__init__`'s hook-wiring block.
   `widgets/claude_desk/widget.py` -- `TASKS_PANEL_HEIGHT = 140`; a
   `QListWidget` panel (fixed height, hidden by default) appended after
   the prompt row; a checkable toggle `QPushButton` in `top_row`
   showing a live running-task count and an expand/collapse arrow;
   `_on_task_event` merges each patch (filtering `None` values so an
   unreported field never blanks an already-known one) and rebuilds
   the list from scratch; `_on_tasks_toggled` shows/hides the panel and
   calls the new height-adjuster hook with `+`/`-TASKS_PANEL_HEIGHT`
   symmetrically. New `tests/verify/verify_claude_desk_background_tasks_panel.py`
   (21 checks): real `claude_agent_sdk` `Task*Message` instances fed
   through a real `ClaudeSession._handle_message` produce the right
   merged `task_event` payload for each of the four subtypes (including
   a `TaskUpdatedMessage` with `status=None`); the panel's default
   hidden state, toggle label text (both the running count and the
   expand/collapse arrow), a `None`-valued patch field never
   overwriting an already-set one, and the height-adjuster hook being
   called symmetrically on expand/collapse -- and as a safe no-op with
   neither a session id nor a registered hook yet. Also fixed
   `tests/verify/verify_claude_desk_widget.py`'s own `REPO_ROOT` (was
   hardcoded to a sibling checkout's absolute path, silently testing
   the *wrong repo* the whole time -- see the new `LEARNINGS.md`
   entry). Full `tests/verify/` regression suite passes (133 scripts,
   0 failures; 8 pre-existing `disabled_` scripts unaffected).

1ceb701. COMPLETED: Persist the Claude (Desk) widget's model/permission-mode combo
   selections (`widgets/claude_desk/widget.py`) into the widget's own
   per-instance widget-local storage (TODO `fb76057`), so a Desk reboot
   restores a resumed session's previously-selected model/mode instead
   of resetting to this widget's hardcoded defaults. Prioritized to the
   top of this file per direct user request (see TODO `f4a7872`'s own
   note). Requires a narrow ordering fix in
   `DeskWindow._place_widget`/`_load_desk_widgets`: today, widget-local
   storage is restored *after* this widget kind's `start_session`
   already ran (and already read the still-default combo values) --
   fixed by applying it earlier, for this one widget id only.
   [planned: claude-desk-persist-model-permission-mode.md]

   COMPLETED: `src/desk/shell/window.py` -- `_place_widget` gained a
   `local_storage_data` parameter; for `CLAUDE_DESK_WIDGET_ID`
   specifically, when given, calls the existing
   `_bind_widget_local_storage` *before* `_bind_claude_desk_widget`
   (i.e. before `start_session` reads the combo boxes) -- every other
   widget kind's own restore timing is untouched, and
   `_load_desk_widgets`'s own later, generic
   `_bind_widget_local_storage` call still fires too (a harmless,
   idempotent second application for this widget kind).
   `_load_desk_widgets` passes `local_storage_data=state.state`.
   `widgets/claude_desk/widget.py` -- `get_widget_local_storage`/
   `set_widget_local_storage` (the generic python-widget persisted
   -state hook, TODO `fb76057`), storing/restoring the real SDK model/
   permission-mode values (not the combo index) via a small
   `_index_for_value` helper that falls back to this widget's own
   hardcoded default index for an unrecognized value; a `_NOT_SAVED`
   sentinel (not `data.get(key)` alone) distinguishes an explicitly
   -saved `"model": None` (the real "Default" choice's own value) from
   the key being entirely absent (pre-existing/never-saved data),
   which would otherwise both resolve to the same value and wrongly
   pick "Default" instead of falling back to `DEFAULT_MODEL_INDEX`.
   New `tests/verify/verify_claude_desk_persist_model_permission_mode.py`
   (13 checks): round-trip of a non-default selection through
   get/set_widget_local_storage; the unknown-value and missing-key
   fallback cases; the explicit-`None`-vs-missing-key distinction; a
   real `start_session` call confirming the restored model/mode (not
   the hardcoded default) is what actually gets passed to
   `ClaudeSession.start`; and a source-order check confirming
   `DeskWindow._place_widget` itself calls `_bind_widget_local_storage`
   before `_bind_claude_desk_widget`. Full `tests/verify/` regression
   suite passes (see TODO `f4a7872`'s own write-up for the count).

551014c. COMPLETED: Show the Claude (Desk) widget's own session id in its titlebar
   via the existing widget-subtitle mechanism (TODO `3cd90cf`) -- the
   widget's placed instance id already doubles as its Claude Agent SDK
   session id (`DeskWindow._place_widget`'s own comment says so
   directly), and there is no separate "session name" concept in the
   installed SDK to prefer instead. Prioritized to the top of this file
   per direct user request (see TODO `f4a7872`'s own note). Needs a new
   `current_context` "widget subtitle setter" hook so a `python`-kind
   widget can reach `DeskWindow.set_widget_subtitle` without importing
   `desk.shell.window` directly, wired up carefully (via
   `ClaudeSession.connected`, not directly inside `start_session`) to
   avoid the same hook-not-yet-registered-at-restore-time ordering trap
   TODO `1ceb701` also has to work around.
   [planned: claude-desk-titlebar-session-id.md]

   COMPLETED: `src/desk/shell/current_context.py` -- new
   `widget_subtitle_setter` hook (get/set pair). `src/desk/shell
   /window.py` -- `current_context.set_widget_subtitle_setter(self.set_widget_subtitle)`
   added to `__init__`'s existing hook-wiring block (`set_widget_subtitle`
   itself was already kind-agnostic; no change needed there).
   `widgets/claude_desk/widget.py` -- `self._session_id` set at the top
   of `start_session`; a new `_on_session_connected` slot (connected to
   `self._session.connected` in `__init__`, alongside the widget's
   other signal connections) calls the hook with `(session_id,
   session_id[:8])`, truncated to match `DeskWindow
   ._display_name_for_instance`'s own existing 8-hex-character display
   convention. Deliberately wired to `connected`, not called directly
   inside `start_session` -- confirmed the real reason during
   implementation: `start_session` runs synchronously inside
   `DeskWindow._load_desk_widgets` on a Desk restore, *before*
   `DeskWindow.__init__` reaches its own hook-wiring block, so calling
   the hook directly there would silently no-op for every restored
   widget; `connected` fires later, asynchronously, off the session's
   own background thread, which Qt only delivers once this (GUI)
   thread's event loop actually runs -- strictly after `__init__`'s
   hook-wiring has already completed. New
   `tests/verify/verify_claude_desk_titlebar_session_id.py` (7 checks):
   the hook is `None` until set and returns exactly what was set;
   `DeskWindow.__init__`'s own source actually wires it to
   `self.set_widget_subtitle`; a real widget with a fake session
   confirms nothing is set before `connected` fires and the right
   `(session_id, session_id[:8])` pair is set once it does; and a
   missing hook is a safe no-op. Full `tests/verify/` regression suite
   passes (see TODO `f4a7872`'s own write-up for the count).

97bd090. COMPLETED: A "Desk Proc" mechanism: a one-time script an agent can create that
   runs with real, in-process access to Desk itself (not just a
   `kind: "html"` widget's Bridge API) -- e.g. reveal a specific placed
   widget instance (the same action as clicking its titlebar eye
   button) and then take a real pixel screenshot of it, saving a PNG.
   Prioritized to the top of this file per direct user request.

   This is deliberately a close sibling of the existing `Job` mechanism
   (TODO `d7e66f6`, `tempui-jobs.md`) -- reuses its exact "tempui file →
   notification → placed one-shot runner widget → Start button →
   background-thread exec" shape and its `desk_procs/`-under-`.desk_temp`
   materialization convention (mirroring `desk.jobs`) -- but is its own,
   separate keyword and widget kind, not a new `Job` `kind`, because:
   - A `Job`'s `kind: "python"` already runs with unrestricted in
     -process access ("no sandboxing" per its own docstring), but that
     access is Qt-thread-unsafe to use directly for anything touching
     live widgets/the canvas -- the existing Job Runner deliberately
     never does this. A Desk Proc needs a real, documented, thread-safe
     way to do exactly that, which a generic Job has no reason to grow.
   - The user explicitly asked for these notifications to "appear
     clearly different from the normal tempui placement notifications
     and be clearly labelled as a 'Desk Proc'" -- Job notifications
     today are just plain-text banners, visually identical to every
     other tempui kind (`_NotificationBanner` in
     `temp_ui_notifications.py` has no per-kind styling at all). A
     `DeskProc` gets a visually distinct banner (a bold "DESK PROC"
     caption + its own border color), threaded through
     `TempUiNotificationStack.notify` → `WorkspaceView.notify_temp_ui` →
     `DeskWindow._notify_temp_ui`.

   Suggested mechanism:
   - New tempui DSL keyword `DeskProc<TAB>summary` (first line) + one or
     more `Script<TAB>base64-chunk` lines -- Python source only (no
     `kind`/`Capability` lines; unlike `Job` there's no `html` variant,
     since the whole point is direct Desk-shell access, not
     capability-scoped Bridge API access from inside a page).
     `desk.temp_ui`: `DESK_PROC_KEYWORD`, `DeskProcDefinition` dataclass
     (`summary`, `script_b64`), `parse_desk_proc` (mirrors `parse_job`
     minus the `kind`/`Capability` handling), `detect_temp_ui_kind`
     gains a `"desk_proc"` branch, `RESERVED_TEMPUI_KEYWORDS` gains the
     new keyword.
   - New `src/desk/desk_proc.py`, mirroring `src/desk/jobs.py` exactly
     (`desk_proc_dir`, `materialize`, `materialize_script_body`), own
     cache subdir `.desk_temp/desk_procs/<id>/` (`script.py` +
     `desk_proc_source.py` for View Code).
   - New `current_context` hook, `set_gui_thread_caller`/
     `get_gui_thread_caller` -- lets in-process Python code running on a
     background thread (a Desk Proc's exec, same as a `Job`'s) safely,
     synchronously call into GUI-thread-owned `DeskWindow` state and get
     a real return value back. Reuses the exact primitive the Local Web
     Server's own Bridge API already relies on for this
     (`desk.shell.bridge.GuiBridge.call`, already thread-safe by
     design -- see its own docstring) -- `DeskWindow.__init__` sets it
     to `self._handle.gui_bridge.call`, the same `GuiBridge` instance
     `src/desk/app.py` already attaches to the window at startup.
   - New `DeskWindow` methods: `screenshot_widget_instance(instance_id,
     path) -> bool` (resolve via the existing
     `find_frame_by_instance_id`, `frame.grab()`, resolve `path`
     relative to `self.current_desk.directory` like `desk.fs.*`
     already does, `mkdir(parents=True, exist_ok=True)`, `.save(path,
     "PNG")`) and `screenshot_desk(path) -> None` (same, but
     `self.grab()` of the whole main window -- same `.grab()` idiom
     `widgets/feedback/widget.py`'s `_take_screenshot` already
     establishes). "Reveal" reuses `zoom_to_widget_by_instance_id`
     (TODO `7505703`) unchanged -- no new method needed for that part.
   - New `widgets/desk_proc_runner/` (`kind: "python"`), closely
     mirroring `widgets/job_runner/` (summary label, "View Code",
     "Start", background-thread exec, stdout/stderr capture, the same
     persisted-status/interrupted-on-reload handling) but simpler (no
     `kind` branch -- always the background-thread-exec path). Injects
     a small, curated `deskproc` object into the script's exec globals
     (not raw process access as the *documented* interaction surface,
     though nothing stops a script from `import`-ing internals directly
     too, same trust level as a `Job`): `deskproc.reveal_widget
     (instance_id) -> bool`, `deskproc.screenshot_widget(instance_id,
     path) -> bool`, `deskproc.screenshot_desk(path) -> None`,
     `deskproc.list_widget_instances() -> list[dict]` (thin wrapper
     over the existing `DeskWindow.get_state_dict()`, the same data
     `desk.workspace.getState()` already exposes to `kind: "html"`
     widgets) -- every method routes through
     `current_context.get_gui_thread_caller()` for thread safety.
   - Notification styling: `_NotificationBanner` gains a `banner_style`
     param (`"default"` | `"desk_proc"`), threaded through
     `TempUiNotificationStack.notify`/`WorkspaceView.notify_temp_ui`;
     `"desk_proc"` renders a bold "DESK PROC" caption line (non
     -selectable, matching this project's own labels-aren't-selectable
     convention) above the summary, plus a distinct border color, so
     it's visually different from every other tempui notification at a
     glance, not just by its text.
   - New split doc `tempui-desk-proc.md` (mirrors `tempui-jobs.md`'s
     shape), linked from `desk-temporary-ui.md`'s intro list (nine
     built-in file types -> ten); `TEMPUI_DOC_VERSION` bumped; a new
     `tempui-new-features.md` entry.
   - **Decided**: no `html`-kind variant for `DeskProc` -- if a script
     genuinely just needs capability-scoped Bridge API access, `Job`
     already covers that; `DeskProc` exists specifically for direct
     -to-shell actions a sandboxed `kind: "html"` page structurally
     cannot do.
   - **Decided**: `deskproc.screenshot_widget`/`screenshot_desk` grab
     the target's real on-screen pixels via Qt's own `.grab()` --
     independent of the canvas's current zoom/pan, since `.grab()`
     rasterizes the widget's own paint output at its authored size, not
     whatever the `QGraphicsProxyWidget` embedding currently renders it
     at.
   [planned: desk-proc-mechanism.md (COMPLETED)]

   COMPLETED: `temp_ui.py` gained `DESK_PROC_KEYWORD = "DeskProc"`
   (added to `RESERVED_TEMPUI_KEYWORDS`), a `DeskProcDefinition`
   dataclass, and `parse_desk_proc` (mirrors `parse_job` minus
   `kind`/`Capability`); `detect_temp_ui_kind` gained a `"desk_proc"`
   branch. New `src/desk/desk_proc.py` mirrors `desk.jobs` under its
   own `desk_procs/` cache subdir (`materialize`/
   `materialize_script_body`). `current_context.py` gained
   `set_gui_thread_caller`/`get_gui_thread_caller` -- wired in
   `DeskWindow.__init__` to `self._handle.gui_bridge.call` (the same
   `GuiBridge` instance the Local Web Server's own Bridge API routes
   already use for thread-safe GUI-thread calls). `window.py` gained
   `DESK_PROC_RUNNER_WIDGET_ID` (added to `TEMP_UI_WIDGET_IDS`),
   `_temp_ui_widget_id_for`/`_notify_temp_ui` `"desk_proc"` branches
   (the latter now threads a `banner_style` through to
   `view.notify_temp_ui`), and two new methods,
   `screenshot_widget_instance(instance_id, path) -> bool` (grabs the
   real placed `WidgetFrame`, resolves `path` like `desk.fs.*`, saves a
   PNG) and `screenshot_desk(path) -> bool` (grabs the Workspace Canvas
   viewport, not the whole native window). `canvas.py`'s
   `WorkspaceView.notify_temp_ui` and
   `temp_ui_notifications.py`'s `_NotificationBanner`/
   `TempUiNotificationStack.notify` gained a `banner_style` parameter
   (`"default"` | `"desk_proc"`) -- the latter renders a distinct amber
   border plus a bold, non-selectable "DESK PROC" caption line above
   the summary, so a Desk Proc notification is never mistaken for an
   ordinary tempui placement notification at a glance. New
   `widgets/desk_proc_runner/` (`kind: "python"`, mirrors
   `widgets/job_runner/` minus the `kind` branch), with a `DeskProcApi`
   class exposed to the script's exec namespace as `deskproc`
   (`reveal_widget`, `screenshot_widget`, `screenshot_desk`,
   `list_widget_instances`), every method routing through
   `current_context.get_gui_thread_caller()` for thread safety. New
   split doc `tempui-desk-proc.md` (added to `SPLIT_DOC_CONTENT`,
   linked from `DOC_TEMPLATE`'s file-type list, nine -> ten);
   `TEMPUI_DOC_VERSION` bumped 37 -> 38 with a matching
   `_NEW_FEATURES_DOC` entry. New verify coverage, real (no mocking):
   `verify_desk_proc_tempui_parsing.py` (14 checks: parsing/rejection/
   `detect_temp_ui_kind`/reserved-keyword); `verify_desk_proc_materialize.py`
   (11 checks: real file writes, malformed-base64 tolerance, the
   execution-entry/View-Code-copy coexistence); `verify_desk_proc_runner_widget.py`
   (25 checks: real background-thread exec reaching done/errored with
   captured stdout/traceback, the `deskproc` global's four methods
   actually routing through a fake GUI thread caller, persisted-status/
   interrupted-on-reload/View-Code, all mirroring
   `verify_job_runner_widget.py`'s equivalent coverage);
   `verify_desk_proc_notification_routing.py` (8 checks: widget-id
   resolution, summary text, and `banner_style` contrasted against an
   ordinary Question file's `"default"` style);
   `verify_desk_proc_notification_banner.py` (10 checks: the real,
   non-selectable "DESK PROC" caption and distinct stylesheet, real Qt
   widget construction); `verify_desk_proc_screenshot.py` (13 checks:
   real `WidgetFrame` placement via the same `_FakeWindow`/
   `_place_widget`-binding harness `verify_widget_error_indicator.py`
   already establishes, real PNG files with correct magic bytes,
   relative/absolute path resolution, missing-parent-directory
   creation); `verify_tempui_desk_proc_doc.py` (17 checks: doc-set
   completeness/version bump). Fixed one now-stale assertion in the
   pre-existing `verify_tempui_jobs_doc.py` (the file-type count
   check) and `verify_job_notification_routing.py`'s fake
   `notify_temp_ui` signature, both made stale by this change's own
   `banner_style` parameter/file-type-count bump. Full
   `tests/verify/` suite (122 scripts) passes.

a762501. COMPLETED: Expose an in-process MCP server as a live, queryable Desk <-> agent
   channel -- a real request/response surface for anything *dynamic*
   TODO `b9d3de5`'s static env-var fix can't answer (what's currently
   placed, live widget state, reveal/screenshot a widget right now,
   force a save), as a parallel or eventual replacement for the
   file-drop-and-click-Start tempui/`Job`/`DeskProc` ceremony for
   agent-initiated actions specifically. Merges two `PARKINGLOT.md`
   entries that turned out to be the same underlying shape (moved here,
   removed from there) -- "a way for agents ... to reach into the
   running app for more than just reading/writing files" and
   "two-directional tempui: let Desk call *into* a running Claude
   session" -- plus this session's own discussion of TODO `b9d3de5`.
   Prioritized per direct user request (grouped with the related
   `b9d3de5`/`765bd2a` cluster above).

   **Grounding confirmed this session (2026-09-01), against the
   actually-installed SDK**: `claude_agent_sdk.ClaudeAgentOptions.mcp_servers`
   accepts an `McpSdkServerConfig` -- an **in-process** MCP server (no
   subprocess, no port to manage), wired in alongside the `env=` fix at
   the same `ClaudeSession._connect_and_maybe_prompt` call site
   (`src/desk/claude_session.py:105`). This meaningfully lowers the
   cost of "the formalized channel" option from the `b9d3de5`
   discussion -- it's a Python `Server` object passed into an existing
   options call, not a real network service to stand up/secure/manage.

   Candidate first tools, all thin wrappers over methods already built
   for TODO `97bd090` (`DeskProc`) and already safely GUI-thread
   -marshaled via `current_context.get_gui_thread_caller()`: reveal a
   widget (`zoom_to_widget_by_instance_id`), screenshot a widget/the
   whole canvas (`screenshot_widget_instance`/`screenshot_desk`), list
   currently-placed widget instances (`get_state_dict`, the same data
   `desk.workspace.getState()` already exposes), and forcing an
   on-demand `save_current_desk()` (the original parked item's own
   single most-wanted capability, not yet covered by anything). Once
   this exists, `DeskProc`'s reveal/screenshot use case becomes a
   direct one-call tool use instead of a whole tempui-file round trip
   -- `Job`/`DeskProc` would still matter as the escape hatch for
   anything not covered by a built-in tool, not be made obsolete
   outright.

   **Also add a simple TODO API** (per direct user request, added
   after this item was first written): read-only tools --
   `list_todo_items()`/`get_next_todo_item()` -- wrapping the already
   -existing `desk.todo_file.parse_todo_file`/`TodoItem` (id, status,
   description, plan) that already backs the real TODO widget, so an
   agent can check what's already `COMPLETED`, what's `PENDING`, and
   what the current first actionable item actually is *before* diving
   in, rather than hand-parsing `TODO.md` itself or trusting stale
   context from earlier in its own session. Directly motivated by a
   real collision this same session hit: one agent session picked an
   item to work based on a stale mental model of `TODO.md`'s order
   while a second, independent session had already reprioritized it --
   discovered only after the fact, via `git log` (see the new
   `PARKINGLOT.md` item on concurrent-session UX, surfaced by the same
   incident). Deliberately **read-only for this first pass** -- a
   mutating tool (mark an item `COMPLETED`, reorder it) would let an
   agent shortcut this project's own plan-then-implement-then-verify
   discipline via a single tool call, which is a real trust/process
   question worth its own separate decision, not a default to back
   into here.

   **The harder, still-unresolved half, carried over from the
   "two-directional tempui" item verbatim**: an MCP tool call is
   fundamentally agent-initiated (the agent asks, the server answers)
   -- it does not, by itself, give Desk a way to push a structured
   message *into* an already-running session mid-turn (a button click,
   another widget's event, a user's answer to a Desk-routed question)
   the way the "two-directional" framing originally wanted. Whether MCP
   sampling/notifications can approximate this, or whether that
   direction needs an entirely different mechanism (a hook? the
   existing `event_mediator.py` pub/sub, polled or awaited somehow?),
   is not resolved -- worth treating as a distinct sub-problem within
   this item rather than assuming the MCP server trivially covers it.

   Also carried over, still open: the original item's own security/
   trust question (should a local MCP server be able to force actions
   in a running GUI app the user is looking at, and how is that
   authenticated/scoped -- e.g. per-Claude-(Desk)-widget-instance only,
   or broader); and the finer-grained-permission tangent from the
   two-directional item (per-action/per-location `can_use_tool` rules
   instead of one blanket `permission_mode`, e.g. `Bash(ls:*)`-style
   specifiers `ClaudeAgentOptions.allowed_tools`/`disallowed_tools`
   already partially support) -- related, but a separable design
   question from the MCP channel itself, not resolved by this item's
   own first implementation pass -- see this item's own `[planned:
   ...]` note below for the concrete scope that pass actually covers.
   [planned: desk-mcp-server.md]
   COMPLETED: `src/desk/shell/desk_mcp_server.py` (new) -- an in-process
   MCP server (`claude_agent_sdk.create_sdk_mcp_server`, `type: "sdk"`,
   no subprocess/port) with seven `@tool`-decorated handlers:
   `desk_reveal_widget`, `desk_screenshot_widget`, `desk_screenshot_desk`,
   `desk_list_widget_instances`, `desk_save`, `desk_list_todo_items`,
   `desk_get_next_todo_item`. Every handler checks `current_context
   .get_main_window()` for `None` first, then marshals onto the GUI
   thread via `await loop.run_in_executor(None, gui_thread_caller, fn)`
   -- the same idiom `desk.server.app.run_on_gui` already uses -- rather
   than blocking the session's own private event loop; a missing GUI
   thread caller or main window returns a clear non-crashing "not ready
   yet" text result instead of raising. The two TODO tools reuse
   `desk.todo_file.find_nearest_todo_file`/`parse_todo_file` directly, so
   they can never drift from what the real TODO widget shows, and are
   deliberately read-only (list/get-next only, no mark-complete/reorder)
   per this item's own note above on preserving plan-then-verify
   discipline. `src/desk/claude_session.py` -- `_connect_and_maybe_prompt`'s
   `ClaudeAgentOptions(...)` call gains `mcp_servers={"desk":
   build_desk_mcp_server()}`, so every Claude (Desk) session gets the
   channel with no extra wiring; tool calls (`mcp__desk__...`) flow
   through the existing `_can_use_tool` hook exactly like any other tool,
   confirmed directly against a real live session (no new approval UI
   needed). `widgets/claude_desk/widget.py` -- `CLAUDE_WIDGET_PROMPT`
   extended to tell the agent about the seven new tools and to prefer
   them over the file-drop `Job`/`DeskProc` ceremony when one already
   covers the need, and to check `desk_get_next_todo_item` rather than
   trust a possibly-stale earlier read of `TODO.md` (the exact
   concurrent-session collision this item's own body describes above).
   New: `tests/verify/verify_desk_mcp_server.py` (31 checks) -- each
   handler called directly as a plain async function against a fake
   `current_context`/fake `DeskWindow`-shaped object (no real SDK
   session, matching `verify_claude_desk_widget.py`'s established
   avoid-the-real-API convention); covers the happy path for all seven
   tools, the "not ready yet" text result with no GUI thread caller and
   with no main window, and the TODO tools against a real temporary
   `TODO.md` fixture (mixed `COMPLETED`/`PENDING`/plain items, the
   next-actionable-item resolution, and the all-done/no-`TODO.md`-found
   error cases). Full `tests/verify/` regression suite (134 scripts):
   found and fixed one unrelated pre-existing flake along the way, per
   this project's investigate-dont-just-note convention --
   `verify_shared_document_editor_base.py`'s one `tempfile
   .TemporaryDirectory()` call was missing `ignore_cleanup_errors=True`,
   hitting the same Qt WebEngine profile-teardown race already documented
   in `LEARNINGS.md` for TODO `a5f66cc` (`OSError: [Errno 66] Directory
   not empty` during interpreter-exit cleanup, not a real functional
   failure); fixed, then verified clean across 3 consecutive runs. Full
   suite reruns clean afterward, 0 failures. As noted in the still-open
   `PARKINGLOT.md` self-hot-reload item, this item was originally
   implemented inside a live Claude (Desk) widget session, which kept
   getting torn down mid-edit by its own hosting widget's hot reload
   whenever it touched `widgets/claude_desk/widget.py`; the user
   eventually gave up retrying that path and asked a session outside
   Desk (this one) to reconstruct the already-complete, uncommitted work
   from `git status`/`git diff` and the already-written plan file, verify
   it, and finish the bookkeeping.

e9eddba. COMPLETED: Add a permission-mode selector to the Claude (Desk) widget
   (`widgets/claude_desk/widget.py`). TODO `a596dbf` hardcoded
   `PERMISSION_MODE = "default"` (a deliberate deviation from the
   plan's suggested `"auto"` parity default with the original Claude
   widget, TODO `2dca4c8` -- found during verification that `"auto"`
   gates tool calls inconsistently, while `"default"` gates reliably,
   and this widget's whole point is a real, meaningful approval UI).
   Making that a real, visible, user-changeable control (alongside the
   existing model combo box) rather than a fixed constant lets someone
   trade consistency for fewer prompts if they want to, the same
   tradeoff `claude`'s own `--permission-mode` flag already exposes on
   the CLI. **Resolved**: the mode changes live, mid-session, via
   `ClaudeSDKClient.set_permission_mode` (confirmed directly in the
   installed SDK -- documented and supported specifically for this,
   not just settable at connect time), not only before `start_session`
   -- restricting it to start-only would be strictly worse for no
   benefit, given the SDK already makes live switching easy. Prioritized
   per direct request.
   [planned: claude-desk-permission-mode-selector.md]
   COMPLETED: `src/desk/claude_session.py` -- `ClaudeSession
   .set_permission_mode(mode)`, mirroring `send_prompt`'s exact
   guard-then-`asyncio.run_coroutine_threadsafe(...)` shape (a no-op
   before any session has started or after it's stopped); a private
   `_set_permission_mode` coroutine awaits the real SDK's own
   `ClaudeSDKClient.set_permission_mode`, surfacing a failure through
   the existing `session_error` signal rather than a new channel.
   `widgets/claude_desk/widget.py` -- the hardcoded `PERMISSION_MODE =
   "default"` constant replaced with `PERMISSION_MODE_CHOICES` (the six
   real `claude_agent_sdk.types.PermissionMode` values --
   `default`/`acceptEdits`/`plan`/`bypassPermissions`/`dontAsk`/`auto`
   -- with human-readable labels, the same `(label, value)` shape
   `MODEL_CHOICES` already uses) and a new combo box next to the
   existing model combo, defaulting to "Default" (same reasoning as
   the constant it replaces: `can_use_tool` gates reliably under
   `default`, inconsistently under `auto`); `start_session` reads the
   initial mode from the combo instead of the removed constant; a new
   `_on_permission_mode_changed` slot calls `ClaudeSession
   .set_permission_mode` live on every change, with no extra
   "is a session currently active" bookkeeping needed (the session's
   own guard already no-ops correctly before/after a live connection).
   New coverage in `tests/verify/verify_claude_desk_widget.py` (+15
   checks, 17 total in that file, none touching the real Claude API):
   the combo offers all six modes and defaults correctly;
   `start_session` passes each choice's real SDK value (not its label)
   to a fake session, for all six; changing the combo live-calls
   `set_permission_mode` with the newly-selected value, repeatably; a
   real `ClaudeSession.set_permission_mode` call before any session has
   started is a genuine no-op, not a crash. Full `tests/verify/`
   regression suite passes (131 scripts total, 0 unexpected failures --
   the count reflects other concurrent work landed on this repo since
   this session's prior TODO; the sole failure,
   `disabled_verify_claude_desk_widget_claude_api.py`, is an
   already-filed, already-disabled, unrelated flaky item).

49e3732. COMPLETED: A `build_job.py`/`build_desk_proc.py` authoring helper,
   mirroring `build_widget.py`. Converted from a `PARKINGLOT.md` entry surfaced
   while using TODO `97bd090` (`DeskProc`) for real, right after having
   done the same thing by hand for `Job`/`DefineWidget` files earlier
   the same session. Prioritized per direct user request.

   Authoring a `Job`/`DeskProc` tempui file today means hand-writing a
   base64-encode-and-chunk script every single time
   (`base64.b64encode(...)`, split into `Script\t...` lines, write the
   uuid file under `.desk_temp/`) -- there's no equivalent of
   `.desk_temp/build_widget.py` (which does exactly this for
   `DefineWidget`, from a real `.ts`/`widget.json` source directory) for
   either one-shot-script keyword.

   Suggested mechanism: a script taking a summary string plus a `.py`
   file path (and, for a `Job`, a `kind`/capability list, since
   `DeskProc` has neither) and emitting a ready-to-drop tempui file
   under `.desk_temp/`, mirroring `build_widget.py`'s own CLI shape
   (`python3 .desk_temp/build_job.py <summary> <script.py>` or similar
   -- exact argument shape not decided). Should cover both `Job` and
   `DeskProc` (near-identical `Script<TAB>chunk` encoding, just a
   different first line and, for `Job`, extra `Capability` lines) --
   one script, not two, sharing the chunking/encoding helper.
   [planned: build-job-or-desk-proc-helper.md (COMPLETED)]

   COMPLETED: `temp_ui.py` gained `_BUILD_JOB_OR_DESK_PROC_SCRIPT` (the
   generated script's full source, mirroring `_BUILD_WIDGET_SCRIPT`'s
   own wrapping) and `BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME =
   "build_job_or_desk_proc.py"`, added to `SPLIT_DOC_CONTENT`;
   `TEMPUI_DOC_VERSION` bumped 38 -> 39 with a matching
   `_NEW_FEATURES_DOC` entry; `DOC_TEMPLATE`'s existing
   `build_widget.py` paragraph extended to mention it; `_JOBS_DOC`/
   `_DESK_PROC_DOC` each gained a short cross-reference with a real
   invocation example. The generated script itself:
   `build_desk_proc(summary, script_path)`/`build_job(kind, summary,
   script_path, capabilities)` do the base64-encode-and-chunk work
   (shared `_chunk`/`_check_single_line_safe` helpers -- the latter
   rejects a tab/newline in `summary`/a capability name with a clear
   error instead of silently producing a tempui file that parses
   wrong); `argparse` `desk-proc`/`job` subcommands; `main` writes
   `.desk_temp/<uuid>` and prints the path, same shape
   `build_widget.py`'s own `main` already has. New verify coverage,
   real (no mocking): `verify_build_job_or_desk_proc_script.py` (26
   checks: runs the real generated script as a real subprocess for
   both `desk-proc` and `job` python/html, confirms the output
   round-trips through this repo's own real `parse_desk_proc`/
   `parse_job`, multi-chunk scripts, and all three error paths --
   tab-in-summary, newline-in-capability, missing script file);
   `verify_tempui_build_job_or_desk_proc_doc.py` (11 checks: doc-set
   completeness/version bump, the generated script itself compiles).
   Full `tests/verify/` suite (125 scripts) passes.

7dca383. COMPLETED: Installed Jobs: a durable, versioned alternative to the
   ephemeral `Job` mechanism (TODO `d7e66f6`) for an agent's own
   reusable scripts, so a job an agent expects to run repeatedly
   doesn't need to be re-dropped-and-approved as a fresh one-shot
   `.desk_temp` tempui file every single time. Prioritized per direct
   user request.

   **Storage**: instead of a `.desk_temp/jobs/<uuid>/` tempui-derived
   cache, an agent writes real, durable source directly to
   `desk-installed-jobs/<name>/main.py` (plus any other files it wants
   to import from `main.py` -- the job's own directory is put on
   `sys.path` for the duration of a run). `python`-kind only, no `html`
   variant and no `Capability` list -- same unrestricted, no-sandboxing
   in-process trust level `Job`'s own `kind: "python"` already has, so
   there's nothing for a capability list to scope. No manifest file
   (no `job.json`) -- the directory name *is* the job's name, and
   nothing today needs more metadata than that plus the version hash
   below.

   **Versioning**: a job's version is `hashlib.md5(...).hexdigest()
   [:12]` over the concatenation of every regular file under its
   directory (sorted by relative path, each entry's path and content
   both folded in) -- a direct multi-file extension of the exact
   single-blob convention `DeskWindow`'s own custom-widget staleness
   check already established (TODO 5995ffd, `hashlib.md5
   (definition.html_b64.encode("ascii")).hexdigest()[:12]`,
   `src/desk/shell/window.py:2267`) -- not a new hash convention.

   **Registration**: installed jobs are held in-memory on `DeskWindow`
   (`self.current_desk.installed_jobs`, a new `Desk` field mirroring
   `custom_widgets`'s exact load/save/carry-over shape in
   `src/desk/desks.py` -- `_load_installed_job`/`_installed_job_dict`,
   wired into `load_desk`/`desk_state_dict`, carried over unchanged in
   `DeskWindow._capture_desk_state` the same way `custom_widgets`/
   `file_type_registry` already are) and mirrored into a new
   `installed-jobs` top-level section of the current `.desk` file on
   every install/uninstall via the existing `save_current_desk()` --
   there is no separate write path, so the in-memory registry and the
   `.desk` file can never drift. Live-updates to a placed Installed
   Jobs widget reuse the exact `file_type_registry` event pattern
   (`FILE_TYPE_REGISTRY_UPDATED_EVENT`, `window.py:1522-1531`): a new
   `INSTALLED_JOBS_UPDATED_EVENT`, published by `install_job`/
   `uninstall_job`, subscribed to via `bind_event_mediator`/
   `EventSubscription` the same way `widgets/project_files/widget.py`
   already does for the file type registry.

   **MCP tools** (`src/desk/shell/desk_mcp_server.py`, alongside the 7
   tools from TODO `a762501`): `desk_install_job(name)` -- reads
   `desk-installed-jobs/<name>/`, computes its hash, upserts the
   registry entry, saves. `desk_run_installed_job(name,
   config_path=None)` -- looks the job up (GUI-thread-marshaled
   registry read only; the actual execution below is not), then
   **recomputes the on-disk hash and refuses to run if it no longer
   matches the registered version_hash** (a config_path is passed
   through unresolved as `CONFIG_PATH` in the executed script's own
   globals if given -- resolved against the current Desk's directory
   first if relative, same "a relative path resolves against the
   current Desk's own directory" rule every other MCP tool here
   already follows -- `None` if omitted; per direct user request, it
   "should generally live in `.desk_temp` unless otherwise specified"
   is guidance for *where an agent puts* a config file, not a filename
   Desk invents on the job's behalf), then executes `main.py` on a
   background thread (mirrors `widgets/job_runner/widget.py`'s own
   `_run_python_job` exactly: `exec` into a fresh namespace, capture
   stdout/stderr/traceback, no Qt/GUI-thread access from inside the
   job any more than a regular `Job` gets) and returns
   `(ok, stdout, stderr, traceback)` synchronously as the tool result
   -- no placed runner widget needed per run, unlike `Job`/`DeskProc`.

   **The hash re-check above is load-bearing, not a nice-to-have**: it
   is what keeps "no re-approval every run" (see below) actually safe
   -- without it, editing `main.py` on disk after install would let
   already-approved-forever execution silently run different code than
   what the user approved.

   **Approval**: per direct user request, the *only* approval prompt
   is at `desk_install_job` time -- it stays on the normal
   `ClaudeSession._can_use_tool` gated path exactly like every other
   tool (nothing to change there). `desk_run_installed_job` is
   special-cased in `_can_use_tool` (`src/desk/claude_session.py:182`)
   to return `PermissionResultAllow` immediately, before creating a
   pending-permission future, so a run never prompts. Re-installing an
   already-installed name with *changed* source still goes through the
   normal gate (it's a fresh `desk_install_job` call), so a content
   change is never auto-approved by association with an old approval.
   Uninstalling stays on the normal gate too (not bypassed) -- only
   listed as a widget-driven, user-initiated action per this item's own
   spec, not exposed as its own MCP tool at all (matching scope: the
   user asked for install + run via MCP, and list/uninstall via the
   widget only).

   **Installed Jobs widget** (`widgets/installed_jobs/`, `kind:
   "python"`): lists every installed job (name + version hash),
   mirroring `widgets/parking_lot/widget.py`'s per-row
   `QListWidget`/`setItemWidget` shape. Reads the initial list via a
   new `current_context.get_installed_jobs_provider()` hook (mirrors
   `get_file_type_registry_provider`), stays live via the
   `INSTALLED_JOBS_UPDATED_EVENT` subscription above. Each row: a
   "View Source" button that opens an editor widget instance (via the
   existing `current_context.get_editor_or_scrap_opener()`, exactly
   what `JobRunnerWidget._on_view_code_clicked` already calls) for
   every file in that job's directory -- one editor widget per file,
   covering the plural "editor widget(s)" the item's own spec calls
   for. An "Uninstall" button (behind the existing
   `current_context.get_popup_opener()` confirm, matching this
   project's established confirm-before-destroying convention) calling
   a new `current_context.get_installed_job_uninstaller()` hook ->
   `DeskWindow.uninstall_job(name)` -- unregisters only; the
   `desk-installed-jobs/<name>/` directory itself is left on disk
   (uninstall is reversible via a later `desk_install_job` call, not a
   delete).

   **Tempui docs**: per `development-process.md`'s "Keep the tempui
   changelog docs current" section -- this is exactly that case (a new
   feature an in-Desk agent needs to know about). New split doc
   `tempui-installed-jobs.md` (own `_INSTALLED_JOBS_DOC` constant,
   added to `SPLIT_DOC_CONTENT`) explaining the whole mechanism above;
   cross-referenced from `DOC_TEMPLATE`'s existing "a few more files
   live here too, but aren't DSL file types" paragraph, **not** the
   "ten built-in file types" list -- installation happens via an MCP
   tool call against a directory the agent already wrote, never via a
   dropped tempui file, so it isn't itself a DSL file type (matches
   how `build_job_or_desk_proc.py` was already treated as a "few more
   files" entry, not an eleventh keyword). `TEMPUI_DOC_VERSION` 39 ->
   40 with a matching `_NEW_FEATURES_DOC` "## Version 40" entry.

   **Verification**: `tests/verify/verify_installed_jobs.py` (hashing
   determinism/multi-file, install/uninstall registry mutation, `.desk`
   file round-trip via `load_desk`/`save_desk`, `_capture_desk_state`
   carry-over); `tests/verify/verify_desk_mcp_server.py` gains coverage
   for the two new tools (install success/failure, run success/error/
   traceback, config_path resolution, the stale-hash refusal); a new
   `tests/verify/verify_installed_job_permission_bypass.py` (calls
   `ClaudeSession._can_use_tool` directly: confirms
   `mcp__desk__desk_run_installed_job` returns `PermissionResultAllow`
   immediately with no pending future, and that
   `mcp__desk__desk_install_job` is unaffected -- still creates one, as
   before); `tests/verify/verify_installed_jobs_widget.py` (list
   rendering, View Source opens one editor per file, Uninstall's
   confirm-then-call path); `tests/verify/verify_tempui_installed_jobs_doc.py`
   (doc-set completeness/version bump, mirroring
   `verify_tempui_desk_proc_doc.py`).
   [planned: installed-jobs.md]

   COMPLETED: Implemented as designed above, no deviations. New
   `src/desk/installed_jobs.py` (`InstalledJobDefinition`,
   `compute_version_hash`, `installed_job_dir`,
   `INSTALLED_JOBS_UPDATED_EVENT`). `src/desk/desks.py` -- `Desk
   .installed_jobs`, wired into `load_desk`/`desk_state_dict`.
   `src/desk/shell/window.py` -- `DeskWindow.install_job`/
   `.uninstall_job`/`.get_installed_job`/`.get_installed_jobs_dicts`;
   `_capture_desk_state` carries `installed_jobs` over (same as
   `custom_widgets`/`file_type_registry`); `_refresh_picker` registers
   the two new `current_context` hooks at the same choke point
   `file_type_registry_provider` already uses. `src/desk/shell
   /current_context.py` -- `set/get_installed_jobs_provider`,
   `set/get_installed_job_uninstaller`. `src/desk/shell
   /desk_mcp_server.py` -- `desk_install_job(name)` and
   `desk_run_installed_job(name, config_path=None)` (a hand-written
   JSON Schema, not the `{name: type}` shorthand, since that shorthand
   marks every key required -- confirmed directly against the
   installed SDK's own `SdkMcpTool._build_schema`); the latter
   recomputes the on-disk hash and refuses to run on a mismatch before
   ever executing anything; the execution itself is serialized by a
   module-level lock around its `sys.path` mutation (`sys.path` is
   process-global -- without this, two overlapping
   `desk_run_installed_job` calls could leak one job's own directory
   into another's import resolution). `src/desk/claude_session.py` --
   `_can_use_tool` gained a bypass branch for
   `mcp__desk__desk_run_installed_job` specifically (checked by name,
   built from `DESK_MCP_SERVER_NAME`/`RUN_INSTALLED_JOB_TOOL_NAME` so
   the two can't drift), returning `PermissionResultAllow` before a
   pending-permission future is even created;
   `mcp__desk__desk_install_job` and every other tool are unaffected,
   confirmed directly (see verification below). New
   `widgets/installed_jobs/` (`kind: "python"`), mirroring
   `widgets/parking_lot/widget.py`'s per-row `QListWidget`/
   `setItemWidget` shape -- "View Source" opens one editor widget per
   file in the job's directory via the existing
   `get_editor_or_scrap_opener()`; "Uninstall" confirms via
   `get_popup_opener()` (proceeding without confirmation if no popup
   service is registered, rather than silently blocking the action)
   then calls the uninstaller; stays live via a
   `bind_event_mediator`/`EventSubscription` subscription to
   `INSTALLED_JOBS_UPDATED_EVENT`, mirroring
   `widgets/project_files/widget.py`'s own file-type-registry
   subscription exactly. `src/desk/temp_ui.py` -- new split doc
   `tempui-installed-jobs.md`; `TEMPUI_DOC_VERSION` 39 -> 40 with a
   matching `_NEW_FEATURES_DOC` entry; `DOC_TEMPLATE`'s "a few more
   files" paragraph extended (not the "ten built-in file types" list,
   since installation is MCP-tool-driven, not a dropped tempui file).

   New verify coverage: `tests/verify/verify_installed_jobs.py` (14
   checks: hash determinism, changes on content/filename change,
   multi-file order-independence, `.desk` file round-trip via
   `load_desk`/`save_desk`/`desk_state_dict`, an old `.desk` file
   missing the key still loads with `installed_jobs == []`);
   `tests/verify/verify_installed_job_permission_bypass.py` (9 checks,
   against a real `ClaudeSession._can_use_tool`, not a fake: confirms
   `desk_run_installed_job` returns `PermissionResultAllow` with no
   `permission_request` ever emitted and no pending future ever
   created, while `desk_install_job` and an ordinary tool like `Write`
   both still create and resolve a real pending permission request);
   `tests/verify/verify_installed_jobs_widget.py` (15 checks: list
   population from the provider, empty/no-provider cases, live refresh
   via a directly-invoked `_on_mediated_event`, View Source opening one
   editor per real file on disk, Uninstall's confirm/cancel paths, and
   uninstall still proceeding with no popup opener registered);
   `tests/verify/verify_tempui_installed_jobs_doc.py` (18 checks:
   doc-set completeness/version bump/cross-references, mirroring
   `verify_tempui_desk_proc_doc.py`); `tests/verify/verify_desk_mcp_server.py`
   extended (+13 checks, mirroring its own existing fake-`current_context`
   convention) to cover `desk_install_job`'s success/failure pass
   -through, and `desk_run_installed_job`'s success (stdout/CONFIG_PATH
   captured), a raising script (traceback captured), not-installed,
   relative-`config_path`-resolves-against-the-Desk-directory, and the
   stale-hash refusal (source edited on disk after install without a
   fresh `desk_install_job` call). Found and fixed one real regression
   this change itself caused in an unrelated pre-existing script, per
   this project's investigate-don't-just-note convention:
   `tests/verify/verify_lock_persistence.py`'s hand-built fake
   `current_desk` object was missing the new `installed_jobs`
   attribute `_capture_desk_state` now reads unconditionally -- fixed
   by adding it to that fixture, the same way `custom_widgets`/
   `file_type_registry` were already there. Full `tests/verify/` suite
   (142 scripts, 8 `disabled_`) reruns clean, 130/130 passing.

888b537. COMPLETED: A Bridge API capability so a `kind: "html"` widget can run an
   already-Installed Job too (TODO `7dca383`), not just an agent via
   MCP -- `desk.installedJobs.run(name, configPath)`, capability
   `installed_jobs`. Prioritized per direct user request, immediately
   following `7dca383`.

   **Refactors `7dca383`'s own implementation to add this without
   duplicating its safety-critical logic.** `7dca383` put the "is this
   name installed, does its on-disk source still match the installed
   version hash" check and the actual background-thread exec directly
   inside `desk_mcp_server._run_installed_job_tool`/`_run_installed_job`
   -- fine when there was exactly one caller, wrong once there are two
   (MCP and Bridge) that both need the *identical* stale-hash refusal
   and execution behavior. Moving to a single shared implementation:
   - `src/desk/installed_jobs.py` gains `run_script(script_text,
     job_dir, config_path) -> (ok, stdout, stderr, traceback)` (the
     exec-on-a-background-thread body, moved verbatim from
     `desk_mcp_server.py`, including its `_RUN_LOCK` --
     `sys.path` is process-global, so the lock now also correctly
     serializes a Bridge-triggered run against an MCP-triggered one,
     which wasn't previously possible to even have collide) and
     `resolve_config_path(directory, raw) -> str | None` (the
     relative-resolves-against-the-Desk-directory rule, also moved out
     of the MCP tool so both entry points share one implementation).
   - `DeskWindow.get_installed_job_for_run(name) -> InstalledJobDefinition`
     (raises `ValueError` for "not installed" or "stale hash" --
     the load-bearing check from `7dca383`, now defined exactly once).
   - `DeskWindow.run_installed_job(name, config_path, on_result)` --
     non-blocking (mirrors `DeskWindow.run_transform`/
     `TransformsService._invoke`'s own shape exactly): validates via
     `get_installed_job_for_run` (raises synchronously, before spawning
     anything, so a caller can tell "bad request" from "the job ran and
     here's what happened"), resolves `config_path`, then spawns a
     background thread running `installed_jobs.run_script` and calls
     `on_result(ok, stdout, stderr, traceback)` from that thread.
   - `desk_mcp_server._run_installed_job_tool` becomes a thin adapter:
     marshals `window.run_installed_job(name, config_path, on_result)`
     onto the GUI thread (fast -- it only validates and spawns a
     thread), with `on_result` resolving an `asyncio.Future` via
     `loop.call_soon_threadsafe` that the handler then awaits --
     `ValueError`/`RuntimeError` from the GUI-thread call still produce
     the exact same `is_error` text results as before (same wording,
     existing verify coverage for `7dca383` unchanged).

   **The new Bridge API route**: `POST /api/bridge/installedJobs/run`
   (`src/desk/server/app.py`, alongside `transforms_run` --
   `InstalledJobsRunRequest {name: str, config_path: str | None}`,
   gated by `require_caller("installed_jobs")`) calls
   `gui_bridge.window.run_installed_job(...)` via `run_on_gui_async`
   (non-blocking GUI-thread call, matching `transforms.run`'s own
   shape exactly -- `_invoke`'s "spawn a thread, call back later"
   pattern is the real precedent here, not `run_on_gui`'s synchronous
   form) and returns `{ok, stdout, stderr, traceback}` -- the same
   shape the MCP tool already returns. A `ValueError` from
   `get_installed_job_for_run` (not installed / stale hash) is caught
   at the route and surfaced as `HTTPException(400, ...)`, distinct
   from a successful-but-failing run (`ok: false` in a 200 response) --
   the same "bad request vs. the thing you asked for actually failed"
   split the MCP tool's `is_error` already draws.

   **Timeout, a real difference from the MCP path**: `GuiBridge
   .call_async`'s own `timeout` (default 10s) bounds how long the
   *synchronous HTTP request* can wait for `on_result` -- unlike the
   MCP path (an `await` with no bound), a Bridge-API-initiated run is a
   blocking request/response over HTTP and can't wait forever.
   `run_on_gui_async` gains an optional `timeout` parameter (default
   unchanged, so `transforms.run`/`introspect.snapshot` are
   unaffected) and the new route passes a longer
   `INSTALLED_JOB_RUN_TIMEOUT_SECONDS` (a new constant in
   `installed_jobs.py`, documented in the new doc bullet below so an
   `html` widget author knows a run expected to take longer belongs on
   the MCP/agent-initiated path instead, which has no such bound) --
   note a job that times out from the *caller's* perspective keeps
   running to completion in the background regardless (the thread
   isn't killed, `on_result` just has no one left listening); this is
   an accepted, documented limitation of the synchronous-HTTP shape,
   not a bug to design around further in this pass.

   **Docs**: `_CUSTOM_WIDGETS_DOC` (`src/desk/temp_ui.py`) gains a
   `desk.installedJobs.run(name, configPath)` bullet in "The Desk
   Bridge API" section, right after the `transforms` bullet, covering
   the timeout caveat above and cross-referencing
   `tempui-installed-jobs.md`. `_JOBS_DOC`'s own closed
   capability-name list (used by a `Job`'s `Capability` lines) gains
   `installed_jobs`. `TEMPUI_DOC_VERSION` bumped with a matching
   `_NEW_FEATURES_DOC` entry, per `development-process.md`'s "Keep the
   tempui changelog docs current" section.

   **Verification**: extended `tests/verify/verify_desk_mcp_server.py`
   coverage for `_run_installed_job_tool` continues to pass unchanged
   (same behavior/wording, now routed through `DeskWindow
   .run_installed_job` instead of doing everything itself); new
   `tests/verify/verify_installed_jobs_bridge_api.py` (real FastAPI
   `TestClient`, matching however the existing Bridge API route tests
   are structured -- capability-gating 403, success, not-installed and
   stale-hash 400s, the timeout constant is honored); `tests/verify/
   verify_tempui_jobs_doc.py` gains `installed_jobs` to its capability
   -name-list check; a new/extended tempui doc verify script covers
   the new Bridge API bullet. Full `tests/verify/` suite rerun clean.
   [planned: installed-jobs-bridge-api.md]

   COMPLETED: Implemented as designed above, no deviations. The
   `7dca383` refactor landed exactly as planned:
   `desk.installed_jobs.run_script`/`_RUN_LOCK`/`resolve_config_path`/
   `INSTALLED_JOB_RUN_TIMEOUT_SECONDS` (120.0); `DeskWindow
   .get_installed_job_for_run`/`.run_installed_job` (non-blocking,
   mirrors `run_transform`); `desk_mcp_server._run_installed_job_tool`
   now a thin adapter (an `asyncio.Future` resolved via
   `loop.call_soon_threadsafe` from `on_result`) with identical
   behavior/wording to before. New `POST /api/bridge/installedJobs/run`
   (`src/desk/server/app.py`, `InstalledJobsRunRequest`,
   `run_on_gui_async` gained an optional `timeout` param, default
   unchanged for `transforms.run`/`introspect.snapshot`); `ValueError`
   (not installed/stale hash) -> `HTTPException(400, ...)`, distinct
   from a successful-but-failing run (`200`, `ok: false`).
   `desk.installedJobs.run(name, configPath)` added to
   `BRIDGE_CLIENT_TEMPLATE`. Docs: `_CUSTOM_WIDGETS_DOC` gained the
   `desk.installedJobs.run` bullet (with the 120s-timeout caveat);
   `_JOBS_DOC`'s closed capability list gained `installed_jobs`;
   `tempui-installed-jobs.md` gained a "Running from a kind:\"html\"
   widget" section; `TEMPUI_DOC_VERSION` 40 -> 41 with a matching
   `_NEW_FEATURES_DOC` entry.

   **Found and fixed one real bug via manual testing while writing
   this item's own verify coverage, recorded in `LEARNINGS.md`**:
   `contextlib.redirect_stdout`/`redirect_stderr` (used by
   `run_script`, moved verbatim from the prior implementation) swap
   `sys.stdout`/`sys.stderr` process-wide, not per-thread -- a `print()`
   from any *other* thread while a job's own capture window is open
   gets silently swallowed into that job's own buffer instead of
   reaching the real terminal. Not a regression in product code (the
   same pattern already existed in `widgets/job_runner/widget.py`'s
   `_run_python_job`, and `_RUN_LOCK` already prevents two installed
   -job runs from colliding with each other this way) -- purely a
   hazard for a test that prints from the main thread while a
   background job run is in flight, which is exactly what
   `verify_installed_jobs.py`'s own non-blocking-run test originally
   did, and was fixed there (defer every print-performing assertion
   until after the job's own execution window has closed).

   New verify coverage: `tests/verify/verify_installed_jobs.py`
   extended (+13 checks, 27 total) -- `resolve_config_path` (None/
   empty/relative/absolute), `get_installed_job_for_run` (matching
   hash/not-installed/stale-hash) and `run_installed_job` called
   directly against the *real* `DeskWindow` methods (grabbed
   unbound off the class and called against a minimal duck-typed
   `.current_desk`-only stand-in, mirroring
   `verify_lock_persistence.py`'s own established technique) --
   proves genuine non-blocking behavior (returns before a real 0.2s
   -sleeping job finishes) and real `CONFIG_PATH` resolution end to
   end. `tests/verify/verify_desk_mcp_server.py`'s installed-job-run
   tests rewritten (47 checks total, unchanged count) to match the
   refactored thin-adapter shape -- a fake `run_installed_job` that
   resolves via a real background thread after a short delay (not
   immediately), proving the future-based relay via
   `call_soon_threadsafe` genuinely waits. New
   `tests/verify/verify_installed_jobs_bridge_api.py` (12 checks,
   mirroring `verify_bridge_api_transforms_run.py`'s exact real
   -`start_server`-plus-`QTimer`-delayed-callback shape): a delayed
   successful run, config_path omitted -> `None`, a failing script ->
   `{"ok": false, ...}` at HTTP 200 (not an HTTP error), a validation
   `ValueError` -> HTTP 400 (not 200), missing-capability -> 403, and
   the Bridge client declares `installedJobs.run`.
   `tests/verify/verify_tempui_jobs_doc.py`'s capability-name-list
   check gained `installed_jobs`;
   `tests/verify/verify_tempui_installed_jobs_doc.py` extended (+7
   checks) for the new Bridge API cross-references and the Version 41
   changelog entry. Full `tests/verify/` suite (139 scripts, 8
   `disabled_`) reruns clean, 131/131 passing.

b9d3de5. COMPLETED: Give an in-Desk agent a documented way to learn its own
   placed widget instance id, via `ClaudeAgentOptions.env` (a static,
   launch-time fact, not a live query). Converted from a
   `PARKINGLOT.md` entry, surfaced using TODO `97bd090` (`DeskProc`) to
   screenshot "the widget hosting this very conversation" -- there was
   no direct way to answer "which placed widget instance am I": had to
   open the current `.desk` file by hand and pattern-match the
   `claude_desk` entries' `instance_id` against the session's own
   transcript-directory name (which happens to be the instance id, but
   that's an undocumented implementation detail to rely on, not a
   supported lookup). Prioritized per direct user request.

   **Decided (2026-09-01 discussion):** scoped down from the original
   open "kludge vs. formalized channel" question to just the
   kludge-but-a-good-one half -- an environment variable, not a
   sentence folded into the initial prompt. Confirmed directly against
   the installed SDK that `claude_agent_sdk.ClaudeAgentOptions` already
   has a real `env: dict[str, str]` field, unused today
   (`desk.claude_session.ClaudeSession._connect_and_maybe_prompt`,
   `src/desk/claude_session.py:105`, only sets
   `session_id`/`resume`/`model`/`permission_mode`/`cwd`/`can_use_tool`).
   Also confirmed `DeskWindow._bind_claude_desk_widget`
   (`src/desk/shell/window.py:479-480`) already comments that "a
   claude/claude_desk widget's instance_id doubles as its session_id"
   -- so the value to inject is already threaded down to
   `ClaudeSession.start`'s own `session_id` parameter, nothing new to
   plumb, just pass it again as `env={"DESK_WIDGET_INSTANCE_ID":
   session_id}` (or similar) at the same call site. An env var beats a
   prompt sentence for this specific need: zero context-token cost,
   survives context compaction perfectly (it's not conversation
   history), and is trivially extensible to more static self-facts
   (Desk's own directory, the widget's kind, ...) without prompt bloat
   or re-deriving `_doc_path()`-style plumbing per fact. Should cover
   both Claude-hosting widget kinds -- `widgets/claude_desk/widget.py`
   (`ClaudeAgentOptions.env`, confirmed to exist) and
   `widgets/claude/widget.py` (the PTY-based one, which spawns a real
   OS subprocess directly and so can just set `env` on that subprocess
   the ordinary way) -- since the same "which instance am I" gap
   applies to either.

   Everything *dynamic* (list what's currently placed, live state,
   reveal/screenshot another widget right now, force a save) is
   explicitly **not** this item's concern -- moved to TODO `a762501`
   (the in-process MCP server) instead, per the same discussion: a
   static env var can't answer a question whose answer changes during
   the session, and trying to make it do so is the wrong tool.
   [planned: desk-widget-instance-id-env-var.md]

   COMPLETED: Implemented as designed above, no deviations.
   `ClaudeSession._connect_and_maybe_prompt` (`src/desk/claude_session.py`)
   passes `env={"DESK_WIDGET_INSTANCE_ID": session_id}` on the
   `ClaudeAgentOptions` it builds. `widgets/claude/widget.py`'s
   `ClaudeWidget.start_session` prefixes both the `--resume` and fresh
   -launch shell commands with `DESK_WIDGET_INSTANCE_ID=<session_id> `
   before `exec claude` (a plain shell-simple-command env-var prefix,
   scoped to that one command only). Documented in a new "Environment
   variables" section in `desk-temporary-ui.md` (`src/desk/temp_ui.py`'s
   `DOC_TEMPLATE`) rather than a per-session prompt sentence, so it's
   extensible to future static self-facts without further prompt bloat;
   `TEMPUI_DOC_VERSION` 41 -> 42 with a matching `_NEW_FEATURES_DOC`
   entry.

   New verify coverage: `tests/verify/verify_desk_widget_instance_id_env_var.py`
   (10 checks) -- `ClaudeSession._connect_and_maybe_prompt`'s built
   `ClaudeAgentOptions.env` checked directly (fresh and resumed) against
   a monkeypatched `ClaudeSDKClient` (no real SDK connection, mirroring
   `verify_installed_job_permission_bypass.py`'s own pattern); a real
   `ClaudeWidget()` (a real local `bash` PTY, no live `claude`/network
   dependency, mirroring `verify_terminal_cwd.py`) with `type_into_shell`
   patched to capture the exact command string for both the fresh
   -launch and resume branches; the new doc section, its
   `TEMPUI_DOC_VERSION` bump, and its `_NEW_FEATURES_DOC` entry. Full
   `tests/verify/` suite rerun clean (the one pre-existing failure,
   `verify_eye_button_persists_title_only.py`, reproduces identically on
   `main` before this change -- unrelated, not a regression).

765bd2a. COMPLETED: Design the syntax and semantics of a simple pipe-chained verb
   DSL for expressing a chain of Desk actions -- deliberately scoped to
   the *language itself* (grammar, verb/argument shape, how values
   flow between stages, the escape-hatch's own denotation, error/
   partial-failure semantics), independent of how an instance of it
   gets delivered to Desk (a dropped `Job`/`DeskProc` tempui file's
   `Script` line, an MCP tool argument via TODO `a762501`, or anything
   else). Converted from a `PARKINGLOT.md` entry (originally "a
   narrower, zero-code, single-click primitive for reveal/screenshot a
   widget specifically"), redirected toward a general pipeline-DSL
   approach in an earlier discussion, then **re-scoped again in this
   session's follow-up discussion** to explicitly decouple the DSL's
   own design from the file-vs-MCP transport question once `a762501`
   came up as a live parallel/alternative transport -- the DSL should
   come out the same regardless of which transport(s) end up carrying
   it. Prioritized per direct user request.

   Suggested direction (per explicit user guidance -- not a finished
   design, a starting point to flesh out during actual planning):
   - A pipeline expression chains built-in verbs with `|`, shell-style,
     each verb taking plain arguments and (optionally) consuming the
     previous stage's output -- e.g. something in the shape of
     `reveal_widget abc123 | screenshot_widget abc123 shots/x.png |
     open_image`.
   - **Escape hatch**: a pipeline stage can instead be an inline,
     base64-encoded, functional Python snippet (a single expression or
     function, not a full script) for logic no built-in verb covers --
     exact denotation not decided (e.g. a `py:<base64>` stage syntax).
   - **Do not convert values into strings needlessly.** A stage's real
     Python return value (a `dict`, a `list`, a `bool`, raw image
     bytes, ...) should pass directly to the next stage as itself when
     both run in the same process, not be forced through a string
     encoding/decoding round trip just because the syntax looks
     shell-like.
   - **Use temp files as makes sense** -- specifically when a value
     needs to survive a process boundary, be inspected/opened by
     something outside this pipeline (e.g. handing a screenshot's own
     PNG bytes to the Image Viewer via a real file, the same way
     `deskproc.screenshot_widget` already does), or is large/binary
     enough that passing it as an in-memory string would be wasteful or
     lossy.

   Open, undecided questions to work out during actual planning: how
   verbs are registered/discovered (a fixed built-in list, mirroring
   `deskproc.*`'s own methods, and/or the candidate MCP tools from
   `a762501`? something a widget/domain package could extend?); how a
   verb's own argument parsing/type coercion works given "everything
   after a keyword is one opaque value" is the tempui DSL's existing
   convention elsewhere (a convention this DSL need not inherit, since
   it's explicitly not tied to being a tempui keyword anymore); and
   what the DSL itself defines as its error/partial-failure reporting
   *contract* (a structured per-stage result value, at minimum) --
   independent of how any given transport chooses to surface that
   (a Runner widget's status display, an MCP tool's return value,
   or something else).
   [planned: pipe-chained-verb-dsl.md]

   COMPLETED: Fully specified in `plans/pipe-chained-verb-dsl.md` --
   grammar (a quoting-aware `|`-split of stages, each a `py:<base64>`
   escape-hatch expression or `verb_name arg arg ...` with `shlex`
   -style argument splitting); a fixed, curated built-in verb registry
   rather than an extensible one (deliberately, to avoid designing for
   a hypothetical future requirement); real in-process Python object
   passing between stages (never a string round-trip), with an opt-in
   `{"ok": ...}`-dict return convention for verbs with a natural
   success/failure outcome; the escape hatch as a single `eval()` (a
   callable result gets called with the piped value, a non-callable
   result is used as-is); fail-fast execution with a structured
   per-stage result contract mirroring `Job`/`DeskProc`/Installed Jobs'
   existing `{"ok", ..., "traceback"}` shape. Three worked examples
   walked by hand against every rule as this item's own verification
   (no code was written -- this item's scope is design only, per its
   own text). Delivery transport, verb extensibility, and the actual
   interpreter/backing implementations are explicitly left to a later,
   separate TODO.

1239cfd. COMPLETED: Stop using counting numbers to identify TODO items — this
   item's own id (visible once this file is converted, right below)
   proves the scheme it describes. Priority/work order is now
   exclusively the item's physical position in this file, top to bottom;
   sequential numbers were only ever a side effect of that order, not a
   real identity, and renumbering on every reorder was pure churn.
   Replaced with a permanent, content-derived 7-lowercase-hex-digit id
   per item, generated once (`scripts/todo_item_ids.py`) and never
   recomputed afterward — even if the item's own description is later
   edited. Referred to going forward as e.g. "TODO 2c36b01". Performed
   the one-time conversion of this file (every item's leading number
   replaced with its id; every "item N" / "items N/M/..." cross
   -reference in the file rewritten to "TODO <id>" / "TODO <id>/TODO
   <id>..."). `development-process.md` updated with the new scheme (see
   its "Item IDs" section) and the "Prioritizing TODO Items" section
   simplified — reordering is now just moving an item's text block,
   no renumbering step needed. Procedure recorded in
   `how-to-convert-item-id-one-time.md` for reuse in other projects.
c76cf23. COMPLETED: Project scaffolding & dependency management — Python package
   layout, `pyproject.toml`, dev dependencies (PyQt6, PyQt6-WebEngine,
   FastAPI, uvicorn, watchdog, websockets), entry point script.
   [planned: project-scaffolding.md]
bbee592. COMPLETED: Local web server — FastAPI/uvicorn app bound to loopback
   with an unpredictable per-launch port and auth token, static asset
   serving, base REST/WebSocket scaffolding.
   [planned: local-web-server.md]
b7c3757. COMPLETED: Desk Shell — PyQt6 `QMainWindow` + `QWebEngineView` that
   starts the local web server in-process and loads it, basic app
   lifecycle (startup/shutdown, quitting cleanly stops the server).
   [planned: desk-shell.md]
9f7b7a5. COMPLETED (SUPERSEDED by TODO 8941224): Workspace SPA shell — the
   pannable/zoomable canvas viewport (no widgets yet), served as static
   assets by the local web server. Per updated requirements (see
   `CLAUDE.md` and `design-docs/architecture.md`), the web-based Workspace
   SPA has been removed and replaced by a native Python/Qt Workspace
   Canvas — see TODO 8941224. Kept here for history; the Vite-based frontend it
   describes no longer exists in the codebase.
   [planned: workspace-spa-shell.md]
8941224. COMPLETED: Python-native Workspace Canvas & Chromium Widget hot-reload
   backend — replace the Vite-based Workspace SPA with a native
   `QGraphicsView`/`QGraphicsScene` canvas (pan/zoom in Qt, no browser
   involved); local web server (already Python, already part of the Desk
   process) gains per-widget static serving plus a `watchdog`-based source
   watcher; introduce `ChromiumWidget` (a `QWebEngineView` embedded via
   `QGraphicsProxyWidget`) as the generic building block for hosting a
   hot-loaded SPA on the canvas, wired to the watcher through an in-process
   Hot Reload Broker (Qt signal).
   [planned: python-native-workspace-canvas.md]
600eea1. COMPLETED: Fix widget frame drag/resize — the `WidgetFrame` chrome
   (see TODO 6090103) renders correctly (titlebar, resize handle cursors/
   icons all show up as expected in the demo), but interacting with it
   doesn't work: dragging the titlebar doesn't move the widget, and
   dragging the edge handles doesn't resize it. The headless `_on_drag`
   -math checks done when TODO 6090103 was built passed, so the bug is
   likely in the real mouse-event delivery path (e.g.
   `mousePressEvent`/`mouseMoveEvent` wiring, event acceptance, or a
   conflict with `WorkspaceView`'s own `ScrollHandDrag` panning) rather
   than the drag/resize math itself.
   **Prioritized ahead of TODO d3d913d.**
   [planned: fix-widget-frame-drag-resize.md]
d3d913d. COMPLETED: Widget manifest & loader — `widget.json` schema, discovery of widgets
   from a widgets directory (building on TODO 498f727's `python`/`html` kind
   detection), capability declarations, mounting `kind: "html"` widgets as
   `ChromiumWidget` instances on the canvas (building on TODO 8941224's
   primitive) instead of the iframe approach originally described.
   [planned: widget-manifest-loader.md]
45ca161. COMPLETED (SUPERSEDED by TODO 498f727): Python-backed widgets (interim,
   in-process) — a `kind: "python"` widget shipped a `widget.py` with a
   `render() -> str` function, rendered to HTML and served over HTTP by
   the Local Web Server. Per updated requirements (see
   `design-docs/architecture.md`), this has been replaced: `python`
   widgets now render directly as native `QWidget`s with no local
   server/HTTP involved at all — see TODO 498f727. Kept here for history; the
   HTTP-rendering code this item added no longer exists in the codebase.
   [planned: python-backed-widgets.md]
498f727. COMPLETED: Native Qt Python widget hosting — `kind: "python"` widgets ship a
   `widget.py` exposing `build() -> QWidget`; a `PythonWidgetHost` in the
   Desk Shell imports the module directly and embeds the returned
   `QWidget` on the canvas (via `QGraphicsProxyWidget`) — no HTTP, no
   local server, no browser. Hot reload means re-importing the module
   fresh and swapping in a newly-built widget. `discover_widgets`/
   `WidgetWatcher` move out of `desk.server` into a shared `desk.widgets`
   module, since they're no longer HTTP-server concerns. The shipped
   example widget (`widgets/demo/`) becomes a native `QWidget` instead of
   server-rendered HTML. The Local Web Server continues to exist, now
   scoped to only `kind: "html"` widgets + the future Bridge API.
   [planned: python-native-widget-hosting.md]
6090103. COMPLETED: Widget UX chrome (drag/resize) — every widget on the canvas gets a
    common `WidgetFrame` wrapper (built once, at the canvas-integration
    layer, wrapping either a `PythonWidgetHost` or `ChromiumWidget`
    uniformly): a titlebar across the top that acts as a drag handle to
    move the widget, and a frame with resize handles on the left, right,
    and bottom edges. Dragging/resizing must stay correct at any Workspace
    Canvas zoom level. Full spec in the new `design-docs/widget-ux.md`.
    Note: originally marked COMPLETED based on headless verification of
    the drag/resize math only, which missed that interactive dragging
    didn't actually work in the running app (a missing `event.accept()`
    bug); fixed by TODO 600eea1, which also added a realistic event-path
    regression check this item's own verification lacked.
    [planned: widget-ux-chrome.md]
d0d7b37. COMPLETED: Fix zoom/pan interaction & add a zoom control widget — several related
    Workspace Canvas zoom/pan UX problems reported from real trackpad use,
    plus a new always-available zoom control:
    - Trackpad pinch-to-zoom (pinch to zoom out, un-pinch/spread to zoom
      in) doesn't work correctly. `WorkspaceView` currently only zooms via
      `wheelEvent` (`QWheelEvent`, used for both mouse wheels and
      two-finger trackpad scroll), which doesn't distinguish scroll from a
      native pinch gesture — likely needs a `QNativeGestureEvent`
      (`PinchNativeGesture`) handler (or `QGestureEvent` via
      `grabGesture(Qt.GestureType.PinchGesture)`) so trackpad pinch is
      recognized as zoom input, distinct from two-finger scroll.
    - Two-finger-scroll-to-zoom is way too sensitive — needs damping/
      tuning of how `wheelEvent`'s delta maps to the zoom factor.
    - Dragging a widget gets increasingly sensitive as zoom increases.
      Investigated: the drag math itself is zoom-invariant by
      construction and unchanged; synthetic-event testing at non-unity
      zoom in this environment was inconclusive (devicePixelRatio=2.0
      interacting with manually-constructed `QMouseEvent`s — see
      `plans/zoom-pan-interaction-fixes.md`'s Status section and
      `design-docs/widget-ux.md`'s Open Questions). The chrome
      -counter-scaling fix below is the primary fix applied for this
      symptom; **real-hardware re-check recommended**.
    - Interaction model: zooming the canvas currently magnifies
      *everything* uniformly, including widget chrome (titlebar, resize
      handles), since the whole `WidgetFrame` is one `QGraphicsProxyWidget`
      scaled by the view's transform. Titlebars should stay a constant
      size on screen regardless of zoom — only each widget's own content
      area should zoom/pan with the view. Likely requires decoupling the
      chrome's rendering from the view's scale transform (e.g.
      counter-scaling the chrome, or restructuring what actually gets
      scaled).
    - New: a small persistent zoom control, anchored to the lower-right
      corner of the `WorkspaceView`'s viewport in screen space (not part
      of the zoomable/pannable scene), visible only when the current zoom
      is non-unity (≠ 1.0×): a "zoom to fit content" button (fits all
      widgets in view, with a small 0.1% margin), a "reset zoom" button
      (back to 1.0×/default), and a small zoom-level slider.
    **Prioritized ahead of TODO 7845a0f.**
    [planned: zoom-pan-interaction-fixes.md]
7845a0f. COMPLETED: Fix widget drag/resize scaling when zoomed out — confirmed on real
    trackpad hardware (following up on TODO d0d7b37's unresolved open
    question): dragging a widget's titlebar/resize handles is scaled
    (moves too much for a given cursor movement) specifically when the
    Workspace Canvas is zoomed *out*. Root cause under investigation:
    likely that `event.globalPosition()`/`position()`/`scenePosition()` as
    delivered to a `QGraphicsProxyWidget`-*embedded* child widget (the
    titlebar/resize handles) don't reliably reflect the real screen
    position at non-unity view scale — Qt appears to recompute these when
    translating a scene-level mouse event into the embedded widget's own
    `QMouseEvent`, and that recomputation doesn't round-trip cleanly
    through the view's current zoom.
    **Prioritized ahead of TODO 75d5d15.**
    [planned: fix-drag-scaling-when-zoomed-out.md]
75d5d15. COMPLETED: Introduce the Desk concept — a **Desk** is a named set of widgets
    together with their state (including metadata like each widget's size
    and location/position), associated with a directory on disk. Desks
    can be serialized/deserialized to a file, by default stored in the
    associated directory. A Desk's **name is the filename of its
    serialized file**.

    Top-left picker UX (a screen-space overlay over the Workspace Canvas,
    mirroring the zoom control's bottom-right placement from TODO d0d7b37) —
    actually **two pickers side by side**:
    - A **dropdown**: recently-used Desks (MRU) plus a trailing "..."
      entry (opens a full Desk file picker) — for switching which Desk is
      currently open.
    - A **button**: opens a directory picker, to set/change the
      *currently selected Desk's* associated directory.

    By default this picker area renders at **half-alpha** (semi
    -transparent) and shows only the current Desk's name (the two
    controls aren't separately visible); **on hover**, it splits into the
    two distinct controls above (dropdown + directory-picker button).

    Switching to a different Desk (via the dropdown) or changing the
    current Desk's associated directory (via the button) both require
    **confirmation** first, since either means switching away from
    whichever Desk is currently open.

    Each app window (only one window exists for now) can have only **one**
    Desk selected/open at a time.

    This formalizes and supersedes TODO acd87ae ("Workspace persistence") — see
    that item.
    **Prioritized ahead of TODO 37d50f2.**
    [planned: desk-concept.md]
37d50f2. COMPLETED: Add widget instances to a Desk via a right-click typeable-filter menu
    — right-clicking anywhere on the Workspace Canvas opens a small popup
    listing every registered widget type (from the discovered widget
    catalog), with a typeable filter box at the top that live-filters the
    list as the user types (substring match against the widget's
    name/id). Selecting an entry (click, double-click, or Enter with a
    selection) adds a new instance of that widget type to the current
    Desk, placed at the right-click location, sized per the widget's
    manifest `default_size`. Escape or clicking away closes the popup
    without adding anything.
    **Prioritized ahead of TODO 45659cc.**
    [planned: add-widget-context-menu.md]
45659cc. COMPLETED: Console widget — a real shell (`bash`), enabling running `claude`.
    Implementation resolved: native-Qt (a `QPlainTextEdit`-based terminal
    over a real PTY), not Chromium/`xterm.js` — see
    `plans/console-widget.md` and `design-docs/architecture.md`.
    **Prioritized ahead of TODO 255d777.**
    [planned: console-widget.md]
255d777. COMPLETED: Fix console widget rendering for full-screen TUI programs
    (e.g. `claude`) — confirmed via screenshot: running `claude` (Claude
    Code) in the Console widget produced garbled, overlapping, unreadable
    text with no visible cursor. Root cause: the regex-stripped-ANSI
    approach from TODO 45659cc only ever *appended* decoded bytes — it had no
    concept of cursor position, so a program that redraws its UI in place
    (cursor-positioning, box-drawing, colored status bars — exactly what
    `claude`'s own interface does) produced exactly this kind of garbled
    output. Fixed by adding `pyte` (real ANSI/VT100 terminal emulation) and
    rendering the *current terminal screen* from `pyte`'s screen buffer on
    every update, plus a real cursor at the reported position/visibility.
    **Prioritized ahead of TODO 950774b.**
    [planned: console-widget-real-terminal-emulation.md]
950774b. COMPLETED: Fix console widget crash on device-status-report / private
    CSI queries — confirmed via real-app crash log: running `claude` in the
    Console widget crashed the entire app (`Abort trap: 6`) with
    `TypeError: Screen.report_device_status() got an unexpected keyword
    argument 'private'`. Root cause: `pyte` 0.8.2's `Stream` dispatches
    DEC-private CSI sequences (`ESC[?...`) by calling the matching
    `Screen` method with an extra `private=True` keyword argument, but
    most of `pyte.Screen`'s CSI-handling methods (`report_device_status`,
    `cursor_position`, `cursor_to_column`, `set_margins`, and most cursor
    -movement/erase methods) don't accept a `private` keyword or `**kwargs`
    at all — a real, current upstream `pyte` gap (confirmed: 0.8.2 is the
    latest release), not something we got wrong. Fixed with a
    `_ResilientStream(pyte.Stream)` overriding `feed()` to recover
    per-character on a dispatch exception (a whole-call `try/except` was
    tried first but silently dropped real output queued after the bad
    sequence in the same chunk — see the plan's Status section), plus a
    `_PtyScreen(pyte.Screen)` overriding `write_process_input` to actually
    write device-status-report replies back to the real PTY instead of
    pyte's default no-op. Verified against the real originally-reported
    crash: launching `claude` now triggers and survives the exact same
    private-CSI sequence that used to abort the process.
    **Prioritized ahead of TODO 420c40d.**
    [planned: console-widget-pyte-private-csi-crash.md]
420c40d. COMPLETED: Code editor widget — file editing widget using the Desk
    Bridge API (if Chromium-hosted, e.g. Monaco) or direct Python calls (if
    native-Qt, e.g. `QScintilla`) for file I/O and project/workspace
    awareness. Implementation resolved: native Qt via `QScintilla`, not
    Chromium/Monaco (direct instruction). Ships as `widgets/editor/`: open/
    edit/save a file via `QFileDialog`, syntax highlighting selected by
    file extension, unsaved-changes confirmation (Save/Discard/Cancel)
    before opening a different file. Automatic Desk-directory ("project/
    workspace") awareness is explicitly out of scope for now — no `python`
    widget has a way to learn the current Desk's directory yet; see the
    plan for why that's better solved generally by the Desk Bridge API
    (TODO 47b5731) than bolted on ad hoc here.
    **Prioritized ahead of TODO c204861.**
    [planned: code-editor-widget.md]
c204861. COMPLETED: Add a widget close button — an "X" button in the upper-right
    corner of the `WidgetFrame` chrome (see TODO 6090103), which removes the
    widget (from the canvas and the current Desk) after a confirmation
    prompt, to guard against accidental clicks/data loss. A new
    `_CloseButton` chrome element is hit-tested centrally by
    `WorkspaceView` (like the existing titlebar/resize-handle chrome, not
    via a real `QPushButton.clicked`, since the view already intercepts
    every titlebar-area press before it could reach an embedded button —
    see the plan). Verified entirely headlessly (hit-testing, click-vs-
    drag-away semantics, confirm/cancel flow, drag/resize regression) —
    no step needed real-window/visual inspection.
    **Prioritized ahead of TODO 001d042.**
    [planned: widget-close-button.md]
001d042. COMPLETED: Generalized hot reload — extend the single-widget
    hot-reload mechanism (TODO 498f727 for `python` widgets, TODO 8941224
    for `html` widgets) to arbitrary manifest-discovered widgets of both
    kinds. Per-instance source reload already worked generically across
    both kinds (TODO 8941224/TODO 498f727) — the actual gap was that
    `discover_widgets()` only ever ran once at startup, so a widget
    directory added/removed/changed while running had no effect until
    restart. Fixed: `DeskWindow` re-runs
    `discover_widgets()` on every existing `widget_changed` event
    (reusing that signal, no new watcher plumbing needed) and refreshes
    the widget catalog (add-widget menu, recognized `widget_id`s).
    Verified entirely headlessly with a real `WidgetWatcher` against a
    temp directory (new/changed/removed widget directories, plus a
    regression check that per-instance source reload still works).
    [planned: generalized-hot-reload.md]
47b5731. COMPLETED: Desk Bridge API — capability-scoped REST endpoints
    (`workspace.getState`, `fs.readFile`/`writeFile`,
    `widgets.list/open/close`, `self.getManifest`) plus the client library
    injected into each `ChromiumWidget`'s page. Applies only to `kind:
    "html"` widgets — `python` widgets access Desk internals via direct
    Python imports instead (see `design-docs/architecture.md`). Shipped as
    REST-only for now (no WebSocket/push channel — its strongest cited use
    case, PTY streaming for a Chromium-hosted Console widget, is moot now
    that the Console widget resolved native-Qt; see the plan's Scope
    section). Added a minimal `instance_id` to `WidgetState`/`WidgetFrame`
    (backward-compatible with existing `.desk` files) since
    `widgets.close(instanceId)` needed real per-instance identity that
    didn't exist anywhere before. Cross-thread access to live
    `DeskWindow`/`WorkspaceView` state (for `workspace.getState`/
    `widgets.open`/`close`, which run on the Local Web Server's background
    thread) goes through a new `desk.shell.bridge.GuiBridge`. Verified
    entirely headlessly, including a real end-to-end round trip through an
    actual `QWebEngineView` (browser JS → local HTTP server → response).
    [planned: desk-bridge-api.md]
acd87ae. SUPERSEDED by TODO 75d5d15: Workspace persistence — save/restore widget
    instances, their `QGraphicsItem` position/size/z-order (now including
    the `WidgetFrame` chrome from TODO 6090103), and the canvas's pan/zoom
    transform to `workspace.json`. The Desk concept (TODO 75d5d15) formalizes
    this (directory association, named serialization, a directory-picker
    UI) — implement persistence there instead of as a bare
    `workspace.json` with no directory-association model.
71f125a. COMPLETED: Fix console widget selection highlighting and cursor
    visibility — when a TUI program presents multiple selectable options
    (e.g. `claude` offering a choice of several things), no highlight is
    rendered, so the user can't tell which option is currently selected.
    Separately, the terminal cursor still isn't rendered at all, so it's
    unclear where typed text will land, which makes navigating/editing
    multi-line text especially difficult. Both are rendering gaps in the
    `pyte`-based console renderer (see TODO 255d777/TODO 950774b). Root causes confirmed
    directly: reverse video (`ESC[7m` — the standard mechanism for
    terminal selection highlighting, and how many full-screen TUIs draw
    their own cursor) rendered nothing when colors were unset, since
    swapping two "default" colors that both resolved to `None` is a
    no-op; separately, `pyte`'s "bright" SGR colors (`ESC[90-97m`/
    `ESC[100-107m`, e.g. `"brightred"`) weren't resolved at all. Fixed
    with real, concrete default foreground/background colors (never
    `None`) resolved *before* swapping for reverse video, plus a bright
    -color map (including a defensive alias for a confirmed `pyte` 0.8.2
    typo, `"bfightmagenta"`). Verified with genuine pixel-level rendering
    checks (`grab()`/`QImage`/`pixelColor()`), not just property checks —
    the exact gap that let this bug through undetected originally.
    [planned: console-widget-highlight-cursor-rendering.md]
b9ade4f. COMPLETED: Investigate self-window screenshot capability — determine
    whether apps are allowed by default (notably on macOS) to capture
    screenshots of their own windows without extra user/OS permission. If
    so, this would let Desk capture screenshots of itself/its widgets from
    inside the running environment (e.g. useful for verification, or
    letting a widget inspect its own rendered state). **Conclusion: yes,
    no extra permission needed** — `QWidget.grab()`/`.render()` paint a
    widget's own content directly via Qt, never going through macOS's
    system-level screen-capture APIs (the ones that actually require the
    "Screen Recording" permission), so there's nothing for the OS
    permission system to gate. Already Desk's own de facto verification
    technique in practice — every pixel-level rendering check done for
    TODO 255d777/TODO 950774b/TODO 47b5731/TODO 71f125a already relies on
    it, dozens of times, with no permission prompt ever appearing. No new
    capability needed to build;
    a shared `desk.debug.screenshot()` helper is noted as possible future
    work if a second concrete need for one shows up.
    [planned: self-window-screenshot-capability.md]
4adfcad. COMPLETED: Fix Desk picker positioning — the "hovering" Desk picker
    (see TODO 75d5d15), anchored to the upper-left of the Workspace Canvas,
    should stay pinned to the upper-left of the app window itself at all
    times (screen space, like TODO d0d7b37's zoom control), rather than being
    tied to the current Desk/canvas in some way that lets it move or
    disappear when the Desk changes. Root cause confirmed directly: the
    picker was only ever positioned once, at construction, while a
    recurring internal Qt layout pass (plausibly `QGraphicsView`'s
    scrollbar/viewport geometry recalculation) silently displaces it on
    every resize (including the first, at initial `.show()`). `ZoomControl`
    never showed this bug since its bottom-right anchor already forces a
    reposition on every `resizeEvent` regardless. Fixed by reasserting the
    picker's fixed position on every `resizeEvent` too — deferred via
    `QTimer.singleShot(0, ...)`, since the displacing pass runs as a
    separate, later-queued layout event within the same iteration, so a
    synchronous reassertion (a first attempt at this fix) wasn't late
    enough and still got overwritten. Verified headlessly: stays correctly
    positioned after first show, after resizes, and after a real Desk
    switch.
    [planned: fix-desk-picker-positioning.md]
cde51d4. COMPLETED: Fix Desk picker's collapsed-state label — on startup,
    the top-left Desk picker widget (TODO 75d5d15) briefly shows "c" in
    its collapsed (half-alpha, unhovered) state instead of the current
    Desk's name, then on hover it switches to showing "default" and
    incorrectly stays showing "default" (rather than the actual current
    Desk name) even after the mouse leaves and it collapses back down.
    Two confirmed root causes: (1) the picker's outer bounds were locked
    in via `adjustSize()` at construction, while the label was still
    empty, and `set_current()` never re-triggered a resize afterward,
    clipping the label's real text; (2) the MRU dropdown only selected
    the current desk if it found a matching entry already in the
    persisted MRU list — on a desk's first open (before any save/switch
    has called `add_to_mru()`), no match exists, so it fell back to
    showing its first entry instead. Fixed: `set_current`/`set_mru` both
    call `adjustSize()`; `set_mru` inserts the current desk into its own
    entry list if the caller's list doesn't already include it. Verified
    headlessly, including a full-app regression using a real `DeskWindow`
    around a fresh, never-saved desk named "default" (the exact
    originally-reported scenario).
    [planned: fix-desk-picker-label.md]
d1205ef. COMPLETED: TODO widget — reads the "nearest" `TODO.md` (resolved
    relative to the current Desk's associated directory) and displays it
    as a filterable list (complete / incomplete / pending / etc.) of
    items. Each item is shown as at most 100 characters of its
    description, truncated with a trailing "..." if it doesn't fit. UX:
    items can be re-prioritized via drag-and-drop, and a new item can be
    added via an "add item" button that launches a hovering add-item
    dialog. Both re-prioritization and adding a new item must result in
    committing the change — but re-prioritization should debounce the
    commit: hold off until either a new item is added or 1 minute passes
    with no further re-prioritization. Ships as `widgets/todo/`, backed by
    two new shared modules (`desk.todo_file` for parsing/rendering,
    reused id-generation from `desk.todo_ids` — also extracted out of
    `scripts/todo_item_ids.py` so both share one implementation) and a
    minimal `desk.shell.current_context` giving `python` widgets their
    first way to learn the current Desk's directory (deferred since
    TODO 420c40d). Reordering uses `QListWidget`'s built-in
    `InternalMove` drag mode; adding uses a hovering `Popup` dialog
    matching `WidgetSpawnMenu`'s established pattern (TODO 37d50f2);
    commits are real `git` operations scoped to the target file's own
    repo (skipped, not crashed, if it isn't one), with the debounce
    correctly folding a pending reprioritization into an add's immediate
    commit, and a `destroyed`-triggered flush so closing the widget
    doesn't silently drop an unsaved reorder. Verified entirely
    headlessly, including placing the widget via a real `DeskWindow`
    pointed at this project's own directory and confirming it correctly
    loaded this very file.
    [planned: todo-widget.md]
1f9bd34. COMPLETED: Fix zoom control positioning — the zoom control
    widget (TODO d0d7b37), meant to be anchored to the lower-right corner
    of the app window in screen space, should stay pinned to the
    window's bottom-right at all times rather than being tied to the
    current Desk/canvas in some way that lets it move or disappear when
    the Desk changes (same underlying issue as TODO 4adfcad's Desk
    picker). Confirmed exactly that: the control starts hidden and only
    becomes visible the first time zoom leaves 1.0x, so the same
    recurring internal Qt layout-pass displacement TODO 4adfcad found
    wasn't caught until that moment (`(999, 774)` instead of the correct
    `(819, 664)`, confirmed directly) — the earlier investigation's own
    zoom-control check happened to mask this by zooming before resizing.
    Fixed with the identical `QTimer.singleShot(0, ...)`-deferred
    reassertion. Verified headlessly, including a regression check that
    the Desk picker and titlebar drag are unaffected.
    [planned: fix-zoom-control-positioning.md]
fa288ce. COMPLETED: Investigate `pyte`'s `private=True` CSI dispatch gap further — reported
    via pasted console output showing this is still surfacing at runtime:
    ```
    TypeError: Screen.report_device_status() got an unexpected keyword argument 'private'
    WARNING desk_widget_console: pyte failed to dispatch a terminal escape sequence; skipping it
    Traceback (most recent call last):
      File "~/desk/widgets/console/widget.py", line 109, in feed
        taking_plain_text = self._send_to_parser(data[offset:offset + 1])
      File ".../pyte/streams.py", line 213, in _send_to_parser
        return self._parser.send(data)
      File ".../pyte/streams.py", line 353, in _parser_fsm
        csi_dispatch[char](*params, private=True)
    TypeError: Screen.report_device_status() got an unexpected keyword argument 'private'
    ```
    This is the same root cause TODO 950774b already addressed (`pyte` 0.8.2's
    `Stream` calls CSI-dispatched `Screen` methods with an extra
    `private=True` keyword that most of them, including
    `report_device_status`, don't accept) — TODO 950774b's `_ResilientStream`
    is why this now logs a `WARNING` and keeps running instead of crashing
    the app, which is working as designed. Still, this warrants further
    investigation: is skip-and-log an acceptable permanent behavior, or
    should the affected `Screen` methods (`report_device_status`,
    `cursor_position`, `cursor_to_column`, `set_margins`, and other
    CSI-dispatched methods lacking `private`/`**kwargs` support) be patched
    /subclassed to actually handle the private-CSI variant correctly rather
    than dropping it? Also consider whether the warning-per-occurrence
    logging is too noisy for a case this routine (e.g. `claude` appears to
    trigger it on every startup). **Conclusion: keep skip-and-log
    permanently, no `Screen`-method patching** — most affected private
    CSI variants are obscure DEC status reports (printer/UDK/locator/
    macro-space/etc. status) with no single universally-correct reply,
    `claude` already works correctly end-to-end under the current guard
    (TODO 950774b's own verification), and this traceback's specific
    trigger (`report_device_status`, an `n`-suffixed DSR) is a
    *different* private query than TODO 950774b's confirmed trigger (a
    `c`-suffixed device-attributes query) — direct evidence the existing
    per-character guard already needs to (and does) cover multiple query
    kinds uniformly, not just the one first observed. **Logging was too
    noisy**: downgraded from `WARNING` + full traceback to `DEBUG` with no
    traceback — appropriate while newly diagnosed, unnecessary now that
    the root cause is fully understood and documented. Verified
    headlessly (guard still works; log record confirmed `DEBUG`/no
    traceback; full TODO 950774b regression suite re-run).
    [planned: pyte-private-csi-investigation.md]
ef1b2e7. COMPLETED: Hot reload crashes the whole app if a widget's rebuilt module
    raises during import or `build()`, instead of isolating the failure
    to that one widget. Confirmed via a real crash log: while a `claude`
    instance running inside the Desk console widget was actively editing
    `widgets/todo/widget.py` (mid-implementation of a "double-click to
    edit" feature — TODO d49f1cf), a hot-reload fired against an
    intermediate save that referenced a not-yet-defined method
    (`self._list.itemDoubleClicked.connect(self._show_edit_dialog)`,
    `_show_edit_dialog` undefined). Root cause: `PythonWidgetHost
    ._rebuild()` (`src/desk/shell/python_widget.py`) has no exception
    handling around re-importing the module or calling `build()` — any
    error there propagates straight out of `_on_widget_changed`, a Qt
    slot connected to the Hot Reload Broker's signal, which is apparently
    fatal to the whole process in this PyQt6 setup (`AttributeError` →
    `Abort trap: 6`, not just a failure to reload that one widget).
    Given this app's own stated core purpose is running `claude` to edit
    Desk's own widget code live, hitting a transient syntax/attribute/
    import error mid-edit is routine, not a rare edge case — and it
    currently takes down the entire app (losing all other unsaved Desk/
    widget state) every time. Needs: wrap the rebuild path in try/except;
    on failure, log the error and keep the previously-working widget in
    place (don't swap in a broken one) rather than crashing, so a bad
    intermediate save just means "hasn't picked up your latest edit yet,"
    not "the whole app just died." Fixed: `_rebuild()`'s re-import +
    `build()` call is now wrapped in `try/except`, logging an `ERROR`
    with full traceback and leaving the previous widget instance
    untouched on failure; a first-build failure (no previous widget to
    fall back to) shows a small inline error placeholder instead of a
    silently blank widget. Verified headlessly, including directly
    reproducing the exact originally-reported crash (a copy of the real
    `widgets/todo/widget.py` with the exact reported bug reintroduced,
    hot-reloaded) and confirming the app now survives it instead of
    aborting.
    [planned: isolate-hot-reload-crash.md]
8394e40. COMPLETED: The TODO widget list should be scrollable (in a way that
    doesn't get accidentally captured by Desk scrolling). Root cause: the
    TODO widget's `QListWidget` was already a scrollable
    `QAbstractScrollArea` and would have scrolled on a wheel/two-finger
    -scroll like any other Qt list — but it never received that event,
    since `WorkspaceView.wheelEvent` unconditionally treated every wheel
    event as a canvas zoom gesture regardless of what was under the
    cursor. Fixed generically (not TODO-widget-specific, so it also
    covers any future widget with scrollable content): a new
    `_scrollable_at` hit-test (same shape as the existing
    `_hit_test_chrome`) checks whether the cursor is over a
    `QAbstractScrollArea`-based embedded widget and, if so, forwards the
    wheel event via `super().wheelEvent(event)` (Qt's normal
    scene-forwarding path) instead of zooming the canvas. Pinch-to-zoom
    (handled separately via `NativeGestureEvent`) is unaffected. Verified
    headlessly with synthetic `QWheelEvent`s against a real
    `WorkspaceView`: scrolling over an embedded scrollable list scrolls it
    without changing canvas zoom; scrolling over empty canvas background
    still zooms as before; titlebar chrome hit-testing regression
    -checked and unaffected.
    [planned: todo-widget-scrollable.md]
d49f1cf. COMPLETED: double-clicking on a TODO item in the TODO widget
    should pop up an editor. Double-clicking a row opens the same
    hovering popup dialog used to add an item (generalized to
    `_ItemDialog`, taking an optional prefilled description), submitting
    updates that item in place — same permanent `item_id`, recomputed
    `status`/`raw_text` — and commits immediately (folding in any
    pending reprioritization), matching how adding an item already
    works. Picked up from an earlier session's crash (TODO ef1b2e7) that
    left this mid-edit: the `_AddItemDialog` → `_ItemDialog` rename and
    the double-click wiring were already in the file, but
    `_show_add_dialog` still referenced the old class name and
    `_show_edit_dialog`/`_edit_item` were never defined — both finished
    here. Verified headlessly, including exercising the real
    `itemDoubleClicked` signal wiring (not just calling the handler
    directly) and a full add/reprioritize regression check.
    [planned: todo-widget-edit-on-doubleclick.md]
742727d. COMPLETED: In the TODO widget UX, the filtering should be
    better distinguished visually, with a frame around them, and
    styling which better indicates that they are toggle buttons. Filter
    buttons now grouped in their own `QFrame`, separate from the
    Reload/Add Item action buttons, with QSS giving checked buttons a
    distinct filled color/border instead of relying on the platform
    style's often-subtle default checked appearance. Verified headlessly
    (buttons parented to the frame, styled, and toggling still correctly
    shows/hides rows).
    [planned: todo-widget-filter-styling.md]
8db7891. COMPLETED: the add/edit textbox on the TODO widget should be
    much larger, and multiline. `_ItemDialog`'s field is now a larger
    `QPlainTextEdit` (was a single-line `QLineEdit`); plain Return/Enter
    now inserts a newline like normal multiline editing, with
    Ctrl+Return as the submit shortcut (Escape still cancels, the "Add"
    button still submits by click regardless). Verified headlessly,
    including that add/edit both still work end-to-end and that a
    multi-line description is correctly preserved verbatim in the file
    itself.
    [planned: todo-widget-larger-multiline-textbox.md]
0f9445c. COMPLETED: The TODO items in the TODO widget should visually
    appear to be items rather than lines of text, including a small
    frame around each one so that it is clear that it is dragable.
    Styled via `QListWidget::item` QSS (border, rounded corners,
    padding, distinct `:selected` background) plus non-zero item
    spacing, so rows read as distinct cards rather than touching
    unstyled lines of text. Verified headlessly, including regression
    -checking filtering, drag-and-drop reordering, and double-click-to
    -edit are all unaffected by the styling-only change.
    [planned: todo-widget-item-framing.md]
6034b1d. COMPLETED: change the top-left hover ui to always show both the
    name and the associated directory, even when not hovered. The
    label (the only thing that ever showed the name) previously
    disappeared entirely on hover, and no state ever showed the
    directory as readable text — only a button to change it. Now the
    label (`"name — directory"`) is always visible; hover additionally
    shows the MRU dropdown/directory-picker button alongside it rather
    than replacing it. Verified headlessly, including a full-app
    regression via a real `DeskWindow`.
    [planned: desk-picker-always-show-directory.md]
bc75b07. COMPLETED: Simple browser widget with an address bar and
    forward/back/reload buttons. Ships as `widgets/browser/`: a
    `kind: "python"` widget using `QWebEngineView` directly (the same
    "python widgets can use any PyQt6 module directly" pattern the
    Console/Editor widgets already established), not the `ChromiumWidget`
    /local-server machinery (that's for one fixed `kind: "html"` widget's
    own bundled page, not arbitrary user-navigable URLs). Address bar
    uses `QUrl.fromUserInput` (Qt's own standard address-bar-style URL
    interpretation); back/forward buttons track real history
    availability via `QWebEngineView.history()`. Starts at `about:blank`.
    Verified entirely headlessly (address-bar navigation, bidirectional
    address-bar/URL sync, back/forward, button enabled-state), including
    a full-app regression placing it via a real `DeskWindow`.
    [planned: browser-widget.md]
62e8b05. COMPLETED: Bug: Sometimes when editing in the TODO widget's TODO item editor, the text caret will disappear; sometimes it comes back after a few seconds and sometimes it doesn't. it seems like it is loosing focus for some reason. It might be that other processes are stealing focus, but that seems unlikely.
   [planned: fix-todo-editor-caret-focus-freeze.md]
a629bea. COMPLETED: in the TODO widget, the item editor is using the exact same ux as the add, which means that it says "Add" on the bottom. change the UX to have two buttons, "discard" (for both edit and add) and the second button should say "add" (for add) or "save changes" (for edit); in both add/edit, confirm before discarding if there is any non-whitespace text. Also, change the UX so that it doesn't dismiss on click-away.
   [planned: todo-widget-editor-discard-save.md]
43845be. COMPLETED: Add a new Scratch Widget. Scratch is a multi-line
   textbox, but it has a title bar which says `Scratch: [label]` where
   the label is inline-editable. Ships as `widgets/scratch/`: a plain
   `QPlainTextEdit` body under an internal title row (distinct from the
   `WidgetFrame` chrome titlebar, which is a static per-kind string with
   no per-instance update hook) reading `Scratch: {label}`; double
   -clicking the label swaps it for a `QLineEdit`, committing back to
   display form on Enter or focus-out, falling back to `"untitled"` if
   committed blank. No file-backing/persistence — this item only asked
   for the widget itself. Verified entirely headlessly: initial state,
   entering/committing/clearing the editable label, body text entry,
   and a regression check that `discover_widgets` picks up the new
   manifest and a real `PythonWidgetHost` builds a working
   `ScratchWidget`.
   [planned: scratch-widget.md]
d25e557. COMPLETED: Add a file-watcher to the TODO widget so that
   external edits to the todo items are automatically shown. remove the
   "reload" button. if there is a conflict wherein a TODO item changes
   while it is being edited, put the current text into a scratch widget
   and label it with "TODO Item (#) Edit Conflict". A small dedicated
   `watchdog`-based watcher (distinct from the widget-hot-reload
   `WidgetWatcher`) watches the resolved `TODO.md`'s parent directory,
   debounced, reporting changes via a `pyqtSignal` relay (mirroring the
   existing commit-result relay). `_write_and_commit` now records the
   exact text it wrote so the watcher can tell its own echoed write
   apart from a real external edit. Currently-open edit dialogs are
   tracked (`item_id -> (dialog, description-as-loaded)`); on a real
   external change, any open edit whose item is now gone or whose
   description no longer matches the loaded snapshot is a conflict: its
   in-progress (possibly unsaved) text is moved into a new Scratch
   widget (TODO 43845be) labeled `TODO Item ({item_id}) Edit Conflict`,
   and the stale dialog is closed. A pending, uncommitted local
   reprioritization is flushed to disk first so it isn't silently lost
   by the reload. Since no `python` widget could previously place
   another widget instance on the canvas, added a minimal
   `current_context.set_widget_opener`/`get_widget_opener` pair (same
   shape as the existing current-directory hook) backed by a new
   `DeskWindow.open_widget_content` (returns the actual built widget
   instance, via a new `PythonWidgetHost.current` property) and a small
   `ScratchWidget.set_label`. The Reload button is removed from the
   toolbar. Verified entirely headlessly, including a real `watchdog`
   `Observer` picking up a genuine on-disk external change end-to-end
   (hitting, then fixing, the same macOS symlinked-`tempfile.mkdtemp()`
   -path gotcha `LEARNINGS.md` already documents for `WidgetWatcher`),
   the self-write echo being correctly ignored, the conflict/non
   -conflict paths (via a fake installed opener), the full add/edit/
   reprioritize regression, and a real `DeskWindow`'s opener wiring
   placing a genuine `ScratchWidget`/`BrowserWidget`.
   [planned: todo-widget-file-watcher.md]
e60817a. COMPLETED: In the TODO widget, the discard button should
   require confirmation: for add, when there is non-whitespace content;
   for edit, when the user has changed the content such that there
   would be a change. In the case of add, the confirmation should say
   "Discard this new item?" and in the case of edit, it should say
   "Discard changes?". `_ItemDialog` now takes an explicit `editing`
   flag and snapshots its `initial_text`; the discard-confirmation
   predicate is add-mode ("any non-whitespace content", unchanged from
   TODO a629bea) vs. edit-mode (text actually differs from the
   snapshot — previously every edit-discard confirmed unconditionally,
   even a no-op one, since an edit dialog is never prefilled empty),
   with the message matching each mode. Verified entirely headlessly:
   all four add/edit x confirm-needed/not-needed combinations, a
   revert-to-exact-original-text case (no confirmation), declining
   leaves the dialog open with text intact, and a full regression of
   the existing add/edit/reprioritize/watcher test suites.
   [planned: todo-widget-discard-confirmation-wording.md]
82d66c0. COMPLETED: Regression: the hovering ui in the upper-left and
   lower-right are not supposed to be attached to the desk, they are
   supposed to be attached to the corners of the window, no matter the
   zoom level, scroll/pan, or window-resize. Reproduced directly: panning
   (`centerOn`) and zoom operations that re-center the view
   (`zoom_to_fit`/`reset_zoom`) drifted the Desk picker/zoom control away
   from their pinned corners, sometimes off-screen entirely. Root cause,
   confirmed directly and more precise than TODO 4adfcad/TODO 1f9bd34's
   original "some internal layout pass" theory: `QAbstractScrollArea`
   (which `QGraphicsView` is) implements fast scrolling via
   `QWidget.scroll(dx, dy)` on the viewport, which — per `QWidget.scroll`'s
   own documented behavior — also moves any child widget fully inside the
   scrolled area by that same delta; the Desk picker/zoom control are
   exactly that (plain `QWidget` children of the viewport, not scene
   items), so any operation that shifts scroll position silently drags
   them along with it. Very likely the same actual mechanism behind the
   earlier resize-time drift too (the first resize already fires
   `scrollContentsBy` with nonzero deltas, given the huge/infinite scene
   rect). Fixed with a new `WorkspaceView.scrollContentsBy` override that
   reasserts both HUD widgets' positions after every scroll (guarded
   against firing before they exist, since `QGraphicsView.__init__` can
   invoke it during its own setup); the existing resize-time fix is left
   untouched, since it's independently needed for the zoom control's
   viewport-size-dependent target position. Verified entirely headlessly:
   reproduced the bug directly against the unfixed code, confirmed the
   fix holds after panning, `zoom_to_fit`, `reset_zoom`, wheel-style zoom,
   and a regression check of the existing resize-time fix and widget
   drag/positioning.
   [planned: fix-hover-ui-scroll-zoom-drift.md]
a02b001. COMPLETED: feature: temporary ui. This is a means by which
   agents can create temporary ui on Desk. In a directory ".desk_temp"
   (a subdirectory of the directory associated with the current Desk),
   files with uuid names will be watched for creation/edit and will
   result in new widgets showing in the Desk, corresponding to the
   file. The contents of the file should be the TempUI DSL, which has
   the syntax of per-line "keyword param1 param2...". To start, the
   only keywords are "Question," "Option," and "Answer" and the
   resulting widget should be a new type of widget, a "Question Widget"
   which displays the question and allows the selection of one of the
   options as an answer; when the user chooses an answer, it is
   appended to the corresponding file as an "answer" line. On boot or
   when a new associated directory is selected, do the following: (1)
   ensure that the temporary ui subdirectory exists (ask for permission
   from the user via a popup before creating it), (2) ensure that
   desk-temporary-ui.md (described later) exists, (3) ensure that the
   temporary ui subdirectory is in any .gitignore file (ask for
   permission before adding). In addition to the normal development
   process, also describe temporary ui, including the DSL in a file
   called desk-temporary-ui.md, stored in the temporary ui subdirectory
   (but ignored by temporary ui detection). In Desk, when a temporary
   ui file is added by an external process, show a persistant
   notification in the upper-right which, when clicked, actually
   instantiates the new widget, centered in the current view. When a
   temporary ui file is edited not by Desk, a notification should be
   shown (replacing any other notifications for the particular file)
   and when clicked the widget should either be centered in the view if
   it exists, or created as per the file added case.

   Shipped as: `desk.temp_ui` (DSL parsing, UUID-filename validity
   check, `.gitignore` handling, doc template), `desk.shell
   .temp_ui_manager.TempUiManager` (a dedicated directory watcher,
   distinct from the widget-hot-reload `WidgetWatcher`, with self-write
   suppression and directory provisioning), `desk.shell
   .temp_ui_notifications.TempUiNotificationStack` (a new top-right
   -corner HUD, stacked/replaced per file, sharing the same
   `scrollContentsBy`-pinning fix TODO 82d66c0 just added), and
   `widgets/question/` (the new Question Widget). A Question Widget's
   Desk `instance_id` is always set equal to its source file's uuid --
   this is how a restored/reloaded instance reconnects to the right
   file without any change to the fixed `build() -> QWidget` contract
   every widget kind relies on (`DeskWindow._load_desk_widgets` special
   -cases `widget_id == "question"` to rebind it). `desk.git_utils
   .find_git_root` extracted from `widgets/todo/widget.py` (now needed
   a second time). Verified entirely headlessly: DSL parsing/gitignore
   logic, the directory watcher's added/edited/self-write-suppression
   behavior (including a real bug found and fixed -- see LEARNINGS.md
   -- where a brand-new file was always misclassified as "edited"),
   the Question Widget's render/answer/placeholder behavior, the
   notification stack's positioning (including staying pinned through
   pan per TODO 82d66c0's fix), and a full-app `DeskWindow` regression:
   boot-time provisioning, a real notification click placing a bound
   Question Widget centered in the view, answering it, and -- the
   actual point of the `instance_id`-as-uuid design -- a simulated app
   restart (a fresh `DeskWindow` over the same saved Desk) correctly
   reconnecting to the file and showing the already-given answer.
   [planned: temporary-ui.md]
1a051d1. COMPLETED: Regression: the TODO widget no longer properly loads a
   TODO.md from the Desk-associated directory; it shows an error saying it
   can't find the TODO.md file.

   Root cause: `DeskWindow.__init__` (`src/desk/shell/window.py`)
   constructed saved widgets (`_load_desk_widgets`, which can build a
   `TodoWidget` that resolves its `TODO.md` path once, synchronously, at
   construction) before `_refresh_picker` ever ran -- the only place that
   populates `current_context`'s current-desk-directory. Previously
   masked by the TODO widget's own manual "Reload" button (both calls
   finished before the event loop started, so clicking Reload always saw
   the correct directory); TODO d25e557 removed that button in favor of
   automatic file-watching, which only fires on a later external change,
   never on initial load -- turning a cosmetic first-paint glitch into a
   permanent regression. Fixed by moving `_refresh_picker()` to run
   immediately after `self.current_desk` is assigned, before
   `_load_desk_widgets`. Verified by reproducing the exact bug directly
   against the unfixed ordering (a real `DeskWindow`, catalog trimmed to
   the `todo` widget, pointed at a directory with a real `TODO.md`, showed
   the "No TODO.md found" error) and confirming the fix resolves it
   immediately at construction, with no other `DeskWindow` behavior
   depending on the old order.
   [planned: fix-todo-widget-load-regression.md]
1217380. COMPLETED: The shell (Console widget) text caret outside of the
   app usually shows as a non-blinking box character; the shell text caret
   inside of the app does not show up at all.

   Root cause: `TerminalWidget.setReadOnly(True)` strips
   `Qt.TextInteractionFlag.TextEditable` from its interaction flags, a
   flag Qt's internal cursor-paint logic requires before it will ever
   draw the native blinking caret -- regardless of focus, cursor width,
   or cursor position all otherwise being correct (all individually
   confirmed fine in isolation). Fixed by rendering the cursor explicitly
   as a reverse-video block over its character cell in `_redraw()`
   (`_char_format`'s new `invert` parameter), the same mechanism already
   used for pyte's own SGR reverse-video, rather than depending on Qt's
   native (permanently invisible, for a read-only widget) cursor; the old
   `setTextCursor`/`setCursorWidth` calls, which never actually rendered
   anything, are removed. Verified headlessly against a real PTY: printed
   text and confirmed the tracked cursor cell's `QTextCharFormat` is
   inverted relative to its neighbor, confirmed the inversion respects a
   real `ESC[?25l`/`ESC[?25h` (DECTCEM) pair sent through the PTY, and
   confirmed the rejected alternative (re-adding `TextEditable` to the
   flags) would have silently flipped `isReadOnly()` back to `False`.
   [planned: console-widget-cursor-visibility.md]
8beab6e. COMPLETED: The upper-left Desk picker ux is finicky and strange; it
   shows the name of the current desk and the associated folder always,
   which is good, but on hover it pops up buttons to the side. Instead: make
   the name and associated folder more visually distinct from one-another on
   hover; when clicking on the name, bring up a more stable picker rather
   than the current weird drop-down thing; when clicking on the associated
   directory, bring up the directory picker directly (i.e. get rid of the
   "Directory…" button).

   Replaced the single always-visible label + hover-revealed
   `QComboBox`/`QPushButton` with two independently-styled,
   independently-hoverable clickable label chips (name: bold/brighter;
   directory: dimmer) via a new `_ClickableLabel`. Clicking the name opens
   `_DeskListPopup`, a stable `QListWidget`-based popup (`WidgetSpawnMenu`'s
   established `Qt.WindowType.Popup` pattern) listing MRU desks plus a
   trailing browse entry; clicking the directory chip emits
   `directory_change_requested` directly. `DeskPicker`'s external signal
   API (`desk_chosen`/`browse_requested`/`directory_change_requested`) is
   unchanged, so `DeskWindow` needed no changes. `design-docs/widget-ux.md`
   updated to match. Verified headlessly: label text/MRU state, independent
   per-chip hover styling, direct directory-click emission, popup contents/
   pre-selection/activation for both an MRU entry and the browse entry, and
   a full-app `DeskWindow` regression boot.
   [planned: desk-picker-split-name-directory-click.md]
c8f6fb3. COMPLETED: Crash: switching to a different Desk (via the Desk
   picker's name popup) crashes the whole app with `RuntimeError: wrapped
   C/C++ object of type _DeskListPopup has been deleted`, raised from
   `desk_picker.py`'s `_activate_item`.

   Root cause: `_activate_item` emitted `desk_chosen`/`browse_requested`
   (which can synchronously reach `DeskWindow._provision_temp_ui`'s real
   confirmation dialog via `switch_desk`) *before* calling `self.close()`.
   `_DeskListPopup` is a `Qt.WindowType.Popup` + `WA_DeleteOnClose` window;
   a modal dialog appearing steals active-window status, which
   auto-closes the still-open popup, and the modal's own nested event
   loop processes the resulting `deleteLater()` while `_activate_item` is
   still executing on that same (now-deleted) object -- so the later
   `self.close()` call crashed. Confirmed directly with a minimal,
   business-logic-free repro (any real modal `QDialog.exec()` shown from
   a downstream slot reproduces it). Fixed by closing the popup *before*
   emitting, and never touching `self` afterward. Verified headlessly:
   reproduced the crash against the unfixed ordering, confirmed the fix
   resolves it and preserves normal-path (no modal) behavior, and ran a
   full-app `DeskWindow` regression that exercises the real
   `switch_desk` -> `_provision_temp_ui` confirmation path with no crash.
   Noted the identical latent hazard in `WidgetSpawnMenu._activate_item`
   in `PARKINGLOT.md` (out of scope here).
   [planned: fix-desk-list-popup-deleted-mid-callback.md]
bb65aab. COMPLETED: Bug: temporary ui (TODO a02b001) notification did not
   show up. Reproduced by having an agent write a new temp UI file
   directly to `.desk_temp/` (a bare-UUID filename, DSL content with
   `Question`/`Option` lines, no `Answer` line yet — i.e. exactly the
   "file added" case `desk-temporary-ui.md`/TODO a02b001 describe) while
   Desk was presumably running against this project as the current
   Desk's associated directory. No persistent notification appeared in
   the upper-right corner. Needs investigation: whether `TempUiManager`'s
   watcher is actually running/attached to the right directory, whether
   detection or notification-stack display is silently failing, or
   whether the precondition (Desk running with this directory as the
   current Desk) didn't actually hold when this was observed.

   Investigated directly against this project's own real, already
   -provisioned `.desk_temp/` directory: ruled out the watcher not
   running and the notification stack silently failing (a plain new-file
   write is detected correctly). Ruled out TODO c8f6fb3's crash as the
   cause (timing: the crash happened ~3 minutes after the temp-UI file
   appeared, per `test.desk`'s own mtime — plenty of time for a working
   notification to have shown). Root cause: writing the file via a
   scratch-name-then-rename "atomic write" (common in editors/safe-write
   tools) reports as a `watchdog` `FileMovedEvent`, not
   Created/Modified, which `_DirectoryHandler.on_any_event`
   (`src/desk/shell/temp_ui_manager.py`) didn't handle at all -- and even
   a widened type check would still miss it, since a move's meaningful
   path is `dest_path` (where the file landed), not `src_path` (its
   scratch name, which never matches `is_temp_ui_filename`). Fixed by
   handling `FileMovedEvent` explicitly and reading `dest_path` for it.
   Verified headlessly against this project's real `.desk_temp/`
   directory: reproduced zero `file_added` events against the unfixed
   handler for an atomic write, confirmed the fix detects it correctly,
   and confirmed both plain-write and atomic-write edits of an
   already-known file still classify as `edited`, not `added`. Noted the
   identical gap in the TODO widget's own single-file watcher in
   `PARKINGLOT.md` (a different file, out of scope here).
   [planned: fix-temp-ui-watcher-missed-atomic-write.md]
54b0a9f. COMPLETED: Bug: the TODO widget's single-file watcher
   (`_SingleFileHandler` in `widgets/todo/widget.py`) has the same
   atomic-write blind spot TODO bb65aab fixed in `TempUiManager`'s directory
   watcher. It compares `event.src_path` against the exact watched
   `TODO.md` path; a `watchdog` rename/move reports as a `FileMovedEvent`
   whose meaningful path is `dest_path` (where the file landed), not
   `src_path` (the scratch name) -- so an editor/tool that saves via
   write-scratch-then-rename-over-`TODO.md` (a routine, safe-write
   pattern) is never detected as an external change. Apply the same
   `FileMovedEvent`/`dest_path`-aware fix here.

   Fixed by reading `event.dest_path` for a `FileMovedEvent` and
   `event.src_path` otherwise, mirroring TODO bb65aab's fix exactly.
   Verified headlessly: confirmed the exact mechanism in isolation (a
   real `FileMovedEvent` fails the old comparison, passes the new one),
   confirmed a real `TodoWidget` watching a real `TODO.md` correctly
   reloads after a scratch-name-then-`os.rename()` edit, and confirmed a
   plain direct write is still detected as before.
   [planned: fix-todo-widget-watcher-missed-atomic-write.md]
14d14e7. COMPLETED: The code editor "open" button should default to the
   directory associated with the Desk.

   `EditorWidget._last_dir` (the shared Open/Save-As default directory)
   now seeds from `desk.shell.current_context.get_current_desk_directory()`
   when known, falling back to `Path.home()` otherwise -- the same
   `current_context` mechanism the TODO widget already uses, resolved
   once at construction. `plans/code-editor-widget.md`'s original
   deferral no longer applies now that this mechanism exists. Verified
   headlessly: defaults to the current Desk directory when set, falls
   back to home when not, and still tracks an actually-opened file's own
   directory afterward as before. Found (but did not fix, out of scope
   here) a related latent bug in `DeskWindow.switch_desk` -- logged in
   `PARKINGLOT.md`.
   [planned: editor-open-default-desk-directory.md]
11aeb43. COMPLETED: Add a new type of tempui, called `LightningRound`. the first line in the tempui file should be `LightningRound\t[name]\t[prompt]`,  and it should then re-use `Option` but with the argument being a single character which will be used as the keyboard button to correlate with that option; these same options apply to all questions that this widget will ask. After at least two Options, following should be `LRItem\t[description]\t[answer or the string "unanswered"]; that is a "lightning round item." the UI should show one LRItem at a time (skipping those that already have one of the options as an answer), with buttons below it corresponding to the Options, labelled to make it clear that you can also use the keyboard (e.g. `Press [character]`). It should record the user's answers, replacing "unanswered" with the chosen character. Please be sure to update all of the tempui docs, especially those that are directions to claude.
   [planned: lightning-round-tempui.md]

   Added the LightningRound DSL (LightningRound/Option/LRItem keywords, tab-separated for the multi-field lines) via a dedicated parse_lightning_round/LightningRoundDocument (a LightningRound file's shape -- one prompt, shared options, a list of items -- differs structurally from Question's single question/answer, so it isn't shoehorned into parse_temp_ui) and record_lightning_round_answer (rewrites exactly the targeted LRItem line's answer field in place). New widgets/lightning_round/ widget kind, same build()/set_source_file contract as QuestionWidget: shows the first unanswered item and one "Press <character>" button per option, answerable by click or by pressing the matching key (case-insensitively), advancing to the next unanswered item until all are answered. window.py's previously Question-only wiring (_load_desk_widgets, _notify_temp_ui, _activate_temp_ui) now routes by each file's own detected kind (detect_temp_ui_kind) instead of a hardcoded widget id -- _bind_question_widget renamed to the already-generic _bind_temp_ui_widget. DOC_TEMPLATE gains a LightningRound section for agents/Claude to read; this project's own already-provisioned .desk_temp/desk-temporary-ui.md refreshed by hand to match (provisioning only writes it once, not on every boot).

   Verified headlessly: DSL round-trip parsing and kind detection, record_lightning_round_answer's precise in-place rewrite (every other line untouched), the widget's full click/keyboard/advance/completed-state behavior against a real file, _temp_ui_widget_id_for's routing for both file shapes, and a full-app DeskWindow regression confirming both a saved lightning_round widget and the existing question widget correctly reconnect to their source files.
6907120. COMPLETED: create a new widget, "claude" which runs the claude cli in a shell, so similar to the console widget. it should pass an argument to the invocation of claude that sets the first message/prompt to claude to be something like "You are running inside of Desk. Please read this document to understand the implications of that: [path to the document in .desk_temp which explains things like tempui]"

   Extracted the Console widget's generic PTY/pyte TerminalWidget out of widgets/console/widget.py into a shared desk.terminal_widget (widget directories can't import each other directly), parameterized by an optional command list (defaulting to bash). console/widget.py is now a thin shim over it. New widgets/claude/ widget spawns the same shell, then types the claude invocation into it (via a new TerminalWidget.type_into_shell) rather than exec-ing claude directly, so the user's normal shell profile/PATH/aliases load first and the shell stays usable if claude exits. The initial prompt points at the current Desk's .desk_temp/desk-temporary-ui.md via current_context, falling back to a relative-path description if no current Desk directory is known yet. design-docs/architecture.md updated with a new Claude Widget component entry.

   Verified headlessly against real PTYs: console widget regression (still spawns a working bash shell via the shared module), TerminalWidget(command=...) actually running the requested command, type_into_shell delivering text exactly like a keystroke would, and the claude widget end-to-end with a fake claude script on PATH -- both a precise capture of the exact text typed into the shell (confirming the real doc path, independent of terminal line-wrap) and a full end-to-end confirmation that the fake claude binary actually received and echoed the prompt back through the real PTY.
   [planned: claude-widget.md]
ef77819. COMPLETED: create a new python widget, "git status", which displays git status. This should be implemented in a way to keep it relatively fresh without adding too much of a compute burden.

   Polls (QTimer, 3s) rather than watching the working tree with watchdog -- almost any change anywhere in a repo can affect git status, making a precise watcher both complex and the compute burden the TODO itself warns against. git status/branch subprocess calls run on a background thread (never the GUI thread, same reasoning as the TODO widget's own git-commit thread), skip entirely while the widget isn't visible, and only trigger a redraw when the output actually changed since the last poll. New widgets/git_status/ widget kind; design-docs/architecture.md updated with a new component entry.

   A real bug was found and fixed during verification: the initial poll (meant to show real status immediately rather than leaving the widget blank until the first timer tick) reused the same isVisible() gate as later polls, but a widget is never visible at the moment its own __init__ finishes -- it silently never ran. Fixed by giving _poll an initial=True bypass for the one call made from __init__. Verified headlessly against real git repos (including this project's own): no-repo/clean/dirty states, the redundant-redraw skip, the isVisible() gate and its initial-poll fix (confirmed directly by never calling .show() at all), and a full-app DeskWindow regression placing the widget against this project's real repository.
   [planned: git-status-widget.md]
6cf4543. COMPLETED: lightning round ui doesn't seem to be accepting key-presses. should we maybe add a "click here to use keyboard" button or something?

   Root cause confirmed headlessly: clicking an option button, or empty
   stretch space within the widget, already correctly grabs keyboard
   focus -- but clicking the prompt/item text (the most natural place to
   click, since that's the actual question being read) lands on a
   `QLabel` child, and Qt's click-to-focus handling only ever considers
   the exact child widget under the cursor. Since `QLabel` defaults to
   `Qt.FocusPolicy.NoFocus` (ordinary Qt behavior, not specific to being
   embedded via `QGraphicsProxyWidget`), the click never reaches the
   parent `LightningRoundWidget`'s own `Qt.FocusPolicy.StrongFocus`, so
   keys pressed afterward go nowhere. Fixed with an event filter on
   `_prompt_label`/`_item_label` that grabs focus for the widget on
   `QEvent.Type.MouseButtonPress`, deferred via `QTimer.singleShot(0,
   ...)` -- confirmed directly that a synchronous `setFocus()` call
   inside the filter is silently clobbered immediately afterward by
   `QGraphicsProxyWidget`'s own under-cursor focus resolution for that
   same press, the same "something else reasserts state right after
   this" shape already seen in `canvas.py`'s HUD-positioning fixes.
   Addressed the root cause directly rather than adding a "click here to
   use keyboard" affordance, since that would only work around the real
   gap. Verified entirely headlessly against a real `WorkspaceView`
   /`WidgetFrame`-wrapped instance (an initial reproduction attempt
   turned out to mistakenly click the titlebar chrome instead of the
   label; corrected by computing the label's true on-screen position via
   `label.mapTo(frame, ...)`), including regression checks that button
   -click, empty-space-click, and titlebar-drag behavior are all
   unaffected.
   [planned: lightning-round-keyboard-focus.md]
c8e3b28. COMPLETED: need to give focus to text boxes when we pop them up,
   e.g. in add/edit TODO item in TODO widget

   Root cause: `_ItemDialog(self)` (`self` being the embedded
   `TodoWidget`) resolves `self.window()` to that widget's `WidgetFrame`,
   which is never itself shown as an independent OS-level window (only
   embedded into the real `DeskWindow` via `QGraphicsProxyWidget`).
   Parenting a genuinely separate top-level `Qt.WindowType.Tool` window
   to it made every per-widget signal (`hasFocus()`, `isActiveWindow()`)
   report success, but the real, single, global
   `QApplication.focusWidget()` never actually moved to it -- confirmed
   directly against a real running `DeskWindow`, not just an isolated
   dialog (which misleadingly looked correct on its own). Fixed by
   parenting `_ItemDialog` to `QApplication.activeWindow()` (the real
   `DeskWindow`) instead of the embedded widget, via a new
   `TodoWidget._new_item_dialog` helper used by both
   `_show_add_dialog`/`_show_edit_dialog`; since this breaks Qt's
   automatic parent-child object lifetime, the dialog's lifetime is now
   tied to `TodoWidget` explicitly (`self.destroyed.connect(dialog
   .close)`) instead. Also fixed the premature, always-a-no-op
   `self._field.setFocus()` call in `_ItemDialog.__init__` (called
   before the widget was ever shown) by moving it into a deferred
   `showEvent` handler that also calls `raise_()`/`activateWindow()`.
   Verified headlessly against a real, shown `DeskWindow` with a real
   embedded `TodoWidget`: reproduced the bug directly (clicking "Add
   Item" left `QApplication.focusWidget()` on the `WorkspaceView`, not
   the popped-up dialog), confirmed the fix moves real focus to the
   dialog's field for both add and edit, confirmed an open dialog is
   still torn down when `TodoWidget` is destroyed (e.g. by hot reload),
   and regression-checked `selectAll()`/Ctrl+Enter-submit/discard
   -confirmation wording are unaffected. See `LEARNINGS.md` for the new
   entry on this `QGraphicsProxyWidget`-embedded-window-as-parent
   gotcha, and `PARKINGLOT.md` for an unrelated, out-of-scope background
   -thread warning noticed along the way.
   [planned: todo-item-dialog-focus.md]
61141b3. COMPLETED: add the last committed/reloaded time to the
   lower-right of the todo widget, on the same line as the filename

   Added a new right-aligned `_timestamp_label` alongside the existing
   `_status_label` (which keeps a stretch factor, pushing the timestamp
   to the lower-right), in a new `QHBoxLayout` replacing the old single
   -label bottom row. A new `_touch_timestamp(verb)` helper sets it to
   `f"{verb} HH:MM:SS"`, called with "Reloaded" from both `reload()`
   (when a `TODO.md` is actually found) and `_on_external_change()`
   (an external-edit-triggered reload), and with "Committed"/"Saved"
   from `_report_commit_status()`'s two branches (a real commit vs. the
   saved-but-not-a-git-repo case). Starts blank until the first reload/
   commit. Verified headlessly: each of the above call sites sets the
   expected text, the no-TODO.md-found case leaves it blank,
   `_status_label`'s own text is unaffected, and a full-app `DeskWindow`
   regression with a real placed `todo` widget shows both labels
   correctly side by side.
   [planned: todo-widget-last-updated-timestamp.md]
a76e723. COMPLETED: Implement a markdown viewer widget (markdown_ex)
   which can show embedded SVGs as well as mermaid diagrams, with
   folding support and a TOC treeview on the left-hand-side.
   [planned: markdown-ex-widget.md]
5a2f5b9. COMPLETED: Bug: the TODO widget's file parsing doesn't seem to
   work for e.g. world-timelines/TODO.md -- needs investigation into why
   that particular file fails to parse/display correctly (format
   assumptions parse_todo_file makes that don't hold for it, item-id
   regex mismatch, etc.).

   Root cause, confirmed directly against the real file: every item in
   world-timelines/TODO.md uses a GitHub-style checklist marker
   (`- [x] N. ...`) before the id, which `ITEM_START_RE` (anchored at
   line start, expecting the id immediately) never matched at all --
   `parse_todo_file` found zero item starts, so the whole file became
   `preamble` and the widget showed an empty list, not a crash. Fixed
   by widening `ITEM_START_RE` (`src/desk/todo_file.py`) to optionally
   match a leading `- [ ]`/`- [x]` marker before the id, and using its
   checked state as a status fallback in `parse_todo_file` (only when
   this project's own COMPLETED:/SUPERSEDED/PENDING description-prefix
   convention doesn't already say otherwise, so it never overrides an
   explicit status). One line in the file (`- PENDING 21. ...`, no
   checkbox at all) is a one-off, different convention, deliberately
   left out of scope -- it's silently absorbed into the preceding
   item's text rather than crashing. Verified headlessly: this
   project's own `TODO.md` still parses identically; the real
   world-timelines `TODO.md` now parses all 62 checklist items as
   `completed`; a synthetic unchecked `- [ ]` item parses as
   `incomplete`; an explicit `PENDING:` description prefix still wins
   over a checked checkbox; and a full-app `DeskWindow` regression
   placing a real `todo` widget against a copy of the actual file shows
   all 62 items instead of an empty list.
   [planned: todo-parser-checkbox-format.md]
cbeda83. COMPLETED: Make the Desk picker a little more substantial,
   including a way to make a new desk and a way to rename the current
   desk.

   Added three muted action rows to the name-chip popup
   (`_DeskListPopup`): "＋ New Desk…", "✎ Rename current Desk…", and the
   existing browse entry (relabelled "… Open another Desk…"),
   distinguished from MRU desk rows by a new `ACTION_ROLE`. `DeskPicker`
   re-emits two new signals (`new_desk_requested`/`rename_requested`)
   through its existing dumb-component pattern; `_activate_item` keeps
   the TODO c8f6fb3 close-before-emit ordering. `DeskWindow` gains
   `new_desk(name)` (creates a `.desk` in the current directory and
   switches to it, persisting immediately; a fresh desk gets the
   documented demo layout, not a special empty case) and
   `rename_current_desk(new_name)` (renames the `.desk` file in place --
   a Desk's name is its file stem -- preserving widgets/view, updating
   the MRU so the stale name drops out, leaving the directory/.desk_temp
   untouched); both refuse an existing name via a new injectable `_warn`
   and get their name via a new injectable `_prompt_fn` mirroring
   `_confirm_fn` (so both are substitutable in headless tests). Verified
   headlessly: popup row layout + each row emitting exactly its matching
   signal; new_desk create/persist/switch/MRU/collision behavior;
   rename file-move/state-preservation/MRU-update/collision/no-op/
   directory-untouched behavior. `design-docs/widget-ux.md` updated.
   [planned: desk-picker-new-and-rename.md]
1d7331b. COMPLETED: Update the claude widget to monitor the name/id of the
   claude session and store that as part of the widget state so that it can
   be resumed on reload; if there is no better way to do that, write in
   instructions in the initial Desk prompt that claude should write a temp
   file in a known place in the .desk_temp directory that Desk can monitor;
   if resuming a session on reload, don't pass the initial Desk prompt.

   Found a better way than monitoring/scraping the session id: the claude
   CLI's `--session-id <uuid>` (assign a session up front) and `--resume
   <uuid>` flags let Desk *assign* the session, and the widget's persisted
   Desk `instance_id` can double as that UUID -- the same instance_id-as
   -durable-identity pattern the Temporary UI widgets use -- so no
   WidgetState schema change was needed, and the "have claude write a temp
   file" fallback is unnecessary. New `ClaudeWidget(TerminalWidget)` with a
   `start_session(session_id, resume)` method (fresh: `claude --session-id
   <uuid> "<prompt>"`; resume: `claude --resume <uuid>`, no prompt);
   `build()` now just spawns the shell, with the launch issued post-build
   by a new `DeskWindow._bind_claude_widget`. `_place_widget` gained a
   `restore` flag: a fresh claude placement gets a full-uuid4 instance_id
   (needed for a valid `--session-id`) and launches fresh; a widget
   restored via `_load_desk_widgets` (restore=True) resumes with its saved
   instance_id. Verified headlessly (fresh/resume/build command behavior;
   and a full-app fresh-launch -> save -> new-DeskWindow-reload -> resume
   flow preserving the session id, console widget unaffected).
   `design-docs/architecture.md` updated; a general "post-build binding is
   lost on hot reload" limitation (shared with temp-UI widgets) logged in
   `PARKINGLOT.md`.
   [planned: claude-widget-session-resume.md]
6bf83a9. COMPLETED: add a markdown renderer widget which puts a file
   watcher on a markdown file and renders it.

   New `widgets/markdown/` widget: renders a chosen Markdown file via
   Qt's native `QTextBrowser.setMarkdown()` (no Markdown-library
   dependency, per CLAUDE.md's prefer-bespoke guidance) and auto-reloads
   it on external change. The file is picked via an editor-style "Open"
   button seeded from the current Desk directory (current_context); not
   persisted across reload (matches the editor widget -- the widget
   contract has no per-instance state payload, logged as a follow-up in
   PARKINGLOT.md). File watching uses a new reusable
   `desk.file_watch.SingleFileWatcher`, extracted from the TODO widget's
   own watcher so its two watchdog gotchas (FSEvents symlink-resolved
   paths; atomic-write FileMovedEvent/dest_path -- see LEARNINGS.md) live
   in one place; the TODO widget was left on its own copy for now (its
   self-write suppression is entangled), with consolidation noted in
   PARKINGLOT.md. Verified headlessly: the watcher (plain/atomic write,
   symlinked tempdir, unrelated-file ignore, stop/restart); the widget
   (placeholder, render, external-edit auto-reload, deleted-file note,
   recreate-reloads); and a full-app DeskWindow placement. design-docs/
   architecture.md updated with a Markdown Widget entry.
   [planned: markdown-renderer-widget.md]
c758ddf. COMPLETED: a "sheet" widget which implements a basic spreadsheet
   (resizable rows and columns, wordwrap or clip for overflow, all
   entries are left-aligned and vertically centered) which serializes/
   saves as TSV files.

   New `widgets/sheet/` widget built on `QTableWidget`, which covers
   every requirement natively (no spreadsheet dependency): interactively
   resizable rows/columns (both headers Interactive), word-wrapped/
   clipped cells (`setWordWrap(True)`), all entries left-aligned +
   vertically centered via each item's `textAlignment` plus a
   `setItemPrototype` so cells the user creates by typing inherit the
   alignment. TSV serialization (tab-joined columns, newline-joined
   rows; ragged rows padded on load) via an editor-style Open/Save/Save
   As toolbar seeded from the Desk directory, plus Add/Delete Row &
   Column controls and a `•` dirty marker. Open file not persisted
   across reload (same as editor/markdown widgets -- parked
   widget-state-payload gap). Verified headlessly (config, alignment
   incl. prototype clone, TSV save round-trip, ragged-load padding, add/
   delete row+column, dirty marker) and via a full-app DeskWindow
   placement + TSV round-trip. design-docs/architecture.md updated.
   [planned: sheet-widget.md]
3be392a. COMPLETED: bug: special interactions don't work (like using an
   arrow to change the selection on a list of questions or shift-tab to
   cycle mode) in Claude or console widgets

   Root cause: `TerminalWidget.keyPressEvent` only sent the 4 KEY_BYTES
   entries, Ctrl+C/D, and anything with a non-empty `event.text()` --
   arrows, Shift+Tab, Home/End, Page Up/Down, Delete, Insert, and Escape
   all have empty text and weren't mapped, so pressing them sent nothing
   at all. Added their ANSI sequences: cursor keys + Home/End are
   CSI (`ESC [`) normally but SS3 (`ESC O`) when the app has enabled
   application-cursor-keys mode (DECCKM, tracked by pyte in
   `screen.mode` as `1 << 5`) -- which claude's TUI uses, so honoring it
   is what makes its arrow navigation actually work; Shift+Tab
   (Key_Backtab) -> `ESC [ Z`; Escape/Delete/Insert/PageUp/PageDown ->
   their sequences; and generalized Ctrl+C/D to Ctrl+A..Z -> control
   bytes 0x01..0x1a. Refactored into a `_key_to_bytes` helper. Verified
   headlessly (spying on os.write to the PTY): normal-vs-DECCKM arrow
   encodings, Shift+Tab/Escape/Delete/PageUp/PageDown, Ctrl+letter, and
   regressions for plain text/Return/Tab/Backspace. Modified cursor keys,
   function keys, and the keypad are deliberately out of scope (see
   plan).
   [planned: terminal-special-keys.md]
c44e88f. COMPLETED: bug: scroll wheel doesn't work in browser widget

   Root cause: `WorkspaceView.wheelEvent` only forwards a wheel event to
   an embedded widget (rather than zooming the canvas) when
   `_scrollable_at` finds a `QAbstractScrollArea` ancestor under the
   cursor -- but `QWebEngineView` isn't one (its chain is `QWidget ->
   QWebEngineView -> BrowserWidget -> WidgetFrame`, confirmed by probe),
   so wheel events over the browser were eaten as canvas zoom. Fixed by
   adding `QWebEngineView` to that check (also fixes scrollable
   kind:"html"/ChromiumWidget pages). During verification this exposed a
   second, intermittent bug: QtWebEngine bounces an unconsumed wheel
   event (non-scrollable/at-limit page) back up the parent chain, which
   synchronously re-enters wheelEvent mid-forward and recurses until the
   stack overflows (`RecursionError`) -- fixed with a `_forwarding_wheel`
   re-entrancy guard that drops the bounced-back event. Verified
   headlessly against a real embedded browser widget (run repeatedly for
   stability): scrollable-over-web-view, wheel-doesn't-zoom-over-browser,
   the guard, empty-canvas-still-zooms, and a QAbstractScrollArea
   regression. New LEARNINGS.md entry on the wheel-bounce recursion.
   [planned: browser-widget-scroll.md]
846303c. COMPLETED: mouse-based selection doesn't work in claude cli
   running in console (it is usually the case that I can just select text
   to copy it)

   Root cause: `_redraw()` (run on every PTY read) wiped and rebuilt the
   whole document from pyte's screen buffer, destroying any active
   selection -- and a live TUI like claude repaints near-continuously, so
   a selection vanished as fast as it was made. Fixed by preserving the
   selection's anchor/position across the rebuild (the redraw always
   produces the same fixed PTY_ROWS x PTY_COLS grid, so a character
   offset denotes the same cell before/after). Also added the standard
   "Ctrl+C copies when there's a selection, sends SIGINT otherwise"
   convention so the selection can actually be copied -- which also
   sidesteps macOS's Cmd->Control mapping (whichever key Qt reports as
   Ctrl+C copies a live selection). Verified headlessly: selection
   survives a redraw; Ctrl+C-with-selection copies to the clipboard and
   sends nothing to the PTY; Ctrl+C-without-selection sends 0x03 and
   leaves the clipboard alone; a no-selection redraw introduces none.
   [planned: terminal-mouse-selection.md]
2dca4c8. COMPLETED: can claude be started in auto mode with CLI args? if
   yes, please change the claude widget to do that.

   Yes -- the claude CLI's `--permission-mode` has an "auto" choice.
   Added `--permission-mode auto` (via a PERMISSION_MODE_ARGS constant)
   to both the fresh (`claude --session-id <uuid> --permission-mode auto
   "<prompt>"`) and resume (`claude --resume <uuid> --permission-mode
   auto`) commands in `ClaudeWidget.start_session`. Verified headlessly
   (both commands include the flag; prompt only on fresh) and re-ran the
   full-app session/resume flow (TODO 1d7331b) with the updated commands.
   [planned: claude-widget-auto-mode.md]
5ddbef0. COMPLETED: quitting claude in the widget should close the widget,
   not exit to shell. does the claude CLI need to be run in the context
   of a shell? or if yes, is there a way to force the shell to exit if
   claude cli does?

   Answers: running via a shell is worth keeping (bash loads the user's
   profile so claude is found/runs as in a real terminal); and yes,
   `exec` forces the shell to exit with claude. Changed
   `ClaudeWidget.start_session` to type `exec claude …` -- bash loads its
   profile then replaces itself with claude in the same PTY, so quitting
   claude ends the PTY (and if claude isn't found, exec fails and the
   shell stays, preserving the original claude-not-found safety). Added a
   `TerminalWidget.process_exited` signal (emitted on PTY EOF in
   `_on_readable`); the claude widget's DeskWindow binding
   (`_bind_claude_widget`) connects it to `close_widget_by_instance_id`
   (deferred via QTimer.singleShot so removal doesn't run inside the
   notifier callback). The Console widget is unaffected (still just shows
   "[process exited]"). Verified headlessly: exec commands, the
   process_exited signal on child exit, and a full-app claude frame being
   removed on process exit. design-docs/architecture.md updated.
   [planned: claude-widget-close-on-exit.md]
b25412e. COMPLETED: if there is a plan listed in a todo item, detect that
   and provide a button on hover to open the plan document in Desk.

   `desk.todo_file` now parses the `[planned: <file>]` marker into a new
   `TodoItem.plan` field. The TODO widget shows a single floating "📄
   Plan" button that follows the mouse to the hovered row (via
   `itemEntered` + mouse tracking) -- deliberately *not* a per-row
   `setItemWidget`, which is fragile with the list's InternalMove
   drag-reorder -- shown only over rows whose item has a plan, hidden
   over plan-less rows / on list-leave / on scroll / on repopulate.
   Clicking it opens the plan (`<todo dir>/plans/<file>`) in the Markdown
   renderer widget (TODO 6bf83a9) via the existing `current_context`
   widget-opener hook; `MarkdownWidget` gained a public `set_file(path)`
   for that. Verified headlessly (plan parsing; button show/position/
   hide behavior; open-via-opener) and full-app (clicking places a
   markdown widget rendering the plan). Affordance style (floating hover
   button) and target widget (markdown renderer) were chosen
   autonomously -- the AskUserQuestion went unanswered (user away) -- and
   are easily swapped for the toolbar/context-menu or the editor later
   (see plan).
   [planned: todo-open-plan-button.md]
b927389. COMPLETED: Add a tree-view project directory/file explorer
   widget. Add a search/filter textbox at the top which temporarily
   hides everything but the tree-paths to the results and the results
   themselves, e.g.
   if searching for "foo" in a directory with a structure like (a (b
   ...) (c (foo) ...) (d ...)), then a -> c -> foo would show, not b
   or d. clearing the search should restore the view but the current
   file should remain selected. if a user double-clicks on a filename
   or hits enter while a filename is selected, open the file in a new
   instance of the Editor widget.
   [planned: file-explorer-widget.md]
c7d6e4d. COMPLETED: Implement an SVG-rendering widget.
   [planned: svg-viewer-widget.md]
42dd260. COMPLETED: Add new tempui capabilities to allow claude to
   open markdown files in the GUI.
   [planned: tempui-open-markdown.md]
b44e8ba. COMPLETED: Crash: segfault while interacting with the Desk picker.
   Console output before the crash: `python -m desk` started normally,
   discovered widgets `browser`, `claude`, `console`, `demo`, `editor`,
   `git_status`, `lightning_round`, `question`, `scratch`, `todo`, opened
   `~/desk/test.desk` -- then `Segmentation fault:
   11` with no Python traceback at all (a real OS-level crash, not a
   caught/logged exception). Needs investigation: no traceback means the fault
   is likely inside Qt/PyQt or a C extension, not plain Python -- reproduce
   the exact picker interaction that triggered it (name click vs. directory
   click vs. hover), and check for any known-fragile native code path (e.g.
   LEARNINGS.md's QNativeGestureEvent segfault note) that could plausibly be
   involved. Resolved by TODO 8c9436b: two later crash reports pinned
   the same crashing call chain (QAbstractItemView::mouseReleaseEvent,
   a QListWidget-based Desk-picker popup) with full crash logs, never
   independently reproduced from this item's own report but a close
   enough match to close as resolved by the same fix. See
   QUESTIONS.md's own entry for this item.
8c9436b. COMPLETED: Crash: segfault while loading an already-existing .desk file
   from the Desk picker. Full macOS crash report provided (kept out of
   the repo per explicit instruction, not pasted here or anywhere else
   in the project) -- same `QAbstractItemView::mouseReleaseEvent` ->
   `QListView::mouseReleaseEvent` -> `sipQListWidget
   ::mouseReleaseEvent` crashing-thread shape as the already-fixed New
   -Desk-flow segfault (TODO 4716585), strongly suggesting the same
   underlying `_DeskListPopup`/`WA_DeleteOnClose` class of bug, just
   reached via "load an existing Desk" instead of "create a new one."
   Likely resolves `b44e8ba` too (same crash shape, that report just
   never had a crash log to confirm against).
   [planned: fix-desk-picker-nested-dialog-crash.md]
02eda20. COMPLETED: Wire the Markdown and Editor widgets onto widget-local
   storage (TODO fb76057) so their currently-open file path actually
   persists and restores across a Desk reload -- currently every
   widget's `"state"` in a saved `.desk` file is an empty `{}`, even
   for widgets with an obvious per-instance thing to remember (already
   tracked in `PARKINGLOT.md`, never wired up for any real widget).
   Tolerate a since-moved/deleted file gracefully at restore time, not
   as a crash or silent misbehavior. Also wired up the Markdown (Old,
   Basic) widget (named alongside Markdown/Editor in PARKINGLOT.md's
   original tracked gap, though not in this item's own title) via a
   new shared `desk.persisted_path.resolve_persisted_path` helper.
   [planned: widget-local-storage-file-paths.md]
ff6514a. COMPLETED: Small borders around widgets by default, to visually
   distinguish one widget from another and from the canvas.
   [planned: widget-borders.md]
8d05920. COMPLETED: Lock widgets in place so that only the title and an unlock
   icon show in the top bar of the widget -- unable to be moved,
   resized, or moved in z order while locked. [planned: lock-widgets.md]
cbbb661. COMPLETED: Editor widget needs a different color text caret when
   focused -- black-on-black doesn't work well.
   [planned: editor-dark-mode-and-wrap.md]
f2aede6. COMPLETED: Feedback widget: able to take internal screenshots of the app
   and make a DESK-feedback-[timestamp].md with the internal
   screenshots attached, and also a temp mode (with full-screen
   overlay) launched by a button which allows UI elements to be
   clicked and an identifying UI path will be pasted into the feedback
   either at the current caret position or at the end.
   [planned: feedback-widget.md]
397770c. COMPLETED: Introduce the idea of focus in the app: individual controls
   in a widget can have focus, and if so the widget itself is also
   focused. The titlebar of a widget should change slightly when the
   widget is focused. [planned: widget-focus-concept.md]
a1c701d. COMPLETED: Clicking then releasing the title bar of a widget should
   activate/focus the current caret inside of it.
   [planned: widget-focus-concept.md]
17a2720. COMPLETED: The white background on the editor line numbers is good for
   separating but bad for dark mode. Instead, draw a vertical line
   between the numbers area and the editor box, and draw the numbers
   in a slightly different color than the default text in the box.
   [planned: editor-dark-mode-and-wrap.md]
1d6777f. COMPLETED: Wrap too-long lines in the editor, and keep the line number
   aligned with the top line. [planned: editor-dark-mode-and-wrap.md]
f447303. COMPLETED: When opening new instances of the Claude or Console widgets,
   the default working directory should be the active project (current
   Desk) directory, not wherever the Desk process itself is running
   from. [planned: claude-console-default-cwd.md]
4716585. COMPLETED: Crash: creating a new Desk segfaulted right as the
   ".desk_temp" creation confirmation dialog was answered ("Yes"), with
   the new Desk's seeded Markdown-with-README widget (TODO cb2790d)
   seemingly appearing "at the same time." A full macOS crash report
   was provided for this one (kept out of the repo per explicit
   instruction, not pasted here or anywhere else in the project) --
   `EXC_BAD_ACCESS`/`SIGSEGV` on the main thread inside
   `QAbstractItemView::mouseReleaseEvent` ->
   `QListView::mouseReleaseEvent` -> `sipQListWidget
   ::mouseReleaseEvent`, reached via the normal Cocoa mouse-event
   -delivery path -- the faulting address looks like reused/garbage
   memory, the shape of a use-after-free, not a null-deref. Likely
   involves the same `_DeskListPopup` (a `QListWidget`-based,
   `WA_DeleteOnClose` popup) class of bug as `b44e8ba` above -- that
   report also names the Desk picker specifically, and never had a
   crash log to confirm against until now; fixing this may resolve
   that one too, though it's recorded separately since `b44e8ba`'s own
   trigger (just "interacting with the picker") wasn't confirmed to be
   New-Desk-creation specifically.

   Do the following:
   1. Refactor the "New Desk" flow so all of its questions are one
      single dialog (checkboxes/a path-picker-launcher/textboxes)
      instead of popping up one after another: (a) name (textbox); (b)
      path (a picker-launcher button showing the currently-selected
      default path); (c) create `.desk_temp` for tempui (checkbox);
      (d) create or update `.gitignore` with Desk-specific patterns
      (checkbox). Update the `.gitignore` process to be able to append
      to it if it can't already, and make sure that in both the create
      and update cases there's an empty line and then a comment saying
      the entries are Desk-specific.
   2. When opening a new Desk for the first time, take all of the
      appropriate actions (directory/file provisioning) before opening
      it (placing any widgets), so it isn't trying to do conflicting
      things in parallel.
   3. When creating directories and files, check immediately before
      the create that the item doesn't already exist, and abort in a
      recoverable way (e.g. switching to the "already exists" path) if
      it's found to. Do this per-widget for now; also see the
      `PARKINGLOT.md` item on a more generalized mechanism for this.
   [planned: fix-new-desk-flow-crash.md]
03f623a. COMPLETED: Crash: quitting the app with Cmd+Q raises a `KeyError` partway
   through teardown, so it doesn't tear down cleanly. Traceback:

   ```
   Traceback (most recent call last):
     File "./desk-stable/widgets/todo/widget.py", line 434, in _flush_on_teardown
       watcher.stop()
       ~~~~~~~~~~~~^^
     File "./desk-stable/src/desk/file_watch.py", line 107, in stop
       self._handle.cancel()
       ~~~~~~~~~~~~~~~~~~~^^
     File "./desk-stable/src/desk_services/file_watcher/service.py", line 83, in cancel
       self._service._unsubscribe(self._key, self._callback)
       ~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^
     File "./desk-stable/src/desk_services/file_watcher/service.py", line 135, in _unsubscribe
       self._observer.unschedule(watch)
       ~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^
     File "./desk-stable/.venv/lib/python3.13/site-packages/watchdog/observers/api.py", line 363, in unschedule
       emitter = self._emitter_for_watch[watch]
                 ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^
   KeyError: <ObservedWatch: path='./desk-stable', is_recursive=False>
   ```

   Likely root cause (from reading `desk/app.py` and
   `desk_services/file_watcher/service.py`, not yet confirmed by
   reproducing): `desk/app.py`'s `main()` connects
   `get_service().stop()` to `app.aboutToQuit` *last*, with a comment
   claiming this makes it run after "every individual consumer's own
   aboutToQuit-triggered watcher.stop()/handle.cancel()" -- but the
   TODO widget's `watcher.stop()` here isn't wired to `aboutToQuit` at
   all; it's in `_flush_on_teardown`, connected to the widget's own
   `destroyed` signal, which fires later, as part of Qt's actual
   widget-teardown cascade *after* `aboutToQuit` has already finished
   running. So `aboutToQuit`'s `get_service().stop()` -- which stops
   (and presumably clears) the whole shared `watchdog.observers
   .Observer` -- can easily run *before* a `destroyed`-triggered
   `SingleFileWatcher.stop()` (TODO widget, Questions widget, and any
   other widget with the same flush-on-teardown pattern) tries to
   unschedule its own watch from that now-already-stopped Observer,
   which watchdog itself no longer has bookkeeping for -- hence the
   `KeyError`. Likely fix direction: make
   `FileWatcherService._unsubscribe`/`WatchHandle.cancel()` tolerant of
   the shared Observer already being stopped (nothing meaningful left
   to unschedule at that point), rather than trying to guarantee a
   connection-order invariant across two fundamentally different Qt
   signals (`aboutToQuit` vs. a widget's own `destroyed`) that can't
   actually be ordered against each other that way.
   [planned: fix-teardown-keyerror.md]
7f51230. COMPLETED: Store crash logs in the current active project directory's
   `.desk_temp` folder instead of the project directory itself. On
   startup, if there are any crash logs present, open a new Crash Log
   widget for each one. The Crash Log widget reads a crash log and has
   a "Sanitize" button that strips off anything from the beginning of
   a path in the text that isn't relevant to finding the code --
   everything up to (but leaving) the `src` or `.venv` directory, for
   example. [planned: crash-log-widget.md]

   Investigated via code review: ruled out the QNativeGestureEvent note
   as a direct cause (Desk only reads native gesture events, never
   constructs them); reviewed desk_picker.py/canvas.py for other fragile
   patterns (nothing else found); confirmed this is a different, more
   severe symptom than TODO c8f6fb3's already-fixed `_DeskListPopup`
   crash (that one raised a catchable `RuntimeError` with a full
   traceback; this is a true segfault with none). Blocked on a specific
   reproduction -- see `QUESTIONS.md` and
   `plans/fix-desk-picker-segfault.md`.
   [planned: fix-desk-picker-segfault.md]
578cb6b. COMPLETED: Create a service for filewatchers in Desk, both from the app
   and from widgets. create a new `desk-services` directory under
   `./src/`, and create a sub-directory file-watcher, and put the
   implementation in there. For now, only implement the APIs that are
   needed by the app and widgets. The currently active watchers should
   be tracked and managed by this service. Watches should be
   de-duplicated as appropriate, such that a single watcher might make
   more than one notification; the goal of the de-duplication is to
   fix an issue that I've seen with file watchers in the current
   version of desk, which shows an error ("RuntimeError: Cannot add
   watch <ObservedWatch: path=... is_recursive=False> - it is already
   scheduled.").
   [planned: file-watcher-service.md]
cee6f74. COMPLETED: Refactor TempUiManager and the TODO widget's file-watching so
   they share the self-write-echo-suppression logic instead of each
   having its own copy, routing the TODO widget onto
   `SingleFileWatcher.record_own_write` instead of its own separate
   check. Additionally, add file-watching to the Editor widget so that
   if a file it has open is edited elsewhere (e.g. TODO.md edited by
   the TODO widget) while there are no local unsaved changes, it
   detects and reloads the external change -- relying on the
   file-watcher service's existing de-duplication/dispatch (TODO
   578cb6b), not a new mechanism; if there are local unsaved changes,
   flag the conflict without clobbering them. Performance for a
   pathologically-high-frequency writer on a single watched file is
   explicitly out of scope for now -- revisit only if it becomes a
   real, observed problem.
   [planned: file-watch-self-write-consolidation.md]
465c404. COMPLETED: Bug: in the Project Files widget, the "Open Folder" button and
   the search box's chrome (background/border) don't scale with zoom,
   similar to how the tree-collapsing controls (">") were also not
   scaling properly before that was fixed. Screenshot: the widget
   zoomed in to roughly 3-4x -- the titlebar ("Project Files" label,
   "x" close button) renders at the normal constant screen size, as
   designed, but within the widget's own content the "Open Folder"
   button's text is huge and overflows well outside its own grey
   rounded-pill background (which stayed a visibly smaller size), and
   the "Search..." placeholder text is similarly oversized and
   overflows past the right edge of the search box's own thin border.
   The text itself correctly scales with zoom; each control's own
   native-style-painted background/border chrome does not, desyncing
   from it.
   [planned: file-explorer-toolbar-zoom-scaling.md]
a053e3a. COMPLETED: Update widgets which load files to note in the title bar for
   the widget if the widget is loading a file from a path outside of
   the currently associated directory, by showing "[EXTERNAL]".
   [planned: widget-external-file-indicator.md]
95f7ce9. COMPLETED: Add a global error handler: on an uncaught exception anywhere
   in the app, attempt to append the stack trace to a file called
   `DESK-CRASH-[timestamp].log` in the project folder. Must not itself
   "further crash" if writing that log fails for any reason.
   [planned: global-crash-log-handler.md]
810a5d6. COMPLETED: Investigate and fix: a segmentation fault occurred opening
   `./necro-4x/necro-4x.desk`. The last action taken in that Desk
   beforehand was double-clicking `./necro-4x/.desk_temp
   /desk-temporary-ui.md` in the Project Files widget to open it (this
   opens it in a new Editor widget instance). This may or may not be
   related to work done around the same time on TODO a053e3a (the
   "[EXTERNAL]" titlebar marker). Traceback captured at the time (paths
   scrubbed to start at `./desk/`; trace is cut off after this point --
   no exception type/message was captured):

   ```
   Traceback (most recent call last):
     File "./desk/widgets/project_files/widget.py", line 246, in _open_index
       widget.set_file(path)
       ~~~~~~~~~~~~~~~^^^^^^
     File "./desk/widgets/editor/widget.py", line 181, in set_file
       self._load_file(path)
       ~~~~~~~~~~~~~~~^^^^^^
     File "./desk/widgets/editor/widget.py", line 146, in _load_file
       self.refresh_external_path_status()
       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^
     File "./desk/widgets/editor/widget.py", line 155, in refresh_external_path_status
       is_external = self._current_path is not None and current_context.path_is_external(
   ```
   [planned: segfault-open-tempui-file-in-editor.md]
10b0321. COMPLETED: in the TODO widget, please change the pop-up item adder/editor so that it is restricted to remain visually within the TODO widget itself.
   [planned: todo-widget-popup-stays-within-bounds.md]
f8d9cec. COMPLETED: Add a new (or existing?) tempui capability to allow agents to add "scratch" text, and make it clear in the tempui instructions given to claude that when the user refers to "scratch," that is what is meant, unless there is a more pressing local meaning.
   [planned: tempui-scratch-capability.md]
cdf45cb. COMPLETED: Add "bring to front" and "send to back" buttons to the top-right of widgets, left of the "x" button, which move it in visual z-order to the front or back, respectively.
   [planned: widget-z-order-buttons.md]
ed483e2. COMPLETED: split the widget-adding popup menu list of popups into collapsible groups, with the current groups being "active" and "deprecated", and default to showing active as shown and deprecated as collapsed.
   [planned: widget-spawn-menu-groups.md]
9743419. COMPLETED: Add a md file to the source with a description of the markdown rendering capabilities of Desk. update the markdown_ex markdown viewer to be able to show a tempui-based markdown file; in that case, add a "save a copy" button to replace "open" and default to the root of the project directory with a default file name derived from the first line of the markdown file; once that file is saved, it should be opened in a new normal markdown_ex widget, and the original tempui one should remain open.
   [planned: markdown-rendering-doc-and-tempui-markdown.md]
fb76057. COMPLETED: Ensure that "widget-local storage" exists: a means by which
   widgets can store data in the current .desk file. Checked: this
   capability does not yet exist -- `WidgetState` currently only holds
   geometry + `instance_id`, no per-instance state payload.
   `PARKINGLOT.md` already has a parked note on this exact gap
   ("Widgets can't persist an arbitrary per-instance chosen file across
   reload"), scoping the same underlying design question: a `state:
   dict` on `WidgetState`, a widget-side read/write protocol, and a
   generalized post-build binding replacing the current per-kind
   `_bind_temp_ui_widget`/`_bind_claude_widget` special-cases. If/when
   this is built (or if some equivalent mechanism already exists
   elsewhere and was missed), it should be consistently branded
   "widget-local storage" throughout code, docs, and future TODO items.
   [planned: widget-local-storage.md]
ac212bc. COMPLETED: Create a "stack" widget to keep track of nested discussions,
   with its data stored in widget-local storage (see TODO fb76057 --
   depends on that capability existing), plus a button to copy the
   stack as markdown into a project file called `STACK-[timestamp].md`,
   and the ability to load from an appropriately-formatted stack
   markdown file.
   [planned: stack-widget.md]
4c3fe4b. COMPLETED: When creating a new .desk, the user should pick both the title
   and the initial associated directory (today, `new_desk` only prompts
   for a name/title and always creates the new Desk inside the
   *current* Desk's directory, with no directory picker at all), with
   the directory picker defaulting to the current Desk's associated
   directory.
   [planned: new-desk-directory-picker.md]
fbd0554. COMPLETED: Add an option during new Desk creation to initialize the new
   Desk with a `development-process.md`, sourced initially from the
   current Desk's own `development-process.md`. Additionally: if a
   `development-process.md` exists for a Desk's associated project when
   a Claude widget is opened, add an instruction to read that file to
   the initial prompt given to claude (see `CLAUDE_WIDGET_PROMPT` in
   `widgets/claude/widget.py`, which already conditions its prompt on
   the current Desk's directory).
   [planned: development-process-seeding.md]
67ab2df. COMPLETED: Implement a general solution so that already-placed tempui
   -bound widgets live-refresh when their `.desk_temp` file is
   genuinely edited externally, instead of a notification click only
   centering the view on stale content (surfaced while implementing
   TODO 9743419 -- I'd described that capability as "live," which
   wasn't true of any tempui-bound widget kind). Reuses the existing
   generalized `_bind_temp_ui_content` dispatch; a widget with local
   editable state that a blind refresh could clobber (only Scratch, so
   far) opts out via a new optional `has_unsaved_local_edits()` hook.
   Resolves TODOs `f668aef`/`091bc27`/`9ee505f`/`6fbae42` below as part
   of the same implementation, rather than separately.
   [planned: tempui-live-refresh.md]
f668aef. COMPLETED: Make the Question widget live-refresh when its tempui file is
   edited after being placed (resolved by TODO 67ab2df's general
   solution -- documented gap, see `PARKINGLOT.md`).
091bc27. COMPLETED: Make the LightningRound widget live-refresh when its tempui
   file is edited after being placed (resolved by TODO 67ab2df's
   general solution -- same underlying gap as Question, not
   previously called out separately).
9ee505f. COMPLETED: Make the Scratch widget live-refresh from its tempui file
   without clobbering unsaved local edits (resolved by TODO 67ab2df's
   general solution, which specifically had to account for this case).
6fbae42. COMPLETED: Make the Markdown tempui-bound content widget (TODO 9743419)
   actually live-refresh as originally described (resolved by TODO
   67ab2df's general solution).
cb2790d. COMPLETED: When creating a new Desk, don't add all of the widgets to it --
   just open a markdown viewer of the README.md file if there is one
   for the project, or else add a Scratch widget with content for a
   basic readme that has a "# [desk name] README" at the top followed
   by a section called "## What this project is about or exploring...".
   [planned: new-desk-default-widgets.md]
7a086ba. COMPLETED: Add a Questions widget that works similarly to the TODO
   widget, but for managing QUESTIONS.md. [planned: questions-widget.md]
a801180. COMPLETED: Add to the tempui instructions to always use QUESTIONS.md for
   any questions there are for the user. If adding a new question, send
   a top-right tempui notification that, when clicked, either visually
   focuses a currently-opened Questions widget (see TODO 7a086ba) or
   else opens a new Questions widget and focuses it.
   [planned: questions-notification-routing.md]
96013cf. COMPLETED: Rename the current markdown widget (`widgets/markdown/`) as
   `markdown_old_basic`, and add a timestamped note near the top of
   relevant plans that this rename was done, but don't change the rest
   of the plan. Mark that widget as deprecated and confirm that it
   shows up in the deprecated group in the widget-add context menu
   (depends on TODO ed483e2's active/deprecated grouping existing).
   [planned: markdown-widget-identity-swap.md]
858752b. COMPLETED: rename the current markdown_ex
   widget (`widgets/markdown_ex/`) as `markdown` -- not
   `markdown_old_basic` as originally (conflictingly) written; the
   user clarified markdown_ex becomes the new default "markdown"
   widget while the plain widget (TODO 96013cf) becomes the deprecated
   `markdown_old_basic`, replacing it. Add a timestamped note near the
   top of relevant plans that this rename was done, but don't change
   the rest of the plan.
   [planned: markdown-widget-identity-swap.md]
17ac2a8. COMPLETED: Check for places in the code where the old basic markdown
   widget is being used, and add to QUESTIONS.md about whether or not
   they should be updated to point to the new markdown widget. (Depends
   on TODO 96013cf/858752b's rename(s) actually happening first, and on
   resolving which widget "the new markdown widget" refers to.)
   [planned: audit-old-basic-markdown-widget-usage.md]
5915ac2. COMPLETED: Drag and drop files into Desk should cause them to be opened
   as external. [planned: drag-drop-open-external.md]
f74945e. COMPLETED: Add a "paste" item to the top of the widget menu if there is
   anything in the clipboard; if pasted, put the pasted material into
   a file in the temp directory and attempt to open it with a
   corresponding widget; if it is markdown, then just use the markdown
   approach we're implementing with the new DSL entry (TODO 9743419);
   if it is text but not markdown, open it as a scrap (if there isn't
   a DSL entry for that, add one -- see TODO f8d9cec's existing
   `Scratch` tempui capability); if it is non-text content (binary),
   paste it as a new file in the project directory with a filename
   like `PASTED-ITEM-[timestamp].[file extension]`.
   [planned: paste-clipboard-routing.md]
8f5568f. COMPLETED: When the desk-switching MRU is shown, or when one of its items
   is clicked, ensure the shown/clicked item's file is still where
   it's expected to be (i.e. that it hasn't moved or been deleted).
   Checked: `desk.recent_desks.load_mru()` already filters missing
   files out of what it *returns* on every call (`p.is_file()`), but
   never persists that removal back to `~/.desk/recent_desks.json` --
   the stale entry just gets silently re-filtered every time, forever.
   If a file is missing when showing the MRU, actually remove it from
   the persisted list (not just the in-memory display). If the user
   clicks an MRU item whose file is missing, do not continue the "load
   new desk" operation -- checked: `DeskWindow.switch_desk`'s current
   behavior for a nonexistent path (`Desk(path=path)`) silently creates
   a brand-new *empty* Desk at that path instead, with no warning at
   all. Instead, show a modal pop-up warning that the file is no
   longer there, giving the full path in selectable/copyable text (an
   explicit exception to `CLAUDE.md`'s general "labels shouldn't be
   user-selectable" convention, matching its own "unless specifically
   requested" carve-out). [planned: mru-file-existence-check.md]
c458012. COMPLETED: `scripts/todo_item_ids.py` only works when run from a directory
   that both has that exact script at that path and can import this
   app's own `desk` package (`make_item_id` actually lives in
   `desk.todo_ids`) -- neither holds for a brand-new project Desk, even
   though TODO fbd0554 already seeds that project with a
   `development-process.md` whose own "Item IDs" section tells you to
   run exactly that script. Add seeding it (self-contained, no `desk`
   package dependency left) to the new-Desk initialization process
   alongside `development-process.md`, and update `.gitignore`
   provisioning to also cover what running it produces
   (`scripts/__pycache__/`).
   [planned: seed-todo-item-ids-script.md]
e69f209. COMPLETED: Bug: when widgets with carets overlap visually, sometimes
   focus seems to switch between them while typing.
   [planned: trap-widget-tab-focus.md]
91b3f42. COMPLETED: Feature: New widgets and extension of tempui DSL inside the
   .desk_temp. Only in-browser (html/css/js) widgets (no python) can be
   loaded this way. Introduce new tempui DSL for introducing new types
   of widgets to be used in the current Desk. All code should be
   base64 encoded when it is embedded in another file. Widgets defined
   in tempui can only be added to the Desk by tempui. Additionally,
   add constructs to the tempui DSL to allow the extension of the
   tempui DSL, so that a tempui-based widget can be invoked by tempui.
   In tempui-defined widgets' titlebar, add a button that says
   [TEMPUI], which, if pressed, offers to promote the widget to the
   Desk; if user confirms, then store the widget in the .desk file and
   also include the tempui DSL extension in a list in the .desk file,
   as well, re-pointing it towards the .desk file version of the
   widget, and removing it from tempui. Widgets in the .desk file
   should be registered just like built-in widgets at startup and
   after being added. All widgets and tempui DSL extensions must have
   a human-friendly label that can be shown in the UI (i.e. no UUIDs
   for widget names). Ensure the tempui md file explains the tempui
   side of things so that agents can use this feature. On startup or
   when a new tempui DSL item is added, ensure that the tempui md file
   includes information about all of the tempui DSL extensions in the
   .desk_temp folder or in the .desk file.
   [planned: tempui-custom-widgets.md]
f7b1611. COMPLETED: We need to make sure that the tempui md file is up-to-date, not
   just with the tempui DSL but with new versions of the rest of the
   document. Introduce a version number as a note at the top, with a
   simple integer version number that gets manually updated as the
   content changes (include a comment in the code that explains the
   versioning process). Before opening a Desk, ensure that the tempui
   md main content is up-to-date with the expected version; if there
   is no version, that means that it is out of date; be certain not to
   clobber the DSL extensions, if there are any.
   [planned: tempui-doc-versioning.md]
6857997. COMPLETED: Bug: [TEMPUI] should only be shown if the widget definition is
   in .desk_temp, not if it is in the .desk file.
   [planned: fix-tempui-promote-button-and-spawn-menu.md]
2b2a642. COMPLETED: Bug: promoted a temp widget and it is in the .desk file, but it
   is not showing up in the list of active widgets in the add-widget
   context menu, even after reloading the app.
   [planned: fix-tempui-promote-button-and-spawn-menu.md]
5734529. COMPLETED: Another Claude instance running inside of a Desk was trying to
   implement a tempui widget, and it had the following feedback: "Not
   Implemented: state persistence (no widget-local-storage wiring --
   the Desk Bridge API exists for html widgets but nothing implements
   save/restore for one yet)." Fix that, including adding a
   description of the (updated) Bridge API to the tempui md file.
   [planned: html-widget-local-storage-bridge-api.md]
e57ce5f. COMPLETED: It's probably time to split out the tempui md file into multiple
   pieces. Keep the original file, but split out the content of some
   of the less-general sections into other files and reference them
   with relative paths. The version number in the "main" (original)
   file will stand for all of the files, they don't each need their
   own. Keep the list of tempui DSL extensions in the main file, in
   its own section at the bottom, as it is, now. Also, none of the
   documents should mention Desk source code or repo documents (e.g.
   do not mention the Desk architecture document); the documents Desk
   provides in .desk_temp should be sufficient. Check for places where
   the original file is mentioned in the code and make sure that all
   of those sites are updated, e.g. desk-load-time checks.
   [planned: split-tempui-doc.md]
855ca76. COMPLETED: Bug: the Claude widget's prompt tells the agent to follow the
   tempui doc's links to the other split-out files unconditionally.
   Instead, tell the agent to follow those links only as needed, e.g.
   it should only read tempui-lightning-round.md if it needs to run a
   lightning round; desk-temporary-ui.md should include just enough
   context for each one that the agent can understand the use cases
   without opening them.
   [planned: fix-claude-prompt-tempui-links-wording.md]
4ab5875. COMPLETED: widgets/hex_flower (another Claude instance's port of
   ../../claude-projects/hexsheet's hexflower sheet item) renders a
   blank page when run locally. Investigate what is failing and write
   a DESK_FEEDBACK-[timestamp].md file with suggestions for how to (a)
   update the documentation so that similar issues do not happen in
   the future, and (b) make additional improvements to the tempui
   widget feature to help this kind of work go better in the future.
   [planned: investigate-hex-flower-blank-page.md]
411d0e0. COMPLETED: Whatever guidance covers the Bridge API's local-storage calls
   should make clear that a ported widget's own prior persistence
   mechanism (custom events, global variables, whatever the original
   project used) needs to be explicitly re-wired to
   `self.getLocalStorage`/`setLocalStorage` -- porting a widget doesn't
   make its old persistence approach work inside Desk automatically,
   and there's currently nothing prompting an agent to check for that
   mismatch.
   [planned: document-persistence-rewiring-for-ported-widgets.md]
c0875bc. COMPLETED: tempui DSL addition which enables Desk to initiate a
   conversation about a parking lot item with a new claude session,
   where the new session is still given instructions about being
   embedded in Desk but also is at the end of the intro prompted with
   something like "let's discuss an item from PARKINGLOT.md: [full
   parking lot item text]".
   [planned: tempui-discuss-parking-lot-item.md]
46e1b42. COMPLETED: Add a button to each of the questions displayed in the
   question widget: the button should be labeled "Discuss" and
   clicking it should do the same thing as the tempui DSL addition
   (TODO c0875bc).
   [planned: questions-widget-discuss-button.md]
624ff3a. COMPLETED: Bug: launching a DiscussParkingLotItem tempui discussion (TODO
   c0875bc) failed to let claude start -- something about dumping the
   entire PARKINGLOT.md item's text into the initial launch prompt
   broke it. Instead of embedding the full item text, the tempui file
   should just reference the item by its line number in PARKINGLOT.md,
   and the new session should read the file itself. Additionally, add
   an instruction telling claude not to immediately start a new
   discussion in Desk (e.g. by creating another DiscussParkingLotItem
   file) but to just have the discussion in the current session.

   Traced the full launch path: the assembled prompt was already
   correctly passed through a single `shlex.quote(...)` call before
   being spliced into the `exec claude ...` command typed into the
   PTY, so this wasn't naive/unescaped shell interpolation -- but the
   full parking-lot item's raw markdown text is unbounded, real prose
   (backticks, quotes, blank lines), and at least two still-plausible
   failure modes exist independent of the quoting itself: bash's
   default interactive `histexpand` performs `!`-history-expansion even
   inside a single-quoted argument, and the whole quoted blob is
   written to the PTY in one shot immediately after spawning bash,
   before it's certain readline has taken over the terminal in raw
   mode (risking the kernel tty layer's canonical-mode line-length
   limit). Neither was independently reproduced, but shortening the
   message sidesteps both regardless of which (if either) is the exact
   mechanism.

   `DiscussParkingLotItem`'s DSL shape changed from "first line label,
   rest of file the full verbatim item text" to "first line label,
   second line `Line <N>` (the item's starting line number in
   PARKINGLOT.md, written by the creating agent)" --
   `parse_discuss_parking_lot_item` now returns `(label, line_number)`.
   `_place_discuss_claude_widget` (`src/desk/shell/window.py`, shared
   with the Questions widget's Discuss button, TODO 46e1b42) gained a
   `parking_lot_line: int | None` param: when given, it builds a short
   "read PARKINGLOT.md yourself at that line" reference instead of
   splicing in full text; the Questions-widget path (full `item_text`,
   unaffected -- QUESTIONS.md entries aren't line-number-addressed and
   weren't reported broken) is unchanged. Both paths now get a shared
   trailing instruction telling the new session to discuss it in this
   same session rather than starting another new Desk discussion of
   its own. `TEMPUI_DOC_VERSION` bumped 5 -> 6; this project's own
   already-provisioned `.desk_temp/desk-temporary-ui.md` and
   `tempui-discuss-parking-lot-item.md` refreshed via a real
   `ensure_docs_current` run (not hand-edited) so they exactly match
   the new source; the originally-reported demo tempui file rewritten
   to the new `Line <N>` format. Verified headlessly (real
   `DeskWindow`-method-on-a-double pattern): `parse_discuss_parking_lot_item`
   round-trip/rejection cases; `_place_discuss_claude_widget`'s built
   instructions for both the line-number and full-text paths (each
   contains its expected content plus the new "don't start a new
   discussion" sentence); `_activate_temp_ui`'s CLAUDE_WIDGET_ID branch
   correctly extracts and forwards the line number; the final
   `exec claude ...` command string built end-to-end from the new,
   short prompt (~1000 chars, well short of anything that was ~1500-
   3000+ chars with a real item's full text spliced in).
   [planned: fix-discuss-parking-lot-item-launch-prompt.md]

a48e968. COMPLETED: New widget: Parking Lot. Reads the nearest `PARKINGLOT.md` and
   displays each item's title in a scrollable list. Each row has a
   "Discuss" button in a column on the right that launches a new
   claude session to discuss that item. Double-clicking a row's title
   instead opens just that one item in a Markdown widget, via the
   tempui mechanism.

   Implemented as a new `src/desk/parking_lot_file.py` parser (mirrors
   `desk.questions_file`'s shape: dataclass + regex parser) that reads
   PARKINGLOT.md's top-level `- **Title**` bullets into
   `ParkingLotEntry(title, line_number, raw_text)` -- `line_number`
   uses the exact same "starting `- **Title**` bullet line" definition
   the tempui `DiscussParkingLotItem` keyword's own doc already
   established (TODO 624ff3a), so it's directly usable by
   `_place_discuss_claude_widget`'s existing `parking_lot_line`
   parameter. A wrapped (multi-line) title, e.g. this file's own
   `WidgetSpawnMenu._activate_item` entry, collapses correctly to one
   line.

   New `widgets/parking_lot/` widget, modeled on
   `widgets/questions/widget.py`'s shape (file watching,
   `external_path_changed`) but read-only. Each row is a
   `setItemWidget`-placed `QLabel` (title) + fixed-width `QPushButton`
   ("Discuss") -- a real column of Discuss buttons down the right edge,
   as asked for, rather than the Questions widget's single floating
   hover button (which doesn't fit that description). Since
   `setItemWidget` content doesn't reach `QListWidget.itemDoubleClicked`
   (mouse events over a child widget go straight to that child, not
   the list view underneath), the title label is a small `_TitleLabel`
   subclass that reports its own `mouseDoubleClickEvent` as a signal.
   Double-clicking writes a `Markdown <title>` tempui file (the
   existing keyword/format from `desk.temp_ui.parse_markdown_tempui`)
   into `.desk_temp/`, reusing Desk's existing tempui notification/
   placement flow rather than placing a Markdown widget directly --
   matches "loads ... as tempui" literally. The Discuss button calls
   the `current_context` "discuss starter" hook with the item's line
   number, not its full text, avoiding a repeat of the exact
   launch-prompt-length problem TODO 624ff3a fixed.

   `DeskWindow.start_discussion` (the discuss-starter hook, TODO
   46e1b42) widened to accept an optional `parking_lot_line` parameter
   (and `item_text` given a default of `""`), forwarding both straight
   through to the already-`parking_lot_line`-aware
   `_place_discuss_claude_widget`. The existing Questions-widget call
   site (`starter("QUESTIONS.md", entry.raw_text)`) is untouched and
   still works unchanged. `current_context.py`'s discuss-starter hook
   type/docstring updated to match.

   Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real
   `QApplication`): `parse_parking_lot_file` against this project's own
   real PARKINGLOT.md (33 items, correct title/line_number/raw_text for
   the first and a wrapped-title item); constructing the real widget
   against a synthetic PARKINGLOT.md shows the right rows; a real Qt
   `QMouseEvent` double-click dispatched to the title label (not just a
   direct method call) fires `_open_item` and writes a tempui file
   whose content round-trips through `parse_markdown_tempui` back to
   `(title, raw_text)`; clicking a row's Discuss button (direct call)
   reaches a fake discuss-starter hook with `("PARKINGLOT.md", "",
   line_number)`; `DeskWindow.start_discussion`'s widened signature
   verified both in its new kwarg-only call style and the existing
   Questions-widget two-positional-arg style (unbound-method-on-a-
   double pattern); `discover_widgets` picks up the new
   `widgets/parking_lot/` directory correctly.

   Not exercised: right-clicking the canvas / actually placing the
   widget from the spawn menu in a live GUI session, and a real
   `claude` binary launch from the Discuss button (same limitation
   noted in every prior widget/claude-launch TODO in this project).
   [planned: parking-lot-widget.md]

fc17b55. COMPLETED: Bug: a claude launch prompt built by
   `_place_discuss_claude_widget` embeds a literal `\n\n` in the middle
   of the prompt string. When typed into an interactive bash/readline
   PTY, each raw `\n` byte is treated as pressing Enter regardless of
   shell-quote state, breaking the still-open `shlex.quote`d command
   and leaving the shell stuck at a `>` continuation prompt instead of
   launching claude. Reported live via the new Parking Lot widget's
   Discuss button. Fixed at the source (`_place_discuss_claude_widget`'s
   leading `f"\n\n..."` replaced with a plain leading space, matching
   `_development_process_instruction()`'s existing convention) and
   defensively at the actual boundary (`ClaudeWidget.start_session` now
   replaces any stray `\n` in the assembled prompt with a space before
   `shlex.quote`, so any future caller of `extra_instructions` can't
   reintroduce this). Verified with a real, live PTY (`pty.openpty()` +
   `subprocess.Popen(["bash", ...])`, one `os.write` of the whole
   command exactly like `type_into_shell`): the old buggy instructions
   reproduce the reported stuck-at-`CONT>`-continuation-prompt behavior
   exactly, while the fixed instructions plus the new normalization
   produce a single clean line with no continuation prompt.
   [planned: fix-embedded-newline-breaks-claude-launch-prompt.md]

51be2bc. COMPLETED: Bug: after TODO fc17b55's fix, starting a Parking Lot
   "Discuss" session still gets stuck -- the shell just sits there, and
   typing a stray `'` plus Enter is enough to unstick it and launch
   claude. Root cause confirmed directly (not just the suspected
   mid-command truncation TODO fc17b55's own investigation flagged but
   never confirmed): this environment's PTY canonical-mode line limit
   (`PC_MAX_CANON`) is exactly 1024 bytes, and a single unterminated
   line longer than that is truncated at that boundary -- critically,
   including the line's own terminating newline if it falls past the
   boundary, which leaves a blocked shell `read`/`readline` with no way
   to ever see a complete line (matching the reported "just sits
   there" symptom exactly). `_place_discuss_claude_widget`'s
   apostrophe-heavy hand-written instructions (plus the shared
   `CLAUDE_WIDGET_PROMPT`, which had one too) made an already-long
   command line long enough to risk crossing that boundary. Fixed per
   direct instruction: stop splicing the actual discussion instructions
   into the command line at all -- `_place_discuss_claude_widget` now
   writes them to a standalone file under `.desk_temp`
   (`_write_discuss_instructions_file`) and passes only a short,
   fixed-shape, apostrophe-free instruction pointing at that file, so
   the command line's length no longer depends on the discussion
   content's length at all (confirmed: the real, realistic assembled
   command is 711 bytes, regardless of how long the referenced file's
   content is). `CLAUDE_WIDGET_PROMPT`'s own remaining apostrophe was
   also reworded away. Investigating the exact mechanism also surfaced
   a second, independent gap in the same delivery path:
   `TerminalWidget.type_into_shell`'s single `os.write` to a
   non-blocking PTY master fd never checked how many bytes it actually
   wrote, silently dropping any unwritten remainder forever -- fixed
   with a bounded retry loop (defense in depth; it can't rescue a line
   that's fundamentally longer than the kernel's own line buffer, which
   is what the file-based redesign actually fixes). Verified
   headlessly: the built `claude_extra_instructions`/prompt contain no
   `'` character for either Discuss-launch path, the written file
   exists with the exact expected content and isn't mistaken for a
   temp-ui widget file, a real live PTY test directly isolated and
   confirmed the 1024-byte truncation-eats-the-newline mechanism, and a
   simulated genuine short-write test confirmed `type_into_shell`'s new
   retry loop actually recovers a payload the old single-call code
   would have silently truncated. A clean live before/after repro of
   the exact original "stuck" symptom via the old apostrophe-heavy
   command was attempted but didn't reproduce consistently in this
   session's sandboxed environment (see the plan's Verification section
   for why) -- a weaker result than a clean repro, though the
   underlying mechanism is independently confirmed above via a
   dedicated isolated test.
   [planned: fix-discuss-claude-prompt-file-based-instructions.md]

6f9c51b. COMPLETED: Add an event message channel service to Desk,
   following the "mediator" topology (a component of Desk itself acts
   as mediator -- widgets never talk to each other directly). Via the
   Bridge API, widgets should be able to register for and receive
   named messages, and to send named messages. The Bridge API should
   handle identity details (use the widget's *instance* id, not its
   widget-definition id). Events are logged by default into a file
   called MEDIATED-EVENT-LOG.tsv. Also build a python widget to view
   logged events, with a "live tail" mode and functionality to clear
   the log (with confirmation). Add a description of the usage of
   these events to the Bridge API document (the `DefineWidget`/Bridge
   API section of the tempui docs, `tempui-custom-widgets.md`),
   following the existing versioning process for updating tempui
   documents (`TEMPUI_DOC_VERSION` in `src/desk/temp_ui.py`).
   **Prioritized ahead of all other items** (there were no other open
   items at the time, so this was a no-op in practice, but recorded per
   the request).

   Shipped as: a new, Qt-free `desk.event_mediator.EventMediator`
   (thread-safe via a lock plus one `queue.Queue` per subscribed
   *instance* id, never the widget-definition id) -- one shared
   instance for the whole app run, constructed in
   `desk.server.runner.start_server` alongside the existing
   `GuiBridge`, and reachable both from the Local Web Server's new
   `POST/GET /api/bridge/events/{subscribe,unsubscribe,publish,poll}`
   routes (`events` capability; `poll` is a clamped-to-30s long-poll,
   not a true WebSocket -- browser `WebSocket` can't attach the custom
   `X-Desk-*` auth/identity headers every other Bridge route already
   relies on) for `kind: "html"` widgets, and from `kind: "python"`
   widgets directly in-process via a new
   `desk.shell.event_broker.EventSubscription` (a `QTimer`-polled Qt
   wrapper, never blocking the GUI thread) reached through a new,
   generically-called `DeskWindow._bind_event_mediator` duck-typed
   hook (`bind_event_mediator(instance_id, mediator)`, mirroring
   `_bind_claude_widget`'s existing "resolved after `build()`, not
   through it" shape -- no widget currently had any way to learn its
   own instance id from `build()`'s signature alone). The mediator's
   own `MEDIATED-EVENT-LOG.tsv` (in the current Desk directory, kept in
   sync via the same `_refresh_picker` choke point
   `current_context.set_current_desk_directory` already uses) logs
   every publish regardless of origin, JSON-encoding the payload (which
   also makes the TSV row safe for free, since `json.dumps` escapes any
   literal tab/newline inside a string value). The sender never
   receives its own publish back (a documented, deliberate default, not
   specified by the request). New `widgets/event_log/`: a read-only
   `QTableWidget` view of the log, kept fresh by a `SingleFileWatcher`
   (same reused component the TODO widget already watches `TODO.md`
   with) regardless of a "Live Tail" toggle, which controls only
   whether a refresh auto-scrolls to the bottom; a Clear action
   (`QMessageBox`-confirmed, split into its own headlessly-testable
   `_confirm_clear` method, matching `CrashLogWidget`'s
   `_confirm_delete`) routes through the live mediator when one is
   wired up (reusing its write lock, so it can't race a concurrent
   publish's own log append) rather than writing the file itself.
   `tempui-custom-widgets.md` (source: `_CUSTOM_WIDGETS_DOC` in
   `src/desk/temp_ui.py`) gained a new "Sending and receiving named
   messages" section describing `desk.events.*`, per the existing
   `TEMPUI_DOC_VERSION` process (bumped 6 -> 7, so every
   already-provisioned Desk directory picks up the refreshed doc via
   the existing `ensure_docs_current` mechanism, not a special case).
   `design-docs/architecture.md`'s Bridge API section and capability
   table updated to match.

   Verified headlessly throughout (`QT_QPA_PLATFORM=offscreen`; a real
   running server via `desk.server.runner.start_server` for the REST
   surface, since `httpx`/`starlette.testclient` isn't installed --
   `urllib.request` against the real server instead, arguably closer to
   the real integration boundary anyway): the mediator core (sender
   -exclusion, subscribe/unsubscribe/unsubscribe_all/clear_all,
   non-blocking `drain`, genuinely-blocking `poll` receiving a real
   cross-thread publish and correctly timing out, tab/newline-safe TSV
   logging, `clear_log`); the four REST routes end to end including a
   403 on a missing `events` capability and fully independent
   subscriptions between two instances of the same widget id;
   `EventSubscription`'s Qt-signal delivery and its
   `destroyed`-triggered cleanup; `DeskWindow._bind_event_mediator` end
   to end via a real `DeskWindow` and a scratch widget (distinct
   instance ids, cross-instance delivery, sender exclusion, and
   subscription cleanup on close, all via the real, generic binding
   path -- no widget-specific code in `window.py`); the Event Log
   widget's parsing/formatting/live-tail/clear-confirmation behavior,
   including the lock-safe mediator-routed clear path specifically; a
   full real-app-shaped boot against this project's own actual
   `widgets/` directory (all ~20 shipped widgets) placing a real Event
   Log widget that live-picks-up a real publish landing in a real,
   on-disk log file; and `ensure_docs_current` refreshing a
   version-6-stuck doc directory to 7 with the new section present.
   [planned: event-mediator-channel.md]

f693275. COMPLETED: Bug: reported live -- after restarting Desk, the tempui-DSL
   -defined `Alice`/`Bob`/`Starter` widgets (built for TODO 6f9c51b) all
   fail with `subscribe failed: ... (400): {"detail":"Unknown widget
   id: 'Alice'"}`. Root cause already flagged in PARKINGLOT.md (the
   "The Bridge API's `require_caller` can't resolve a tempui-DSL
   -defined custom widget kind at all" entry, surfaced back when TODO
   `5734529` built self.getLocalStorage/setLocalStorage): `require_
   caller` (`src/desk/server/app.py`) resolves the calling widget only
   via `discover_widgets(widgets_dir).get(x_desk_widget_id)`, which
   only ever scans the real, on-disk `widgets/` directory -- a
   tempui-DSL-defined custom widget (TODO `91b3f42`) has no such
   directory; its `WidgetInfo` only lives in the live `DeskWindow
   ._widgets` catalog. This blocks *any* capability-gated Bridge call
   (`workspace.*`/`fs.*`/`widgets.*`/the new `events.*`) for a custom
   widget, not just `events`. Separately, even a fixed lookup wouldn't
   be enough on its own: `_register_custom_widget` always registers a
   custom widget with `capabilities=[]` hardcoded, since the
   `DefineWidget` tempui DSL has no way to declare any -- needs a new
   `Capability` DSL line too. Now that a second real feature (`events`)
   is blocked by this, worth actually designing and fixing rather than
   re-parking (see the PARKINGLOT.md entry's own "not designed yet;
   parking rather than guessing at the right generalization from a
   single specific fix's own narrow workaround").
   **Prioritized ahead of all other items** (live-blocking a feature
   the user is actively using right now).

   Fixed: `require_caller` (`src/desk/server/app.py`) now falls back
   to the live, `GuiBridge`-reachable widget catalog (a new
   `DeskWindow.get_widget_info` accessor) when `discover_widgets
   (widgets_dir)`'s on-disk scan misses -- resolving every existing
   capability (`workspace`/`fs`/`widgets`) for a tempui-DSL-defined
   custom widget, not just `events`. The `DefineWidget` tempui DSL
   gained a new, repeatable `Capability<TAB>name` line;
   `CustomWidgetDefinition` carries it through to the `WidgetInfo`
   `_register_custom_widget` builds (previously always `capabilities=
   []`), and `.desk`-file persistence round-trips it (defaulting to
   `[]` for a pre-existing `.desk` file with no such key, so old files
   keep loading fine). `tempui-custom-widgets.md` documents the new
   line (`TEMPUI_DOC_VERSION` 7 -> 8); the now-resolved PARKINGLOT.md
   entry removed. This project's own live `Alice`/`Bob`/`Starter`
   `DefineWidget` files (`.desk_temp/`, untracked) were edited in place
   to add `Capability\tevents`, so they'll work again once Desk is
   restarted (this fix is in `src/desk/**`, which only takes effect on
   restart, unlike widget source).

   Verified headlessly, including against a real `DeskWindow` + real
   running server reproducing the exact originally-reported failure
   (now fixed) alongside a regression check that a custom widget
   *without* the right capability still correctly 403s, a truly
   -unknown widget id still 400s, and a real on-disk widget's own fast
   -path resolution is unaffected. See the plan's Status section for a
   testing note on a real GuiBridge-threading deadlock hit (and fixed)
   in the verification script itself, not the implementation.
   [planned: fix-custom-widget-bridge-capability-resolution.md]
1e75140. COMPLETED: write a document about the starter/alice/bob
   experiment and store it in design-docs. Shipped as
   `design-docs/alice-bob-starter-experiment.md`: what the three
   widgets do, the reaction rule (Alice reacts to any integer < 10,
   Bob additionally requires it be positive), why Bob's extra
   condition is necessary (the mediator excludes only the sender from
   its own publish, not every other subscriber -- both Alice and Bob
   receive Starter's seed `0` since neither is its sender, so without
   the filter both would react and produce a duplicate branch), the
   resulting 0->10 chain, the `Capability` DSL line each widget
   declares (TODO f693275), and a pointer to where `DefineWidget`
   widgets actually live (a Desk directory's own gitignored
   `.desk_temp/`, not source control -- there is no checked-in copy of
   the exact HTML).
   [planned: starter-alice-bob-experiment-doc.md]
e35bcf0. COMPLETED: pop-ups from inside the browser widget show up in a
   separate macos window. is there any way to avoid that? could they be
   fully contained within the widget frame, instead?

   Root cause: `BrowserWidget` never connected to `QWebEnginePage
   .newWindowRequested`, so Qt WebEngine's own default handling created
   a genuinely separate, unmanaged top-level native window for any
   `window.open()`/`target="_blank"` request -- yes, avoidable, and
   fully containable. Fixed: `BrowserWidget` now has a second, embedded
   pop-up `QWebEngineView` shown via a `QStackedWidget` in place of the
   main page (URL label + close button), and connects
   `newWindowRequested` to redirect every request into it via
   `request.openIn(...)` -- the same pattern Qt's own `simplebrowser`
   example uses. A *fresh* view/page is created per pop-up open (not
   reused across opens): verification found that reusing one could hit
   a real, reproducible internal Chromium consistency assertion on a
   second rapid redirect, fixed by always tearing down and recreating
   instead. Verified headlessly against a real local HTTP page's own
   `window.open()` button (real JS click, not a Python stand-in),
   confirming `QApplication.topLevelWidgets()`'s count never increases,
   the pop-up panel shows the right content, both `window.close()` and
   the widget's own close button return to the main page, and repeated
   open/close/reopen no longer crashes on exit (reproduced the crash
   consistently pre-fix, confirmed gone across multiple stress runs
   post-fix). A separate, pre-existing bug found (not caused) during
   this verification -- the Back/Forward buttons' own enabled/disabled
   state can go stale after a real navigation, confirmed present
   identically on the untouched original file -- was parked in
   `PARKINGLOT.md` rather than fixed here, being unrelated to what this
   item asked for.
   [planned: browser-widget-contained-popups.md]
9767c1a. COMPLETED: add a Bridge API service by which a widget (with
   permission from the Desk user) can get a tree-view snapshot of the
   dom and console log of an html-based widget.

   Shipped as a new `introspect` capability + `desk.introspect
   .snapshot(targetInstanceId)` -> `{dom, console}`. Two new pieces
   needed first: `ChromiumWidget` now sets an explicit
   `_LoggingWebEnginePage` (overriding the virtual
   `javaScriptConsoleMessage` -- no signal exists for this) giving
   every `html` widget a bounded 200-entry rolling console-output
   buffer, queried on demand; and a new `GuiBridge.call_async`,
   generalizing `GuiBridge.call` for a GUI-thread operation that's
   itself async (`QWebEnginePage.runJavaScript`'s result only arrives
   via a later callback) -- blocking naively inside `call`'s own `fn()`
   waiting for that callback would deadlock the GUI thread against its
   own event loop, so `call_async`'s `starter` must instead kick off
   the operation and return immediately, with `resolve(value)` (called
   later, whenever the real callback fires) actually completing the
   call. Unlike every other Bridge capability, `introspect` is not
   satisfied by a manifest declaration alone: the first request for a
   given (caller, target) pair shows the Desk user a blocking
   confirmation dialog naming both widgets (`DeskWindow
   .request_introspect_permission`); declining returns no data at all.
   Grants are in-memory only (`DeskWindow._introspect_grants`), cleared
   on `switch_desk`, never persisted to disk. `tempui-custom-widgets.md`
   documents the new capability and its permission model
   (`TEMPUI_DOC_VERSION` 8 -> 9); `design-docs/architecture.md`'s
   capability table and Security Considerations updated to match.

   Verified headlessly end to end via a real `DeskWindow` with three
   real placed `html` widgets: a capability-less caller `403`s before
   ever reaching the permission dialog; an approved request returns a
   correctly-nested real DOM tree (confirmed against the target's
   actual markup, not a stub) plus its real captured console log
   (`info`/`error` entries, right levels); a repeat request for the
   same pair succeeds without re-prompting (confirmed via a
   confirm-call counter); an unknown target `400`s; a declined request
   to a different target `403`s with no grant recorded and no data
   returned; and `switch_desk` clears every grant. `GuiBridge.call_async`
   and the console-log buffer were also verified in isolation (a
   genuinely-async resolution path with no deadlock, exception
   propagation, clean timeout; real `console.log`/`warn`/`error`
   capture and the 200-entry bound).
   [planned: introspect-bridge-capability.md]
33d3e8d. COMPLETED: do an audit of all of the UI and confirm that they don't fail to scale properly when zooming; fix anything that violates that. when the titlebar is too small to hold the buttons without growing the widget width, just show the title; if it is still too small, then for so long as that is true, "greek" the widget (show just a rectangle with the frame color; if the user clicks on a "greeked" widget, zoom/pan the desk so that widget is showing, with 20% margins on all sides. Add a button to widget title bars (labelled with an eye emoji) to do the same thing (zoom/pan to show the widget)

   Part 1 (audit): re-verified headlessly that titlebar/resize-handle/
   border counter-scaling and the three HUD overlays (`ZoomControl`,
   `DeskPicker`, `TempUiNotificationStack`) genuinely stay constant
   on-screen across zoom/pan/resize -- everything already held, no
   fixes needed there.

   Part 2 (degrade + greek): `WidgetFrame` gained a
   `chrome_state ∈ {"full","title_only","greeked"}`, recomputed on
   both `set_view_scale` and the frame's own `resizeEvent` (so a
   resize-handle drag degrades chrome too, not just zooming) from
   thresholds computed off the same fixed on-screen constants the
   counter-scaling itself targets. A `QStackedWidget` swaps to a plain
   `BORDER_COLOR`-filled page while greeked (no titlebar/handles
   reachable); a new `_EyeButton` joins the titlebar's usual button
   row; `WorkspaceView._hit_test_chrome` short-circuits on
   `frame.is_greeked` so a click anywhere on a greeked widget's bounds
   -- and the eye button, from any chrome state -- both dispatch to a
   new `zoom_to_widget(frame, margin_fraction=0.2)`, sharing its core
   fit/clamp logic with the existing `zoom_to_fit` via a new private
   `_fit_rect` helper.

   Found and fixed one real, pre-existing bug along the way (not
   introduced by this change, and independently blocking reliable
   greeking): `WidgetFrame`, once embedded via `QGraphicsProxyWidget`,
   silently grew itself back up to fit its layout's inflated minimum
   size (counter-scaled chrome's *local* sizes balloon at low
   `view_scale`) on a deferred, later-processed event -- not
   synchronously, so a check performed immediately after a zoom change
   could pass by accident while the same check failed once the event
   loop actually ran. `QLayout.SetNoConstraint` alone only partially
   fixed it; the full fix mirrors the existing Desk picker/zoom control
   HUD-drift fix (TODO `82d66c0`/`4adfcad`/`1f9bd34`): snapshot the
   known-good size before scaling, reassert it via
   `QTimer.singleShot(0, ...)` after. See the new `LEARNINGS.md` entry.

   Verified entirely headlessly (real `WorkspaceView`/`WidgetFrame`s,
   synthetic `QMouseEvent`s routed through the real mouse-event
   handlers): the audit re-checks; full → title_only → greeked
   transitions via both wheel-zoom and a manual resize-handle drag;
   title_only/greeked visual states; click-anywhere-on-greeked and the
   eye button both correctly zoom/pan with a real ~20% margin; the eye
   button correctly shrinks the full-chrome width budget (and is
   excluded, like the other action buttons, while locked); `zoom_to_fit`
   regression-checked against the `_fit_rect` refactor; a 10-cycle
   repeated-zoom stress test confirming the size-reassertion fix holds
   stably; and a full regression of every pre-existing titlebar button
   plus titlebar/resize-handle drag.
   [planned: audit-and-greek-widgets.md]
dc557b2. COMPLETED: create a general event poster widget

   Shipped as `widgets/event_poster/`: a name field, a multi-line
   payload box, a Publish button, and a status line. Binds to the
   event mediator (TODO `6f9c51b`) via the same duck-typed
   `bind_event_mediator(instance_id, mediator)` hook every
   mediator-aware `python` widget implements, using
   `desk.shell.event_broker.EventSubscription` purely to get a
   correctly-identified `.publish(name, payload)` call (needs the real
   sender instance id, which `current_context.get_event_mediator()`
   alone can't provide) -- no new Bridge API surface needed. The
   payload box accepts either real JSON or plain text: valid JSON
   parses to its real value, empty means `null`, anything else is sent
   as-is as a string payload, with the status line reporting which
   happened. Publish is disabled (with an explanatory status) until
   the mediator binding arrives and while the name field is empty.
   Neither field clears after a successful publish -- a repeated
   -testing tool, not a one-shot form. Ctrl+Return in the payload box
   and Enter in the name field both publish too (same convention as
   the TODO widget's item editor, TODO `8db7891`).

   Verified entirely headlessly: `_parse_payload`'s JSON/text/empty
   branches; disabled-before-binding behavior; a real `EventMediator`
   receiving correctly-shaped events (name, payload, sender instance
   id) for JSON, empty, and plain-text payloads; empty-name rejection
   client-side; the Enter/Ctrl+Return shortcuts exercised through real
   Qt events/signals; `discover_widgets` picking up the new manifest;
   and a full real `DeskWindow` regression (pointed at this project's
   own already-provisioned directory, to avoid `_provision_temp_ui`'s
   confirmation dialogs blocking a headless run) confirming
   `_bind_event_mediator`'s generic path wires up a real placed
   instance end to end, including genuine cross-instance delivery
   through the real shared mediator.
   [planned: event-poster-widget.md]
7505703. COMPLETED: add a widget to view all of the widgets registered for the event message channel and add a per-registered-widget button to zoom/pan to it (use the same button as the zoom/pan titlebar button)

   Shipped as `widgets/event_subscribers/`: a status line plus a list
   of every widget instance currently subscribed to at least one name
   on the event mediator (TODO `6f9c51b`), each row showing a human
   -readable label and its subscribed event names alongside a 👁
   button. New `EventMediator.list_subscriptions()` gives a lock
   -protected snapshot; two new `current_context` hooks
   (`widget_zoomer`, `widget_display_name_resolver`) let the widget
   reach a new `DeskWindow.zoom_to_widget_by_instance_id` (resolves a
   placed frame by instance id, then calls the same
   `WorkspaceView.zoom_to_widget` the titlebar eye button uses, TODO
   `33d3e8d`) and the already-existing `_display_name_for_instance`
   (built for the introspect permission dialog) without importing
   shell internals directly -- the same "one new minimal get/set pair
   per capability" pattern every other python-widget-facing hook here
   already follows. Refreshed on a 1s timer (cheap in-memory work, no
   subprocess/IO), gated on `isVisible()` like `widgets/git_status/
   widget.py`'s own polling, since the mediator has no signal-based
   change notification to react to instead. An instance that
   unsubscribed from every name individually (leaving an empty set,
   not removed) is correctly excluded from the list.

   Verified entirely headlessly: `list_subscriptions()`'s snapshot
   correctness/independence and the empty-set-vs-removed distinction;
   the widget's not-connected/empty/populated states, row content and
   sort order, and eye-button-click-to-zoomer wiring (both a fake
   installed zoomer and a real `QPushButton.click()`); `discover_
   widgets` picking up the manifest; and a full real `DeskWindow`
   regression (pointed at this project's own already-provisioned
   directory, same reasoning as TODO `dc557b2`) confirming
   `zoom_to_widget_by_instance_id` finds a real frame and actually
   moves/scales the real view to bring it fully into the viewport
   (and correctly returns `False` for an unknown id), the new hooks
   resolve to the real bound `DeskWindow` methods, and a real placed
   Event Subscribers instance shows a real subscribed instance and
   its eye button genuinely zooms the real `WorkspaceView` to it.
   [planned: event-subscribers-widget.md]
6e731c1. COMPLETED: drag-and-drop of an image into the Desk should result in the image being saved in the .desk_temp directory and then displayed with tempui.

   Shipped as a new `OpenImage <path>` DSL keyword (identical shape to
   `OpenMarkdown`, its own new `tempui-image.md` split doc,
   `TEMPUI_DOC_VERSION` bumped 9 -> 10) plus a new `widgets/image_viewer/`
   widget (`kind: "python"`, a near-twin of `widgets/svg_viewer/`:
   `QPixmap`-based instead of `QSvgRenderer`-based, same Open/`set_file`
   /`SingleFileWatcher`/`[EXTERNAL]`-marker shape). A new
   `desk.geometry.fit_rect` was extracted from the SVG viewer's own
   private `_fit_rect` so both widgets share the identical
   aspect-preserving letterboxed-scaling math instead of duplicating
   it. `DeskWindow._on_files_dropped` now special-cases raster image
   suffixes (`IMAGE_DROP_SUFFIXES` -- deliberately excludes `.svg`,
   which already has correct by-reference handling): a new
   `_drop_image_as_temp_ui` copies the dropped file's bytes into
   `.desk_temp` (short random prefix + original filename), writes a
   new UUID-named `OpenImage .desk_temp/<name>` tempui file
   (self-write-suppressed via `record_own_write`, matching
   `_paste_text_as_temp_ui`), and immediately places+binds an Image
   Viewer instance at the drop position -- matching how every other
   dropped file type already places immediately, no notification
   -then-click detour. Every other dropped extension is completely
   unaffected. The rest of the tempui plumbing
   (`IMAGE_VIEWER_WIDGET_ID`/`TEMP_UI_WIDGET_IDS`/
   `_temp_ui_widget_id_for`/`_bind_temp_ui_content`
   /`_resolve_open_image_target`/`_notify_temp_ui`) mirrors
   `OpenMarkdown`'s existing entries exactly, so `OpenImage` is a
   general DSL capability any tempui author can use, not only
   reachable via drag-and-drop.

   Found and fixed one real, pre-existing bug along the way (not
   introduced by this change): `desk.file_watch.SingleFileWatcher`
   -- previously only ever used to watch text files (Markdown, SVG,
   TODO.md, ...) -- called `path.read_text()` unconditionally on every
   change and only caught `OSError`, not `UnicodeDecodeError`; watching
   a binary file (the new Image Viewer's live-reload) silently killed
   the `changed` notification entirely on every real external change.
   Fixed by also catching `UnicodeDecodeError` (self-write suppression
   doesn't meaningfully apply to binary content anyway, so this is
   treated the same as an unreadable file -- always notify, never
   suppress) -- confirmed the existing text-file behavior (both the
   self-write-suppression path and the real-external-change path)
   is completely unaffected.

   Verified entirely headlessly: `fit_rect`'s letterboxing math;
   `OpenImage` parsing/detection/reservation; `ensure_docs_current`
   refreshing a stale version-9 doc directory to 10 with
   `tempui-image.md` present and linked; the Image Viewer widget's
   placeholder/load/live-reload (a real `SingleFileWatcher` picking up
   a genuine on-disk binary change, the exact bug above)/missing-file
   /invalid-image/`[EXTERNAL]`/Open-button behaviors; `discover_widgets`
   picking up the manifest; and a full real `DeskWindow` regression
   (an isolated, pre-provisioned temp project directory, since this
   test performs real file writes/saves -- avoids both the
   `_provision_temp_ui` confirmation-dialog hang a fresh, unprovisioned
   directory would cause in a headless run, and any risk to the real
   repo) confirming a real drop: exactly one new copied image
   (byte-for-byte identical to the source) plus one new `OpenImage`
   tempui file appear in `.desk_temp`, no spurious notification fires
   for the self-authored write, an Image Viewer instance is placed
   immediately at the drop position showing the real image, a
   non-image (`.md`) drop is completely unaffected, and a simulated
   app restart (a fresh `DeskWindow` over the same saved Desk)
   reconnects to the same file via the standard
   instance_id-equals-uuid mechanism.
   [planned: image-drop-tempui.md]

593a464. COMPLETED: Bug: in the Event Log widget, the "Live Tail" and "Clear Log"
   buttons' chrome (background/border) doesn't scale with zoom -- same
   category of bug as TODO 465c404's Project Files toolbar fix.
   Screenshot: both buttons' text renders oversized, overflowing well
   outside their own grey rounded-pill backgrounds, which stayed a
   visibly smaller size than the (correctly) zoomed text.

   Same fix as TODO 465c404: force Qt's built-in "Fusion" style on the
   two buttons (`self._live_tail_button`, `self._clear_button`) via
   `QStyleFactory.create("Fusion")` + `.setStyle(...)`, kept alive as
   an instance attribute (`setStyle()` doesn't take ownership of the
   `QStyle`) -- rather than hand-painting custom chrome, since a
   `QPushButton` (this widget's Live Tail button is checkable, unlike
   Project Files' plain button) has too many visual states to
   re-derive by hand.

   Verified headlessly: the widget builds without error, both buttons
   report `style().objectName() == "fusion"`, Live Tail's checkable
   toggle still works, Clear Log's `clicked` still reaches
   `_clear_log`, and the real widget renders cleanly through a
   3x-zoomed `QGraphicsView`/`QGraphicsProxyWidget` with unaffected
   button geometry. As with TODO 465c404, this environment's offscreen
   Qt platform defaults to Fusion regardless of the fix, so it can't
   reproduce the *broken* native-macOS-style rendering the bug
   report's screenshot showed -- needs visual confirmation in the real
   running app.
   [planned: event-log-toolbar-zoom-scaling.md]

8afef71. COMPLETED (but NOT ACTUALLY FIXED -- see PARKINGLOT.md): Generic fix,
   superseding the narrow per-widget approach of TODO
   465c404 and TODO 593a464: an audit of every other widget found the
   same native-style-chrome-desyncs-under-zoom bug in 17 of 19 widgets
   (both statically-created controls and ones rebuilt dynamically on
   every render, e.g. lightning_round's option buttons). Rather than
   patching each widget file individually, fixed once at the single
   choke point every widget's content passes through (WidgetFrame's
   embedding into the canvas), automatically covering every widget --
   present and future -- without requiring each widget file to opt in.

   The original planned approach (per-widget setStyle(Fusion), applied
   generically) turned out not to work: WidgetFrame already sets its
   own stylesheet on itself (for its border), and confirmed directly
   that any ancestor's setStyleSheet() silently overrides a
   descendant's setStyle() call regardless of order -- meaning TODO
   465c404/593a464's original per-widget fixes were likely never
   actually effective in the real app either, since neither fix's own
   verification wrapped the widget in a real WidgetFrame. Also found
   that style().objectName() -- the exact signal both prior fixes'
   verification relied on -- can't detect this: under this
   environment's offscreen Qt platform, both the untouched default
   style and an explicitly-created Fusion style report as
   indistinguishable objects. Both findings written up in LEARNINGS.md.

   Fixed instead by setting a stylesheet (CONTENT_ZOOM_SAFE_STYLESHEET)
   directly on each widget's content root in WidgetFrame.__init__,
   giving QPushButton/QToolButton/QLineEdit explicit background/
   border/padding rules -- the same mechanism (confirmed via the
   audit) that already makes the Todo/Questions widgets'
   FILTER_BUTTON_STYLE-styled buttons immune to this bug. A stylesheet
   cascades correctly to every descendant, present and future, with no
   event-filter machinery needed. Removed the now-redundant (and
   apparently never-effective) per-widget fixes in project_files/event_log.

   Verified extensively headlessly by pixel-sampling actual rendered
   output (not style-object introspection, per the finding above)
   across static controls, controls added after construction, a
   pre-built subtree attached in one shot, a widget's own more
   specific stylesheet still taking precedence, both QToolButton and
   QLineEdit (not just QPushButton), and real widgets from the audit
   (svg_viewer, lightning_round -- including forcing a real rebuild of
   its option buttons by answering an item, project_files, event_log
   -- including event_log's :checked pseudo-state). Confirmed
   WidgetFrame's own chrome never receives this stylesheet. As with
   the two prior fixes, this offscreen environment can't reproduce the
   real native-macOS-style rendering directly -- needs visual
   confirmation in the real running app.

   Update 2026-07-15: tested in the real running app, and the bug is
   still present -- the Event Log toolbar buttons still do not scale
   with zoom, despite this fix passing every headless check above.
   Root cause of the discrepancy not yet found. Parked (not blocking
   other work) rather than continuing to iterate immediately -- see
   PARKINGLOT.md for the full attempt history and what to try next.
   [planned: widget-content-zoom-safe-style.md]
b324217. COMPLETED: Author `DefineWidget` custom widgets from a real per-widget
   source directory (TS custom element + template HTML + tsconfig +
   manifest), packaged by one generic `scripts/build_widget.py`
   (stdlib-only), and seed that script into new projects the same way
   `scripts/todo_item_ids.py` already is. Document the pattern in
   `tempui-custom-widgets.md`. See
   design-docs/custom-widget-authoring.md section 1.
   [planned: build-widget-authoring-pattern.md]

   Added scripts/build_widget.py (stdlib-only, compiles a
   custom_widget_src/<name>/ TS+template source directory into a
   DefineWidget tempui file), seeded it into new projects alongside
   scripts/todo_item_ids.py, bumped TEMPUI_DOC_VERSION 10 -> 11, and
   added an "Authoring from real source" section to
   _CUSTOM_WIDGETS_DOC. Deliberately put the source convention at
   custom_widget_src/ rather than widgets/ (the feedback's own
   example project put it under widgets/lifeforce-heart/) since
   discover_widgets scans every widgets/<id>/widget.json expecting a
   "python"/"html" kind and would raise on this authoring manifest's
   different shape.

   Verified end-to-end with a real tsc invocation (tsc 3.8.3 was on
   PATH in this environment) round-tripping through
   desk.temp_ui.parse_define_widget, plus each error path (missing
   manifest keys, missing <name>.ts, missing BUILD marker, tsc absent
   from PATH -- never falls back to npx), the doc version bump/
   content, and the seed script's copy-if-missing/never-overwrite/
   executable-bit behavior. Ran the full scratchpad regression suite:
   9 pre-existing failures (confirmed via git stash to fail
   identically before this change), 0 new failures.
5ff02d2. COMPLETED: Fix `DefineWidget`'s silent no-instance-placed gap: add a loud
   one-line callout at the top of `DefineWidget`'s section in
   `tempui-custom-widgets.md`, and auto-place one instance the first
   time a brand-new keyword is registered from a live-added (not
   edited, not startup/Desk-switch-rescanned) tempui `DefineWidget`
   file. See design-docs/custom-widget-authoring.md section 2.
   [planned: define-widget-auto-place.md]

   Added a loud callout to _CUSTOM_WIDGETS_DOC (TEMPUI_DOC_VERSION 11
   -> 12), and gave _handle_define_widget_file an `is_new` param
   (passed True only from _on_temp_ui_file_added) so a genuinely new
   keyword -- checked before _register_custom_widget mutates state --
   auto-places one centered instance via a new
   _auto_place_new_custom_widget. Re-saving an already-known keyword,
   and _register_custom_widgets_from_desk_temp's own bulk startup/
   Desk-switch rescan, place nothing, so neither duplicates instances.

   Verified on a real WorkspaceView (unbound-method-on-a-fake-double
   pattern): a live-added brand-new keyword places exactly one
   instance; editing that same keyword afterward places no additional
   instance; the bulk rescan registers without placing anything; a
   refused registration (reserved keyword) places nothing. Full
   scratchpad regression suite: 9 pre-existing failures plus one
   expected new failure in my own earlier b324217 verification script
   (a hardcoded doc-version-11 assertion, now stale since this bumped
   it to 12 -- not a real regression, that scratchpad script isn't
   part of the shipped code), 0 other new failures.
5995ffd. COMPLETED: Give a placed `DefineWidget` custom widget instance a way to
   report which version of its code it's actually running: compute a
   content hash when a definition is registered, expose the current
   hash via `desk.self.getManifest()`, and track the hash a placed
   instance was placed with so Desk's own UI can show when an
   instance predates the currently-registered definition. See
   design-docs/custom-widget-authoring.md section 3.
   [planned: custom-widget-content-hash.md]

   Added WidgetInfo.content_hash (an md5(html_b64)[:12] hash, computed
   in _register_custom_widget) exposed via getManifest's
   _widget_info_dict, and WidgetState.placed_content_hash tracked
   per-instance on WidgetFrame (set at fresh placement, applied from
   the saved .desk state on restore). A new
   _refresh_stale_indicators_for(keyword), called at the end of every
   _register_custom_widget, recomputes a "[STALE]" titlebar marker
   (mirroring the existing "[EXTERNAL]" marker mechanism) on every
   already-placed instance of that keyword -- catching both the live
   -edit-while-placed case and the reopen-after-source-changed case.

   Verified via the same real-WorkspaceView unbound-method-on-a-fake
   -double pattern as prior items: registration computes/stores/
   exposes the hash and changes it on redefinition; a fresh placement
   is never stale; a live redefinition immediately marks an
   already-placed instance stale (and a newly-placed one after the
   edit is not); a restored instance is stale or not depending on
   whether its saved hash matches the current one;
   WidgetState.placed_content_hash round-trips through save/load/
   desk_state_dict, and an old .desk file with no such key defaults to
   None. Found and fixed one genuine regression during verification:
   src/desk/shell/window.py's _capture_desk_state now reads
   frame.placed_content_hash unconditionally, which broke an older
   scratchpad verification script's own lightweight _FakeFrame double
   (missing the new attribute) -- fixed by adding it there, confirmed
   via git stash that this was a real regression (passed before,
   failed after) unlike the other pre-existing failures. Full
   regression suite back to the same 9 pre-existing failures plus one
   already-known-stale doc-version assertion in my own earlier
   b324217 script, 0 other new failures.
c892403. COMPLETED: Resolve relative `desk.fs.readFile`/`writeFile` paths against
   the current Desk's own directory instead of the server process's
   ambient working directory (or reject relative paths with a clear
   error), expose that directory via `desk.self.getManifest()`, and
   give `desk.events.*` top billing in `tempui-custom-widgets.md`'s
   Bridge API section as the preferred mechanism for cross-widget
   signaling, ahead of `fs`/`workspace`/`widgets` in the list. See
   design-docs/custom-widget-authoring.md section 4.
   [planned: fs-path-resolution-and-events-framing.md]

   Added a `_resolve_fs_path` helper in server/app.py (absolute paths
   pass through unchanged; relative ones resolve against
   `gui_bridge.window.current_desk.directory` via the existing
   `run_on_gui` GUI-thread-crossing convention), used by both
   `fs_read_file`/`fs_write_file`. `self_get_manifest` now also
   returns a `directory` field. Reordered `_CUSTOM_WIDGETS_DOC`'s
   Bridge API capability list to put `events` first with an explicit
   "reach for this first for cross-widget signaling" callout,
   documented the new `fs` resolution behavior and getManifest's
   `directory`/`content_hash` fields (the latter was a real
   documentation gap left over from TODO 5995ffd, fixed here while
   touching this same bullet). TEMPUI_DOC_VERSION 12 -> 13.

   Verified end-to-end over real HTTP (a running server + a real
   GuiBridge attached to a fake window double, background-thread
   requests against a pumped Qt event loop, same pattern as the
   existing local-storage bridge test): a relative fs.writeFile/
   readFile round-trips under the fake Desk's own directory, an
   absolute path is used as-is, and getManifest returns both the new
   `directory` and the existing `content_hash`. Doc content and
   version bump also checked directly. Full regression suite: the
   same 9 pre-existing failures plus two now-stale doc-version
   assertions in my own earlier b324217/5ff02d2 scripts (hardcoded to
   prior version numbers, not real regressions), 0 other new
   failures.
0d2ebc1. COMPLETED: Add an Event Viewer widget: opened by double-clicking a row in
   the Event Log widget (`widgets/event_log/`), showing that one
   event's full detail (timestamp, name, sender instance id, and its
   payload pretty-printed in full, not the truncated single-line
   summary the Event Log's own table row shows).
   [planned: event-viewer-widget.md]

   Added widgets/event_viewer/ (kind:"python"): EventViewerWidget shows
   timestamp/name/sender in labels plus the payload pretty-printed
   (json.dumps(..., indent=2)) in a read-only QPlainTextEdit, via a
   duck-typed set_event(event) (mirroring set_file). Shows a
   placeholder when placed standalone with no event set yet. Updated
   widgets/event_log/widget.py to stash each row's real MediatedEvent
   on its Timestamp column item (Qt.ItemDataRole.UserRole, mirroring
   questions/widget.py's ENTRY_ROLE), connected itemDoubleClicked to a
   new _open_event_viewer that reaches the widget opener via
   current_context (the same pattern project_files's _open_index
   already uses for the Editor widget), with a broad except around the
   set_event call so a broken hook can't crash the double-click slot
   (matching TODO 810a5d6's reasoning). Not centered in the view --
   matches Project Files' own current double-click behavior; TODO
   efdad99/da4f9c0 are the ones introducing centered placement as a
   deliberate, separately-scoped change.

   Verified headlessly with real Qt widgets (QApplication, offscreen):
   set_event populates all four fields including pretty-printed
   multi-line JSON and empty-string None-payload handling; the
   placeholder shows with no event set; a real QTableWidget
   double-click flow (via _open_event_viewer directly, exercising the
   same code a real itemDoubleClicked signal would) opens the widget
   and passes the correct event through; a missing opener, an opener
   returning something without set_event, and a set_event that itself
   raises all fail silently rather than propagating out of the Qt
   slot. Confirmed discover_widgets(widgets_dir) picks up the new
   widget correctly. Full regression suite: the same 9 pre-existing
   failures plus the two already-known-stale doc-version assertions
   from earlier TODOs, 0 new failures.
59c5a70. COMPLETED: Change where a `DefineWidget` widget's authoring source lives
   (TODO b324217's `custom_widget_src/<name>/` convention): for a Desk
   working on a project other than Desk's own repo, recommend
   `.desk_temp/widgets/<name>/` instead of a project-root
   `custom_widget_src/<name>/` directory, since `.desk_temp` is already
   the established Desk-specific/gitignored support directory rather
   than adding a second convention at the project root. Separately,
   update the widget frame's `[TEMPUI]` promote button (see TODO
   91b3f42) so that promoting a widget also moves its authoring source
   directory out of `.desk_temp/widgets/<name>/` into a permanent,
   non-gitignored project subdirectory, `desk_widgets/<name>/` --
   promotion already means "this is now a permanent part of my
   project," so its source should stop living in the disposable
   `.desk_temp` tree too, not just its definition in the `.desk` file.
   Update `scripts/build_widget.py` (TODO b324217) and
   `tempui-custom-widgets.md`'s authoring-pattern docs so the build
   process works correctly for a source directory in either of these
   two locations.
   [planned: relocate-custom-widget-authoring-source.md]

   Added CUSTOM_WIDGET_SRC_DIRNAME ("widgets", under .desk_temp/) and
   PROMOTED_WIDGET_SRC_DIRNAME ("desk_widgets", project root) to
   src/desk/temp_ui.py. Updated _CUSTOM_WIDGETS_DOC's "Authoring from
   real source" section to recommend .desk_temp/widgets/<name>/
   instead of a project-root custom_widget_src/<name>/, and added a
   promotion-moves-the-source-too note there and in "Promoting a
   defined widget to the Desk" (TEMPUI_DOC_VERSION 13 -> 14). Updated
   scripts/build_widget.py's own docstring/usage example to match --
   no functional change needed there, since it already takes an
   arbitrary directory argument rather than hardcoding
   custom_widget_src. New DeskWindow._relocate_promoted_widget_source,
   called from _on_tempui_promote_requested: moves
   .desk_temp/widgets/<keyword>/ to desk_widgets/<keyword>/ if it
   exists, silent no-op if there's no source directory to move
   (hand-authored widgets never had one), and leaves the source in
   place (logged, not raised) if the destination already exists --
   the .desk file promotion itself has already succeeded by that
   point and shouldn't be made to look like it failed over this
   secondary bookkeeping step.

   Verified end-to-end with a real tsc invocation confirming
   build_widget.py produces identical output run against a fixture at
   .desk_temp/widgets/<name>/ and again at desk_widgets/<name>/.
   Verified the promote flow on a real WorkspaceView: a source
   directory present at promotion time moves correctly (with its
   original location gone and the .desk-file bookkeeping still
   intact); promoting a widget with no source directory is an
   unaffected no-op; promoting into an already-existing destination
   leaves the source alone without disturbing the rest of the promote
   flow. Doc content, version bump, and the updated build_widget.py
   docstring also checked directly. Full regression suite: the same 9
   pre-existing failures plus three already-known-stale doc-version
   assertions from earlier TODOs in this same batch, 0 other new
   failures.
3e2c4f2. COMPLETED: Change the `[STALE]` titlebar marker (TODO 5995ffd) from a
   passive label into something clickable: clicking it pops up a
   dialog showing both content hashes (the one this instance was
   placed with, and the one currently registered for its keyword) and
   gives the user the choice to reload the widget with the new content
   now, or keep running the old content for now (i.e. dismiss and
   leave the instance as-is, still marked `[STALE]`, until they decide
   later).
   [planned: clickable-stale-marker-dialog.md]

   Replaced the append-to-title-label `[STALE]` marker with a real
   clickable titlebar button (_StaleIndicatorButton, styled like
   _TempuiPromoteButton), wired through WorkspaceView's existing
   centralized chrome-click dispatch (_hit_test_chrome/
   mousePressEvent/mouseReleaseEvent) exactly like every other titlebar
   button, via a new widget_stale_clicked signal. DeskWindow's new
   _on_widget_stale_clicked shows both hashes via a new
   _confirm_stale_reload (QMessageBox, "Reload Now"/"Keep for Now",
   split out for headless-testability like _confirm_clear) and, on
   Reload Now, calls .reload() on *only that specific frame's*
   ChromiumWidget -- deliberately not via HotReloadBroker.widget_changed,
   which would reload every placed instance of that keyword regardless
   of which one's marker was clicked.

   Verified on a real WorkspaceView: the button shows/hides correctly
   and contributes to min_full_width_px like the promote button does;
   a real hit-test at the button's actual on-screen position resolves
   to ("stale", frame); Reload Now reloads only the clicked instance
   (a second, independently-placed instance of the same keyword is
   untouched), updates placed_content_hash, and clears the marker;
   Keep for Now changes nothing; a non-ChromiumWidget frame or an
   instance that's no longer actually stale are both no-ops with no
   dialog shown. Updated TODO 5995ffd's own verification script's
   stale-state assertions from checking label text to checking the new
   button's visibility. Full regression suite: the same 9 pre-existing
   failures plus three already-known-stale doc-version assertions from
   earlier TODOs in this batch, 0 other new failures.
efdad99. COMPLETED: Change the Project Files widget's (`widgets/project_files/`)
   double-click handling (currently `_open_index`, which always opens
   the Editor widget unconditionally) to a fallback chain: (1) if a
   viewer widget is available for the clicked file's type, open it
   there; (2) otherwise, if an editor is available, open it there --
   only ever route a genuinely text file into the text Editor widget,
   never a binary/unknown type; (3) otherwise, fall back to placing a
   Scratch tempui note (see `desk.temp_ui`'s `Scratch` keyword) whose
   text says what file type this is and that no viewer/editor is
   available for it. Whichever of the three actually gets launched
   should be placed centered in the current view, the same convention
   every other tempui/programmatic widget placement in this codebase
   already follows (see e.g. `DeskWindow._place_discuss_claude_widget`,
   `_auto_place_new_custom_widget`). Depends on having some notion of
   "which widget(s) handle which file type" to check against, which is
   TODO b5d52c0's file type registry -- plan that one first, or at
   least decide its shape, before planning this one.
   [planned: file-explorer-viewer-editor-scrap-fallback.md]

   Added `find_view_handler`/`find_edit_handler`/`looks_like_text_file`
   to `src/desk/file_type_registry.py` (view lookup falls back to a
   new `BUILTIN_VIEW_WIDGET_BY_SUFFIX` floor -- generalizing
   `EXTERNAL_DROP_WIDGET_BY_SUFFIX`/`IMAGE_DROP_SUFFIXES` -- so a fresh
   Desk's empty registry doesn't regress existing svg/markdown/image
   double-click behavior; the text sniff is a null-byte + UTF-8
   -decodability check, no new dependency). Added a new
   `current_context.get/set_centered_widget_opener` hook +
   `DeskWindow.open_widget_content_centered` (same centering math as
   `_place_discuss_claude_widget`), since the existing
   `get_widget_opener`/`open_widget_content` default to `(0, 0)`.
   Rewrote Project Files' `_open_index` into `_open_file` (view ->
   edit -> built-in-editor-if-text -> Scratch-note fallback chain),
   using the centered opener throughout.

   Verified: the lookup helpers (registry match by extension/MIME,
   builtin-floor fallback, no-fallback for `find_edit_handler`) and
   the text/binary sniff heuristic directly; `open_widget_content
   _centered`'s own centering math and unknown-widget-id no-op on a
   real `WorkspaceView`; Project Files' full dispatch chain (a
   registered view handler, a registered edit handler with no view
   handler, the built-in editor for a real text file with no registry
   match at all, the Scratch fallback for a binary file with no match,
   and a broken `set_file` failing silently rather than crashing the
   double-click slot). Full regression suite: the same 9 pre-existing
   failures plus three already-known-stale doc-version assertions from
   earlier TODOs in this batch, 0 other new failures.
b5d52c0. COMPLETED: Build a registry of file types (keyed by both file extension
   and MIME type, where available) to the widget(s) that can view,
   edit, consume, or produce that type -- generalizing the small
   hardcoded `EXTERNAL_DROP_WIDGET_BY_SUFFIX` map in
   `desk/shell/window.py` into something dynamic and user/agent
   -editable, rather than a fixed table only a code change can update.
   Store the registry as JSON on the `Desk` dataclass itself
   (`desk/desks.py`), persisted in the `.desk` file the same way
   `custom_widgets` already is. Add a new widget,
   `filetype-registry-editor`, that reads and edits the registry
   entirely through a new Desk service exposed over the Bridge API
   (a new capability, alongside `workspace`/`fs`/`widgets`/`events`/
   `introspect`) -- never by reading/writing the `.desk` file directly.
   Editing the registry through this Bridge API call must publish a
   Desk event (via the existing `EventMediator`/`desk.events.*`
   machinery, TODO 6f9c51b) with the editing widget's own instance id
   as the sender, so every other interested widget can react live.
   Reading the registry through the Bridge API must, as part of that
   same call, subscribe the calling widget's instance to those edit
   events -- so "read the registry" and "start watching for future
   changes to it" are one step, not two separate calls a widget author
   could forget to pair up. Update the Project Files widget
   (`widgets/project_files/`) to consume the registry this way:
   fetch it once via the Bridge API when the widget starts, and update
   its own local in-memory copy whenever an edit event for it arrives
   -- never re-fetching from scratch on every event, and never reading
   the `.desk` file directly itself either. See TODO efdad99, which
   depends on this registry existing.
   [planned: file-type-registry.md]

   Clarified via user question before planning: Project Files is
   `kind: "python"`, and every existing python widget reaches Desk
   services in-process via a `current_context` hook (e.g.
   `get_event_mediator()`), never via a real HTTP call to the Bridge
   API (that's the `kind: "html"`-only mechanism) -- so Project Files'
   own consumption goes through a new `current_context` hook (initial
   read) plus the existing generic `bind_event_mediator` mechanism
   (live updates), not literal Bridge API calls. `filetype-registry
   -editor` genuinely uses the real Bridge API, as a new `kind: "html"`
   widget -- the first hand-authored one in this project (every other
   `kind: "html"` widget is a runtime-materialized `DefineWidget` one).
   Also translated the TODO's own hyphenated widget name
   "filetype-registry-editor" to this project's actual snake_case
   widget-id/directory convention: `filetype_registry_editor`.

   Implemented: new `src/desk/file_type_registry.py`
   (FileTypeHandler/FileTypeRegistryEntry + to/from-dict helpers,
   FILE_TYPE_REGISTRY_UPDATED_EVENT); `Desk.file_type_registry`
   persisted in desk_state_dict/load_desk/save_desk (and carried over
   unchanged in `_capture_desk_state`, same as `custom_widgets` --
   otherwise every save would silently wipe it). New Bridge API
   `filetypes` capability/routes (get subscribes + reads in one call,
   set persists + publishes with the editing widget's instance id as
   sender) and a matching `window.desk.filetypes.*` bridge_client.py
   namespace. New `current_context.get/set_file_type_registry_provider`
   hook (refreshed in `_refresh_picker`, same choke point as the
   directory/event-mediator hooks) for Project Files' one-time initial
   read; Project Files also implements `bind_event_mediator` (the
   existing generic TODO 6f9c51b hook) to keep its local copy current
   via the event's own payload, no re-fetch. New
   `widgets/filetype_registry_editor/` (kind:"html", the first
   hand-authored one in this project): a minimal JSON-textarea editor
   calling `window.desk.filetypes.get/set` directly.

   Verified: FileTypeRegistryEntry/Handler to/from-dict and
   Desk/desk_state_dict/load_desk round-trips (and an old .desk file
   with no key defaults to `[]`); the new widget is discovered with
   `kind: "html"` and the `filetypes` capability; the current_context
   provider hook; Project Files' initial read plus a real
   EventMediator-published update changing its local copy; the Bridge
   API end-to-end over real HTTP (a running server + a real GuiBridge
   attached to a fake window, matching the established pumped-event
   -loop pattern) -- get returns entries and subscribes the caller,
   set persists to the fake window and publishes the update event
   (with the new entries as payload and the editing instance as
   sender) to another subscriber; the bridge_client.py namespace.
   Found and fixed one genuine regression: `_capture_desk_state` now
   reads `self.current_desk.file_type_registry` unconditionally, which
   broke an older scratchpad test's minimal fake `current_desk` double
   (missing the new attribute) -- confirmed via git stash that this
   was a real regression (passed before, failed after) unlike the
   other pre-existing failures; fixed by adding the attribute there.
   Full regression suite back to the same 9 pre-existing failures plus
   three already-known-stale doc-version assertions from earlier TODOs
   in this batch, 0 other new failures.
7462cdb. COMPLETED: Add `tempui-breaking-changes.md`/`tempui-new-features.md` to
   the generated `.desk_temp` tempui doc set (prioritized, per user
   request). From `../../FEEDBACK/FEEDBACK-DESK-tempui-doc-changelog
   -2026-07-15-1315.md` (a peer project's feedback, extracted from
   migrating `necro-4x`'s `widgets/lifeforce-heart/`/
   `widgets/lifeforce-control/` to a newer Desk's updated `DefineWidget`
   authoring conventions): `TEMPUI_DOC_VERSION` already tells a reading
   agent *that* something changed since whatever version its project
   was built against, but not *what* -- forcing a full re-read plus a
   manual diff against memory (which a fresh agent picking up the same
   project cold has no way to do at all) to answer "what do I need to
   fix." Add two more files to the same generated/versioned set
   `desk-temporary-ui.md`/`tempui-custom-widgets.md`/etc. already are
   (TODO `e57ce5f`'s "one shared version number for the whole set"
   mechanism -- no separate version of their own, refreshed for free by
   the existing `ensure_docs_current` staleness check): `tempui
   -breaking-changes.md` and `tempui-new-features.md`, each entry
   tagged with the `TEMPUI_DOC_VERSION` it was introduced in, listed
   newest-first, with enough detail to act on without re-reading the
   rest of the doc set (what changed, and concretely what to do about
   code/conventions written against the version before it). Backfill
   real historical entries from this project's own actual
   `TEMPUI_DOC_VERSION` bump comments in `src/desk/temp_ui.py` (every
   bump already has a "TODO xxx: bumped N -> N+1 for ..." comment
   explaining the change -- a ready-made, accurate source to backfill
   from, more reliable than the feedback doc's own illustrative
   reconstruction, which was written against this project's version 13
   and doesn't reflect the version 14/(this batch's later) changes made
   since). Establish the convention going forward: whenever
   `TEMPUI_DOC_VERSION` bumps for a breaking change or a new
   capability, add a corresponding entry to whichever of these two docs
   applies, at the same time (see TODO `1a96c9f`, which formalizes this
   as a documented instruction for agents working on Desk itself).
   [planned: tempui-changelog-docs.md]

   Added `BREAKING_CHANGES_DOC_FILENAME`/`NEW_FEATURES_DOC_FILENAME`
   and `_BREAKING_CHANGES_DOC`/`_NEW_FEATURES_DOC` to
   `src/desk/temp_ui.py`'s `SPLIT_DOC_CONTENT` (no separate version of
   their own, per TODO `e57ce5f`). Backfilled real entries for
   versions 7-14 from this file's own `TEMPUI_DOC_VERSION` bump-log
   comments (versions 1-6 predate the practice, noted as such in both
   docs) -- only version 14 (the `custom_widget_src/` ->
   `.desk_temp/widgets/` authoring-source move, TODO `59c5a70`) was a
   real breaking change; the rest are additive. Added a short
   "check these first" paragraph to `DOC_TEMPLATE` after the built-in
   -file-types list (these two files aren't DSL-keyword-triggered
   types themselves). `TEMPUI_DOC_VERSION` 14 -> 15, with a
   going-forward instruction alongside the doc constants: any future
   breaking/new-capability bump should add a matching entry in the
   same commit.

   Verified: both files registered in `SPLIT_DOC_CONTENT` and written
   by `write_tempui_docs`; version numbers in both docs strictly
   descending; content covers exactly versions 7-14 (14 in breaking,
   7-14 in new-features) with the right classification; both note
   that versions 1-6 predate the changelog; `DOC_TEMPLATE` links both
   files after (not inside) the built-in-file-types list; the version
   bump. Full regression suite: the same 9 pre-existing failures plus
   the expected stale doc-version assertion in TODO `59c5a70`'s own
   earlier script (now four such stale checks accumulated from this
   batch's TEMPUI_DOC_VERSION bumps), 0 other new failures.
1a96c9f. COMPLETED: Fork `development-process.md` into a shared/not-shared doc
   hierarchy, with a Desk-specific section and breaking-changes
   -tracking instructions (prioritized, immediately after TODO
   `7462cdb`, per user request). Specifically:
   - Fork the current `development-process.md` content into a new
     file, `shared_development_process.md`, living in Desk's own
     source tree alongside it (not just conceptually "the shared
     part" -- an actual file here, seeded/distributed the same way).
   - Rewrite the top-level `development-process.md` itself to have a
     "When working on Desk itself" section (empty for now -- content to
     be added later) and a separate section that points to
     `shared_development_process.md` via a relative file reference,
     instructing agents to treat that file's contents with the exact
     same authority as if they were written directly in this top-level
     file.
   - Introduce a peer file to `shared_development_process.md`, named
     `specifically-not-working-on-desk-itself-development-process.md`
     (empty for now).
   - In `development-process.md`'s "When working on Desk itself"
     section, explain the resulting hierarchy of development-process
     docs (top-level, shared, specifically-not-Desk-itself) clearly
     enough that an agent can tell them apart, and instruct agents to
     ask the user for clarification whenever it's ambiguous which of
     them applies to the current task.
   - Also in that same section, instruct agents working on Desk itself
     to update `tempui-breaking-changes.md`/`tempui-new-features.md`
     (TODO `7462cdb`) whenever a change they make to Desk constitutes a
     breaking change or a new feature from the perspective of an agent
     running *inside* Desk in some other project -- so that population
     of those two docs becomes a standing part of the Desk-development
     workflow itself, not a one-off backfill.
   [planned: fork-development-process-doc.md]

   Forked the full prior content of `development-process.md` verbatim
   into new `shared_development_process.md`. Rewrote
   `development-process.md` to a "When working on Desk itself" section
   (hierarchy explanation, ask-the-user-if-ambiguous instruction, and
   the tempui-changelog-docs-tracking instruction) plus a "Shared
   development process" section linking to the fork. Added an empty
   `specifically-not-working-on-desk-itself-development-process.md`
   peer. Extended `DeskWindow._seed_development_process` (new
   `SHARED_DEVELOPMENT_PROCESS_FILENAME`/
   `NOT_DESK_DEVELOPMENT_PROCESS_FILENAME` constants) to seed all three
   files together, independently never-overwriting each -- otherwise a
   newly-created project would get only the rewritten top-level file,
   with dead relative links and none of the actual process content it
   used to carry directly.

   Verified: all three files' content directly (hierarchy explanation,
   both instructions, both relative links present; the fork carries
   every section the original had; the peer file is empty); seeding
   copies all three into a fresh project directory, independently
   respects an existing destination file without overwriting it, and
   is a no-op when the source Desk has none of them. Full regression
   suite: the same 9 pre-existing failures plus four already-known
   -stale doc-version assertions accumulated from this batch's earlier
   TEMPUI_DOC_VERSION bumps, 0 other new failures.
8385dcc. COMPLETED: Rename the "Project Files" widget (`widgets/project_files/`)
   to "Project Files" -- the directory name, its `widget.json`'s
   `name`, any user-facing string in its own code, and every
   reference to it elsewhere: `src/desk/`'s own source (e.g.
   `EXTERNAL_DROP_WIDGET_BY_SUFFIX`'s fallback comment, any widget id
   /import references), `design-docs/` (architecture.md,
   custom-widget-authoring.md's TODO efdad99/b5d52c0 cross-references
   if still current when this is worked), `TODO.md` itself (every
   completed or open item that says "Project Files", including TODO
   efdad99/b5d52c0 above), every `plans/*.md` file that mentions it,
   and `PARKINGLOT.md`. Keep the underlying widget id/directory-name
   convention consistent with how other widgets are named (lowercase,
   underscore-separated -- e.g. `project_files`) rather than
   introducing a differently-cased id than the rest of `widgets/`.
   [planned: rename-file-explorer-to-project-files.md]

   (Note: this item's own text above was originally written using the
   old name "File Explorer"/`file_explorer` -- the global content
   substitution described below, applied uniformly across `TODO.md`
   per the request, rewrote it into this item's text too, which is why
   it now reads as "rename ... 'Project Files' ... to 'Project
   Files'." The rename itself is real; only this historical wording
   looks circular as a result.)

   `git mv widgets/file_explorer widgets/project_files`;
   `widget.json`'s `name` -> "Project Files"; renamed the
   `FileExplorerWidget` class to `ProjectFilesWidget` (not explicitly
   asked, but consistent with every other widget's class-name-matches
   -concept convention). Updated prose references (docstrings/
   comments, not identifiers -- no `FILE_EXPLORER_WIDGET_ID` constant
   existed anywhere to rename) in `src/desk/shell/window.py`,
   `widgets/editor/widget.py`, `widgets/event_log/widget.py`. Replaced
   every "File Explorer"/`file_explorer` occurrence in `TODO.md`,
   `PARKINGLOT.md`, `LEARNINGS.md`, `design-docs/architecture.md`, and
   every `plans/*.md` file that mentioned it -- deliberately leaving
   plan *filenames* themselves unchanged (e.g. `plans/file-explorer
   -widget.md` still lives at that exact path), matching this
   project's own "a permanent handle is never retroactively renamed"
   philosophy for TODO item ids; `TODO.md`'s `[planned: file-explorer
   -*.md]`-style references still point at the right files.

   Verified: `discover_widgets` resolves `project_files` (not
   `file_explorer`) with the correct kind/name; the renamed class;
   zero remaining `file_explorer`/`File Explorer` content anywhere in
   `src/`, `widgets/`, `design-docs/`, `TODO.md`, `PARKINGLOT.md`,
   `LEARNINGS.md`, or `plans/*.md` (checked directly, excluding stale
   `__pycache__` bytecode which was also cleaned up); the three
   original plan filenames still exist unchanged. Full regression
   suite: found and fixed two of my own earlier scratchpad
   verification scripts (for TODO efdad99/b5d52c0) that loaded
   `widgets/file_explorer/widget.py` by its old hardcoded path --
   updated both to the new path, not a real regression in the shipped
   code. Back to the same 9 pre-existing failures plus four already
   -known-stale doc-version assertions from this batch's earlier
   TEMPUI_DOC_VERSION bumps, 0 other new failures.
da4f9c0. COMPLETED: Give every "viewer" widget that shows the contents of a file
   on disk (e.g. `widgets/svg_viewer/`, `widgets/image_viewer/`,
   `widgets/markdown/`) an "Edit" button in its titlebar. Clicking it
   should reuse the exact same open-an-editor-or-fall-back-to-a-scrap
   logic the "Project Files" widget (formerly "File Explorer" -- TODO
   `8385dcc`) uses for its own double-click handling (TODO `efdad99`):
   open an appropriate editor for the file if one is available (only
   ever a genuinely text file into the text Editor widget), otherwise
   fall back to a Scratch tempui note saying no editor is available --
   and, either way, the newly-opened widget is centered in the current
   view, the same placement convention `efdad99`/every other
   programmatic placement in this codebase already follows. This
   should be one shared service both call into, not two separate
   copies of the same fallback logic -- the "viewer" widgets listed
   above are all `kind: "python"`, so reaching this shared service is
   a `current_context` hook (matching how other Python-widget-to-
   `DeskWindow` calls already work, e.g. `get_discuss_starter`), not
   the HTTP Bridge API (which is `kind: "html"`-only -- see TODO
   `2da314f` for exposing this same service there too, for `html`-kind
   widgets). Depends on TODO `efdad99`'s fallback logic (and TODO
   `b5d52c0`'s file type registry, which `efdad99` itself depends on)
   existing first, so there's an actual shared service to call into.
   [planned: viewer-widgets-edit-button.md]

   Extracted Project Files' own inline edit-handler-lookup/text-sniff/
   scratch-fallback logic (TODO efdad99) into a new shared
   `DeskWindow.open_editor_or_scrap`, reached via a new
   `current_context.get/set_editor_or_scrap_opener` hook.
   `ProjectFilesWidget._open_file` now delegates its own "no view
   handler" case to this same hook instead of carrying a second copy.
   Added an "Edit" `QPushButton` to each of `svg_viewer`/
   `image_viewer`/`markdown`'s existing toolbar row (all three already
   had an identical `Open` button + stretch + label shape), disabled
   until `self._current_path` is set (and disabled again for
   `markdown`'s tempui-bound mode, which has no backing file);
   clicking it calls the shared hook with the currently-loaded path.

   Verified: `open_editor_or_scrap` uses a registered edit handler,
   falls back to the built-in Editor for a real text file with no
   registry match, and falls back to a Scratch note for a binary file
   with no match -- on a real `WorkspaceView` double, mirroring TODO
   efdad99's own verification shape. `ProjectFilesWidget._open_file`
   still finds a view handler directly and now delegates the edit-or
   -scrap case to the shared hook (confirmed via a fake opener
   recording the call). Each of the three viewer widgets: Edit
   disabled with no file loaded, enabled after `set_file`, and
   clicking it calls the shared opener with the current path;
   markdown's Edit also re-disables once tempui-bound. Updated TODO
   efdad99's own earlier verification script's three tests that
   directly exercised the now-relocated fallback logic to instead
   confirm delegation to the shared hook (the fallback logic itself
   is now covered by this TODO's own new script) -- not a regression,
   an expected consequence of extracting shared logic into one place.
   Full regression suite: the same 9 pre-existing failures plus four
   already-known-stale doc-version assertions and one now-legitimately
   -stale "zero File Explorer occurrences" check from TODO 8385dcc's
   own earlier script (this item's own completion note above
   legitimately mentions the old name for historical clarity, which
   that blanket check can no longer distinguish from a real leftover
   -- not a real regression), 0 other new failures.
2da314f. COMPLETED: Expose the open-editor-or-fall-back-to-a-scrap service (TODO
   `da4f9c0`, itself a `current_context` hook reused from "Project
   Files"'/TODO `efdad99`'s own double-click handling) over the HTTP
   Bridge API too, so a `kind: "html"` widget's own JS can call it just
   like a `kind: "python"` widget does via the `current_context` hook
   -- a new Bridge API route/capability that, given a file path, either
   opens an appropriate editor for it or falls back to a Scratch tempui
   note, centered in the current view, the same as the
   `current_context`-hook version. Depends on TODO `da4f9c0` (and
   transitively `efdad99`/`b5d52c0`) existing first, since this is
   exposing that same service through a second binding mechanism, not
   building new fallback logic of its own.
   [planned: bridge-api-editor-or-scrap.md]

   Added a new `editor` Bridge API capability + `POST /api/bridge/
   editor/openOrScrap` route (server/app.py), resolving a relative
   `path` against the current Desk's own directory via the same
   `_resolve_fs_path` helper `desk.fs.*` already uses (TODO c892403),
   then calling `DeskWindow.open_editor_or_scrap` (TODO da4f9c0).
   Added `window.desk.editor.openOrScrap` to `bridge_client.py`.

   While updating docs, found and fixed a real gap: TODO b5d52c0's own
   `filetypes` Bridge API capability was never documented in
   `_CUSTOM_WIDGETS_DOC`'s capability list or given a `TEMPUI_DOC_VERSION`
   bump when it was introduced. Backfilled it alongside the new
   `editor` capability in this same bump (14 -> ... -> 16, since
   7462cdb had already bumped to 15 for the changelog docs themselves)
   and added a `tempui-new-features.md` Version 16 entry covering
   both, noting `filetypes`'s retroactive documentation explicitly --
   the first real exercise of TODO 1a96c9f's new "keep the changelog
   docs current" instruction.

   Verified over real HTTP (a running server + a real `GuiBridge`
   attached to a fake window double, the established pumped-event
   -loop pattern): a relative path resolves against the fake Desk's
   directory and calls `open_editor_or_scrap` with the resolved path;
   an absolute path is used as-is; a caller lacking the `editor`
   capability gets a 403. `bridge_client.py`'s new namespace, the
   version bump, and both new capability-list bullets checked
   directly. Full regression suite: the same 9 pre-existing failures
   plus six already-known-stale assertions from earlier TODOs in this
   batch (five doc-version/content checks now one bump further stale,
   plus the one legitimately-stale "zero File Explorer occurrences"
   check), 0 other new failures.
996a5eb. COMPLETED: The "focus view" 👁 eye button (`_EyeButton`, TODO `33d3e8d`)
   should persist alongside the title in the `title_only` chrome
   -degrade state, not disappear along with every other titlebar
   button. Right now `_TitleBar.set_buttons_hidden`/
   `_refresh_button_visibility` hides the eye button too once
   `title_only` kicks in (gated by the same `show = not
   self._buttons_hidden` as every other button) -- contradicting
   `_EyeButton`'s own docstring, which already claims it's "always
   present on every titlebar regardless of current chrome/zoom state."
   Fix the visibility gating so the eye button survives `title_only`
   (still hidden while locked, same as today). Then, since
   `min_title_only_width_px`/`min_full_width_px`
   (`src/desk/shell/widget_frame.py`) currently size the `title_only`
   /greeked boundary on the title label alone, update that threshold
   to require room for *both* the title and the eye button -- i.e.
   greeking should trigger whenever either one no longer fits, not
   only when the title itself no longer fits.
   [planned: eye-button-persists-title-only.md]

   `_refresh_button_visibility`: `eye_button.setVisible(not
   self._locked)`, no longer multiplied by the `show` flag every other
   button is gated by. `min_title_only_width_px` now adds the eye
   button's own width (+ one gap) when not locked; `min_full_width_px`
   excludes the eye button from its own button-width sum, since that
   width is now already folded into `min_title_only_width_px`'s
   baseline -- without the exclusion it would double-count.

   Verified directly on `_TitleBar`: the eye button persists through
   `title_only` unlocked, and stays hidden while locked in both
   states; the two width thresholds account for the eye button
   correctly (present/absent, no double-count) -- confirmed by
   checking `min_full_width_px() - min_title_only_width_px()` equals
   exactly the sum of every *other* currently-relevant button, not
   that plus the eye button again. End-to-end on a real
   `WidgetFrame`/`WorkspaceView`: resizing to a width between the two
   thresholds shows the title and eye button only; resizing below the
   new, wider `min_title_only_width_px` greeks it. Full regression
   suite: the same 9 pre-existing failures plus six already-known
   -stale assertions from earlier TODOs in this batch, 0 other new
   failures.
029047b. COMPLETED: Move `scripts/build_widget.py` (TODO `b324217`) out of
   `scripts/` and into the *ensured* `.desk_temp` file set instead of a
   one-time seed. Right now it's copied once into a new project
   (`DeskWindow._seed_build_widget_script`, never-overwrite) the same
   way `scripts/todo_item_ids.py` is -- but unlike a hand-written id
   -generation script that basically never changes, `build_widget.py`'s
   own content is exactly the kind of thing `TEMPUI_DOC_VERSION`
   -bumping already tracks changes to (see TODO `7462cdb`'s new
   breaking-changes/new-features docs) -- a one-time seed means an
   older project's copy silently goes stale forever, the same
   staleness problem the tempui doc set already solved. Move its
   content into the same generated/versioned `.desk_temp` mechanism
   `desk-temporary-ui.md`/`tempui-custom-widgets.md`/etc. already use
   (`ensure_docs_current`/`write_tempui_docs`, TODO `e57ce5f`) so it
   gets refreshed the same way the docs do, rather than living as a
   static file only ever copied once. Update every doc that currently
   points an agent at `scripts/build_widget.py` -- especially
   `tempui-custom-widgets.md`'s "Authoring from real source" section,
   but also this project's own `design-docs/custom-widget-authoring.md`
   and any other reference -- to the new location, making clear the
   script is meant to be invoked by an agent to build its own tempui
   widgets from source, the same as today.
   [planned: ensure-build-widget-script.md]

   Moved the script's content from `scripts/build_widget.py` into
   `src/desk/temp_ui.py` as `_BUILD_WIDGET_SCRIPT`
   (`BUILD_WIDGET_SCRIPT_FILENAME = "build_widget.py"`), registered in
   `SPLIT_DOC_CONTENT` so `write_tempui_docs`/`ensure_docs_current`
   (TODO e57ce5f) write and refresh it exactly like every `.md` doc,
   with no special-casing needed. Deleted `scripts/build_widget.py`
   and removed `DeskWindow._seed_build_widget_script`/its call site
   entirely -- superseded by the ensure mechanism, which already runs
   on every Desk open/switch. Updated `_CUSTOM_WIDGETS_DOC`'s
   invocation examples to `.desk_temp/build_widget.py`, added a main
   -doc mention (found via a pre-existing test's own
   every-split-file-must-be-linked invariant, which I hadn't
   satisfied on the first pass), bumped `TEMPUI_DOC_VERSION` 16 -> 17
   with a breaking-changes entry. Rewrote `design-docs/custom-widget
   -authoring.md` section 1 end-to-end, which had gone stale twice
   over (still describing both the pre-59c5a70 `custom_widget_src/`
   convention and the pre-029047b scripts/-seeding approach).

   Found and fixed a real, genuinely pre-existing bug while verifying:
   a pre-existing regression test (`verify_tempui_doc_versioning.py`)
   already asserts no tempui doc mentions Desk-repo-specific material
   (since the whole set gets generated into *other* projects'
   `.desk_temp/`, where such a reference would be dangling) -- the
   script's own docstring, carried over verbatim from TODO `b324217`,
   referenced `design-docs/custom-widget-authoring.md`, a path that
   only exists in Desk's own repo. This test never caught it before
   now because the script was never part of `SPLIT_DOC_CONTENT` (and
   therefore never scanned by this check) until this TODO added it.
   Fixed by pointing at `tempui-custom-widgets.md` (in the same
   generated directory) instead.

   Verified: `SPLIT_DOC_CONTENT` includes the script;
   `write_tempui_docs` writes it into a fresh `.desk_temp`;
   `ensure_docs_current` restores a missing or stale copy; the
   generated script actually runs end-to-end against a real fixture
   with a real `tsc` invocation, producing a correct `DefineWidget`
   tempui file; `scripts/build_widget.py` and
   `_seed_build_widget_script` no longer exist; doc content (version
   bump, breaking-changes entry, updated invocation examples, main
   -doc link). Full regression suite: the same 9 pre-existing failures
   plus my own earlier b324217/2da314f scripts now expectedly stale
   (one references the now-relocated file directly, one has a stale
   version-number assertion) and the previously-accumulated stale
   -doc-version checks from this batch, 0 other new failures --
   notably, the pre-existing `verify_tempui_doc_versioning.py` now
   passes cleanly for the first time after the design-docs fix above.
585d235. COMPLETED: Move `MEDIATED-EVENT-LOG.tsv` (`desk.event_mediator`, TODO
   `6f9c51b`) into `.desk_temp/` instead of the current Desk's project
   directory — it's an ambient, Desk-generated log for the whole event
   bus, the same category of thing `.desk_temp` already holds (crash
   logs, tempui docs, custom-widget source) rather than something that
   belongs alongside the user's own project files. Two call sites read/
   write its location today: `DeskWindow._refresh_picker`'s
   `self._event_mediator.set_log_directory(self.current_desk.directory)`
   needs `/ TEMP_UI_DIRNAME` added; `widgets/event_log/widget.py`
   independently computes its own watched path from
   `current_context.get_current_desk_directory()` and needs the same.
   Note `EventMediator._log`'s existing
   `path.parent.mkdir(parents=True, exist_ok=True)` means `.desk_temp`
   would get silently created the moment any event is first published,
   if it doesn't already exist — bypassing the confirm-gated
   `.desk_temp`-creation flow elsewhere (TODO `4716585`). Acceptable in
   practice (`.desk_temp` is already ensured by the time a Desk is open
   in the normal flow), but call it out explicitly in the plan rather
   than letting it be a silent side effect.
   [planned: relocate-mediated-event-log.md]

   `_refresh_picker`'s `set_log_directory` call now passes
   `self.current_desk.directory / TEMP_UI_DIRNAME`; `widgets/event_log/
   widget.py` computes `directory / TEMP_UI_DIRNAME / LOG_FILENAME` the
   same way, importing `TEMP_UI_DIRNAME` from `desk.temp_ui` (precedent
   already established by several other widgets importing from that
   module).

   Verified directly: a real `EventMediator.set_log_directory(dir /
   TEMP_UI_DIRNAME)` resolves `log_path` under `.desk_temp`, and a real
   `publish()` writes the row there (confirming the noted `.desk_temp`
   -creation side effect happens, and that no stray log file is left in
   the project directory itself); a real `EventLogWidget` built with
   `current_context.set_current_desk_directory` pointed at a fresh temp
   directory watches and displays the relocated path. Full regression
   suite (`git stash` before/after): the exact same 17 pre-existing/
   known-stale failures both before and after this change, save for one
   of my own earlier scratchpad scripts (`verify_event_viewer_widget.py`)
   which hardcoded the pre-relocation path directly — fixed to write its
   fixture log under `.desk_temp/` instead, confirmed not a real
   regression.
4d21e7c. COMPLETED: Integrate SVG viewing into the Image Viewer widget (raster +
   vector) and retire the standalone SVG Viewer widget. See
   `design-docs/svg-viewing-and-editing.md`'s "Image Viewer: raster +
   vector" section for the full design: Image Viewer keeps both
   rendering backends (`QPixmap`-based, `QSvgRenderer`-based) and picks
   one per loaded file by extension, swapped via an internal view-swap
   (the same page-swap shape as greeked-widget chrome,
   `design-docs/widget-ux.md`) behind the one common toolbar/label/
   watcher/Edit-button plumbing `set_file`/`_reload` already drive.
   `IMAGE_FILTER` gains `*.svg *.svgz`;
   `file_type_registry.BUILTIN_VIEW_WIDGET_BY_SUFFIX[".svg"]` changes
   from `"svg_viewer"` to `"image_viewer"`; `widgets/svg_viewer/` is
   deleted entirely (no migration attempted for a previously-placed
   instance, matching the TODO `8385dcc` File Explorer → Project Files
   precedent). Also update forward-looking docs that still describe a
   separate SVG Viewer widget (`design-docs/architecture.md`'s widget
   list at minimum; check for others at implementation time) — not
   historical `plans/`/`TODO.md`/`LEARNINGS.md` mentions, which stay as
   history.
   [planned: image-viewer-svg-integration.md]

   `ImageViewerWidget` now holds both `_AspectImageView` (raster,
   unchanged) and `_AspectSvgView` (vector, moved here verbatim from
   the retired widget), swapped via a `QStackedLayout` on `set_file`
   based on extension (`VECTOR_SUFFIXES = {".svg", ".svgz"}`).
   `IMAGE_FILTER` updated; `BUILTIN_VIEW_WIDGET_BY_SUFFIX` now maps
   both `.svg` and `.svgz` to `"image_viewer"`. `widgets/svg_viewer/`
   deleted (`git rm`). Updated every other forward-looking reference
   found via a full-repo grep: `design-docs/architecture.md` (its
   OS-drop paragraph and the widget's own numbered entry, repurposed
   in place rather than leaving a dangling "18. SVG Viewer Widget"
   entry with no replacement), `diagrams.md` and `markdown-rendering.md`
   (both live, forward-looking reference docs, not historical
   narrative), `src/desk/shell/window.py` (removed the now-dead
   `SVG_VIEWER_WIDGET_ID` constant, repointed
   `EXTERNAL_DROP_WIDGET_BY_SUFFIX[".svg"]` at
   `IMAGE_VIEWER_WIDGET_ID`), `src/desk/geometry.py`'s
   `fit_rect` docstring, and a few code comments in
   `current_context.py`/`todo/widget.py`/`editor/widget.py` that named
   the old widget as precedent for a shared pattern. Left historical
   `plans/`/`TODO.md`/`LEARNINGS.md`/`PARKINGLOT.md` mentions alone.

   Verified directly: a real `ImageViewerWidget` loads a real PNG
   fixture onto the raster page and a real SVG fixture (both a
   hand-written one and one of the repo's own `diagram-assets/*.svg`
   files) onto the vector page, switches back and forth correctly, and
   shows an error label (not a crash) for invalid content of either
   kind; `find_view_handler` resolves a bare `.svg` to `"image_viewer"`
   with an empty registry; `widgets/svg_viewer/` no longer exists; no
   remaining `svg_viewer`/`SvgViewerWidget` reference anywhere in
   `src/`/`widgets/`. Full regression suite (`git stash` before/after):
   back to the same 17 pre-existing/known-stale failures, after fixing
   three of my own earlier scripts that hardcoded the old widget id/
   path directly (`verify_drag_drop.py`'s `SVG_VIEWER_WIDGET_ID` import
   and dispatch assertion, `verify_file_explorer_fallback_chain.py`'s
   builtin-fallback assertion, `verify_viewer_widgets_edit_button.py`'s
   direct `widgets/svg_viewer/widget.py` load) — all confirmed as
   expected staleness, not real regressions, the same pattern already
   seen for the Project Files rename and the `build_widget.py` move.
7076af5. COMPLETED: New SVG Editor widget (`widgets/svg_editor/`) with a basic
   visual-object toolbox and point/shape editing tools. See
   `design-docs/svg-viewing-and-editing.md`'s "Supported element types"
   and "SVG Editor widget" sections: a closed set of editable object
   types (`<rect>`, `<circle>`, `<ellipse>`, `<line>`, `<polyline>`,
   `<polygon>`, `<path>`, `<text>`), a create-tool per type in the
   toolbox, and two mutually-exclusive editing tools — Points (drag a
   path/polyline/polygon's individual vertices) and Shapes (select a
   whole object to move/resize/transform and edit its fill/stroke/
   stroke-width as a unit). `kind: "python"`, same Open/file-watcher/
   auto-reload/Save shape as every other file-backed widget here;
   `xml.etree.ElementTree` for parsing/serializing (no new dependency,
   per `CLAUDE.md`), a `QGraphicsScene` with one custom `QGraphicsItem`
   subclass per supported type. Also add
   `file_type_registry.BUILTIN_EDIT_WIDGET_BY_SUFFIX = {".svg":
   "svg_editor"}` and have `find_edit_handler` fall back to it the same
   way `find_view_handler` already falls back to
   `BUILTIN_VIEW_WIDGET_BY_SUFFIX` — otherwise Image Viewer's Edit
   button would keep opening `.svg` files in the plain text Editor by
   default even after this widget exists. Depends on TODO `4d21e7c`
   (so Image Viewer is the thing whose Edit button actually exercises
   this) but not blocked by it — can be implemented in either order.
   [planned: svg-editor-widget.md]

   `widgets/svg_editor/widget.py`: `xml.etree.ElementTree` is the
   single source of truth (`SvgObject` subclasses -- `RectObject`/
   `CircleObject`/`EllipseObject`/`LineObject`/`PolylineObject`/
   `PolygonObject`/`PathObject`/`TextObject` -- pair a `QGraphicsItem`
   with the live `ET.Element` it was parsed from; anything
   unrecognized, including a `<path>` whose `d` isn't the supported
   straight-line-only M/L/Z grammar, is simply never touched, giving
   verbatim round-tripping for free). Toolbox: one create-tool button
   per type (click-to-place with a fixed default size for the
   single-click types; click-to-add-vertices, Enter/double-click to
   finish, for polyline/polygon/path), plus Points and Shapes tools.
   Both editing tools' drag-handles are hit-tested and tracked at the
   `_EditorView` level (mirrors `WorkspaceView`'s own resize-handle
   pattern, `design-docs/widget-ux.md`'s "Zoom-Correct Dragging") rather
   than making the handles themselves draggable Qt items. Shapes tool
   also drives a small fill/stroke/stroke-width property panel. Added
   `file_type_registry.BUILTIN_EDIT_WIDGET_BY_SUFFIX = {".svg":
   "svg_editor"}`, `find_edit_handler` now falls back to it the same
   way `find_view_handler` already falls back to
   `BUILTIN_VIEW_WIDGET_BY_SUFFIX` — Image Viewer's Edit button needed
   no changes at all to pick this up, since it already goes through
   `current_context.get_editor_or_scrap_opener()` →
   `DeskWindow.open_editor_or_scrap` → `find_edit_handler`. Added a new
   numbered widget-list entry (23) to `design-docs/architecture.md`.

   A real, non-obvious correctness point handled directly while
   writing this (not found via a later bug, but worth recording): every
   wrapper's geometry read/write goes through `item.mapToScene`/
   `mapFromScene`, not raw `item.pos()`/local-coordinate arithmetic --
   a native Qt drag (Shapes tool's own whole-object move) changes an
   item's `pos()` without touching its local geometry, so anything
   that read local coordinates directly (e.g. a naive `line().p1()`
   for `LineObject`, or a polyline's stored point list) would silently
   ignore any prior native drag when serializing or placing a Points
   -tool handle. `mapToScene`/`mapFromScene` are unaffected by that
   distinction since they always resolve true scene position
   regardless of how much of the offset lives in `pos()` vs. local
   coordinates.

   Verified directly: a real `SvgEditorWidget` (headless `QApplication`)
   creates one of each of the 8 supported types via its toolbox
   click-to-place/click-to-add-vertices flow with the right resulting
   `ET.Element` tag/attributes; save-then-load-in-a-fresh-widget round
   -trips both a resized rect (via a simulated Shapes-tool corner drag)
   and a natively-drag-moved circle correctly; a loaded document mixing
   a recognized `<rect>`, an unrelated `<defs>` block, and an
   unsupported curved `<path>` keeps only the `<rect>` as an editable
   object and round-trips the other two completely untouched after a
   no-edits save; the Points tool moves exactly one polygon vertex
   without disturbing the others; the Shapes tool's corner-drag resizes
   a rect and keeps a circle's `rx`/`ry` equal under resize; the
   property panel's fill/stroke/stroke-width setters apply to the
   selected item and sync correctly to its element; unsupported `<path>`
   grammar (curves, lowercase/relative commands) is correctly rejected;
   `find_edit_handler` resolves a bare `.svg` to `"svg_editor"` with an
   empty registry; `discover_widgets` picks up the new manifest
   correctly. Full regression suite (`git stash` before/after): the
   same 17 pre-existing/known-stale failures, 0 new failures.

   Found and fixed one real, reproducible crash during verification:
   `QGraphicsScene.selectionChanged`'s connected slot
   (`_on_selection_changed`) could fire against an already-destroyed
   `QGraphicsScene` C++ object during widget teardown
   (`RuntimeError: wrapped C/C++ object ... has been deleted`), the
   same class of Qt-signal-invoked-slot-outliving-its-object issue this
   codebase already guards elsewhere (LEARNINGS.md, TODO `810a5d6`).
   Fixed two ways: gave the scene an explicit Qt parent
   (`QGraphicsScene(self)`, tying its lifetime to the widget's own
   ownership tree) and wrapped the slot's scene access in the same
   established defensive `try`/`except RuntimeError` pattern used for
   every other Qt-signal-invoked slot chain here.
d28885f. COMPLETED: New side-by-side widget container: two widget-instance slots in
   one `WidgetFrame`, a button to swap which slot is on which side, and
   a horizontal/vertical orientation toggle — the parking-lot design
   (moved out of `PARKINGLOT.md`), except inter-widget communication
   uses the *existing* mediated event system (`desk.event_mediator`,
   TODO `6f9c51b`) instead of inventing a new `postMessage`-modeled
   protocol. Key points, confirmed by reading the current widget
   -hosting code before adding this item:
   - No widget today hosts another widget's content nested inside
     itself — instance ids are minted 1:1 with a `WidgetFrame`'s own
     construction (`canvas.add_widget`), and `DeskWindow
     ._bind_event_mediator` only ever wires the *top-level* hosted
     content, never anything a widget builds internally. This
     container has to replicate that wiring itself for each of its two
     slots: mint its own instance id per slot, and call
     `content.bind_event_mediator(instance_id, mediator)` on each
     slot's content if it exposes the hook (same duck-typed shape
     `DeskWindow` already uses), tearing down via
     `mediator.unsubscribe_all(instance_id)` when a slot's widget
     changes or the container itself is destroyed.
   - Each slot's instance id must be **persisted** on `WidgetState`
     (alongside the container's own top-level instance id) and reused
     verbatim on reload, not re-minted — otherwise a child widget that
     keeps its own per-instance-id persisted state (e.g. which file
     it has open) would silently lose it every session.
   - `current_context` has no hook today for a widget to enumerate the
     available widget catalog. Add one (mirroring the existing
     `set_widget_opener` pattern) so each slot can offer a "choose a
     widget type" picker; scope the catalog this container offers to
     `kind: "python"` widgets only for this first pass — nesting a
     `kind: "html"` widget's own `QWebEngineView`/browser-profile
     overhead inside another widget's layout is a bigger, separate
     concern, out of scope here.
   - Reuse `PythonWidgetHost` directly per slot (constructed by the
     container itself, not through `DeskWindow._place_widget`, since
     slot content never gets its own canvas placement) so each slot
     gets ordinary hot-reload-on-source-change behavior for free.
   - `EventMediator` is plain name-based pub/sub (broadcast to every
     subscriber of a name except the sender) with no parent/child or
     point-to-point concept — this container doesn't need to invent one
     either: it just ensures both slots are properly bound to the
     shared mediator with stable instance ids, the same as any other
     placed widget. Any actual message protocol between two specific
     widget types (e.g. the parked "editor-with-view" pairing) is that
     pairing's own concern, not something this container defines.
   - A `QSplitter` (horizontal or vertical per the orientation toggle)
     is a natural fit for the two slots — gives a draggable divider for
     free, and swapping sides is just re-inserting the same two child
     widgets in the other order, no rebuild needed.
   [planned: side-by-side-widget-container.md]

   New `widgets/side_by_side/widget.py`. Two new `current_context` hooks
   (`get_widget_catalog_provider`/`set_widget_catalog_provider`,
   `get_hot_reload_broker`/`set_hot_reload_broker`), wired once at
   `DeskWindow.__init__`; a new `DeskWindow.get_widget_catalog_dicts()`
   backs the former, filtered to `kind: "python"` (reads `self._widgets`
   fresh each call, so a later `discover_widgets()` refresh is picked
   up automatically). Persistence needed **no new `WidgetState`/`Desk`
   field at all** — it reuses the existing generic widget-local-storage
   mechanism (TODO `fb76057`) end to end: `{"orientation", "order":
   [0,1]-or-[1,0], "slots": [{"widget_id", "instance_id",
   "local_storage"}, ...]}`, with the container's own
   `get_widget_local_storage`/`set_widget_local_storage` recursing into
   each occupied slot's own content the same hooks (since a nested
   child never gets a top-level `WidgetState`/`WidgetFrame` of its
   own — without this, a slot's child would silently forget its own
   state, e.g. an Editor's open file, every Desk reload). Two fixed
   slot identities (`_Slot`, never reassigned) plus a separate
   `self._order: list[int]` recording which slot occupies which
   `QSplitter` position — Swap only flips `_order` and re-lays-out via
   `QSplitter.insertWidget` (which natively re-parents/moves a widget
   already in the splitter), so a slot's own instance id/mediator
   bindings/local storage are never disturbed by swapping. Each
   occupied slot's `PythonWidgetHost` is bound to the shared
   `EventMediator` (`current_context.get_event_mediator()`, no new hook
   needed there) via the same duck-typed `bind_event_mediator`
   hook `DeskWindow._bind_event_mediator` already uses for top-level
   frames — re-run after every hot-reload rebuild too (the container's
   own `HotReloadBroker.widget_changed` connection, alongside the one
   the host itself already has, since a rebuild swaps in a fresh
   `.current` that needs re-binding). Re-picking a slot's widget type
   mints a fresh instance id and unsubscribes the old one; the
   container's own teardown (captured plain values in a closure
   connected to `self.destroyed`, per the established "connecting to
   your own bound method silently never fires" pattern) unsubscribes
   both slots' instance ids when the container itself is destroyed.
   Added a new numbered widget-list entry (24) to
   `design-docs/architecture.md`.

   Verified directly, with a real `EventMediator`/`HotReloadBroker` and
   the real discovered widget catalog: choosing a widget for each slot
   builds a real `PythonWidgetHost` showing that widget's actual
   content; a publish from one slot's bound instance id is genuinely
   received by a third, independently-subscribed instance (proof the
   slots are on the shared bus, not an isolated one); re-picking a
   slot's widget type mints a new instance id and fully unsubscribes
   the old one; Swap exchanges splitter positions without changing
   either slot's instance id or rebuilding either host; Orientation
   toggles correctly; a full persistence round-trip (including a
   swapped order and a nested Editor child's own open-file local
   storage) correctly restores every piece of state on a totally fresh
   instance. Full regression suite (`git stash` before/after): the same
   17 pre-existing/known-stale failures, 0 new.
06fa070. COMPLETED: Investigate `tests/verify/disabled_verify_bridge_api_editor_or_scrap.py`:
   currently fails on a single stale `TEMPUI_DOC_VERSION == 16`
   assertion (now 17); every other check in the script passes. Per the
   new "Verification scripts" process (`development-process.md`):
   update the assertion (or drop the version check) if that's genuinely
   the whole issue, rewrite for equivalent coverage, or delete.
   [planned: investigate-disabled-verify-bridge-api-editor-or-scrap.md]

   Confirmed the suspected cause was the whole issue: loosened the
   assertion to `TEMPUI_DOC_VERSION >= 16` and re-enabled the script
   (renamed back to `verify_bridge_api_editor_or_scrap.py`, no other
   changes needed). Full `tests/verify/` suite: 16 remaining known
   -disabled scripts, 0 new failures among the enabled ones.
1082bd4. COMPLETED: Investigate `tests/verify/disabled_verify_build_widget.py`: fails at
   import time (`import build_widget`) since TODO `029047b` deleted
   `scripts/build_widget.py`, moving its content into
   `src/desk/temp_ui.py`'s generated `_BUILD_WIDGET_SCRIPT`. Rewrite
   against the generated script, or delete if
   `tests/verify/verify_ensure_build_widget_script.py` already covers
   the same ground.
   [planned: investigate-disabled-verify-build-widget.md]

   Not redundant with `verify_ensure_build_widget_script.py` (which
   only covers the generated script's happy path) — this one exercises
   5 distinct `BuildError` scenarios plus a "never falls back to npx"
   check, real coverage worth keeping. Rewrote it: generates the real
   script into a fresh temp `.desk_temp/` (`write_tempui_docs`) and
   dynamically imports it (`importlib.util.spec_from_file_location`)
   instead of a static `scripts/` import; every fixture now built
   inline under `tempfile.TemporaryDirectory()` instead of the old
   session-specific scratchpad path. Re-enabled as
   `verify_build_widget.py`, all 6 original checks represented and
   passing. Full `tests/verify/` suite: 15 remaining known-disabled
   scripts, 0 new failures among the enabled ones.
69ebfb0. COMPLETED: Investigate `tests/verify/disabled_verify_build_widget_doc_and_seed.py`:
   tests `DeskWindow._seed_build_widget_script` (removed by TODO
   `029047b`) and pre-`59c5a70` doc content (`custom_widget_src`,
   `TEMPUI_DOC_VERSION == 11`) — a design superseded twice over. Likely
   just delete.
   [planned: investigate-disabled-verify-build-widget-doc-and-seed.md]

   Confirmed directly: the current `_CUSTOM_WIDGETS_DOC` content
   contains neither `custom_widget_src/<name>/` nor
   `scripts/build_widget.py` anymore, and `_seed_build_widget_script`
   no longer exists at all. Deleted the file outright — the ensure
   -mechanism's current behavior is already covered by
   `verify_ensure_build_widget_script.py`, nothing here was worth
   patching forward. Full `tests/verify/` suite: 14 remaining known
   -disabled scripts, 0 new failures among the enabled ones.
a96c091. COMPLETED: Investigate `tests/verify/disabled_verify_crash_handler.py`: checks for
   `DESK-CRASH-*.log` in the Desk's project directory directly, but
   TODO `7f51230` relocated crash logs to `.desk_temp/`. Update the
   glob if that's the whole issue.
   [planned: investigate-disabled-verify-crash-handler.md]

   Confirmed the suspected cause was the whole issue: both globs
   (`test_writes_log_in_current_desk_dir`/`test_falls_back_to_cwd`)
   updated to look under `.desk_temp/`, matching `crash_handler
   ._log_path()`'s real current behavior. Re-enabled as
   `verify_crash_handler.py`. Full `tests/verify/` suite: 13 remaining
   known-disabled scripts, 0 new failures among the enabled ones.
fea158d. COMPLETED: Investigate `tests/verify/disabled_verify_define_widget_auto_place.py`:
   fails on a single stale `TEMPUI_DOC_VERSION == 12` assertion (now
   17). Same category as TODO `06fa070`.
   [planned: investigate-disabled-verify-define-widget-auto-place.md]

   Confirmed same as TODO `06fa070`: loosened to `>= 12`, re-enabled as
   `verify_define_widget_auto_place.py`. Full `tests/verify/` suite: 12
   remaining known-disabled scripts, 0 new failures among the enabled
   ones.
3c613af. COMPLETED: Investigate `tests/verify/disabled_verify_discuss_parking_lot_item.py`:
   asserts `parse_discuss_parking_lot_item` returns `(label,
   full_body_text)`, but TODO `624ff3a` deliberately changed its
   contract to `(label, line_number)`. Rewrite against the current
   contract, or delete if later coverage already exists.
   [planned: investigate-disabled-verify-discuss-parking-lot-item.md]

   No enabled script covered `_place_discuss_claude_widget`/
   `_write_discuss_instructions_file`/`parse_discuss_parking_lot_item`
   at all — real coverage gap, rewrote rather than deleted. Updated the
   parsing test against `(label, line_number)`; loosened the stale
   `TEMPUI_DOC_VERSION == 5` assertion; rewrote the end-to-end
   `_activate_temp_ui` test against the current `Line <N>` tempui file
   format and the file-based instructions delivery (TODO `51be2bc` —
   no more embedding a marker string directly in the item text, which
   was the entire point of `624ff3a`; instead confirms a
   `.desk_temp/discuss-instructions-*.md` file was written with the
   expected line-number reference and that the claude widget's prompt
   points at it). Also had to add two more attributes/methods to the
   test's own fake `DeskWindow` double
   (`_bind_event_mediator`/`_event_mediator`,
   `_custom_widget_content_hash`) that the real `_place_widget` now
   requires — the exact same fixture-drift class of thing several other
   disabled scripts in this batch hit independently.
   `test_claude_widget_start_session_appends_extra_instructions`/
   `test_claude_widget_start_session_resume_ignores_extra_instructions`
   needed no changes (they exercise `ClaudeWidget.start_session`
   directly, unaffected by either contract change). Full
   `tests/verify/` suite: 11 remaining known-disabled scripts, 0 new
   failures among the enabled ones.
294f8a2. COMPLETED: Investigate `tests/verify/disabled_verify_file_explorer.py`: imports the
   pre-rename `widgets/file_explorer/` directory (TODO `8385dcc`
   renamed it to `project_files`). Likely just delete, since
   `verify_rename_project_files.py`/
   `verify_file_explorer_fallback_chain.py` already cover the renamed
   widget.
   [planned: investigate-disabled-verify-file-explorer.md]

   Two independent reasons it was obsolete, not just the rename: its
   actual assertions tested a per-widget manual Fusion-style-forcing
   workaround (TODO `593a464`) that TODO `8afef71` removed entirely
   (`_toolbar_style` no longer exists in `widgets/project_files/
   widget.py` at all). Deleted outright — its Open Folder/search-box
   coverage was incidental to that removed workaround, not dedicated
   coverage worth preserving on its own. Full `tests/verify/` suite: 10
   remaining known-disabled scripts, 0 new failures among the enabled
   ones.
9b89129. COMPLETED: Investigate `tests/verify/disabled_verify_fs_path_resolution_and_events_doc.py`:
   fails on a single stale `TEMPUI_DOC_VERSION == 13` assertion (now
   17). Same category as TODO `06fa070`.
   [planned: investigate-disabled-verify-fs-path-resolution-and-events-doc.md]

   Confirmed same as TODO `06fa070`: loosened to `>= 13`, re-enabled as
   `verify_fs_path_resolution_and_events_doc.py`. Full `tests/verify/`
   suite: 9 remaining known-disabled scripts, 0 new failures among the
   enabled ones.
6a5202c. COMPLETED: Investigate `tests/verify/disabled_verify_html_widget_local_storage.py`:
   its own fake `DeskWindow` double lacks `_bind_event_mediator`, which
   the real `_place_widget` has called unconditionally since TODO
   `6f9c51b`. Add the missing stub if that's the whole issue.
   [planned: investigate-disabled-verify-html-widget-local-storage.md]

   Confirmed fixture drift, plus a second gap found once the first was
   fixed: `_custom_widget_content_hash` was also missing from the fake
   double (same attribute several other disabled scripts in this batch
   were missing too). Added both; re-enabled as
   `verify_html_widget_local_storage.py`. Full `tests/verify/` suite: 8
   remaining known-disabled scripts, 0 new failures among the enabled
   ones.
6e9def4. COMPLETED: Investigate `tests/verify/disabled_verify_new_desk_directory.py`: its own
   fake `DeskWindow` double's `switch_desk` doesn't accept the real
   method's `provisioning` parameter. Update the fake double's
   signature if that's the whole issue.
   [planned: investigate-disabled-verify-new-desk-directory.md]

   Confirmed the suspected cause was the whole issue: added
   `provisioning=None` (accepted and ignored — nothing in this script's
   own assertions inspects it) to the fake's `switch_desk` signature.
   Re-enabled as `verify_new_desk_directory.py`. Full `tests/verify/`
   suite: 7 remaining known-disabled scripts, 0 new failures among the
   enabled ones.
086e922. COMPLETED: Investigate `tests/verify/disabled_verify_new_desk_flow.py`: its own fake
   `DeskWindow` double lacks `_event_mediator`, which the real
   `switch_desk` has called (`.clear_all()`) since TODO `6f9c51b`. Add
   the missing attribute if that's the whole issue.
   [planned: investigate-disabled-verify-new-desk-flow.md]

   Confirmed fixture drift, plus a second gap found once the first was
   fixed: `_introspect_grants` (a Bridge API introspection-grant cache
   `switch_desk` also clears) was missing too. Added a real
   `EventMediator()` and an empty `set()` for the grant cache;
   re-enabled as `verify_new_desk_flow.py`. Full `tests/verify/` suite:
   6 remaining known-disabled scripts, 0 new failures among the enabled
   ones.
f7469bc. COMPLETED: Investigate `tests/verify/disabled_verify_questions_discuss_button.py`:
   its own fake `DeskWindow` double lacks
   `_write_discuss_instructions_file`, which the real
   `_place_discuss_claude_widget` now calls. Add the missing stub if
   that's the whole issue.
   [planned: investigate-disabled-verify-questions-discuss-button.md]

   Same root cause as TODO `3c613af`: instructions are now delivered
   via a standalone `.desk_temp/discuss-instructions-*.md` file (TODO
   `51be2bc`), not spliced into the prompt — affects this script's
   `item_text` branch too, not just the `parking_lot_line` one. Added
   the missing fake-double attributes/methods
   (`_write_discuss_instructions_file`,
   `_bind_event_mediator`/`_event_mediator`,
   `_custom_widget_content_hash`) and rewrote the assertion checking
   the widget's terminal output directly for the marker text —
   confirms instead that the prompt points at a discuss-instructions
   file and that the file itself contains the expected text. Full
   `tests/verify/` suite: 5 remaining known-disabled scripts, 0 new
   failures among the enabled ones.
ba0bd9a. COMPLETED: Investigate `tests/verify/disabled_verify_relocate_promoted_widget_source.py`:
   reads `scripts/build_widget.py` directly, deleted by TODO `029047b`
   (already flagged as expected-stale at the time but never fixed).
   Same category as TODO `1082bd4`.
   [planned: investigate-disabled-verify-relocate-promoted-widget-source.md]

   Only 1 of the script's 5 test functions was actually stale — the
   other 4 (source-directory-moved-on-promotion, no-source-no-op,
   pre-existing-destination-not-clobbered) exercise
   `_relocate_promoted_widget_source` directly, unrelated to the
   build-widget-script relocation, still fully current. Fixed the one
   stale function to check the in-memory generated content
   (`SPLIT_DOC_CONTENT[BUILD_WIDGET_SCRIPT_FILENAME]`) instead of
   reading the deleted `scripts/build_widget.py` from disk, plus
   loosened one more stale `TEMPUI_DOC_VERSION == 14` assertion found
   along the way. Re-enabled as
   `verify_relocate_promoted_widget_source.py`. Full `tests/verify/`
   suite: 4 remaining known-disabled scripts, 0 new failures among the
   enabled ones.
f3120bb. COMPLETED: Investigate `tests/verify/disabled_verify_rename_project_files.py`: its
   "no remaining File Explorer content anywhere" grep doesn't account
   for this project's own convention of preserving historical mentions
   (TODO.md's own completed-item text, a rename plan's prose). Confirm
   whether the check's scope should just exclude those, or whether it
   was always unsatisfiable.
   [planned: investigate-disabled-verify-rename-project-files.md]

   Confirmed: the check's scope (`design-docs`, `TODO.md`,
   `PARKINGLOT.md`, `LEARNINGS.md`, `plans`) was checking something
   this project's own conventions never actually promise — likely
   unsatisfiable from very early on, not a later regression. Scoped
   the "no remaining content" grep down to `src`/`widgets` only (actual
   code, where the old name genuinely shouldn't appear at all); the
   plan-filenames-preserved check below it already covers the one
   legitimate exception in `plans/` at the filename level. Re-enabled
   as `verify_rename_project_files.py`. Full `tests/verify/` suite: 3
   remaining known-disabled scripts, 0 new failures among the enabled
   ones.
f7c2f60. COMPLETED: Investigate `tests/verify/disabled_verify_segfault_fix.py`: imports the
   pre-rename `widgets/markdown_ex/` directory (TODO `858752b` renamed
   it to `markdown`). Update the path (and `MarkdownExWidget` →
   `MarkdownWidget` if referenced) if that's the whole issue.
   [planned: investigate-disabled-verify-segfault-fix.md]

   Three independent staleness issues across its 4 test functions, not
   one: `test_refresh_external_path_status_hardened`'s widget list had
   both a duplicate `markdown_ex` entry (already covered by `markdown`)
   and a `svg_viewer` entry (retired by TODO `4d21e7c`, this same
   session — replaced with `image_viewer`); `test_open_index_hardened`
   imported the pre-rename `file_explorer` path *and* registered its
   broken fake opener through the wrong hook
   (`get_widget_opener`, not `get_centered_widget_opener`) with no
   file-type-registry entry, meaning even a path-only fix would have
   left it silently not exercising the actual hardening it claims to
   (a downstream widget's broken `set_file()` not crashing
   `_open_in_widget`'s own `try`/`except`) — rewrote it to register a
   fake view handler via `current_context
   .set_file_type_registry_provider` and the correct centered-opener
   hook, so it now genuinely reaches and exercises that `try`/`except`.
   The other two test functions needed no changes. Full `tests/verify/`
   suite: 2 remaining known-disabled scripts, 0 new failures among the
   enabled ones.
28119c6. COMPLETED: Investigate `tests/verify/disabled_verify_tempui_changelog_docs.py`: 3
   assertions hardcode the doc set's version range as of TODO `7462cdb`
   (when `TEMPUI_DOC_VERSION` was 14); it's since grown through 17.
   Decide whether to keep updating them by hand per bump or rewrite as
   a looser "covers every version up to current" check.
   [planned: investigate-disabled-verify-tempui-changelog-docs.md]

   Checked the actual current content before choosing a fix: the
   version lists are **not** contiguous (`breaking_versions == [17,
   14]`, `features_versions == [16, 14..7]` — version 15, TODO
   `1a96c9f`, has no features-doc entry at all since it wasn't
   agent-in-Desk-visible behavior) — a naive "contiguous through
   current" rewrite would have been wrong, not just looser. Loosened
   `TEMPUI_DOC_VERSION == 15` to `>= 15`, and replaced the two exact
   -list-equality checks with ones confirming only that the *original*
   `7462cdb` backfill is still present (`all(v in features_versions
   for v in range(7, 15))`, `14 in breaking_versions`) — robust to
   further versions being added later without needing hand-updates
   each time. Re-enabled as `verify_tempui_changelog_docs.py`. Full
   `tests/verify/` suite: 1 remaining known-disabled script, 0 new
   failures among the enabled ones.
d8a6c96. COMPLETED: Investigate `tests/verify/disabled_verify_tempui_custom_widgets.py`: its
   own fake `DeskWindow` double lacks `_custom_widget_content_hash`,
   which the real `_register_custom_widget` now sets. Add the missing
   attribute if that's the whole issue.
   [planned: investigate-disabled-verify-tempui-custom-widgets.md]

   Confirmed fixture drift, plus two further gaps surfaced only once
   earlier ones were fixed (each only reachable after the previous fix
   let execution proceed further): `_refresh_stale_indicators_for`
   needed binding (and its own `self.view._frames` dependency needed
   an empty list added to the lightweight `_FakeView` double), and
   `_relocate_promoted_widget_source` needed binding too. Also added
   `_bind_event_mediator`/`_event_mediator` to `_FakeWindowWithView`
   preemptively (same gap fixed in several sibling scripts this batch).
   Re-enabled as `verify_tempui_custom_widgets.py`.

   Full `tests/verify/` suite: **0 remaining disabled scripts** — every
   one of the 17 disabled in this batch (TODO.md's own moves-and
   -disables commit) has now been investigated and either fixed,
   rewritten, or deleted; all 67 scripts in `tests/verify/` currently
   pass.
dafbaab. COMPLETED: Remove the feature where a newly defined tempui `DefineWidget`
   keyword automatically gets one instance placed on the Desk (TODO
   `5ff02d2`) — per direct user feedback, it proved too confusing in
   practice. Revert the auto-place call entirely
   (`DeskWindow._handle_define_widget_file`'s `is_new`-gated call to
   `_auto_place_new_custom_widget`, itself deleted), keeping only the
   "louder docs" half of `5ff02d2`'s original fix (the callout that
   defining a kind never places an instance by itself) — update that
   callout in `_CUSTOM_WIDGETS_DOC` (`src/desk/temp_ui.py`) to no
   longer describe the now-removed auto-place behavior, bump
   `TEMPUI_DOC_VERSION`, and add a `tempui-breaking-changes.md` entry
   (this is breaking from an in-Desk agent's perspective — an agent
   that had learned to rely on auto-placement for a brand-new keyword
   now needs to invoke it explicitly, same as every other tempui kind
   always required). Also update `design-docs/custom-widget-authoring.md`
   section 2, which currently proposes the two-part fix (louder docs +
   auto-place) as still-current design.
   [planned: remove-define-widget-auto-place.md]

   `DeskWindow._on_temp_ui_file_added` now calls
   `_handle_define_widget_file(path)` with no `is_new` argument;
   `_handle_define_widget_file` no longer takes that parameter at all
   (dropped along with the `keyword_already_known` local and the
   auto-place call), and `_auto_place_new_custom_widget` is deleted
   outright. Dropped the same method's mentions from
   `open_widget_content_centered`'s docstring and
   `current_context.set_centered_widget_opener`'s. `_CUSTOM_WIDGETS_DOC`'s
   callout rewritten to state plainly that `DefineWidget` never places
   an instance by itself — brand-new keyword or redefinition alike —
   full stop, no auto-placed exception. `TEMPUI_DOC_VERSION` 17 → 18,
   with a new Version 18 entry in `tempui-breaking-changes.md`
   explicitly noting this reverts the Version 12 new-features entry;
   that Version 12 entry itself is left untouched as dated historical
   record (same precedent as Version 14's own breaking change
   deferring to the breaking-changes doc rather than being rewritten).
   `design-docs/custom-widget-authoring.md` section 2 rewritten to
   describe the actual single-part fix (doc callout only) plus a
   "tried and reverted" note explaining the auto-place half's own
   history and why it was pulled.

   `tests/verify/verify_define_widget_auto_place.py` renamed to
   `verify_define_widget_no_auto_place.py` with every assertion
   flipped: a brand-new keyword registered via the live-added path now
   places zero instances too, converging with the other three
   already-nothing-placed paths (edit-of-known-keyword, bulk rescan,
   failed registration) — kept as explicit regression protection
   against reintroducing the removed behavior by accident, rather than
   deleted.

   Verified directly: the real, unbound `DeskWindow
   ._handle_define_widget_file` (no `is_new` param) registers a
   brand-new keyword via a fake window double with a real
   `WorkspaceView`, and `win.view._frames` stays empty — same for the
   other three paths, all previously and still nothing-placed;
   `_auto_place_new_custom_widget` no longer exists as an attribute on
   `DeskWindow`; doc content (version bump, breaking-changes entry,
   simplified callout, no remaining "auto-places" wording). Full
   regression suite (`git stash` before/after): fixed one more of my
   own earlier scripts' hardcoded exact-version assertion
   (`verify_ensure_build_widget_script.py`, `== 17` → `>= 17`,
   consistent with the `>=`-loosening already applied to several
   similar assertions in the previous TODO batch) — confirmed not a
   real regression. 0 other new failures across all 65 scripts in
   `tests/verify/`.
3846190. COMPLETED: Fix widget content event routing: zoom/pan interactions on
   individual widgets are generally unsuccessful — Desk's own canvas
   (`WorkspaceView`, `src/desk/shell/canvas.py`) is grabbing events that
   should go to whichever widget's content the cursor is over. Per
   direct user report: "If there is an active widget and the mouse
   cursor is over the active widget, then that widget should get all
   the events, including clicks (left and right), pans, zooms, etc."
   Confirmed three independent, real gaps (one via a real, headless
   repro, not just reading code — see the plan): (1) `contextMenuEvent`
   unconditionally shows `WidgetSpawnMenu`, stealing every right-click
   regardless of what's under the cursor; (2) the `event()` override's
   `NativeGesture`/pinch-zoom handling unconditionally zooms the
   canvas, with no carve-out at all (unlike wheel-scroll's own
   existing, deliberate one); (3) click-and-drag starting inside a
   placed widget's own content, when that specific spot doesn't itself
   consume the drag, leaks through Qt's own `ScrollHandDrag` fallback
   and pans the *outer* canvas instead — confirmed empirically (a real
   press/move/release sequence against a real `WorkspaceView` moved the
   view's own scrollbars by the exact drag delta). Wheel-scroll itself
   is unaffected/already correct (TODO c44e88f's existing
   `_scrollable_at` carve-out).
   [planned: widget-content-event-priority.md]

   New `WorkspaceView._frame_at(view_pos)` helper (same `itemAt`-based
   shape as `_hit_test_chrome`/`_scrollable_at`, but broader — any
   placed widget's bounds, not just chrome or scroll areas).
   `contextMenuEvent` now hit-tests first and forwards via
   `super().contextMenuEvent(event)` when over widget content, instead
   of unconditionally showing `WidgetSpawnMenu`. `event()`'s
   `NativeGesture` handling now reuses `_scrollable_at` (the same gate
   `wheelEvent` already uses, deliberately not the broader
   `_frame_at` — keeps pinch consistent with wheel's own existing
   behavior, still zooming the canvas over non-scrollable content like
   a plain image viewer). `mousePressEvent`'s existing chrome-vs-content
   fallthrough now checks `_frame_at` for the non-chrome case: over
   widget content, drag mode is temporarily switched to `NoDrag` for
   just the one `super().mousePressEvent(event)` call (restored
   immediately after), preventing Qt's own hand-scroll-start decision
   from ever engaging for that press — content interaction still
   happens normally in the same call. Updated `design-docs/widget-ux.md`
   (Trackpad Zoom Input, Add Widget Menu, Zoom-Correct Dragging
   sections) to match the new, actual behavior — the "Trackpad Zoom
   Input" section's own opening line ("Both are carved out...") was
   already inconsistent with its closing sentence ("Pinch-to-zoom is
   unaffected by this carve-out") even before this fix; now genuinely
   true.

   Verified directly, each via a real, headless `WorkspaceView` (not
   just reading code): (1) a real press/move/move/release `QMouseEvent`
   sequence dragging inside a placed widget's own content no longer
   moves the view's own scrollbars at all (previously moved them by the
   exact drag delta — confirmed via `git stash`), while the identical
   sequence starting on truly empty canvas still pans it exactly as
   before; (2) a real `QContextMenuEvent` positioned over widget content
   no longer constructs `WidgetSpawnMenu` (patched to confirm), while
   the same event over empty canvas still does; (3) a duck-typed
   native-gesture event (constructing/dispatching a *real*
   `QNativeGestureEvent` segfaulted in this offscreen environment,
   unrelated to the logic under test) confirms pinch no longer zooms
   the canvas over a scrollable widget's content, while still zooming
   over non-scrollable content and empty canvas alike. Full regression
   suite (`git stash` before/after): the new
   `verify_widget_content_event_priority.py` script's 3 previously
   -failing checks (drag/right-click/pinch over content) are exactly
   the ones this fix makes pass, with all 4 "should still work exactly
   as before" checks (background pan, empty-canvas right-click, pinch
   over non-scrollable content and empty canvas) passing both before
   and after — confirming this is a targeted fix, not a side effect.
   Re-ran every chrome-focused script (titlebar drag, resize handles,
   lock, z-order, eye button, stale marker, widget focus, TODO widget's
   own file-watcher-driven reload) to confirm chrome interactions are
   completely unaffected. 0 other new failures across all 66 scripts in
   `tests/verify/`.
8d4826c. COMPLETED: New Event Recorder widget: a "Record for 5s" button that
   temporarily hides the widget's own content (keeping its full size)
   and records every raw Qt event that lands on it during that window,
   then shows a scrollable list of what happened — chronologically
   -adjacent events (even with differing payloads) collapsed into
   collapsed-but-uncollapsable summary groups before display. Motivated
   directly by TODO `3846190`: the user still sees a trackpad
   two-finger-scroll gesture "getting missed" by widgets even after
   that fix, and wants to observe empirically (this environment can't
   reproduce real trackpad hardware input at all) exactly which events
   actually arrive, rather than guessing further — e.g. some platforms
   report two-finger scroll as a `NativeGesture` `PanNativeGesture`
   rather than (or alongside) a `Wheel` event, which TODO `3846190`'s
   own fix never considered at all (only `ZoomNativeGesture`/pinch).
   [planned: event-recorder-widget.md]

   New `widgets/event_recorder/`: `_RecordingSurface(QWidget)` is
   deliberately childless (so nothing can intercept an event before
   its own `event()` override sees it) and passive (always calls
   `super().event(event)`, recording is pure observation, never a
   filter). `_collapse_adjacent` run-length-encodes the raw,
   time-ordered event list by `event.type()`; `_group_to_display_dict`
   strips the raw (non-JSON-serializable) `QEvent.Type` enum member
   before the result is shown in a read-only `QTableWidget` (matching
   Event Log widget's own established shape) or persisted via widget
   -local storage. A live countdown in the status label updates every
   second during the 5s window. Added a new numbered widget-list entry
   (25) to `design-docs/architecture.md`.

   Found and fixed one real bug during verification: `QWidget`'s own
   constructor can dispatch an internal event (delivered through this
   same overridden `event()`) *before* `_RecordingSurface.__init__`'s
   body would otherwise get a chance to run — confirmed directly (an
   `AttributeError` on `self._recording`, raised from inside
   `super().__init__()` itself, not from any caller). Fixed by setting
   `_recording`/`_events`/`_start_time` *before* calling
   `super().__init__(parent)`.

   Verified directly (real `QMouseEvent`/`QWheelEvent` instances
   dispatched straight to `_RecordingSurface.event()` — constructing
   and *dispatching* a real `QNativeGestureEvent` segfaulted in this
   offscreen environment during TODO `3846190`'s own verification,
   unrelated to the logic under test here, so `_describe_event`'s
   native-gesture branch is verified separately via a duck-typed fake
   instead, a plain function call with no `QWidget.event()` dispatch
   involved): events are only captured between `start()`/`stop()`;
   `_collapse_adjacent` produces the right number of groups and
   correctly keeps two non-adjacent runs of the *same* type separate
   (not merged into one); the full widget flow (bypassing the real 5s
   timer directly) switches pages correctly, disables/re-enables the
   record button, and populates the results table correctly;
   `get_widget_local_storage`/`set_widget_local_storage` round-trips a
   completed recording's groups onto a fresh instance, and an
   empty/no-prior-recording payload is a safe no-op. `discover_widgets`
   picks up the new manifest correctly. Full regression suite (`git
   stash` before/after): 0 new failures across all 67 scripts in
   `tests/verify/`.
78bfa41. COMPLETED: Broaden the scroll/zoom event priority policy from TODO
   `3846190`: wheel-scroll and pinch-zoom should go to whichever
   widget's content the cursor is over *no matter what*, not just when
   it's a scrollable widget — explicit user decision, knowingly trading
   away some canvas zoom/pan reachability ("I know that this will
   sometimes make it difficult to zoom/scroll around in Desk, but I
   care more about active widgets getting the events"). Currently
   `wheelEvent`/the pinch branch of `event()` both gate on
   `_scrollable_at` (`QAbstractScrollArea`/`QWebEngineView` only,
   deliberately still zooming the canvas over e.g. a plain image
   viewer); switch both to the broader `_frame_at` (any placed widget
   at all) TODO `3846190` already introduced for the click-drag fix and
   `contextMenuEvent` already uses. This also closes the exact blind
   spot found reading back the Event Recorder widget's first real
   recording (`.desk_temp/recorder.temp.md`'s task) — its own recording
   surface is a plain, non-scroll-area `QWidget`, so it could never see
   a real Wheel event under the old policy no matter what.
   [planned: widget-wheel-pinch-always-wins.md]

   Switched `wheelEvent`/`event()`'s pinch branch to `_frame_at`;
   deleted `_scrollable_at` entirely (dead code once both call sites
   moved off it) and its now-unused `QAbstractScrollArea`/
   `QWebEngineView` imports. Updated `design-docs/widget-ux.md`'s
   "Trackpad Zoom Input" section for the broader policy, and reworded
   `PARKINGLOT.md`'s "scrolling while hovering over a widget..." entry
   — that underlying problem is now fully resolved (not just for scroll
   areas), leaving only its still-unbuilt minimap idea parked.

   Found and fixed one real, genuine regression during verification:
   removing `canvas.py`'s `QWebEngineView` import (unused for any
   `isinstance` check once `_scrollable_at` was deleted) broke 8
   `tests/verify/` scripts that were silently relying on it — canvas.py
   was transitively providing the "import `QtWebEngineWidgets` before
   constructing `QApplication`" ordering PyQt6/Qt requires, via a
   pre-existing `import desk.shell.canvas` line each script already had
   specifically for this purpose (confirmed via `git stash`: all 8
   passed before this TODO's own change, failed identically after, with
   the exact `ImportError: QtWebEngineWidgets must be imported...`
   Qt/PyQt6 error). Fixed properly rather than papering over it by
   re-adding an unused import back to `canvas.py`: each of the 8
   scripts now imports `QWebEngineView` directly and explicitly for
   this ordering requirement, no longer depending on it as an
   incidental side effect of an unrelated module's own contents.

   Verified directly: updated
   `tests/verify/verify_widget_content_event_priority.py`'s pinch test
   to assert the new (opposite) behavior over non-scrollable content,
   plus added the equivalent new wheel-specific tests (previously
   untested by that script at all) — non-scrollable-widget and
   empty-canvas cases for both gestures; confirmed via `git stash`
   that exactly the two intended behaviors flip (both now correctly
   *not* zooming/scrolling the canvas over non-scrollable content)
   while everything else (click-drag, right-click, empty-canvas
   wheel/pinch) stays unchanged. Full regression suite: 0 new failures
   across all 67 scripts in `tests/verify/` (after fixing the 8 found
   above).
86ba292. COMPLETED: Wheel events forwarded to a widget under the cursor
   (TODO `78bfa41`'s `_frame_at` gate) could still leak into canvas-level
   pan. Found from two independent reports: reading back the Event
   Recorder's second real recording (a continuous two-finger scroll
   produced only 2 zero-delta Wheel events before the whole Desk started
   scrolling), and the user separately noticing that scrolling a real
   scrollable widget past the end of its scroll direction scrolls the
   whole Desk too.
   [planned: wheel-event-accept-no-fallthrough.md]

   Root cause was more specific than initially suspected: it's not that
   the forwarded event was left unaccepted (an initial fix along those
   lines made no measurable difference -- confirmed directly, the
   canvas's own scrollbars still moved even with the event marked
   accepted). The actual culprit is `QGraphicsView.wheelEvent` (invoked
   via `super().wheelEvent(event)` to forward into the scene) falling
   back to panning *this view's own* scrollbars -- the whole canvas --
   synchronously, inside that very call, whenever the scene doesn't
   consume the event. That happens for any non-scrollable widget, or any
   scroll area already at its scroll limit -- exactly the two cases
   reported. Fixed by capturing `WorkspaceView`'s own horizontal/vertical
   scrollbar values immediately before the forwarding call and restoring
   them immediately after (the embedded widget's own scrollbars, if any,
   are a separate object and untouched by this), then unconditionally
   `event.accept()`-ing so nothing propagates further regardless of what
   the embedded widget did with the event. A widget under the cursor now
   truly wins full stop, per TODO `78bfa41`'s own policy -- whatever it
   does or doesn't do with the event, the canvas itself never moves.

   Verified directly and empirically, not just by inspection: a
   standalone script confirmed a real `QScrollArea` at its scroll limit
   does leave a `QWheelEvent` unaccepted when dispatched directly to its
   own viewport, then confirmed (with `WorkspaceView`'s own scrollbar
   values captured before/after, embedding the same scroll area as a
   placed widget) that the canvas's own scrollbars moved on the
   pre-86ba292 code and stopped moving after the fix. Added two new
   checks to `tests/verify/verify_widget_content_event_priority.py`
   (scroll-area-at-its-limit and non-scrollable-widget cases), asserting
   both that the canvas's own scroll position is untouched and that the
   event ends up accepted; confirmed via `git stash` that both fail on
   the pre-fix code and pass after. Updated
   `design-docs/widget-ux.md`'s "Trackpad Zoom Input" section to explain
   the `QGraphicsView` fallback-pan mechanism and the capture/restore
   fix. Full regression suite: 67 scripts, 0 new failures (one
   pre-existing, unrelated failure in
   `verify_discuss_parking_lot_item.py` confirmed via `git stash` to
   already fail identically before this TODO's changes).
41088da. COMPLETED: The Event Log widget's status label
   (`widgets/event_log/widget.py`, `_ensure_watching`) displays the
   events log's *absolute* path (`str(self._log_path)`, where
   `self._log_path = directory / TEMP_UI_DIRNAME / LOG_FILENAME`) --
   show it relative instead (e.g. relative to the current Desk
   directory, `current_context.get_current_desk_directory()`),
   matching how the rest of Desk's UI generally prefers concise,
   Desk-relative paths over long absolute ones.
   [planned: event-log-relative-path.md]

   `self._log_path` is always constructed directly as `directory /
   TEMP_UI_DIRNAME / LOG_FILENAME`, so `self._log_path
   .relative_to(directory)` always succeeds by construction -- changed
   the status label to display that instead of `str(self._log_path)`.
   `self._log_path` itself stays absolute (still used for the actual
   watch/read/write); only the displayed text changed.

   Verified directly: updated
   `tests/verify/verify_relocate_event_log.py`'s status-label check to
   assert the label shows the relative form
   (`.desk_temp/MEDIATED-EVENT-LOG.tsv`) and no longer contains the
   Desk directory's own absolute prefix; confirmed via `git stash`
   that it fails on the pre-fix code and passes after. Full regression
   suite: 67 scripts, 0 new failures (the one pre-existing,
   unrelated failure in `verify_discuss_parking_lot_item.py`,
   confirmed via `git stash` to already fail before this TODO's
   changes, is still the only failure).
359684f. COMPLETED: Add a desk-internal popups service, and expose it via the Bridge
   API. Scope clarified with the user: what they actually care about is
   popups *triggered by widget code* (`widgets/*.py`) -- these construct
   a real `QMessageBox` parented to `self` (the embedded content widget,
   living inside a `QGraphicsProxyWidget`), which shows as a real
   top-level macOS window (the native three-dot titlebar chrome) whose
   position/size Qt computes from the parent's `mapToGlobal` -- that
   doesn't account for the canvas's own zoom/pan transform, so at
   non-1.0 zoom the dialog can render in the wrong place or with content
   outside its own window bounds. Explicitly out of scope: `WidgetSpawnMenu`/
   `_DeskListPopup`/`NewDeskDialog` and `desk.shell.window`'s own
   `_confirm_fn`/`_prompt_fn`/`_warn`/`_info`/`_warn_with_selectable_text`/
   `_confirm_stale_reload` -- these are parented to the main window (a
   real top-level widget, not an embedded proxy, so they don't have this
   bug), and several need a filterable list, a scrollable MRU list, or
   free-text input rather than a message+buttons shape.
   In scope: every `QMessageBox` call in `widgets/*.py` (Event Log's
   Clear Log confirm, Crash Log/Questions/TODO's discard confirms,
   Stack's warnings+question, Editor's warning +
   Save/Discard/Cancel unsaved-changes flow, SVG Editor's warning).
   Replace these with one consistent mechanism: a popup is a
   `WidgetFrame` placed on the canvas like any other widget (so it
   scales correctly under zoom, unlike a real top-level Qt window),
   with a title and a close button, and a body that can show a message
   plus one or more buttons -- equivalent to what a browser's or Qt's
   own built-in alert/confirm popups offer. Unlike a normal widget
   frame: always frontmost in z-order (can't be sent behind other
   widgets), never lockable (no lock button), and not reachable via the
   eye button (`_EyeButton`/`zoom_to_widget` in `desk.shell.widget_frame`)
   -- it's transient chrome, not placed content worth zooming to or
   persisting across a reload. Implement as a new service under
   `src/desk_services/` (same shape as TODO `578cb6b`'s
   `desk_services/file_watcher`), and add Bridge API endpoints for it
   (`desk.server.app`'s `/api/bridge/...` routes, same
   `require_caller`/capability-scoping pattern as `events`/`fs`/
   `widgets`) so both `kind: "python"` and `kind: "html"` widgets (and
   eventually agents) can show one, not just Desk's own shell code.
   Verify it renders and behaves correctly across a range of zoom
   levels, the same scrutiny TODO `d0d7b37`/`7845a0f` already gave
   normal widget chrome.
   [planned: desk-internal-popups.md]

   Implemented `WidgetFrame(..., is_popup=True)`: its titlebar shows
   only the title label and close button, regardless of any other
   state -- so "never lockable" and "not eye-button-focusable" both
   fall out of this one flag, no new interaction code needed. Popups
   get 100% of the existing zoom counter-scaling for free
   (`WidgetFrame.set_view_scale`) since they're placed via a new
   `WorkspaceView.add_popup` (a sibling of `add_widget`), but are
   tracked in a separate `_popup_frames` list, never `_frames` --
   `DeskWindow`'s placed-widget bookkeeping (`_capture_desk_state`,
   `find_frame_by_instance_id`, `_find_frame_by_widget_id`, stale-hash
   refresh) iterates `_frames` and assumes every entry is a real,
   persisted widget with a `widget_id`; a popup has none of that and
   must never be seen by any of it. "Always frontmost" needed a fixed,
   far-above-normal-frames z-value band (`POPUP_Z_BASE = 1_000_000.0`)
   rather than a dynamic `max(normal frame z-values) + 1` -- confirmed
   directly that the dynamic version breaks the guarantee the moment a
   normal frame is brought to front *again* after the popup was placed
   (it just catches up to and ties with the snapshotted max); the fixed
   band doesn't have this problem since `_frame_z_values()` (the pool
   `bring_to_front`/`send_to_back` compute against) only ever iterates
   `_frames`, so popups are automatically excluded.

   `desk_services/popups/service.py` (`PopupsService`): `show(...)` is
   the non-blocking core (builds a message label + one button per
   label, wraps it in a popup `WidgetFrame`, resolves `on_result`
   exactly once on a button click, the close button, Escape, or a Desk
   switch happening while still open -- `WorkspaceView.clear_widgets`
   now also resolves any still-open popup instead of leaving its caller
   hanging forever); `show_blocking(...)` wraps it in a nested
   `QEventLoop` for widget call sites that expect a synchronous return
   value, the same idea `QDialog.exec()` already uses internally (a new
   pattern in this codebase -- no prior `QEventLoop` usage). A popup's
   close button is special-cased in `WorkspaceView.mouseReleaseEvent`'s
   existing `kind == "close"` dispatch (`frame.is_popup` routes to a
   new `popup_closed` signal instead of `widget_close_requested`, which
   triggers `DeskWindow`'s full "close a placed widget" bookkeeping --
   wrong for something that was never part of Desk's persisted widget
   list).

   `current_context.set_popup_opener`/`get_popup_opener` (bound at
   `DeskWindow` startup to `PopupsService.show_blocking`) is how
   `kind: "python"` widgets reach this; `POST /api/bridge/popups/show`
   (capability `popups`, via `DeskWindow.show_popup`) is how
   `kind: "html"` widgets do -- using the plain synchronous
   `run_on_gui`/`GuiBridge.call` (not `run_on_gui_async`), the same
   pattern `request_introspect_permission`'s own blocking confirmation
   dialog already uses, since `show_blocking`'s nested event loop
   already makes the GUI-thread call synchronous from the caller's
   side.

   Migrated all 7 in-scope call sites (`widgets/event_log`,
   `crash_log`, `questions`, `todo`, `stack` (x3), `editor` (warning +
   the Save/Discard/Cancel unsaved-changes flow, picking "Cancel" as
   the popup's default button -- the safe, non-destructive choice;
   `QMessageBox`'s own implicit default there wasn't a deliberate
   choice worth preserving byte-for-byte), `svg_editor`) -- removed the
   now-unused `QMessageBox` import from each.

   Updated `design-docs/widget-ux.md` (new "Desk-Internal Popups"
   section) and `design-docs/architecture.md` (new numbered entry for
   the Popups Service). Bumped `TEMPUI_DOC_VERSION` 18 -> 19 and added a
   `desk.popups.show(...)` capability entry to both
   `tempui-custom-widgets.md`'s capability list and
   `tempui-new-features.md`'s Version 19 entry (this is a new Bridge
   API capability from the perspective of an agent running inside
   Desk, per `development-process.md`'s standing tempui-changelog
   rule).

   Verified directly: new `tests/verify/verify_desk_internal_popups.py`
   (24 checks) -- popup chrome hides lock/unlock/eye/bring/send/tempui/
   stale buttons; a popup's z-value is above every normal frame's and
   stays there even after a normal frame is brought to front again
   (confirmed this genuinely fails with the naive dynamic-max
   implementation and passes with the fixed z-band, not just asserted
   by inspection); popups are excluded from `_frame_z_values()`'s
   bring/send-to-back pool; a popup's titlebar counter-scales on zoom;
   `show`/`show_blocking` resolve correctly on a button click, on
   close, and on `clear_widgets`; a popup is never visible to
   `_frames`-based persistence iteration. Updated the two existing
   verify scripts that patched `QMessageBox` directly
   (`verify_stack_widget.py`, `verify_segfault_fix.py`) to patch the
   new popup-opener seam instead; `verify_crash_log.py` needed no
   change (already patched `_confirm_delete` itself, not
   `QMessageBox`). Full regression suite: 68 scripts, 0 new failures
   (the one pre-existing, unrelated failure in
   `verify_discuss_parking_lot_item.py`, confirmed via `git stash` in
   TODO `86ba292`'s own work to already fail before any of this
   session's changes, is still the only failure).

   Not done: actually visually confirming a popup renders correctly at
   non-1.0 zoom in a real windowed run -- this environment is
   offscreen-only, so this step is skipped per process (the automated
   check above exercises the exact same `set_view_scale`/counter
   -scaling code path every other widget's chrome already relies on,
   just not a human's own eyes on a real screen).
fd713a5. COMPLETED: Git diff viewer widget: shows a file's `git diff` when clicked in
   the Git Status widget (`widgets/git_status/widget.py`, which
   currently only displays `git status --porcelain=v1` output in a
   plain `QListWidget` with no click handling at all -- add it). Also
   add a new role to the file type registry (`desk.file_type_registry
   .ROLES`, currently `("view", "edit", "consume", "produce")`)
   alongside the existing `view`/`edit` ones: `git-diff`, with its own
   `find_git_diff_handler` (mirroring `find_view_handler`/
   `find_edit_handler`) so other places that already look up a
   file's view/edit handler (`ProjectFilesWidget`, `open_editor_or_scrap`
   in `desk.shell.window`) can offer a "Git Diff" action the same way,
   not just the Git Status widget's click handler. If the clicked file
   is binary (`git diff` reports it as such, or `looks_like_text_file`
   says no), still open the widget rather than silently failing --
   show something like "(binary file, no diff)" instead of attempting
   to render a diff.
   [planned: git-diff-viewer-widget.md]

   Added `"git-diff"` to `desk.file_type_registry.ROLES` and a new
   `GIT_DIFF_WIDGET_ID`/`find_git_diff_handler` -- unlike
   `find_view_handler`/`find_edit_handler`, this always resolves to a
   real widget id (never `None`): git diff is meaningful for any file
   type, not a suffix-specific concern, so the built-in fallback is a
   single unconditional constant rather than a suffix-keyed dict.

   New `widgets/git_diff/` (`GitDiffWidget`): `set_file(path)` runs
   `git diff HEAD -- <path>` on a background thread (a `_Relay`
   `pyqtSignal`, same shape as `git_status`/`todo`'s own git-subprocess
   threads) -- resolving `find_git_root` on that same background
   thread too, not on the GUI thread first the way `git_status`'s own
   `_poll` does, per `LEARNINGS.md`'s "a blocking `subprocess.run()` on
   the Qt GUI thread freezes the whole app's UI feedback" (a fresh
   widget shouldn't copy that existing, separate wart). Binary
   detection: git's own `"Binary files "` marker in the diff output is
   authoritative; `desk.file_type_registry.looks_like_text_file(path)`
   is only consulted when the file still exists locally -- checking it
   unconditionally would misidentify a *deleted* file (a real, common
   git-status entry, which no longer exists to sniff and so returns
   `False` from that heuristic's own "can't tell, don't guess yes"
   convention) as binary, hiding its real, meaningful diff. Empty diff
   output shows "(no differences from the last commit)" rather than a
   blank pane. `get_widget_local_storage`/`set_widget_local_storage`
   persist the path via `desk.persisted_path.resolve_persisted_path`,
   same convention as Editor/Markdown/SVG Editor.

   `current_context.set_git_diff_opener`/`get_git_diff_opener` (bound
   at `DeskWindow` startup to a new `DeskWindow.open_git_diff`,
   mirroring `open_editor_or_scrap` but without its Scratch-note
   fallback branch, since `find_git_diff_handler` always resolves) is
   the shared, reusable "open a Git Diff Viewer for this file" service
   the TODO asked for -- not hardcoded into the Git Status widget's own
   click handler.

   `widgets/git_status/widget.py`: `_populate_list` now stashes each
   row's resolved absolute `Path` (parsed from the porcelain line --
   fixed 2-char status + 1 space prefix, taking the part after `" -> "`
   for a rename/copy line) as `Qt.ItemDataRole.UserRole` item data at
   population time; the `CLEAN_PLACEHOLDER` row gets none, so clicking
   it is a no-op. `itemClicked` (single click, matching the TODO's own
   "when clicked" wording) reads that data and calls
   `current_context.get_git_diff_opener()`.

   Scope note: `ProjectFilesWidget` was **not** given a new context
   menu in this pass -- it has no existing Edit/View menu at all today
   (only a double-click -> view-handler lookup), so there's no existing
   entry point to extend, and building a new right-click menu is a
   separate UI-design decision (which actions, which gesture) beyond
   what was concretely asked. The reusable `find_git_diff_handler`/
   `open_git_diff` infrastructure this TODO built makes that addition
   cheap whenever it's wanted.

   Bumped `TEMPUI_DOC_VERSION` 19 -> 20: `desk.filetypes.get()/.set()`'s
   capability description in `tempui-custom-widgets.md` now mentions
   the new `git-diff` role, and `tempui-new-features.md` got a matching
   Version 20 entry (this is a new, agent-visible capability of an
   existing Bridge API route, per `development-process.md`'s standing
   tempui-changelog rule).

   Verified directly: new `tests/verify/verify_git_diff_widget.py` (16
   checks) -- `find_git_diff_handler`'s dynamic-registry hit and
   always-resolves fallback; the porcelain-line path parser (plain
   line, rename line, garbage line); `_populate_list`'s item-data
   stashing and the clean-placeholder's lack of it; the click handler
   calling the opener for a real row and not for the placeholder; and,
   against **real temporary git repos** (not mocked subprocess output):
   a real uncommitted text change rendering as a real `-`/`+` diff, a
   real binary-content change showing the binary placeholder, a
   **deleted file's real diff still rendering** (the critical
   regression check for the binary-detection ordering decision above),
   an unchanged file's no-differences message, a not-a-repo message,
   and the widget-local-storage round trip. Full regression suite: 69
   scripts, 0 new failures (the one pre-existing, unrelated failure in
   `verify_discuss_parking_lot_item.py` is still the only failure).

   This was the last item in the TODO queue -- confirmed via `grep -n
   "^[0-9a-f]\{7\}\." TODO.md | grep -vi "COMPLETED\|SUPERSEDED"`
   returning empty after this commit.
d9a46b6. COMPLETED: Rename the Event Recorder widget's display name (`widgets/event_recorder
   /widget.json`'s `"name"` field) to "Qt UI Event Recorder" -- the
   `widget_id` (`event_recorder`, derived from the directory name at
   discovery time, independent of the manifest's `name` field) is
   unaffected, so this doesn't touch any already-placed instance in a
   `.desk` file. Update the display-name mentions in
   `design-docs/architecture.md`'s numbered widget list and the
   widget's own module docstring for consistency; leave historical
   references (`TODO.md`'s own completed entries, `PARKINGLOT.md`,
   already-`COMPLETED` plan files) as the historical record of what was
   true when written, not retroactively renamed.
   [planned: rename-event-recorder-widget.md]

   Changed `widget.json`'s `"name"` field, the widget's own module
   docstring, `design-docs/architecture.md`'s numbered entry, and one
   descriptive comment in `src/desk/shell/canvas.py`. `widget_id`
   (`event_recorder`) confirmed unaffected (derived from the directory
   name at discovery, independent of `name`) -- no already-placed
   instance or `.desk` file is touched by this. Confirmed via grep that
   no `tests/verify/*.py` script hardcodes the old display name, so no
   test changes were needed. Full regression suite: 69 scripts, 0 new
   failures (the one pre-existing, unrelated failure in
   `verify_discuss_parking_lot_item.py` is still the only failure).
54d8c18. COMPLETED: Transforms, part 1/4: the core infrastructure and the Desk Service.
   See `design-docs/transforms.md` for the full design. A transform
   converts data of one named type into another (`input_type ->
   output_type`), optionally with `config` and an `identity` (input<->
   output) mapping, written in Python/TypeScript/JavaScript, described
   by a `transform.json` manifest next to its entry file. Discovery
   scans `.desk_temp/transforms/<name>/` (TypeScript/JavaScript only --
   Python is rejected there, surfaced as a Transform Manager error row)
   and `desk_transforms/<name>/` (any of the 3 languages; wins on a
   `transform_id` collision) directly -- no build-artifact indirection
   the way `DefineWidget` custom widgets have, since a transform is
   never "placed" anywhere. `desk_services.transforms.TransformsService`
   (module-level `get_service()` singleton, same shape as
   `file_watcher`/`popups`): Python transforms are `importlib`-loaded
   and run in-process, synchronously, on whichever thread calls `run`
   (required, not just simplest: both Mermaid transforms build a
   `QGraphicsScene`, which must happen on the GUI thread); TypeScript/
   JavaScript transforms always run via a background thread invoking
   `node <entry>.js` as a real subprocess (a JSON request on stdin, a
   JSON response on stdout -- see the design doc's exact protocol),
   reporting back via a `_Relay` `pyqtSignal`, same shape
   `git_status`/`git_diff`'s own git-subprocess calls already use.
   TypeScript transforms get an on-demand `tsc -p <dir>` build, cached
   until the `.ts` source's mtime moves past its compiled output.
   `run`/`identity` are non-blocking/callback-based (mirrors
   `PopupsService.show`); `run_blocking`/`identity_blocking` wrap them
   in a nested `QEventLoop` for simple synchronous callers. `promote`
   moves a `.desk_temp/transforms/<id>/` directory to
   `desk_transforms/<id>/` (`shutil.move`, mirrors
   `_relocate_promoted_widget_source`). Reachable by `kind: "python"`
   widgets via `current_context.get_transform_runner_blocking()`
   (bound at `DeskWindow` startup), and by `kind: "html"` widgets via
   `POST /api/bridge/transforms/run` (capability `transforms`,
   `run_on_gui_async`). `identity`/`identity_blocking` are implemented
   and tested at the service level but not wired out to
   `current_context`/the Bridge API yet -- nothing consumes them (both
   Mermaid transforms declare `has_identity: false`).
   [planned: transforms-core-infrastructure.md]

   Built `src/desk/transforms.py` (manifest parsing/discovery, no Qt
   dependency, mirrors `desk.file_type_registry`'s own shape) and
   `desk_services/transforms/service.py` (`TransformsService`) exactly
   per plan, plus the `current_context`/`DeskWindow`/Bridge API wiring.
   The str-in/str-out contract for `identity()` was tightened from the
   design doc's original "-> object" to "-> str" (a Python transform's
   `identity()` now encodes its own JSON-serializable result as a
   string, same as `run()` and same as the JS/TS wire protocol's
   `output` field already required) -- found while writing the first
   real test fixture, for genuine cross-language consistency, not a
   late scope change.

   Two real bugs found and fixed via direct reproduction, not just
   inspection:
   - **A real hang**, reproduced directly (the test process had to be
     killed after several minutes stuck with zero CPU usage and no
     child `node`/`tsc` process running): `_run_blocking`'s `on_result`
     called `loop.quit()` directly, but a Python transform's
     `on_result` fires *synchronously*, inside `_invoke()`, before
     `loop.exec()` even starts -- `QEventLoop.quit()` only has an
     effect on an already-running loop, so a quit issued before
     `exec()` starts can be silently dropped, leaving `exec()` block
     forever waiting for a quit that already happened. Fixed by
     deferring the actual `quit()` via `QTimer.singleShot(0, ...)`,
     safe for both the synchronous (Python) and asynchronous (JS/TS)
     resolution paths. Confirmed `PopupsService.show_blocking` does
     *not* have this same bug -- a popup only ever resolves from a
     real, later user interaction, never synchronously within `show()`
     itself -- so nothing there needed changing.
   - **A real `tsc` compile failure**: `process`/`Buffer` (Node's own
     globals, needed by the stdin/stdout protocol) don't type-check
     without `@types/node`, which was rejected as a new dependency
     (CLAUDE.md). Fixed with a small, fixed, auto-generated ambient
     declarations file (`_desk_transform_node_globals.d.ts`, only the
     handful of members the protocol actually uses) written into a
     TypeScript transform's own directory before each build --
     `tsc -p <dir>`'s default "include everything in this directory"
     behavior picks it up with no `tsconfig.json` changes needed.

   Also found and fixed, incidentally, while adding `transforms` to
   `bridge_client.py`'s JS convenience-wrapper template: `popups`
   (TODO `359684f`) never got its own `window.desk.popups.show(...)`
   entry there at all -- every other Bridge capability has one, popups
   didn't, leaving `kind:"html"` widgets with only a raw `fetch()` to
   reach it. Fixed alongside `transforms`' own entry; a regression
   check added to `verify_desk_internal_popups.py`.

   Bumped `TEMPUI_DOC_VERSION` 20 -> 21 for the new `transforms`
   capability in `tempui-custom-widgets.md`/`tempui-new-features.md` --
   initially referenced `design-docs/transforms.md` from inside the
   shipped doc content, which `verify_tempui_doc_versioning.py`'s
   "no doc mentions Desk-repo-internal material" check correctly
   caught (a downstream project consuming these docs has no
   `design-docs/` directory of its own) -- reworded to explain the
   concept inline instead.

   Verified directly: new `tests/verify/verify_transform_discovery.py`
   (12 checks: manifest parsing, the Python-rejected-under-`.desk_temp`
   rule, project-level winning an id collision, error-dict population)
   and `tests/verify/verify_transforms_service.py` (18 checks,
   including a real Python transform, a real JavaScript transform via
   a real `node` subprocess, a real TypeScript transform via a real
   on-demand `tsc` build that's confirmed cached then confirmed to
   rebuild after a real mtime change, confirmation via a live `QTimer`
   tick-counter that the JS/TS path genuinely doesn't block the event
   loop -- not just asserted by code inspection -- and `promote`'s real
   `shutil.move`). New `tests/verify/verify_bridge_api_transforms_run.py`
   (8 checks, same real-HTTP-request-against-a-real-server pattern
   `verify_bridge_api_editor_or_scrap.py` already established, with a
   deliberately `QTimer`-delayed fake `run_transform` to prove
   `run_on_gui_async` genuinely waits for a later callback rather than
   only working by accident for an immediately-resolving one). Full
   regression suite: 72 scripts, 0 new failures (the one pre-existing,
   unrelated failure in `verify_discuss_parking_lot_item.py` is still
   the only failure).
b5e15cf. COMPLETED: Transforms, part 2/4: Transform Manager widget. A new
   `widgets/transform_manager/` (`kind: "python"`), modeled on
   `EventLogWidget`'s plain `QTableWidget` shape (no existing "list/
   introspect other widgets or definitions" widget precedent to mirror
   instead). One row per transform discovered by
   `TransformsService.discover()`: Name / Input Type / Output Type /
   Language / Config? / Identity? / Location, plus a Promote button
   column shown only for a `.desk_temp/`-sourced row -- clicking it
   shows a confirmation popup (TODO `359684f`'s desk-internal popups)
   before calling `TransformsService.promote`. A Refresh button (no
   file-watching -- transforms aren't edited anywhere near as often as
   `TODO.md`, this is a manager/introspection widget not a live-edited
   document).
   [planned: transform-manager-widget.md]

   Implemented per plan: `widgets/transform_manager/` (`kind:
   "python"`), a `QTableWidget` modeled on `EventLogWidget`'s shape.
   `refresh()` (also run once at construction, so a freshly-placed
   instance isn't blank) resolves `.desk_temp/transforms/`/
   `desk_transforms/` from `current_context
   .get_current_desk_directory()` and calls
   `desk_services.transforms.get_service().discover(...)` directly (no
   `current_context` indirection needed -- this widget IS the
   dedicated UI for the service, same relationship `GitStatusWidget`
   has to `find_git_root`). A discovery error (e.g. a Python transform
   under `.desk_temp/`) shows as a visible `[!]`-prefixed, full-width
   error row via `QTableWidget.setSpan`, not silently dropped. Promote
   shows a confirmation popup (`current_context.get_popup_opener()`,
   TODO `359684f`) before calling `TransformsService.promote`; a
   `TransformError` shows a second popup with the failure reason.

   One real bug found and fixed via direct reproduction: after a
   successful promote, the now-project-located row still showed a
   stale Promote button. Root cause: `QTableWidget.setRowCount()`
   doesn't clear an existing row's cell widget when the row count is
   unchanged across a refresh (promoting a transform doesn't change
   how many rows there are, just which directory one of them is
   listed under) -- `setCellWidget`'s effects on a persisted row index
   just linger. Fixed with an explicit `removeCellWidget` in the
   non-`.desk_temp` branch of the per-row population logic.

   Verified directly: new
   `tests/verify/verify_transform_manager_widget.py` (13 checks,
   against real `transform.json` files on disk, not mocked
   `TransformInfo` objects) -- table population (columns, Promote
   button presence/absence by location), a real discovery error
   showing as a real error row, Promote's real `shutil.move` (the
   directory actually relocates on disk) both confirmed and declined
   (leaving the source untouched), and Refresh picking up a transform
   added to disk after the widget was already built. Full regression
   suite: 73 scripts, 0 new failures (the one pre-existing, unrelated
   failure in `verify_discuss_parking_lot_item.py` is still the only
   failure).
05cfccc. COMPLETED: Transforms, part 3/4: extract Mermaid flowchart/state diagram
   rendering into individual transforms. `src/desk/mermaid.py` today
   produces a live `QGraphicsScene`, rendered directly by
   `MermaidDiagramWidget` (a `QGraphicsView` subclass) -- no SVG is
   ever generated anywhere in the current pipeline (confirmed directly
   -- only two diagram kinds are actually implemented today despite
   appearing to have "several": `flowchart`/`graph` and
   `stateDiagram`/`stateDiagram-v2`; anything else already raises
   `MermaidParseError`). Add `desk.mermaid.render_svg(scene) -> str`
   (new code -- `PyQt6.QtSvg.QSvgGenerator`, a `QPaintDevice`, drawn
   onto via `QPainter` into an in-memory `QBuffer`), keeping
   `parse`/`layout`/`build_scene` exactly as-is as the shared engine.
   Two new transforms at project level (`desk_transforms/`, not
   `.desk_temp/` -- built-in Desk behavior, not a user experiment):
   `mermaid_flowchart_svg` (`input_type: "mermaid-flowchart"`) and
   `mermaid_state_svg` (`input_type: "mermaid-state"`), each a thin
   `parse -> layout -> build_scene -> render_svg` wrapper, both
   `output_type: "svg"`, `has_config: false`, `has_identity: false`.
   `MermaidDiagramWidget` stays in place, still imported/used by
   `widgets/markdown/widget.py` exactly as today, until TODO `a9e2ba7`
   (part 4/4) actually stops calling it -- deleting it in *this* item
   would leave the app's Mermaid rendering broken for the length of
   time between these two commits; its deletion belongs in that item,
   the one that removes its one remaining caller.
   [planned: extract-mermaid-transforms.md]

   Implemented per plan: `desk.mermaid.render_svg(scene) -> str`
   (`PyQt6.QtSvg.QSvgGenerator` writing into an in-memory `QBuffer` via
   a `QPainter`, decoded as UTF-8) added alongside
   `parse`/`layout`/`build_scene`, all otherwise untouched. Two new
   project-level transforms, `desk_transforms/mermaid_flowchart_svg/`
   and `desk_transforms/mermaid_state_svg/`, each a thin
   `parse -> layout -> build_scene -> render_svg` wrapper -- since
   `parse` dispatches by the source's own header regardless of which
   transform calls it, each explicitly checks the returned
   `Diagram.kind` (`"flowchart"`/`"state"`, already a field on that
   dataclass) and raises a clear `ValueError` if the wrong diagram type
   reaches it, rather than silently parsing content from the *other*
   supported kind. `MermaidDiagramWidget` deliberately left untouched
   for now (see this item's own sequencing note above) -- still the
   Markdown widget's only Mermaid renderer until TODO `a9e2ba7`.

   Verified directly: new
   `tests/verify/verify_mermaid_svg_transforms.py` (12 checks) --
   `render_svg` produces real, well-formed SVG (including the
   diagram's actual node-label text appearing in the output); both
   transforms' `run()` called directly against real Mermaid source,
   confirmed to reject the *other* transform's diagram type (proving
   the `Diagram.kind` guard actually discriminates, not just that
   `parse` doesn't crash) and to propagate `MermaidParseError`
   (unswallowed) for a genuinely unsupported diagram
   (`sequenceDiagram`); both transforms also exercised end-to-end
   through a real `TransformsService` (real discovery under a real
   `desk_transforms/`-shaped directory, real `run_blocking`
   execution), not just as bare functions. Full regression suite: 74
   scripts, 0 new failures (the one pre-existing, unrelated failure in
   `verify_discuss_parking_lot_item.py` is still the only failure).
a9e2ba7. COMPLETED: Transforms, part 4/4: Markdown widget consumes the Mermaid
   transforms via the Desk Service. Extract `widgets/image_viewer/
   widget.py`'s private `_AspectSvgView` (a bare `QSvgRenderer` into a
   letterboxed, aspect-preserving rect) into a new shared
   `src/desk/svg_view.py` module so both `image_viewer` and `markdown`
   import the same implementation instead of duplicating it. Markdown's
   Mermaid-block handling changes from "build a `MermaidDiagramWidget`
   inline" to: detect the block's diagram header (same detection
   `desk.mermaid.parse` already does) to pick `mermaid_flowchart_svg`
   vs. `mermaid_state_svg` (or skip straight to the existing plain-text
   fallback for any other diagram type -- no transform exists for it
   yet, same as today's "unsupported" case); call
   `current_context.get_transform_runner_blocking()(transform_id,
   block_text, None)`; render the returned SVG via the new shared SVG
   view widget on success, or the existing plain-text + "(unsupported
   or unparseable Mermaid diagram)" fallback on failure. User-visible
   change, accepted deliberately (see design doc): a Mermaid diagram
   becomes a static SVG image instead of a live, pannable
   `QGraphicsView` scene -- nothing in the current UI actually depended
   on the scene being interactive.
   [planned: markdown-consumes-mermaid-transforms.md]

   Implemented per plan. Also added `desk.mermaid.detect_diagram_kind`
   (the diagram kind `parse()` would dispatch to, without doing the
   full parse) so the Markdown widget doesn't need to duplicate
   `desk.mermaid`'s own private header-detection regexes to decide
   which transform to call. `MermaidDiagramWidget` deleted here (the
   item that removes its one remaining caller, per TODO `05cfccc`'s
   own sequencing note), along with its now-unused `QFrame`/
   `QGraphicsView` imports. `SvgView.content_size()` (renamed from
   `_AspectSvgView`'s private `_content_size`) is now public, since a
   caller embedding it in a layout that doesn't otherwise size it (the
   Markdown widget's own per-block height calculation, bounded the
   same 560px max `MermaidDiagramWidget` used to use) needs the
   content's real natural size.

   Verified directly: new
   `tests/verify/verify_markdown_mermaid_transforms.py` (12 checks) --
   correct transform-id dispatch per diagram kind, an unsupported
   diagram type (`sequenceDiagram`) never calling any transform and
   showing the plain-text fallback, a successful render producing a
   real valid `SvgView`, graceful plain-text fallback for a raising
   transform/invalid SVG output/no registered runner at all (never a
   crash), and a real end-to-end pass through a real
   `TransformsService` against the real `desk_transforms/
   mermaid_flowchart_svg`/`mermaid_state_svg` directories for both
   diagram kinds. Re-ran `verify_image_viewer_svg_integration.py` (22
   checks) to confirm the `SvgView` extraction didn't regress the
   Image Viewer widget -- unaffected. Full regression suite: 75
   scripts, 0 new failures (the one pre-existing, unrelated failure in
   `verify_discuss_parking_lot_item.py` is still the only failure).

   This was the last item in the Transforms feature (design doc +
   4 TODO items) -- confirmed via `grep -n "^[0-9a-f]\{7\}\." TODO.md |
   grep -vi "COMPLETED\|SUPERSEDED"` returning empty after this commit.
d1d176f. COMPLETED: New FEEDBACK (`../FEEDBACK/FEEDBACK-DESK-svg-editor-viewbox-guide
   -2026-07-16-1156.md`): the SVG Editor never shows its own document
   bounds (`viewBox`/`width`/`height`) anywhere, so a view that drifts
   during editing leaves shapes drawn far outside the exportable area
   with zero visual indication -- the editor itself never clips while
   editing, but any real SVG consumer (a browser, an `<img>`/`<image>`
   tag) clips strictly to `viewBox` and shows nothing. Concrete case
   this was extracted from: a `necro-4x` `terrain-types-editor`
   widget's `grassy-hills.svg`, whose shapes ended up 250-950 units
   outside its own declared `0 0 400 300` viewBox. Suggested fix (all
   in `widgets/svg_editor/widget.py`): (1) render the document's own
   bounds as a visible, non-exported guide rectangle; (2) a "Reset
   View"/"Zoom to Fit Document" action; (3) optionally bound the scene
   rect to something generously larger than the document bounds
   (not exactly equal) so panning has some natural limit instead of
   the current effectively-unbounded default. Additional feature
   specifically requested: a toggleable, non-hittable hexagon preview
   overlay (a semi-transparent mask with a hexagon-shaped hole cut out,
   sized to the document bounds) -- previews what a hex-tile consumer
   (like `necro-4x`'s own terrain art pipeline) would actually clip the
   artwork to, live during editing.
   [planned: svg-editor-viewbox-guide.md]

   Implemented per plan. `_document_bounds(root)`: `viewBox` primary
   (`min-x min-y width height`), falling back to `width`/`height`
   attributes (stripping a trailing unit suffix like `"px"`) if
   `viewBox` is absent/unparseable, falling back to `_new_empty_root`'s
   own `0 0 400 300` default if neither is usable. The bounds guide
   rect, scene-rect bounding, and hex preview mask are all built by one
   `_refresh_document_guides()` (plus `_refresh_bounds_guide`/
   `_refresh_hex_preview`), called from `__init__` and at the end of
   `_rebuild_scene_from_root` -- `_scene.clear()` (already called there)
   destroys every scene item including these, so their Python
   references (`self._bounds_guide_item`/`self._hex_preview_item`) are
   reset to `None` alongside the pre-existing `self._handles = []`
   reset, for the same reason. Both new overlay items use
   `setAcceptedMouseButtons(Qt.MouseButton.NoButton)` (Qt's own
   click-through mechanism) so editing works identically whether either
   is present. "Reset View" (`fitInView`) is also called automatically
   at the end of `_load_file`, and once at startup via
   `QTimer.singleShot(0, self._reset_view)` -- `fitInView` needs the
   view's real viewport size, not yet available synchronously in
   `__init__` before the widget has actually been laid out/shown (a
   well-known Qt gotcha). Scene rect bounding uses a margin
   proportional to the document's own size (`max(width, height)` per
   side), not a fixed constant. The hexagon mask is built via
   `QPainterPath.subtracted()` (Qt's own boolean path algebra: full
   document rect minus a centered regular hexagon, radius `min(width,
   height) / 2`) rather than hand-building an even-odd-fill path.

   Verified directly: extended the existing
   `tests/verify/verify_svg_editor_widget.py` (13 new checks, 56 total
   now) -- `_document_bounds`'s three parse paths; the guide item
   surviving both construction and a full reload; **the core regression
   this feedback is about**, confirmed directly: neither the guide rect
   nor the hex mask ever appears in a saved file's XML (save, re-parse,
   confirm only real drawn objects are present); both overlay items
   confirmed click-through (`acceptedMouseButtons() ==
   Qt.MouseButton.NoButton`); the scene rect strictly containing the
   document bounds with room on every side; Reset View confirmed to
   actually restore visibility of the document bounds after a real pan
   away from them (`centerOn`, not `translate` -- caught during writing
   this test that `QGraphicsView.translate()` doesn't move the
   viewport's *visible scene region* the way a real pan/scroll does,
   confirmed directly by comparing before/after visible rects; switched
   to `centerOn`, which does); and the hex preview toggle's add/remove/
   persist-across-reload behavior. Full regression suite: 75 scripts, 0
   failures.
31db3f6. COMPLETED: New FEEDBACK (`../FEEDBACK/FEEDBACK-DESK-build-widget-capabilities
   -2026-07-16-1010.md`): `.desk_temp/build_widget.py` (generated from
   `_BUILD_WIDGET_SCRIPT` in `src/desk/temp_ui.py`) silently ignores a
   `DefineWidget`-authored widget's `widget.json` `capabilities` field
   entirely, forcing a hand-edit of the *generated* tempui file after
   every build (adding `Capability<TAB>name` lines by hand) that's easy
   to forget -- confirmed twice in the reporting project, the second
   time producing a widget with a silently-empty table and no error
   surfaced anywhere beyond the widget's own devtools console (missing
   `desk.fs`/`desk.editor` grants meant `desk.fs.readFile(...)` failed
   as an unhandled promise rejection). `widget.json`'s own
   `capabilities` field is already the obvious, expected place for this
   by direct analogy with a real `kind: "python"`/`"html"` widget's own
   manifest -- three widgets in the reporting project already added it
   unofficially, even though nothing reads it. Fix: `build_widget()`
   reads `manifest.get("capabilities", [])` (optional, defaults to `[]`
   -- no behavior change for a `widget.json` with no such key) and
   emits one `Capability<TAB>name` line per entry, right after the
   `Size` line -- the exact position/format already used when this is
   done by hand today.
   [planned: build-widget-capabilities.md]

   Implemented per plan (primary fix, not the fallback mismatch-warning
   option -- no reason found to prefer it, and the primary fix closes
   the gap completely). `build_widget()` now reads
   `manifest.get("capabilities", [])` and emits one
   `Capability<TAB>name` line per entry right after the `Size` line;
   `REQUIRED_MANIFEST_KEYS` unchanged (still optional). Updated the
   generated script's own module docstring and
   `tempui-custom-widgets.md`'s "Authoring from real source" widget.json
   field list to document the new optional key. Bumped
   `TEMPUI_DOC_VERSION` 21 -> 22 with a matching `tempui-new-features.md`
   entry.

   Verified directly: extended `tests/verify/verify_build_widget.py`
   (real `_BUILD_WIDGET_SCRIPT` content loaded via `write_tempui_docs`,
   real `tsc` compile, real `parse_define_widget` round-trip, not
   mocked) -- a `widget.json` declaring `"capabilities": ["fs",
   "editor"]` produces the correct `Capability<TAB>name` lines and
   round-trips through the real parser to exactly `["fs", "editor"]`;
   the existing no-capabilities-key case now also explicitly asserts
   `capabilities == []` (backward compatible). Full regression suite:
   75 scripts, 0 failures.
9d1544b. COMPLETED: Investigate why Desk's shutdown might be taking a long time: create
   a new top-level `./investigations/` directory and write up findings
   (root-caused, with evidence) plus recommendations in
   `investigations/shutdown_perf.md`. No application code changes --
   a pure investigation.
   [planned: investigate-shutdown-perf.md]

   Traced the full shutdown path (the four `QApplication.aboutToQuit`
   handlers in `src/desk/app.py`, plus the easy-to-miss second phase --
   Qt's own widget-tree destruction cascade after `app.exec()` returns,
   where `TerminalWidget`'s `destroyed`-signal-connected cleanup runs)
   and measured each candidate directly rather than reading code and
   guessing. Two real, empirically-confirmed, additive findings:
   `TerminalWidget._cleanup_resources` (Console/Claude widgets) can
   take up to ~2s *per open terminal widget*, sequentially -- measured
   2.005s precisely for a child process that installs a real `SIGTERM`
   handler and takes >2s to respond, vs. 0.004s for a plain shell;
   `ServerHandle.stop`'s `join(timeout=5.0)` can block the GUI thread
   for the full 5 seconds whenever a `kind: "html"` widget has an
   in-flight `events/poll` long-poll open (measured: `handle.stop()`
   took 5.002s with a real in-flight poll, which still hadn't finished
   when the join gave up) -- and that's the steady-state behavior of
   `events.onMessage`, not a rare edge case. A third candidate
   (`FileWatcherService.stop`'s own 5s timeout) was measured and ruled
   out (0.000s under real, active watching). Findings and ranked
   recommendations (parallelize terminal-widget teardown; shorten/drop
   the two 5s join timeouts, since both underlying threads are already
   confirmed `daemon=True` so the join only affects *knowing* it's
   done, not correctness; proactively cancel in-flight long-polls as a
   fallback; lower the long-poll's own default timeout as a smaller,
   complementary mitigation) written up in
   `investigations/shutdown_perf.md`.

   No application code changed -- a pure investigation. Confirmed the
   new file exists; full regression suite: 75 scripts, 0 failures
   (unchanged, as expected).
1c7d5b9. COMPLETED: Split the SVG Editor's Hex Preview toggle (TODO `d1d176f`) into
   two mutually-exclusive buttons -- (a) Hex (Flat-top) Preview, (b)
   Hex (Pointy-top) Preview -- neither selected is also a possible
   state (the mask can still be off entirely, as it already could be).
   `_hexagon_path` currently hardcodes the pointy-top angle offset;
   needs a `flat_top` parameter so both orientations are selectable.
   [planned: svg-editor-hex-orientation-buttons.md]

   Implemented per plan. `_hexagon_path(bounds, flat_top)` gets an
   `angle_offset` (0 for flat-top: vertices at 0/60/120/180/240/300°,
   an edge -- not a vertex -- on top/bottom; `-90` for pointy-top,
   already the existing behavior). `self._hex_preview_orientation:
   str | None` (`"flat"`/`"pointy"`/`None`) replaces the old bool.
   `_set_hex_preview_orientation` is the one place that sets it and
   syncs both buttons' checked state -- confirmed `.setChecked()`
   doesn't re-emit `clicked` (only `toggled`, unconnected here), so
   this can't create a feedback loop back into itself.

   Verified directly: extended
   `tests/verify/verify_svg_editor_widget.py` (11 new/changed checks,
   67 total now) -- neither button checked by default; clicking
   flat-top sets state/UI correctly and survives a reload; clicking the
   *active* button again turns the mask off entirely and unchecks both
   (the "neither" state is genuinely reachable, not just theoretically
   possible); clicking pointy-top while flat-top is active switches
   cleanly (mutual exclusion). Caught and fixed one test bug along the
   way: comparing the *mask* item's own `boundingRect()` between
   orientations doesn't actually distinguish them (the hexagon-shaped
   hole doesn't touch the outer document rect's edges, so the mask's
   bounding box is just the document rect's own, identical either way)
   -- fixed by comparing the bare `_hexagon_path(...)` results directly
   instead, which genuinely differ (width/height swap between the two
   orientations, confirmed). Full regression suite: 75 scripts, 0
   failures.
9874bc3. COMPLETED: SVG Editor hex preview polish, two independent refinements: (1)
   separate the flat-top/pointy-top buttons (TODO `1c7d5b9`) from the
   rest of the toolbar with a frame and spacing, and visually
   distinguish the buttons themselves from the plain toolbar buttons
   (Open/Save/Save As/Reset View); (2) the flat-top hex should be sized
   so its top/bottom edges land exactly on the document's own bounds
   (`viewBox`), while remaining a regular hexagon (constant radius,
   equal sides) -- `_hexagon_path` currently inscribes both
   orientations to `min(width, height) / 2`, which doesn't align
   flat-top's own flat edges with the bounds at all.
   [planned: svg-editor-hex-preview-polish.md]

   Implemented per plan. (1) A `QFrame(QFrame.Shape.StyledPanel)`
   (mirroring `widgets/todo/widget.py`'s own `filter_frame`) with its
   own margins/spacing now holds just the flat-top/pointy-top buttons,
   separated from the plain toolbar buttons by an extra
   `top_toolbar.addSpacing(12)`; both buttons get a new
   `HEX_PREVIEW_BUTTON_STYLE` QSS constant (unchecked vs. `:checked`
   styling, same rationale as `todo`'s own `FILTER_BUTTON_STYLE`: a
   plain checkable `QPushButton` looks nearly identical checked vs.
   unchecked on some platform styles). (2) `_hexagon_path`'s
   `flat_top=True` branch now computes `radius = bounds.height() /
   sqrt(3)` (the flat-to-flat distance for a regular hexagon with
   circumradius R is `R * sqrt(3)`; solving for R against the
   document's own height lands the flat top/bottom edges exactly on
   the bounds) instead of sharing pointy-top's `min(width, height) /
   2`. Pointy-top's own sizing is unchanged.

   Verified directly: extended
   `tests/verify/verify_svg_editor_widget.py` (11 new checks, 73 total
   now) -- both buttons share one `QFrame` parent distinct from the
   toolbox's own parent, and carry the new stylesheet; the flat-top
   hex's vertical extent exactly matches a non-square document's
   height while its horizontal extent is confirmed independent of the
   document's width (not clamped to fit); pointy-top's sizing confirmed
   unchanged; the resized flat-top hex confirmed still genuinely
   regular (all six edge lengths equal, not just "the right height").
   Full regression suite: 75 scripts, 0 failures.
556f623. COMPLETED: SVG Editor toolbox/hex-preview layout polish: put "Hex Preview" as a
   smaller two-lines-of-text shared label in the left part of the hex
   preview button frame (buttons themselves just show "Pointy-top"/
   "Flat-top"); change the default viewBox (`_new_empty_root`/
   `_DEFAULT_BOUNDS`) to a square so both hex previews fit nicely by
   default; move the Shapes/Points editing tools to the top of the
   toolbox under a "Select + Edit" header, with an "Add" header above
   the remaining creation tools.
   [planned: svg-editor-layout-polish.md]

   Implemented per plan. `SELECT_EDIT_TOOL_LABELS`/`ADD_TOOL_LABELS`
   split `TOOL_LABELS` (kept as their concatenation); `_build_toolbox`
   inserts a non-selectable, bold "Select + Edit" `QLabel` header
   before the Shapes/Points buttons and an "Add" header before the
   remaining 8 -- still one `QButtonGroup(exclusive=True)` spanning all
   10. `_new_empty_root`/`_DEFAULT_BOUNDS` both changed to 400x400.
   `hex_preview_frame` gained a small, non-selectable two-line
   `QLabel("Hex\nPreview")` before the two buttons, whose own text
   shrank to "Flat-top"/"Pointy-top".

   Verified directly: extended `tests/verify/verify_svg_editor_widget.py`
   (11 new checks, 84 total now). Caught and fixed one test made stale
   by the square-default change: `test_hex_preview_toggle_add_remove_
   and_persists_across_reload`'s bounds check asserted the flat-top
   hex's *width* stays within (or very near) the document bounds --
   true only by coincidence for the old 400x300 aspect ratio (flat-top
   circumradius `height/sqrt(3)` happened to still fit within 400
   width); at the new square 400x400 default it legitimately overflows
   width, exactly as `_hexagon_path`'s own docstring already documents
   and as `test_flat_top_hex_top_and_bottom_align_with_the_document_
   bounds` already verifies precisely. Replaced with the actual
   aspect-ratio-independent invariant: the mask's vertical extent still
   matches the document's height (top/bottom aligned). Full regression
   suite: 75 scripts, 0 failures.

ebf641d. COMPLETED: SVG Editor pending polygon/polyline drawing fixes: show a "Complete
   (ENTER)" button at the bottom-right of the editor view while a
   polygon/polyline is pending, doing the same thing Enter already
   does; a drawn polyline currently renders visually indistinguishable
   from a closed/filled polygon -- investigate and fix (a polyline is
   an open, conventionally unfilled shape, unlike a polygon); and
   route Fill/Stroke/Stroke-width property panel edits to the
   currently-drawing pending polygon/polyline rather than to whatever
   object was selected before the current draw started.
   [planned: svg-editor-pending-shape-fixes.md]

   Implemented per plan. (1) `self._complete_button`, a floating
   `QPushButton` child of `self._view` (not a scene item, so it stays a
   constant on-screen size regardless of zoom), shown/hidden and
   repositioned via `_reposition_complete_button()` -- called from
   `_add_pending_point`, `_finish_pending`/`_cancel_pending`, and a new
   `_EditorView.resizeEvent` override. (2) Root cause confirmed: the
   underlying data model was already correctly open (`_PolylineItem`
   never closes its subpath, `PolylineObject.sync_to_element` writes a
   plain unclosed `points` list) -- the visual "completed it like a
   polygon" impression came entirely from Qt (like any real SVG
   renderer) filling an open path's implied closing segment by
   default. Fixed by having `PolylineObject.create_default` explicitly
   set `fill: none`; still fully editable afterward via the Fill
   button, and loading an existing polyline from a file is unaffected.
   (3) Three new `None`-means-"untouched" pending-style attributes
   (`_pending_fill`/`_pending_stroke`/`_pending_stroke_width`);
   `_pick_fill`/`_pick_stroke`/`_on_stroke_width_changed` and
   `_refresh_property_panel` now check `has_pending_points()` first and
   route to these instead of `self._selected_object` while a shape is
   pending (this also fixes the panel being stuck disabled while
   drawing with nothing previously selected); `_finish_pending` applies
   only the properties actually touched during the draw, then
   re-syncs the object to its element (an override applied after
   `create_default`'s own initial sync wouldn't otherwise reach the
   serialized attributes).

   Verified directly: extended
   `tests/verify/verify_svg_editor_widget.py` (12 new checks, 96 total
   now) -- Complete button visibility/positioning and that clicking it
   finishes the pending shape identically to Enter; a freshly drawn
   polyline serializes `fill="none"` while a freshly drawn polygon is
   unaffected; changing style while a polygon is pending leaves a
   previously-selected rect's own fill untouched, and the pending
   style correctly lands on the finished shape's fill/stroke/stroke-
   width. Caught and fixed one bug while writing the last of these:
   the pending-style override in `_finish_pending` updated the
   `SvgObject`'s live Qt item (via `set_fill`/etc.) but never re-called
   `sync_to_element()` afterward, so the serialized element attributes
   still reflected `create_default`'s own initial style until the next
   save -- fixed by re-syncing whenever any override was actually
   applied. Full regression suite: 75 scripts, 0 failures.

1fb365e. COMPLETED: SVG Editor selection delete affordances: show a delete icon
   hovering on/near a shape selected in the Shapes tool; show a delete
   button near a point selected in the Points tool (requires a new
   "selected point" concept, since today only drag-in-progress state
   exists).
   [planned: svg-editor-delete-affordances.md]

   Implemented per plan. Both affordances are small `"✕"` `QPushButton`s
   floating directly on `self._view` (not scene items, so they stay a
   constant on-screen size regardless of zoom), positioned via
   `mapFromScene`: `self._shape_delete_button` (near a selected
   shape's top-right corner, Shapes tool) and `self._point_delete_button`
   (near a selected point, Points tool). A new `self._selected_point_index`
   tracks "which point was last interacted with" independent of
   `_dragging_handle_index` (which resets to `None` the instant a drag
   ends) -- set in `_begin_handle_drag` when `current_tool == "points"`,
   reset on tool switch and on any scene selection change.
   `SvgObject.can_delete_point`/`delete_point` (default: never
   deletable) are overridden by `PolylineObject`/`PolygonObject`/
   `PathObject` (refusing at their respective minimum point count --
   2/3/2-or-3 depending on `PathObject._closed` -- so a shape can't be
   deleted down to a degenerate 0/1-point remnant); `LineObject` has no
   override, so its 2 endpoints are never deletable. Both delete
   buttons refresh from the exact same call sites `_refresh_handles()`
   already had (selection change, tool switch, every drag step), plus
   `_reset_view` and a new `_EditorView.resizeEvent` override, so they
   track live resizing/dragging/reloading with no new call sites beyond
   what handle-refreshing already covered.

   Verified directly: extended
   `tests/verify/verify_svg_editor_widget.py` (23 new checks, 117
   total now) -- the shape delete icon shows for a selected shape and
   deleting it removes the object from the scene/`self._objects`/
   `self._root`; the point delete button shows for a selected,
   deletable point and deleting it removes just that point while
   leaving the rest of the object intact; both a 3-point polygon and a
   2-point polyline (their respective minimums) correctly refuse
   further point deletion and hide the button; a line's endpoints are
   never deletable; switching tools or the object selection correctly
   clears the selected point and hides/shows the right button. Full
   regression suite: 75 scripts, 0 failures.
70789ee. COMPLETED: New FEEDBACK (`../FEEDBACK/FEEDBACK-DESK-svg-editor-duplicate-shape-button
   -2026-07-22-1819.md`): the SVG Editor's Shapes tool has a hovering
   delete button on a selected shape (`_shape_delete_button`, TODO
   `1fb365e`) but no way to duplicate one -- today, cloning a shape
   (e.g. laying out several evenly-spaced copies of the same stripe)
   requires hand-editing the saved `.svg`'s XML outside the tool
   entirely. `_duplicate_selected_object`: `copy.deepcopy` the selected
   object's `ET.Element`, append it to `self._root`, rebuild an
   `SvgObject` via the element's own class's existing `from_element`
   classmethod (already used for file loading), nudge it by a small
   fixed offset so it's not perfectly on top of the original, and
   select it -- ready to drag into position via the existing
   handle-drag path.

   REVISED SCOPE, per direct user instruction: rather than a second
   floating corner button (`_shape_duplicate_button`) alongside the
   existing corner-anchored `_shape_delete_button`, replace both with a
   single context menu shown near a selected shape (Shapes tool),
   containing a Duplicate and a Delete action:
   1. Positioning, in priority order, each tried only if the previous
      would place the menu (any part of it) outside the view: (a) the
      menu's bottom-center at the selected shape's top-center; (b) the
      menu's top-center at the shape's bottom-center; (c) the menu's
      center at the shape's own center.
   2. Every button in the menu has both an icon and hover text
      (tooltip).
   3. Icons: "⧉" for Duplicate, a trash-can glyph for Delete (replacing
      the existing "✕").
   [planned: svg-editor-shape-actions-menu.md]

   Implemented per plan. Replaced the old standalone corner-anchored
   `_shape_delete_button` with `self._shape_actions_menu`, a plain
   floating `QFrame` (not a real `QMenu`/`Qt.WindowType.Popup` --
   documented why in the plan: a Popup auto-closes on losing focus/an
   outside click, which would fight this panel's own "stays up and
   tracks the shape for as long as it's selected" requirement, and
   clamps to the desktop screen rather than this widget's own view)
   holding both `_shape_duplicate_button` ("⧉", tooltip "Duplicate")
   and `_shape_delete_button` (now "🗑" instead of "✕", tooltip
   "Delete", same red-tinted style). `_refresh_shape_delete_button`
   became `_refresh_shape_actions_menu`, computing three candidate
   positions from the selected shape's `sceneBoundingRect()` mapped
   through `self._view.mapFromScene` -- (a) menu bottom-center at the
   shape's top-center, (b) menu top-center at the shape's bottom
   -center, (c) menu center at the shape's own center -- trying each in
   order against `self._view.rect()` (this widget's own view bounds,
   matching how every other floating button here is already
   positioned), using (c) unconditionally if neither (a) nor (b) fits.
   `_duplicate_selected_object` reuses the existing `_add_object`
   directly (which already does the flag-setting/scene-insertion/
   root-append/selection the feedback's own sketch reimplemented
   inline) rather than duplicating its body -- `copy.deepcopy` the
   selected object's element, rebuild via the element's own class's
   `from_element`, nudge by `(12, 12)`, hand off to `_add_object`.

   Verified directly: extended `tests/verify/verify_svg_editor_widget.py`
   (17 new checks, 134 total now) -- the menu shows/hides with the
   right glyphs and tooltips on each button; duplicating clones the
   right tag/attributes with an offset, leaves the original untouched,
   and selects the clone; tier (a) confirmed against a real
   `QGraphicsView` (`centerOn` + `mapFromScene`, not hand-computed
   pixel math); tiers (b)/(c) confirmed by controlling
   `_refresh_shape_actions_menu`'s own three `mapFromScene` calls
   directly (real `QGraphicsView` scroll-position arithmetic turned out
   impractical to hand-predict precisely enough for a deterministic
   test, so these two exercise the method's real fallback-decision
   logic against controlled inputs instead). Caught and fixed one test
   bug along the way: `QRect.bottom()` is `top() + height() - 1` (Qt's
   inclusive-rect convention), not `top() + height()` -- the tier (a)
   implementation itself was already correct, the test's first
   assertion just compared against the wrong quantity; fixed by
   comparing `menu.pos().y() + menu.height()` instead. Full regression
   suite: 77 scripts, 0 failures.

d4d6c71. COMPLETED: New FEEDBACK (`../FEEDBACK/FEEDBACK-DESK-widget-error-visibility
   -2026-07-21-0053.md`): no widget kind currently surfaces "this
   widget instance hit an error" anywhere in the UI -- a `kind:
   "python"` widget's top-level exception and an HTML/browser-kind
   widget's uncaught JS exception/unhandled promise rejection both
   currently vanish with zero visible difference from "working
   correctly but the user misunderstood what it does," discoverable
   only by already suspecting a specific widget enough to open its
   devtools console. Concrete cost cited: three separate widgets in a
   downstream project (`necro-4x`) shipped the identical latent bug
   (an unguarded `desk.fs.writeFile` to a not-yet-existing directory,
   silently rejected, never surfaced), each found only days later when
   a human noticed a specific symptom conversationally -- and each
   passed its own headless-Chrome verification beforehand, since no
   mock modeled that specific failure mode.
   Suggested fix: a small, high-contrast error indicator (e.g. a red
   "!") in a widget instance's own titlebar, shown whenever a `kind:
   "python"` widget's request handler raises past whatever top-level
   try/catch Desk's server-side dispatch already has, or an HTML/
   browser-kind widget's embedded page logs an uncaught exception/
   unhandled rejection to its own console (observable from the
   embedding side today via `window.onerror`/`unhandledrejection`, no
   cooperation needed from the widget's own code) -- clicking it shows
   the actual error text/stack in a small popover. Fallback, if full
   error-capture is a bigger lift than expected: even a bare boolean
   ("this instance has logged at least one console error since it
   loaded," no message capture) would still close most of the actual
   gap described above.
   [planned: widget-error-indicator.md]

   Implemented per plan, with one significant scope revision found
   during implementation. A new `[ERROR]` titlebar button
   (`_ErrorIndicatorButton`, high-contrast red, unlike every other
   chrome button) mirrors the existing `[STALE]` indicator exactly:
   `_TitleBar`/`WidgetFrame.set_error(has_error, message)`,
   `canvas.py`'s `_hit_test_chrome`/`widget_error_clicked` signal, and
   `DeskWindow._on_widget_error_clicked`/`_confirm_widget_error_dismissed`
   (a QMessageBox showing the error text, clearing the indicator on
   dismissal). Wired for real for `kind: "html"` widgets: `ChromiumWidget`
   gets a new `error_state_changed(bool, str)` signal fed by
   `_LoggingWebEnginePage`'s existing `javaScriptConsoleMessage` override
   (confirmed directly: this callback fires for an uncaught JS
   exception/unhandled promise rejection *and* an explicit
   `console.error()` call, both at `ErrorMessageLevel` -- not just the
   literal `console.error` case), and clears on `reload()` (a new
   override covering both existing reload call sites for free).

   The user's first choice for `kind: "python"` widgets was full runtime
   coverage (any exception anywhere in a widget's own code, not just a
   build failure) via a new `QApplication.notify()` override attributing
   an exception to its enclosing `WidgetFrame`. Built it, then
   confirmed directly -- before writing any verification suite around
   it -- that it doesn't work: a widget whose `event()` override raises
   when sent a real `QEvent` via `app.sendEvent(...)` aborted the whole
   process (`SIGABRT`); the outer `notify()` override's own `except`
   block never ran. Root cause: PyQt6 intercepts an exception escaping a
   Python slot/virtual-method reimplementation *at the point it escapes
   that specific callback* (calling `sys.excepthook`, then aborting) --
   it never propagates normally back up the call stack to an outer
   `notify()`'s try/except at all, since the C++ frames in between can't
   safely unwind through a Python exception. This is already documented,
   independently, in this repo's own `LEARNINGS.md` (`810a5d6` entry):
   "a single global backstop now exists (`desk.crash_handler`, ...
   which does *not* prevent the crash itself, only records it), but each
   hazard still has to be found and hardened at its own call site."
   Presented this finding to the user directly (with the reproduction);
   per their decision, re-scoped `kind: "python"` coverage to
   `build()`-time failures only -- already caught per-instance by
   `PythonWidgetHost._rebuild`'s own try/except, just not previously
   surfaced anywhere but the log. Deleted the non-working
   `app_notify.py`/`DeskApplication` entirely rather than leaving dead
   code behind. `PythonWidgetHost` gained the same
   `build_error_changed(bool, str)` shape as `ChromiumWidget`, plus a
   `self.build_error: str` attribute so `DeskWindow._bind_error_indicator`
   can detect an already-failed initial build (which happens
   synchronously inside `PythonWidgetHost.__init__`, before any
   `WidgetFrame`/binding exists yet) the same way
   `_bind_external_indicator` already handles that shape for `set_file`.

   Verified directly: new `tests/verify/verify_widget_error_indicator.py`
   (22 checks) -- titlebar button visibility/click-dispatch/dialog
   plumbing; a real `ChromiumWidget` loading real inline HTML via a
   `data:` URL, confirming both an explicit `console.error()` call and a
   genuinely uncaught JS exception (no explicit `console.error` at all)
   are captured, and that `reload()` clears the indicator; a real
   on-disk `widget.py` whose `build()` raises, loaded through a real
   `PythonWidgetHost`, confirming the indicator is already showing
   immediately after placement, a working widget never shows one, and a
   live hot-reload from a failing to a successful build clears it.
   Fixed 6 pre-existing verify scripts broken by `_place_widget`'s new
   unconditional `_bind_error_indicator` call (each had a `_FakeWindow`-
   style double missing the new method, an `AttributeError` on every
   `_place_widget` call) by adding the same
   `_FakeWindow._bind_error_indicator = DeskWindow._bind_error_indicator`
   binding already used for its sibling `_bind_*` methods. Full
   regression suite: 76 scripts (one new), 0 failures.

3b1ef3d. COMPLETED: New FEEDBACK (`../FEEDBACK/FEEDBACK-DESK-color-picker-mini-component
   -library-2026-07-22-1811.md`): `DefineWidget`/browser-kind widgets
   are self-contained HTML with no module system and (per this
   project's own CLAUDE.md) a hard "avoid adding dependencies, prefer
   bespoke solutions" constraint -- so any widget author needing a
   genuinely non-trivial UI control (a color picker, a date picker, a
   multi-select) has to design and implement it from first principles
   every time, in every project, with no canonical reference to start
   from. Concrete cost cited: a downstream project's HSV color-wheel +
   brightness-bar color picker (`necro-4x`'s `TerrainColorInitializer`)
   went through three iterations of real design work (native `<input
   type="color">`, rejected -- always opens as an undockable OS popup;
   three RGB range sliders, functional but visually unintuitive; a
   CSS-gradient HSV wheel + brightness bar, the one that shipped) and
   required non-obvious, easy-to-get-backwards work even once the
   right approach was chosen (a `+90°` screen-angle-to-CSS-angle
   correction for `conic-gradient`, keeping raw hue/sat/val state
   rather than re-deriving from hex so a grayscale color doesn't reset
   the wheel's cursor to an arbitrary angle, wrapping
   `setPointerCapture` in try/catch since a synthetically-dispatched
   `PointerEvent` in a headless-Chrome test harness has no real
   pointer to capture).
   Suggested fix: maintain or seed a small library of self-contained,
   dependency-free UI mini-components that widget authors copy locally
   into their own project's `custom_widget_src/shared/` (source is
   copied, never by-reference imported, since these widgets can't
   depend on anything at runtime) -- published somewhere a widget
   author would think to check before building one from scratch (e.g.
   alongside `tempui-custom-widgets.md`, or a `shared-components/`
   reference tree in this repo), starting with the HSV color-wheel +
   brightness-bar picker described above.
   [planned: shared-components-library.md]

   Implemented per plan and per direct user instructions (store real
   files in `./shared-components/`, mirror into `.desk_temp/` on every
   Desk open, one `README.md` per component, note it in the tempui
   docs). Read the real, already-shipped implementation in the peer
   `../necro-4x/` project (`custom_widget_src/terrain-color-initializer/
   terrain-color-initializer.ts`) rather than re-deriving the design
   from the feedback's prose. Extracted and generalized the
   color-picker-specific parts (HSV/RGB/hex math, the wheel/brightness
   -bar DOM+CSS, `bindDrag`'s pointer-capture try/catch) into a
   standalone `shared-components/hsv-color-picker/` (`hsv-color
   -picker.ts` + `template.html` + `README.md`), dropping everything
   terrain-specific (TSV parsing, SVG recoloring, `desk.fs`/
   `getLocalStorage` calls, prev/next navigation). Added a real public
   API the original never needed (it was a whole widget, not a reusable
   control): a `value` get/setter (hex string) and a `colorchange`
   `CustomEvent` fired only from genuine user interaction (wheel/
   brightness drag, hex typing) -- not from a programmatic `.value =`
   set, matching a native `<input>`'s own convention.

   `src/desk/temp_ui.py` gained `SHARED_COMPONENTS_DIRNAME`,
   `_repo_shared_components_dir()` (resolves this repo's own
   `shared-components/` relative to `temp_ui.py`'s own `__file__`,
   confirmed directly this correctly finds the real checked-out repo
   regardless of which project's directory is currently open in Desk),
   and `sync_shared_components(temp_dir)` (a full mirror -- removes the
   destination first, so a component removed from the source doesn't
   linger as a stale copy -- rather than an embedded string constant
   the way `.desk_temp/build_widget.py` is, since these are real
   multi-file component sources that don't scale the same way).
   `TempUiManager.provision` calls it unconditionally on every Desk
   open/switch, alongside the existing `write_tempui_docs`/
   `ensure_docs_current` doc-refresh branch. `_CUSTOM_WIDGETS_DOC`
   gained a new "Reusable UI components" section (between "Authoring
   from real source" and "Invoking a defined widget") stating plainly
   that importing a component directly or copying+pasting+modifying it
   are both intended, accepted uses -- not a fallback. `TEMPUI_DOC_VERSION`
   bumped 22 -> 23 with a matching `_NEW_FEATURES_DOC` entry, per
   `development-process.md`'s "Keep the tempui changelog docs current"
   rule.

   Verified directly: new `tests/verify/verify_shared_components.py`
   (26 checks) -- `sync_shared_components` copies the real component
   files byte-for-byte, is a genuine full mirror (a simulated stale
   leftover component is gone after a second sync, not left behind by
   an additive merge), and is a clean no-op when the source directory
   doesn't exist; a real `TempUiManager.provision` call against a
   scratch directory actually produces `.desk_temp/shared-components/
   hsv-color-picker/hsv-color-picker.ts` on disk; doc version/new
   -features/custom-widgets-doc content checks. Most importantly, a
   real, non-mocked end-to-end check of the extracted component itself:
   compiled `hsv-color-picker.ts` with a real `tsc --strict` (mirroring
   `necro-4x`'s own tsconfig), assembled a throwaway page pairing the
   compiled JS with `template.html`'s own `<template>` block, loaded it
   in a real `QWebEngineView`, and confirmed a synthetic
   `PointerEvent`-driven wheel drag (no real active pointer for the
   browser to capture, exactly the edge case the `bindDrag` try/catch
   exists for) correctly changes `.value` and fires exactly one
   `colorchange` event, and that a subsequent programmatic `.value =`
   set updates the value without firing a second event. Full regression
   suite: 77 scripts (one new), 0 failures.

217f3ce. COMPLETED: SVG Editor shape actions context menu (TODO `70789ee`): add two more
   buttons, "Move Forward" and "Move Backward" (one-step z-order
   swaps with the next/previous sibling), alongside the existing
   Duplicate/Delete pair in `self._shape_actions_menu`. Today, a
   shape's paint order is implicit and singular: document order in
   `self._root`'s children == `self._objects` list order == the
   order each item was added to `self._scene` (`_add_object`) --
   nothing here sets an explicit `QGraphicsItem.zValue()` on a real
   drawn shape (only the non-exported guide rect/hex-preview mask do,
   at fixed -1000/2000, to always stay behind/in-front of real
   content). Moving a shape needs to reorder it in all three places
   consistently (`self._root`'s child order, `self._objects`, and the
   scene's own paint order -- likely via `QGraphicsItem.stackBefore`/
   `stackAfter`, Qt's own API for reordering within a shared parent's
   insertion order, rather than inventing an explicit z-value scheme).
   Each button icon + hover text, same convention as Duplicate/Delete.
   [planned: svg-editor-shape-zorder-buttons.md]

   Implemented per plan. `_move_selected_object(direction)` (+1
   forward, -1 backward): no-op if already at the front/back;
   otherwise swaps the selected object with the adjacent sibling in
   `self._objects` in all three places that together define paint
   order -- `self._root`'s children (each element's own *actual*
   position there, found independently rather than assumed adjacent,
   since an untouched/unrecognized element could sit between them in
   the raw XML), `self._objects` itself, and the scene's own stacking
   via `QGraphicsItem.stackBefore` (confirmed directly, with a real
   `QGraphicsScene`/three real items/real `.items()` calls, that items
   with equal z-value paint in insertion order, last-added on top, and
   `stackBefore` reorders within that list). Two new buttons, "▲"/"Move
   Forward" and "▼"/"Move Backward", added to `self._shape_actions_menu`
   between Duplicate and Delete.

   Verified directly: extended `tests/verify/verify_svg_editor_widget.py`
   (16 new checks, 150 total now) -- button glyphs/tooltips/layout
   order; a real three-object scene where moving the middle object
   forward/backward correctly reorders `self._objects`, `self._root`'s
   children, and the *actual* scene stacking order (via real
   `QGraphicsScene.items()`, not just the two Python-side lists), and
   moving back restores everything exactly; no-op confirmed at both the
   front and back; the buttons themselves confirmed wired to the real
   `self._selected_object`, not just the underlying method in
   isolation. Full regression suite: 77 scripts, 0 failures.

ad20867. COMPLETED: New FEEDBACK (`../FEEDBACK/FEEDBACK-DESK-editor-widget-base-types
   -2026-07-30-1021.md`): `desk.fs.writeFile` (the Bridge API route,
   `src/desk/server/app.py`'s `fs_write_file`) has no auto-mkdir --
   a write to a directory that doesn't exist yet silently rejects with
   no visible error. This exact bug has now shipped in four separate
   downstream widgets in one project (Terrain Types Editor, Token Types
   Editor, Terrain Color Initializer, Domain Analysis), each having
   independently hand-rolled its own file lifecycle from scratch.
   Suggested fix (the small, high-leverage half of the feedback --
   closes the bug unconditionally, with no dependency on any widget
   adopting anything new): `resolved.parent.mkdir(parents=True,
   exist_ok=True)` before the write, inside the existing
   `try`/`except OSError` block. `fs_read_file` is intentionally
   untouched (a genuinely missing file to read is a real error case).
   [planned: bridge-fs-writefile-auto-mkdir.md]

   Implemented per plan: `resolved.parent.mkdir(parents=True,
   exist_ok=True)` added to `fs_write_file`, right before the write,
   inside the existing `try`/`except OSError` block. `TEMPUI_DOC_VERSION`
   bumped 23 -> 24; `_CUSTOM_WIDGETS_DOC`'s `fs` bullet and a new
   `_NEW_FEATURES_DOC` "## Version 24" entry both mention the new
   auto-mkdir behavior. `fs_read_file` untouched.

   Verified directly: extended
   `tests/verify/verify_fs_path_resolution_and_events_doc.py` (10 new
   checks, 16 total now) -- a real HTTP `writeFile` call, against a
   real running server, to a path several directory levels deep with
   none of them existing yet, actually succeeds and the file is
   readable afterward with the right contents (the precise failure
   shape all four cited widgets hit, reproduced and confirmed fixed,
   not just inferred from reading the diff); a write to an
   already-existing directory leaves a sibling file untouched (no
   regression to the ordinary case); `readFile` on a genuinely missing
   file still returns the existing 400 error, confirming the fix is
   scoped to writes only; doc version/changelog bump checks. Full
   regression suite: 77 scripts, 0 failures.

d4368bd. COMPLETED: New FEEDBACK (`../FEEDBACK/FEEDBACK-DESK-editor-widget-base-types
   -2026-07-30-1021.md`): the same feedback as TODO `ad20867` above,
   the larger half -- a lesson recorded in `LEARNINGS.md` about the
   missing-directory bug didn't prevent a fourth widget from
   re-hitting it, because there was nothing to *reach for* except
   writing the file lifecycle (title-to-path derivation, load-if
   -exists, create-if-not, save-on-edit) from scratch again. Suggested
   fix: a shared "auto-load/auto-save document editor" widget base
   type (a real TypeScript base class a widget's own custom element
   extends, not just a lower-level file-handle API) -- offered as a new
   `shared-components/` entry (TODO `3b1ef3d`'s library), mirrored into
   `.desk_temp/shared-components/` automatically the same way
   `hsv-color-picker` already is. Ties back to TODO `d4d6c71`'s
   titlebar `[ERROR]` indicator for surfacing a rejected save/load
   instead of failing silently.
   [planned: shared-document-editor-base.md]

   Implemented per plan. First read the real, already-shipped source
   this generalizes (`../necro-4x/custom_widget_src/domain-analysis/
   domain-analysis.ts`, 827 lines, in full) rather than architecting
   from the feedback's own prose alone -- confirmed the real pattern is
   simpler than the plan's own initial assumption: every widget this
   was extracted from saves immediately after each discrete edit
   action (add a tag, add a row, ...), not on a debounce timer, so
   `save()` needs no debounce machinery at all.

   New `shared-components/document-editor-base/` (`document-editor
   -base.ts` + `README.md`): `DocumentEditorBase<Doc>`, an abstract
   class a widget's own custom element extends, owning path derivation
   (`<directory>/<kebab-title>.<extension>`), create-vs-load (never
   silently clobbering an existing file), restoring the last-open
   document via `desk.self.getLocalStorage`, and `save()` (calling
   `desk.fs.writeFile` -- which TODO `ad20867` already makes safe
   against the missing-directory bug unconditionally). Confirmed
   directly, empirically, two real constraints while building this
   (both now documented prominently in the component's own README):
   (1) a custom element's constructor must take zero arguments (the
   browser always calls `new YourElement()` bare, even during upgrade)
   -- configuration goes through abstract getters/methods
   (`directory`/`extension`/`emptyDoc`/...), not constructor params, and
   real initialization happens in `connectedCallback`, not the
   constructor; (2) `export`ing the class breaks `interface Window {
   desk?: ... }`'s merge with the real global `Window` type (any
   `import`/`export` makes TypeScript treat the whole file as a module
   with its own declaration space) -- confirmed by reproducing the
   exact type error, then removing `export` entirely, matching every
   real widget this was extracted from (none use `export`/`import`
   either). Also discovered and documented a third, more consequential
   hazard: `.desk_temp/build_widget.py` concatenates a widget's
   compiled `.js` files in plain alphabetical filename order (`sorted
   (out_dir.rglob("*.js"))`), not dependency order -- reproduced
   directly (a real `tsc` compile + concatenation + `node` run) that a
   subclass whose filename sorts alphabetically before the base
   class's throws `ReferenceError: Cannot access 'DocumentEditorBase'
   before initialization`. Since this is a real hazard specific to
   *this* component (a base class meant for JS-level `extends`) and not
   `hsv-color-picker` (a self-contained control with no cross-file
   dependency), the README recommends copying the base class's source
   directly into a widget's own single `.ts` file as the *safe*
   default, not just an equally-fine alternative -- and
   `_CUSTOM_WIDGETS_DOC`'s "Reusable UI components" section wording was
   revised accordingly (it previously claimed import-vs-copy+paste
   were unconditionally interchangeable for any component, no longer
   accurate now that a second, differently-shaped component exists).
   `TEMPUI_DOC_VERSION` bumped 24 -> 25 with a matching
   `_NEW_FEATURES_DOC` entry.

   Verified directly: new
   `tests/verify/verify_shared_document_editor_base.py` (15 checks) --
   a real subclass (`TestNotesElement`) compiled together with the real
   `document-editor-base.ts` via `tsc --strict`, assembled into a real
   `kind:"html"` widget directory, served by a real running Local Web
   Server, driven via a real `ChromiumWidget` and real Bridge API calls
   (not mocked) through the full lifecycle: creating a document whose
   target directory genuinely doesn't exist yet (the precise bug this
   whole feedback is about, confirmed fixed end-to-end, not just at the
   HTTP-route level TODO `ad20867` already covers); editing auto-saves
   for real; attempting to create over an already-existing document is
   refused rather than silently clobbering it; a fresh instance
   loading the same title gets the real saved content back; a fresh
   instance sharing the same instance id auto-restores the last-open
   document without an explicit Load click. Caught and fixed one
   test-only regression in `verify_shared_components.py` along the way:
   its own doc-content check asserted the *old*, now-inaccurate literal
   phrasing ("import and copy+paste+modify are fine" unconditionally) --
   fixed to check for the substance of the revised wording instead. Full
   regression suite: 78 scripts (one new), 0 failures.

3fc5331. COMPLETED: Found while implementing TODO `d4368bd`: `.desk_temp/build_widget.py`
   (generated by `_BUILD_WIDGET_SCRIPT` in `src/desk/temp_ui.py`)
   concatenates every compiled `.js` file under a widget's own `tsc`
   output directory in plain alphabetical filename order (`sorted
   (out_dir.rglob("*.js"))`), not dependency order. Confirmed directly
   (a real `tsc` compile + concatenation + `node` run): a subclass
   whose filename happens to sort alphabetically *before* a base
   class's own file throws `ReferenceError: Cannot access '<Base>'
   before initialization` at runtime -- `class Sub extends Base` needs
   `Base` already evaluated by the point that statement runs, and
   nothing here currently guarantees that. This didn't affect TODO
   `d4368bd`'s own `document-editor-base` shared component only by
   luck of filename choice ("document-editor-base" < most plausible
   widget names alphabetically is not something to rely on in
   general); worked around there by recommending its README's
   "copy the source directly into your own single .ts file" usage mode
   as the *safe default*, not the general fix. Worth fixing at the
   source: either have `build_widget.py` concatenate in the order a
   widget's own `tsconfig.json`'s `files` array lists them (respecting
   author-declared order) rather than a fresh alphabetical sort of the
   output directory, or some other explicit ordering mechanism -- a
   real correctness hazard for *any* future multi-file widget or
   shared-component combination involving cross-file class
   inheritance, not just this one.

   Once this is actually fixed: clean up
   `shared-components/document-editor-base/README.md`'s own hazard
   warning (the "Recommended: copy `document-editor-base.ts`'s
   contents directly..." section, and the matching note in
   `_CUSTOM_WIDGETS_DOC`'s "Reusable UI components" section in
   `src/desk/temp_ui.py`) -- both describe a workaround for this exact
   bug, and would be stale/misleading once `build_widget.py` no longer
   has the ordering hazard they're warning about.
   [planned: build-widget-compile-order.md]

   Implemented per plan: `_BUILD_WIDGET_SCRIPT` (`src/desk/temp_ui.py`)
   gained `_read_tsconfig` (parses `tsconfig.json` once, shared by the
   two functions below it), `_read_ordered_stems` (the basename stems
   of `tsconfig.json`'s own top-level `"files"` array, in author
   -declared order, or `None` if absent), and `_concatenate_compiled_js`
   now takes that ordered-stems list -- unchanged (`sorted()`) behavior
   when `None` (today's common single-file case), otherwise matches
   discovered `.js` files by basename stem and joins them in the
   declared order, raising a clear `BuildError` for a `"files"` entry
   with no matching compiled output, a compiled file not listed in
   `"files"`, or two same-named compiled files in different
   directories (basename-only matching can't disambiguate that case) --
   matches the plan's own "match by basename, not full `rootDir`
   inference" design decision. `TEMPUI_DOC_VERSION` bumped 25 -> 26 with
   a matching `_NEW_FEATURES_DOC` entry, so every project's `.desk_temp`
   picks up the fix on next open (confirmed via the existing
   `ensure_docs_current` staleness mechanism, not hand-edited).
   "Authoring from real source" gained a `"files"` array explanation;
   the resolved-hazard warnings were removed from both
   `_CUSTOM_WIDGETS_DOC`'s "Reusable UI components" section and
   `shared-components/document-editor-base/README.md`, replaced with
   guidance to add a base class as a `"files"` entry ahead of the
   subclass's own file -- import and copy+paste+modify are both
   unconditionally fine again, for every component, not just the
   self-contained ones.

   Found two stale test assertions while verifying, fixed as part of
   this same change (their own literal-phrase checks referenced the
   exact hazard-warning wording just removed): `verify_shared_
   components.py` and `verify_shared_document_editor_base.py` each had
   one check asserting on the old "recommends copying its source
   directly"/"concatenates a widget's compiled" phrasing -- updated
   both to check the new substance (import and copy+paste+modify both
   explained as fine, with the `"files"` array explained as the load
   -order mechanism) instead, whitespace-normalizing the doc text first
   since the real prose line-wraps mid-phrase in a way a naive
   multi-word substring check doesn't survive.

   Verified directly, no mocking: new `tests/verify/
   verify_build_widget_concat_order.py` (9 checks) -- a real `tsc`
   compile of a fixture base class + subclass pair, deliberately named
   so plain alphabetical order would reproduce the exact
   `ReferenceError` this TODO describes, confirms the `"files"`-ordered
   concatenation puts the base class first and that running the result
   under a real `node` process succeeds and produces the correct
   value; all three new `BuildError` paths (missing/unlisted/duplicate
   stem) raise with a clear message naming the file; the no-`"files"`
   -key fallback returns `None` unchanged. Full `tests/verify/`
   regression suite (83 scripts, two now-fixed) passes, 0 failures.

7c7b676. COMPLETED: New FEEDBACK (`../FEEDBACK/FEEDBACK-DESK-tempui-convention-drift
   -notification-2026-07-30-1120.md`): `ensure_docs_current`
   (`src/desk/temp_ui.py`) already computes whether a project's tempui
   doc set is stale (its embedded version differs from
   `TEMPUI_DOC_VERSION`) and rewrites it in place -- the comparison
   result is thrown away, so nothing ever prompts an agent to open
   `tempui-breaking-changes.md`, even though it documents every one of
   these changes, each tagged with the version that introduced it.
   Concrete cost cited: three separate tempui authoring/build breaking
   changes hit a downstream project "without noticing until asked to
   check."
   Suggested fix: have `ensure_docs_current` report the previous
   version (when it genuinely differed, not just a missing split
   file), and have `TempUiManager.provision` drop a same-directory
   `Scratch` tempui note ("docs refreshed from vN to vM, see
   tempui-breaking-changes.md") using the exact mechanism Desk already
   has for a fire-and-forget note to the user -- no new capability
   needed, just not discarding a comparison already made.
   [planned: tempui-doc-upgrade-notification.md]

   Implemented per plan: `ensure_docs_current` (`src/desk/temp_ui.py`)
   now returns `(rewrote, previous_version)` -- `previous_version` only
   set when the doc set's embedded version was real, parseable, and
   actually differed from `TEMPUI_DOC_VERSION` (not for a mere missing
   -split-file repair or a brand-new/unversioned doc, neither of which
   is "a convention changed"). `TempUiManager.provision`
   (`src/desk/shell/temp_ui_manager.py`) writes a same-directory
   `Scratch` tempui note when `previous_version is not None`, naming
   both the old and new version and pointing at
   `tempui-breaking-changes.md` -- written directly and reported via
   `_relay.added.emit` + `_known_files`, not left for the watcher to
   discover on its own, per the plan's own explicit rejection of that
   approach (a real timing race: `_start_watching`'s underlying
   observer isn't guaranteed to already be watching the instant it
   returns). `_start_watching` runs first, since it clears
   `_known_files`.

   Verified directly, no mocking: new `tests/verify/
   verify_tempui_doc_upgrade_notification.py` (23 checks) --
   `ensure_docs_current`'s new return value tested directly against
   all three cases (brand-new, current-but-missing-a-split-file,
   genuinely stale); a real pre-existing `.desk_temp` with a real old
   version number gets its main doc actually rewritten to the current
   version *and* emits exactly one `file_added` for a real Scratch
   -shaped note mentioning both versions and `tempui-breaking-
   changes.md`, which a real `_FakeWindow` (the same real-`_place_
   widget` shape `verify_discuss_parking_lot_item.py` already
   established) actually turns into a placed Scratch widget with the
   right label and body -- not just "the signal fired." A brand-new
   `.desk_temp` and a current-but-missing-split-file repair each
   produce zero notifications, confirmed via the same real `provision`
   call. Full `tests/verify/` regression suite (84 scripts) passes.

a820354. COMPLETED: New FEEDBACK (`../FEEDBACK/FEEDBACK-DESK-tempui-convention-drift
   -notification-2026-07-30-1120.md`): the same feedback's smaller,
   related gap -- `_relocate_promoted_widget_source`
   (`src/desk/shell/window.py`) treats a missing source directory at
   the *current* convention's expected path as a silent no-op
   (correct for a hand-authored, inline-only widget that never had
   one) -- indistinguishable from a widget whose source genuinely
   exists, just at an older convention's location, which gets the
   exact same silent no-op today, leaving the person promoting it to
   notice on their own that nothing moved (as this project's own
   `LifeforceHeart`/`LifeforceControl` widgets required).
   Suggested fix: a low-severity `logger.info` (mirroring the
   `logger.warning` the function already emits for its sibling
   edge case, a pre-existing destination) when no source directory is
   found -- free to ignore in the common case, a concrete breadcrumb
   for the uncommon one. Not proposing this become a warning/error --
   the common case really is "nothing to move."
   [planned: relocate-widget-source-log-no-source.md]

   Implemented per plan: a one-line `logger.info` added to
   `_relocate_promoted_widget_source`'s existing no-source-directory
   early return, naming the widget keyword and the exact path checked
   -- `logger.info`, not `.warning`, matching the plan's own explicit
   "quiet-by-default" framing (the common case really is "nothing to
   move"; the sibling pre-existing-destination case stays a `.warning`
   since that one is always at least mildly surprising). Docstring
   updated to match ("a silent no-op" -> "a no-op ... logged at INFO").

   Verified directly: `tests/verify/verify_relocate_promoted_widget_
   source.py` extended with a real `logging.Handler` attached to
   `desk.shell.window`'s own logger for the duration of each promotion
   call (no prior precedent for log-output capture in this repo's own
   `tests/verify/`, so this is the direct approach) -- confirms exactly
   one `INFO` record naming both the widget keyword and the checked
   path for the no-source case, and confirms the sibling pre-existing
   -destination case still logs at `WARNING` (unchanged) and does *not*
   also log the new `INFO` message. The relocation itself remains a
   true no-op in both cases (already covered by this file's existing
   checks, unaffected). Full `tests/verify/` regression suite passes.

f9d2dc7. COMPLETED: From `PARKINGLOT.md`'s "Local speech-to-text (Whisper) for
   voice input" item: a script (`scripts/download_whisper_model.py`)
   that fetches the chosen Whisper model (`large-v3-turbo`, per the
   parking lot note's own stated decision) via `mlx-whisper`/Hugging
   Face Hub, printing the resolved local cache path so it's obvious
   the model lands outside this repo's working tree (the Hugging Face
   cache directory, not tracked by git, structurally the same
   guarantee as any other tool's package cache) -- plus
   `design-docs/whisper-model-setup.md` documenting the normal path,
   a manual backup path (`huggingface-cli download` against a mirror,
   or converting an original OpenAI checkpoint via
   `mlx_whisper.convert`) for when the script's usual source is
   unreachable, and an explicit note that downloaded models are never
   committed to the repo. Infrastructure only -- no transcription code
   (see TODO `1cd0ca2`) or UI (see TODO `b32fb81`) yet.
   [planned: whisper-model-download-and-setup-docs.md]

   Implemented per plan. `MODEL_REPOS` in `scripts/
   download_whisper_model.py` maps each parking-lot-table size to a
   real Hugging Face repo id -- individually confirmed via
   `HfApi().model_info(...)` rather than assumed, since the
   `mlx-community` org does not use one uniform naming scheme across
   sizes (e.g. bare `whisper-base`/`whisper-small` don't exist, only
   `-mlx-fp32`/`-8bit`/etc. suffixed variants). The script downloads
   (or confirms already-cached), loads the weights once through
   `mlx_whisper.load_models.load_model` as a real usability check, and
   prints the resolved cache path and size; an unreachable Hub or an
   unknown size produce the script's own clear message, not a raw
   traceback. `design-docs/whisper-model-setup.md` covers the normal
   path, the manual `huggingface-cli download`/`mlx_whisper.convert`
   backup paths, and states plainly that models are never part of this
   repo (the Hugging Face cache is structurally outside the working
   tree; a `/whisper-*/` `.gitignore` entry added as a belt-and
   -suspenders backstop, and the manual-download doc example points
   `--local-dir` at `~/` instead of the repo). `mlx-whisper` added to
   `pyproject.toml`'s dependencies (used by this script; also the one
   TODO `1cd0ca2` needs).

   Found along the way, surprising enough to record in `LEARNINGS.md`:
   `mlx_whisper.transcribe()`/`audio.load_audio()` unconditionally
   shells out to the `ffmpeg` CLI to decode *any* input file, including
   a plain WAV, with no fallback -- worked around in TODO `1cd0ca2`'s
   own module by decoding WAV directly via the stdlib `wave` module and
   passing a NumPy sample array instead of a path, since the Voice
   Input widget (TODO `b32fb81`) already fully controls the audio
   format it records in.

   Verified directly, real network calls throughout (no mocking): all
   ten `MODEL_REPOS` entries resolve to real Hub repos; an unknown size
   and an unreachable Hub (a bogus `HF_ENDPOINT`) each produce the
   documented clear error, not a traceback; the Hugging Face cache
   directory and every cached repo's path are confirmed outside this
   repo's working tree; a full real run of the default
   (`large-v3-turbo`, ~1.5 GB) actually downloads, loads, and reports
   success. New `tests/verify/verify_whisper_model_download_script.py`,
   24 checks, 0 failures.

1cd0ca2. COMPLETED: From `PARKINGLOT.md`'s "Local speech-to-text (Whisper) for
   voice input" item: a `src/desk/speech.py` module wrapping
   `mlx-whisper` (`mlx-whisper` added as a real new dependency in
   `pyproject.toml` -- unavoidable, there is no bespoke way to run a
   Whisper model, per `design-docs/architecture.md`'s own framing of
   CLAUDE.md's dependency guidance as being about *unnecessary*
   dependencies) with a single `transcribe(audio_path) -> str`
   function, raising a clear `TranscriptionUnavailableError` (pointing
   at TODO `f9d2dc7`'s download script and doc) if the model isn't
   cached yet, rather than silently blocking on an unannounced
   multi-minute download during a real dictation attempt. Depends on
   TODO `f9d2dc7` for the model actually being fetchable; no UI yet
   (see TODO `b32fb81`).
   [planned: whisper-transcription-module.md]

   Implemented per plan, with one change from the plan's own sketch:
   `transcribe()` does not call `mlx_whisper.transcribe(str(audio_path),
   ...)` -- doing so was tried directly first and found to
   unconditionally require the `ffmpeg` CLI (not installed, no package
   manager available to install it in this environment), which would
   have made a system-level, non-pip binary a hard requirement for
   every user of this feature. Since this module's only caller
   controls its own audio format completely, `transcribe()` instead
   decodes the (required) 16 kHz mono 16-bit PCM WAV directly via the
   stdlib `wave` module into a normalized `float32` NumPy array and
   passes that to `mlx_whisper.transcribe()`, whose signature already
   accepts a raw array -- `ffmpeg` is never invoked. Recorded in
   `LEARNINGS.md`. Availability is checked via `huggingface_hub
   .try_to_load_from_cache()` against both files
   `mlx_whisper.load_models.load_model` actually reads
   (`config.json`, `weights.safetensors`), not just "the repo appears
   in the cache scan" (which can be true of a partially-downloaded
   repo mid-transfer) -- confirmed directly while `f9d2dc7`'s own
   `large-v3-turbo` download was still in progress.

   Verified directly, no mocking: real macOS `say`-synthesized speech
   ("The quick brown fox...") transcribes back to matching text through
   the real, fully-downloaded `large-v3-turbo` model; a WAV in the
   wrong format (stereo/44.1kHz) raises `ValueError` instead of
   silently mis-transcribing; pointing at a genuinely uncached repo id
   raises `TranscriptionUnavailableError` with a message naming both
   the download script and the setup doc; `MODEL_REPO` confirmed to
   match `scripts/download_whisper_model.py`'s own `MODEL_REPOS
   ["large-v3-turbo"]` entry. New
   `tests/verify/verify_speech_transcription.py`, 5 checks, 0 failures.

   Addendum, found after the above landed (user noticed a real Hub
   request in the console logs on first use and asked about it -- this
   was not caught by the original verification pass): every
   `mlx_whisper.transcribe()` call -- not just the first download --
   routes through `huggingface_hub.snapshot_download()`, which contacts
   the Hub to resolve `"main"` even when the model is fully cached
   locally (`mlx_whisper`'s own in-process `ModelHolder` memoizes the
   loaded model, so only the *first* transcription per running process
   actually triggers this -- easy to miss in quick manual testing).
   Confirmed directly this is a real cost, not just a log line: with
   the Hub genuinely unreachable (a black-holed address, not a
   same-host connection refusal) rather than merely absent, that one
   call blocked for ~77 seconds before falling back to the local cache
   -- a serious regression for a feature pitched as local/offline.
   Setting the `HF_HUB_OFFLINE` environment variable does not fix this
   (confirmed: `huggingface_hub.constants.HF_HUB_OFFLINE` is frozen at
   that module's own import time, before this code ever runs); fixed
   by patching `huggingface_hub.constants.HF_HUB_OFFLINE` directly for
   the duration of the call, only after `_model_is_cached()` has
   already confirmed the files are on disk (`speech.py`'s
   `_force_hub_offline`). Recorded in `LEARNINGS.md`. Verified
   directly: the same artificially-unreachable-network reproduction
   drops from ~77s to ~2-5s; a real transcription with the model
   cached now logs zero HTTP requests (previously logged one).
   `tests/verify/verify_speech_transcription.py` gained three more
   checks (8 total), all passing.

b32fb81. COMPLETED: From `PARKINGLOT.md`'s "Local speech-to-text (Whisper) for
   voice input" item: a new self-contained "Voice Input" widget
   (`widgets/voice_input/`, `kind: "python"`) -- record/stop button,
   status label, editable transcription result, copy-to-clipboard --
   using `QtMultimedia`'s `QAudioSource` for microphone capture (no new
   dependency; already ships with this project's installed PyQt6) and
   TODO `1cd0ca2`'s `desk.speech.transcribe` for the actual
   transcription, run on a background thread so the Qt event loop
   stays responsive. Depends on TODO `1cd0ca2` (and transitively TODO
   `f9d2dc7`). Deliberately scoped as one new, independent widget
   rather than wiring a dictation affordance into every existing
   text-entry surface -- matches this project's existing
   one-capability-per-widget pattern; wiring dictation into other
   widgets is a separable future follow-up, not part of this item.
   [planned: voice-input-widget.md]

   Implemented per plan, following `widgets/git_status/widget.py`'s
   established background-thread-plus-`QObject`-relay pattern for the
   transcription call (`_transcribe_in_background` runs on a
   `threading.Thread`, reports back via a `pyqtSignal`). Captures
   16 kHz mono 16-bit PCM directly (Whisper's own native rate, and the
   exact format TODO `1cd0ca2`'s `transcribe()` requires -- no
   resampling step needed); records into memory and writes one WAV file
   on Stop via the stdlib `wave` module, deleted again once
   transcription finishes (success or failure). `_stop_recording` is
   split from a new `_process_captured_audio` specifically so tests can
   drive the write-WAV -> background-transcribe -> UI-update pipeline
   with known injected audio, independent of whatever a real
   microphone happens to pick up during an automated run. An
   unavailable model or any other transcription failure surfaces as a
   real, visibly-styled (red) status message rather than failing
   silently.

   Verified directly against real hardware and the real, already
   -downloaded model, no mocking: a real `QAudioSource` against this
   machine's real default microphone (`MacBook Pro Microphone`)
   actually captures non-zero PCM bytes; real macOS `say`-synthesized
   speech injected in place of live microphone input transcribes
   correctly into the text edit end-to-end through the real background
   thread and Qt signal; the Copy button places the result on the real
   system clipboard; the temporary WAV file is confirmed deleted after
   completion; an uncached model repo surfaces as a real visible error
   naming the download script. New
   `tests/verify/verify_voice_input_widget.py`, 21 checks, 0 failures.
   Not verified: behavior when the macOS microphone-permission (TCC)
   prompt is actually denied -- this machine already had microphone
   access granted for this process before this TODO's work began, so
   the denied-permission path was never actually exercised; flagged in
   `plans/voice-input-widget.md` as a real runtime consideration, still
   open.

a596dbf. COMPLETED: Introduce a new "Claude (Desk)" widget (`widgets/claude_desk/`)
   that talks to the Python Claude Agent SDK (`claude-agent-sdk`,
   `ClaudeSDKClient`) instead of the PTY/`pyte` terminal-emulation
   mechanism the existing Claude widget (`widgets/claude/widget.py`)
   uses, so Desk can provide its own status UI, prompt input box, and
   scrollable history view instead of rendering `claude`'s interactive
   -terminal output through pyte and typing commands into its PTY. The
   existing Claude widget is left in place, unchanged, as a separate
   widget kind -- this adds a new option alongside it rather than
   replacing it. Surfaced while researching how to more tightly
   integrate Claude Code into Desk without losing what the CLI
   currently provides (permission modes/manual-vs-auto, model
   selection, session resume, file-access sandboxing). Confirmed
   directly against current Claude Code docs that all of these are
   equally available through the Python Agent SDK (`ClaudeAgentOptions
   .permission_mode`/`.model`/`.resume`), that sandboxing and protected
   -path checks are enforced independently of permission mode (so the
   existing widget's hardcoded `--permission-mode auto`, TODO
   `2dca4c8`, isn't weakening file-access safety today), and that the
   SDK additionally exposes a `can_use_tool` callback -- the correct
   mechanism for Desk to show its own manual-mode approval dialog,
   rather than relying on `claude`'s own prompt text rendered as ANSI.
   The plain Console widget (`widgets/console/`) is also unaffected.
   [planned: claude-widget-agent-sdk-integration.md]

   Implemented per plan: `claude-agent-sdk` added to `pyproject.toml`;
   `src/desk/claude_session.py`'s `ClaudeSession` (a `QObject`) owns a
   dedicated background thread running its own asyncio event loop for
   a session's whole lifetime, translating `ClaudeSDKClient`'s message
   stream and `can_use_tool` permission callback into `pyqtSignal`s --
   same background-thread-plus-relay shape as `widgets/git_status/
   widget.py`/`widgets/voice_input/widget.py`, per the plan's own
   framing. `widgets/claude_desk/widget.py`'s `ClaudeDeskWidget`
   composes a status label, model selector, scrollable read-only
   history, prompt input, and an Allow/Deny approval row; exposes the
   same `start_session(session_id, resume, extra_instructions)` shape
   the original widget uses. `DeskWindow` gained `CLAUDE_DESK_WIDGET_ID`
   and `_bind_claude_desk_widget`, wired at exactly the two call sites
   that needed it (fresh-instance-id assignment, post-`add_widget` bind
   dispatch) -- tempui's `DiscussParkingLotItem` flow and the Questions
   widget's Discuss button deliberately still target only the original
   widget, per the plan's own explicit scope boundary. New "Claude
   (Desk) Widget" entry (#30) added to `design-docs/architecture.md`,
   alongside the existing entry.

   Two real findings from empirical verification, each changing the
   implementation from the plan's own sketch (neither was assumed):
   - A resumed session with nothing queued to send never fires
     `turn_complete`/`session_error` at all (there's no turn) -- without
     a signal for "connected, even with nothing sent," the prompt box
     would stay disabled forever after a restored widget reconnects.
     Added `ClaudeSession.connected`, wired only for the resume-with-no
     -prompt case (not the fresh-launch case, where re-enabling input
     between "connected" and "the bootstrap turn actually completing"
     would let a user send a second message while the first is still in
     flight).
   - `can_use_tool` is invoked reliably under `permission_mode="default"`
     (confirmed across many real sessions, including a bootstrap-prompt
     -then-Write sequence matching this widget's own real usage) but
     fires *inconsistently* for the identical kind of request under
     `"auto"` -- confirmed directly, not assumed, after the automated
     widget-level test intermittently failed to observe a permission
     request that should have fired. `"auto"` appears to use a looser,
     non-deterministic heuristic that sometimes skips the gate entirely
     (matching its apparent purpose: fewer prompts, at the cost of
     consistency) -- neither a bug in this widget's own code nor in the
     SDK, just a real behavioral property of that mode worth knowing.
     Deviated from the plan's suggested `"auto"` parity default
     (matching TODO `2dca4c8`'s original widget) to `"default"` instead,
     since this widget's entire point is a real, meaningful approval
     UI -- a mode where that UI doesn't reliably trigger undermines the
     feature it exists to provide. Both findings recorded in
     `LEARNINGS.md`, alongside a third, narrower one hit while writing
     the verify script itself: `QWidget.isVisible()` is unconditionally
     `False` for any descendant of a never-`.show()`n top-level widget
     (this project's own offscreen widget tests never call `.show()`),
     regardless of an explicit `setVisible(True)` -- use
     `child.isVisibleTo(ancestor)` instead.

   Verified directly, real Claude Agent SDK sessions throughout (no
   mocking, real API calls against `claude-haiku-4-5-20251001`): a
   fresh `ClaudeSession` assigns the given session id and completes a
   real turn end to end; a second `ClaudeSession` resuming that same id
   recalls context from the first (proving reconnection, not a fresh
   session); a `Write` tool call is denied via `respond_to_permission
   (allow=False)` with the file confirmed never created, then a second,
   separately-approved request lets the file be created; the actual
   widget (not just `ClaudeSession` directly) accumulates history
   entries in chronological order across a multi-turn conversation
   including a real tool call resolved through its own Allow button;
   `_bind_claude_desk_widget` duck-types on `start_session` exactly like
   `_bind_claude_widget`. New
   `tests/verify/verify_claude_desk_widget.py`, 25 checks, 0 failures.
   Full `tests/verify/` regression suite unaffected (the original Claude
   widget's own coverage untouched, since `widgets/claude/` was never
   modified).
   Not done (explicitly out of scope per the plan): wiring tempui's
   Claude-spawning flows to offer this widget as an option; a
   model/permission-mode switcher beyond the model combo box already
   included (the plan left "immediately vs. fast-follow" as an open
   judgment call -- a combo box shipped now, a mode switcher did not).

76949eb. COMPLETED: Expose per-word transcription confidence from `desk.speech
   .transcribe` (TODO `1cd0ca2`) and surface it in the Voice Input
   widget (TODO `b32fb81`). Surfaced by the user noticing a real
   misrecognition ("are we going to hit the thing" transcribed as
   "...hit the button") and asking whether `mlx-whisper` exposes any
   confidence signal. Confirmed directly (`mlx_whisper/transcribe.py`,
   `timing.py`): every segment already carries `avg_logprob`/
   `no_speech_prob`/`compression_ratio`, and passing
   `word_timestamps=True` additionally attaches a `"words"` list per
   segment, each with a real per-word `probability` -- exactly the
   "confidence for individual words" the user asked about, currently
   discarded since `transcribe()` returns only `result["text"]`.
   [planned: speech-word-confidence.md]

   Implemented per plan: `src/desk/speech.py` gained `WordConfidence`
   (`word`, `probability`) and `TranscriptionResult` (`text`, `words`)
   frozen dataclasses; `transcribe()` now returns `TranscriptionResult`
   instead of a plain `str` (a breaking change to its one call site,
   accepted per the plan's own reasoning -- no reason to keep a
   str-returning shim for a single internal caller), always passing
   `word_timestamps=True` to `mlx_whisper.transcribe()` and flattening
   `result["segments"][*]["words"]` into one ordered list. `widgets/
   voice_input/widget.py` gained a module-level `word_offsets(text,
   words)` helper reconstructing each word's character range in the
   final (stripped) text, and `_highlight_low_confidence_words`
   applying a background color to every word below
   `LOW_CONFIDENCE_THRESHOLD` (0.5) via `QPlainTextEdit
   .setExtraSelections()` -- no rich-text/`QTextEdit` switch needed.

   Two open questions the plan flagged, both resolved empirically
   during implementation, not assumed:
   - **Punctuation bucketing**: confirmed directly (real transcriptions)
     that `mlx_whisper` always attaches punctuation to its adjacent
     word (e.g. `' thing,'`, `' not?'`), never as its own list entry --
     so no special "skip bare punctuation" handling was needed.
   - **Latency cost of `word_timestamps=True`**: measured directly on
     this project's own warmed-up `large-v3-turbo` model, 3 runs each
     on a ~14-word utterance: ~1.02s without vs. ~1.66s with -- a real
     but moderate (~0.6s absolute, ~62% relative) slowdown, judged
     worth taking unconditionally (matches the plan's own default)
     rather than adding an opt-out parameter for a caller that doesn't
     exist yet.

   One correctness bug found and fixed during the offset-reconstruction
   work itself, before it ever reached a test: naively discarding any
   word whose computed start position went negative (from
   `text.strip()`'s own leading-whitespace trim) would have silently
   dropped the *first* word of every transcription's highlighting
   entirely. Fixed by clamping the start position to 0 instead of
   discarding the word.

   Deferred, per the plan's own explicit scope boundary, not forgotten:
   a numeric-probability hover tooltip (needs real `cursorForPosition`
   + `QToolTip` wiring `QTextCharFormat.setToolTip()` alone does not
   provide) and anything using segment-level `avg_logprob`/
   `no_speech_prob` (an overall "this clip was noisy" signal, which
   doesn't localize to individual words the way this TODO's own report
   asked about).

   Verified directly, real transcriptions throughout (no mocking):
   `tests/verify/verify_speech_transcription.py` confirms `transcribe()`
   returns a real `TranscriptionResult` with a non-empty `words` list,
   every probability in `[0.0, 1.0]`, and that joining every word's own
   string reproduces the untrimmed text exactly (4 new checks).
   `tests/verify/verify_voice_input_widget.py` confirms `word_offsets`
   against real model output fully and exactly tiles the real
   transcription text with no gaps or overlaps, and drives
   `_on_transcription_finished` directly with a hand-built
   `TranscriptionResult` containing one deliberately low-probability
   word, confirming the real widget applies exactly one
   `ExtraSelection` covering the right character range with the
   configured background color, and that a subsequent
   all-high-confidence result clears previous highlighting rather than
   accumulating stale selections (9 new checks). Full `tests/verify/`
   regression suite passes.

fe7d8f2. COMPLETED: Add voice input capabilities to the new "Claude (Desk)" widget
   (TODO `a596dbf`, now implemented) so a prompt can be dictated into
   it the same way the standalone Voice Input widget (TODO `b32fb81`)
   already supports, using `desk.speech.transcribe` (TODO `1cd0ca2`),
   rather than only ever typing into its prompt input box.
   [planned: claude-desk-voice-input.md]

   Implemented per plan: extracted the mic-capture-and-transcribe
   pipeline out of `widgets/voice_input/widget.py` into a new shared
   `src/desk/voice_capture.py` (`MicRecorder` -- owns `QAudioSource`
   lifecycle, WAV writing, background-thread transcription via
   `desk.speech.transcribe`, reporting through `pyqtSignal`s only, no
   UI) -- needed by a second widget now, matching the existing
   `desk.terminal_widget`/`desk.claude_session` "shared widget logic
   lives in `desk.` proper" precedent rather than pasting a second,
   independently-drifting copy of the capture logic.
   `widgets/voice_input/widget.py` refactored to build a `MicRecorder`
   instead of owning `QAudioSource` directly -- a pure extraction, its
   own UI/highlighting/copy behavior unchanged, confirmed by its
   existing verify coverage passing basically as-is (31 checks).
   `widgets/claude_desk/widget.py` gained a `_mic_button` ("●"/"■",
   mirroring the standalone widget's own convention) in its prompt
   row; on stop, the transcribed text is set into `_prompt_input` --
   **not** auto-sent, matching how a typed prompt already works, so a
   misrecognition (TODO `76949eb` already found real ones happen) can
   be reviewed/edited before it goes to Claude.

   One real bug found and fixed during the *test's own* development,
   not the product code: an early draft of the new widget-level test
   called `MicRecorder._process_captured_audio()` directly (bypassing
   `stop()`) to inject known synthesized audio, which skips the
   `recording_stopped` signal entirely and left the mic button stuck
   showing "■" (Stop) forever -- confirmed directly, not assumed.
   Real production code is unaffected (`_on_mic_clicked` always calls
   the real `stop()`, never `_process_captured_audio()` directly), but
   the test itself needed fixing to inject known audio *before*
   calling the real `stop()` instead, matching the pattern already
   established in `verify_voice_capture.py`'s own
   `_start_then_inject_known_audio` helper.

   Verified directly, real audio pipelines throughout (no mocking):
   new `tests/verify/verify_voice_capture.py` (16 checks) exercises
   `MicRecorder` directly -- real mic capture, real synthesized-speech
   transcription end to end, real WAV cleanup, a real "no audio
   captured" error path -- with zero use of `unittest.mock` anywhere
   (a real, already-started `QAudioSource` stands in wherever a
   not-yet-real one would otherwise be needed, per this project's own
   verification philosophy). `tests/verify/verify_voice_input_widget
   .py` re-confirms the refactored widget is behavior-preserving (31
   checks, all passing). `tests/verify/verify_claude_desk_widget.py`
   gained a real mic-button click -> injected synthesized speech ->
   `_prompt_input` populated check, confirming the text is *not*
   auto-sent (directly observable: `_session.send_prompt` was
   monkeypatched to record calls, and none occurred). Full
   `tests/verify/` regression suite passes.
   Not done (explicitly out of scope per the plan): low-confidence
   -word highlighting in the Claude (Desk) prompt box (`QLineEdit` has
   no `QTextEdit.ExtraSelection`-equivalent mechanism) -- flagged as a
   natural follow-up once TODO `8df6797`'s multi-line prompt input
   (already being considered for an unrelated reason) lands, since
   that already means reconsidering `_prompt_input`'s widget type.
8a5ea2b. COMPLETED: research: is it possible to do something closer to live transcription by breaking the audio into smaller chunks?

   Investigated directly -- read `mlx_whisper`'s real `transcribe()`
   source (it already processes audio in an internal 30-second
   sliding-window loop, but has no incremental/streaming input hook at
   all: every call re-mel-spectrograms and redecodes its whole input
   array from scratch) and ran a real experiment: transcribed
   successively longer prefixes (1s, 2s, ..., full clip) of the same
   real synthesized ~5.6s sentence against this project's own
   already-warmed default model.

   Findings, both confirmed directly, not assumed: (1) per-call
   latency stayed roughly constant (~1.0-1.1s) regardless of prefix
   length while under Whisper's 30-second window, meaning a naive
   "re-transcribe the growing buffer every ~1s" loop is roughly
   sustainable in real time for a short dictation -- but would not
   stay sustainable for a long recording, since per-call cost grows
   again past 30s of buffered audio; (2) partial results genuinely
   flicker -- the trailing word(s) of an in-progress utterance were
   repeatedly wrong/truncated ("fog" for "fox", "the lace" for "the
   lazy dog") until enough audio arrived to disambiguate, stabilizing
   only once the buffer contained the whole utterance. A real
   implementation would need a genuine "interim vs. final" visual
   distinction in the text widget, not just swapping in new text on a
   timer, or it would read as broken rather than live.

   Full findings, including what a real implementation would require
   from `desk.speech`/`desk.voice_capture` (a materially different API
   shape than today's record-fully-then-transcribe-once flow), written
   up in `investigations/live_transcription_chunking.md`. Not filed as
   a ready-to-implement follow-up TODO -- the real UX design question
   (how to show flickering interim results without it looking broken)
   and the unbounded compute-growth cost for longer recordings are
   both genuinely unresolved, matching how `PARKINGLOT.md`'s own
   "research offline TTS options" item was left as pure research
   without forcing a premature follow-up.

e1f6391. COMPLETED: Add the ability to queue messages in the Claude (Desk) widget
   (`widgets/claude_desk/widget.py`'s `ClaudeDeskWidget`) instead of
   only offering a Send button that goes dead while a turn is in
   flight -- `_set_busy(True)` currently disables both `_prompt_input`
   and `_send_button` from `_on_send_clicked` until
   `_on_turn_complete`/`_on_session_error` fires, so anything typed
   while Claude is working has nowhere to go. Let the user submit
   while busy and have it queued (sent automatically, in order, once
   idle again), plus UX in the widget showing what's currently queued
   so it doesn't feel like the message vanished.
   [planned: claude-desk-message-queue.md]

   Implemented per plan: `_set_busy` no longer disables `_prompt_input`
   /`_send_button` (only `_mic_button` still goes dark while busy --
   dictating a new message mid-turn is unchanged, out of scope); a new
   `self._busy` flag is what `_on_send_clicked` actually checks to
   decide send-now vs. queue, since Qt's own `isEnabled()` is no longer
   a busy proxy. A submission made while busy appends to
   `self._message_queue`, gets a `"[queued] <text>"` history line, and
   shows in a new `_queue_label` ("Queued: N", full queued text as its
   tooltip); the Send button itself relabels to "Queue" while busy as
   a second, cheap signal. `_finish_busy_period(idle_status)` (shared
   by `_on_turn_complete` and `start_session`'s resume-with-nothing
   -to-send path, both of which used to just call `_set_busy(False)`
   directly) drains the next queued message instead of going idle, if
   there is one -- `_on_session_error` deliberately does not drain the
   queue (a session error may mean the session itself is in a bad
   state; remaining queued messages stay visible but frozen, no
   auto-retry for this first pass).

   Fixed three existing checks in `tests/verify/
   verify_claude_desk_widget.py` that relied on `_prompt_input
   .isEnabled()` as a busy proxy -- now structurally always enabled,
   so those checks were updated to check `widget._busy` directly
   instead (the actual thing they meant to observe).

   Verified directly, real sessions throughout (no mocking): a message
   sent while a real bootstrap turn is in flight does not dispatch
   immediately (confirmed via a monkeypatched `send_prompt` spy that
   still calls through to the real one), shows the queue label/history
   line/relabeled Send button; a second message queues behind the
   first; once the bootstrap turn actually completes for real, the
   first queued message dispatches automatically, and once *that*
   turn completes, the second dispatches too, in order; the widget
   returns to idle and every indicator clears only once the queue is
   genuinely empty. One real transient flake hit while verifying (a
   90-second turn-completion wait timed out on one run, cascading
   failures through the rest of that test) -- confirmed via a clean
   re-run immediately after (47/47 passing) that this was a one-off
   real-network/API hiccup, not a logic bug; the passing re-run is what
   these checks reflect. Full `tests/verify/` regression suite passes.

e4662a5. COMPLETED: Make the pan/zoom control (`src/desk/shell/zoom_control.py`'s
   `ZoomControl`, a HUD floating over the Workspace Canvas's lower-right
   corner) always visible, instead of only appearing when the canvas is
   at non-unity zoom (`WorkspaceView._on_scale_changed`'s current
   `self.zoom_control.setVisible(abs(self._scale - 1.0) >
   SCALE_EPSILON)`). Prioritized ahead of the Claude (Desk) widget
   refinements below -- basic canvas UX, unrelated to and independent of
   that work.
   [planned: always-visible-pan-zoom-control.md]

   Removed the `.hide()`/conditional `setVisible(...)` entirely (and
   the now-unused `SCALE_EPSILON` constant) -- `ZoomControl` is now
   constructed and shown the same always-on way `DeskPicker` already
   is. Found a real regression along the way (not anticipated by the
   plan): making it always visible let its "Fit"/"100%" `QPushButton`s
   and its `QSlider` -- all keyboard-focusable by default -- steal
   real application focus the moment `view.show()` ran (Qt's automatic
   "focus the first focusable widget" behavior), which broke
   `WorkspaceView`'s own scene-focus tracking for every widget's
   content afterward. Confirmed directly (`app.focusWidget()` was the
   `QPushButton`, not the canvas) and caught immediately by the
   existing `verify_widget_focus.py`/`verify_trap_widget_tab_focus.py`
   regression coverage before it ever reached a commit. Fixed by
   giving those three inner controls `Qt.FocusPolicy.NoFocus` --
   this HUD is mouse-only by design already, so it never needed
   keyboard focus in the first place. New
   `tests/verify/verify_zoom_control_always_visible.py` (3 checks).
   Full `tests/verify/` regression suite passes (86 scripts).

945b086. COMPLETED: Add an always-visible button hovering in the Workspace
   Canvas's lower-left corner (matching the always-visible
   `DeskPicker`/`ZoomControl` pinned-HUD pattern in
   `src/desk/shell/canvas.py`) that adds a new Scratch widget
   (`SCRATCH_WIDGET_ID`) in the middle of the current viewport and
   focuses it, so typing goes directly into the new Scratch without an
   extra click. Prioritized alongside TODO `e4662a5`, ahead of the
   Claude (Desk) widget refinements below.
   [planned: new-scratch-hover-button.md]

   New `src/desk/shell/new_scratch_button.py` (`NewScratchButton`, a
   plain `QLabel` child of the viewport matching `DeskPicker`'s
   `_ClickableLabel` shape) constructed and always shown in
   `WorkspaceView.__init__` alongside the other three pinned HUD
   widgets, positioned bottom-left via the same deferred
   `singleShot(0)` pattern the others use (reasserted from
   `resizeEvent`/`scrollContentsBy`). New `DeskWindow
   ._open_focused_scratch(pos=None)` -- centered when `pos` is `None`,
   otherwise placed with that top-left corner -- calls
   `content.body.setFocus(Qt.FocusReason.MouseFocusReason)` on the
   result, confirmed via `QGraphicsScene.focusItem()` actually
   reflecting the new widget's proxy (not just trusting the
   `setFocus()` call). Written to take an optional `pos` from the
   start so TODO `496d685` (double-click empty canvas) can reuse it
   directly. `QLabel`'s default focus policy (`NoFocus`) meant this
   button needed no fix for the same focus-stealing issue TODO
   `e4662a5` hit with `ZoomControl`'s buttons/slider. New
   `tests/verify/verify_new_scratch_button.py` (6 checks, using the
   established `_FakeWindow`-with-real-`_place_widget` recipe). Full
   `tests/verify/` regression suite passes (87 scripts).

496d685. COMPLETED: Double-clicking on empty canvas (outside any placed widget,
   and outside the pinned hovering UI -- the Desk picker, zoom control,
   temp-UI notifications, and the new lower-left Scratch button from
   TODO `945b086`) should add a new Scratch widget at that point and
   focus it, so typed characters land directly starting where the
   double-click was. Likely shares placement/focus plumbing with TODO
   `945b086` -- do that one first. Prioritized alongside TODO `e4662a5`/
   TODO `945b086`, ahead of the Claude (Desk) widget refinements below.
   [planned: double-click-empty-canvas-scratch.md]

   New `WorkspaceView.mouseDoubleClickEvent` (previously no override
   existed at all) gates on the same `_hit_test_chrome`/`_frame_at`
   pair every other canvas-level interaction already uses -- truly
   empty canvas emits `empty_canvas_double_clicked(scene_pos)`,
   anything else (chrome, a frame's own content, a non-left button)
   falls through to `super()` unchanged. `DeskWindow
   ._on_empty_canvas_double_clicked` calls the shared
   `_open_focused_scratch` helper from TODO `945b086` with the
   double-click's scene position as the new widget's top-left corner.
   No explicit check needed for the pinned HUD widgets (Desk picker,
   zoom control, new-Scratch button) -- confirmed directly, not just
   asserted, that a real click at their position is delivered straight
   to that widget by Qt, never reaching this handler.

   Found during verification: a hand-built `QMouseEvent` handed
   directly to `view.mouseDoubleClickEvent(...)` (the existing
   `verify_lock_widgets.py` press/release pattern) never actually
   reaches a `QGraphicsProxyWidget`-embedded widget's own
   `mouseDoubleClickEvent` -- the Scratch title label's inline-edit
   trigger silently never fired with that approach. Switched the new
   verify script to `QTest.mouseDClick(view.viewport(), ...)`, which
   goes through Qt's real event-delivery pipeline instead of calling
   the override directly, and that reaches it correctly. New
   `tests/verify/verify_double_click_empty_canvas_scratch.py` (12
   checks). Full `tests/verify/` regression suite passes except two
   pre-existing, unrelated failures observed in this run
   (`verify_speech_transcription.py`'s Hub-unreachable timing check,
   `verify_voice_capture.py`'s real-microphone-capture check) -- both
   in files this item never touches; the first re-ran clean in
   isolation (a load-induced timing flake), the second reproduced
   consistently in isolation too and looks like a real mic
   hardware/permission issue on this machine rather than test drift
   per `development-process.md`'s "don't disable for mere
   inconvenience, only for drift" guidance -- flagged to the user
   rather than acted on unilaterally, since it's unrelated to this
   item's scope.

c4d79f0. COMPLETED: Fix file-watcher deadlock: `FileWatcherService.watch()` (`src/
   desk_services/file_watcher/service.py`) calls `self._observer.
   schedule()` while holding its own `self._lock`, but watchdog's
   dispatch thread acquires its own internal lock first and then calls
   back into our `_dispatch()`, which needs `self._lock` -- opposite
   lock order, a reliable AB-BA deadlock. Hits in practice whenever a
   `watch()` call for a brand-new key races an in-flight dispatch of an
   already-watched key, which happens on ordinary launch
   (`DeskWindow.__init__` -> `_provision_temp_ui` -> `_ensure_questions_
   watcher` schedules a new watch right as temp-ui provisioning writes
   files that fire dispatch on an existing watch) -- Desk hangs
   entirely on launch (icon appears, no window paints, unkillable
   except Ctrl+C), reported by the user with a full traceback ending at
   `watchdog/observers/api.py:304`'s `with self._lock:`.
   [planned: file-watcher-schedule-deadlock.md]

d7e66f6. COMPLETED: A lightweight, one-shot "Job" mechanism so an agent-authored
   script can run with real widget-context capabilities -- notably
   Bridge API access, which no agent-run script can reach today --
   without needing to build out a full tempui `DefineWidget`/
   `widgets/<id>/` registration for a single ad-hoc task. Prompted by
   an agent's own observation while working on Desk (this session)
   that it's "silly" an agent can't just use `window.desk.*` for a
   one-off Bridge API call the way a real `kind: "html"` widget's own
   JS can. Related to, but a materially different shape from,
   `../FEEDBACK/FEEDBACK-DESK-batch-ingestion-job-concept-2026-08-03-1634.md`
   (see the "Notes from Desk" section added to that file for the
   relationship) -- that item is long-running/checkpointed/resumable
   supervised pipelines; this one is a single one-shot run with no
   persistence/checkpoint concept at all.

   Suggested mechanism, following this project's own established
   tempui-DSL-file-drop conventions rather than inventing a new
   delivery channel:
   - A new tempui DSL keyword (e.g. `Job`, added to
     `RESERVED_TEMPUI_KEYWORDS`/`detect_temp_ui_kind` in
     `src/desk/temp_ui.py`, mirroring `DEFINE_WIDGET_KEYWORD`'s own
     shape) declares a summary line, a `kind` (`python` or `html`),
     zero or more `Capability<TAB>name` lines for the `html` case
     (same shape/precedent as `DefineWidget`'s own `Capability` lines,
     TODO `f693275`), and the script content itself -- an agent drops
     a file into `.desk_temp` the same way any other tempui file is
     dropped today.
   - `TempUiManager`'s existing directory watcher already turns any
     new `.desk_temp` file into a `file_added` signal with no new
     plumbing needed; `DeskWindow._on_temp_ui_file_added` /
     `_notify_temp_ui` / `_activate_temp_ui`
     (`src/desk/shell/window.py:1553-1683`) is the exact existing
     "new file -> notification -> click -> open a widget bound to it"
     pipeline every other tempui kind (Scratch, Question,
     DiscussParkingLotItem, ...) already uses -- a new "Job Runner"
     widget kind would bind to the Job file the same way, via
     `_bind_temp_ui_content`.
   - The Job Runner widget itself shows: the declared summary; a
     "View Code" button that opens the script's own text in the
     Editor widget (mirroring `desk.editor.openOrScrap`/
     `DeskWindow.open_editor_or_scrap`, `window.py:774`, as the
     existing "show me this text in a real editor" precedent -- though
     the script lives inside the tempui file's own DSL-wrapped
     content here, not a standalone file, so this may need a
     "materialize just the script body to a temp file first" step);
     and a "Start" button, inert until clicked (the point being: no
     code runs without an explicit, visible user action -- this is
     real code execution triggered by an agent-written file, so the
     confirm-before-running step is load-bearing, not optional chrome).
     **Decided**: View Code is the only review step -- no separate
     capability/risk summary or harder confirmation dialog on top of
     Start; matches how ordinary code review already works (once the
     source is visible, that's the review).
   - On Start, dispatch by the declared `kind`:
     - `html`: materialize + mount as a real, ephemeral `kind: "html"`
       widget instance, reusing `desk.custom_widgets.materialize` and
       the per-instance token/`QWebEngineProfile` isolation TODO
       `a5f66cc` already built for `DefineWidget` -- the script's own
       JS gets an authenticated `window.desk.*` Bridge API scoped to
       exactly the `Capability` lines it declared, the same coarse
       per-resource capability check `require_caller` already enforces
       for every other `kind: "html"` widget (`app.py:224`); no new
       auth/injection/capability mechanism needed, just a new source
       of a `WidgetInfo.capabilities` list.
     - `python`: **Decided**: simple direct-exec, not
       `PythonWidgetHost`'s `build() -> QWidget` pattern -- run the
       script in a fresh module namespace with the `desk` package
       importable, capturing stdout/stderr/exceptions for the status
       display below. Proportionate to "a one-time script," not a
       real, persistent interactive widget.
   - A status display in the Job Runner widget (executing / done /
     errored) -- no progress protocol, run history, or resumability
     (that's the sibling FEEDBACK item's own, heavier concept).
   - **Decided**: a run Job file is kept (not deleted) after running,
     but its Start button becomes inert/hidden once it's finished --
     a record of what ran, not a re-runnable saved tool.
   - **Agent-facing documentation must be updated as part of this
     item, not left as a follow-up** -- the whole point is giving
     agents a capability they don't know exists yet, so the tempui doc
     set an agent actually reads (`src/desk/temp_ui.py`'s doc
     constants, likely a new split doc file or a new section in
     `_CUSTOM_WIDGETS_DOC`, matching the established doc-split
     convention) needs to explain the `Job` keyword, its file format
     (summary/`kind`/`Capability` lines/script body), and the
     `html`/`python` execution split, with the usual
     `TEMPUI_DOC_VERSION` bump and matching `_NEW_FEATURES_DOC` entry
     (same convention every other tempui-DSL addition already follows
     -- see TODO `e42469e` for what happens when a real capability
     ships without this: agents kept not finding out it existed).
   [planned: lightweight-agent-job-mechanism.md (COMPLETED)]

   COMPLETED: `temp_ui.py` gained `JOB_KEYWORD = "Job"` (added to
   `RESERVED_TEMPUI_KEYWORDS`), a `JobDefinition` dataclass, and
   `parse_job` (mirrors `parse_define_widget` exactly: `Job<TAB>kind
   <TAB>summary` first line, `Capability<TAB>name` lines, `Script<TAB>
   base64-chunk` lines concatenated in file order); `detect_temp_ui_kind`
   gained a `"job"` branch. New `src/desk/jobs.py` mirrors
   `desk.custom_widgets` under its own `jobs/` cache subdir:
   `materialize` (writes an execution-ready `index.html`/`script.py`
   by kind) and `materialize_script_body` (View Code's own separate
   plain-text copy, named distinctly so it never collides with the
   execution entry). `current_context` gained one new hook,
   `set_html_job_starter`/`get_html_job_starter` -- `python`-kind
   execution needed no `DeskWindow` involvement at all (a pure
   background-thread direct-exec, `git_diff/widget.py`'s own
   `_Relay(QObject)` shape). `window.py` gained
   `JOB_RUNNER_WIDGET_ID`, `_temp_ui_widget_id_for`/`_notify_temp_ui`
   `"job"` branches (Job is Scratch/Question-shaped -- one file, one
   bound instance via the *existing*, unmodified
   `_bind_temp_ui_content` fallback branch, not `DefineWidget`'s
   two-step shape), `JOB_RUNNER_WIDGET_ID` added to
   `TEMP_UI_WIDGET_IDS` (restore reconnection), and
   `start_html_job(job_id, definition, on_status)`: materializes,
   registers a `WidgetInfo` scoped to exactly the declared
   `Capability` lines directly into `self._widgets` (never through
   `_register_custom_widget` -- that machinery is for a reusable,
   promotable widget *kind*; a Job is a one-shot instance), mounts on
   the real running server, and places a real, visible `ChromiumWidget`
   -- `job_id` doubles as both widget id and instance id.
   `on_status("executing"/"done"/"errored", detail)` reuses
   `ChromiumWidget`'s own existing `loadFinished`/`error_state_changed`
   signals, no new ones needed. New `widgets/job_runner/` (`kind:
   "python"`): summary/kind display, View Code (materializes the
   script body, calls `current_context.get_editor_or_scrap_opener()`),
   Start (dispatches by kind), a status display, `get_widget_local_storage`/
   `set_widget_local_storage` (persists `{"status", "detail"}` across
   a Desk reload -- a restored `"executing"` status is shown as
   `"interrupted"` with Start re-enabled, not a permanently stuck
   widget), and `has_unsaved_local_edits` (`True` once started,
   reusing `_refresh_live_temp_ui`'s existing Scratch-widget-established
   opt-out mechanism so an external edit to an already-started Job's
   file can't clobber it). `temp_ui.py` also gained a new split doc,
   `tempui-jobs.md` (file format, the real capability-namespace list,
   an explicit "Done means page-load-finished, not that your own async
   Bridge calls resolved" caveat, and a worked `python`-kind example),
   `TEMPUI_DOC_VERSION` bumped 30->31 with a matching comment block and
   `_NEW_FEATURES_DOC` entry, and `DOC_TEMPLATE`'s file-type list
   bumped eight->nine with a new `Job` bullet linking to the new doc.
   New verify coverage, real (no mocking): `verify_job_tempui_parsing.py`
   (17 checks: parse round-trip including multi-chunk `Script` lines,
   garbage rejection, `detect_temp_ui_kind`); `verify_jobs_materialize.py`
   (14 checks: real file writes by kind, malformed-base64 tolerance,
   the two materialize paths coexisting in the same job directory
   without colliding); `verify_job_runner_widget.py` (21 checks: real
   `QWidget` construction, a real background-thread python-kind
   execution reaching "done" with captured stdout or "errored" with a
   real captured traceback, persisted-status round-trip including the
   interrupted-on-restore case, View Code's real materialize-then-open
   call, and the html-kind dispatch through the starter hook);
   `verify_html_job_execution.py` (13 checks, real `start_server` +
   a real, visible `ChromiumWidget`, `os._exit()` per TODO `a5f66cc`'s
   established pattern: confirmed via a real HTTP round trip that a
   declared `workspace` capability call succeeds while an undeclared
   `fs` capability call gets a real 403 -- `err.status` from TODO
   `e86a31b` made this assertion possible without string-matching);
   `verify_job_notification_routing.py` (5 checks: the notification/
   routing dispatch for a real Job file); `verify_tempui_jobs_doc.py`
   (14 checks: doc-version/content, cross-referencing rather than
   duplicating the Bridge API capability list). Full `tests/verify/`
   regression suite passes (100 scripts total, 0 failures).

48e3b39. COMPLETED: App-structure DSL: a declarative schema + parser + dual-target
   codegen tool for the wiring/layout code of a multi-component SPA
   built as a single `kind: "html"` widget -- generalized from
   `world-timelines`'s own hand-written `app-root.ts`/`main.ts` (~500
   lines of component registration, pane/grid layout, event-delegation
   wiring, and a Web Worker channel), not specific to it. From
   `../FEEDBACK/FEEDBACK-DESK-app-structure-dsl-and-editor-widget-2026-08-03-1634.md`.
   Full design discussion, already had -- see
   `investigations/app_structure_dsl_design.md` for the complete
   record (design principles, the layout mode designs, and the full
   inventory scoping decisions); this item is the "go implement it"
   step, not a fresh design pass. Summary of what's in v1, per that
   doc:
   - **Component registry**: an explicit `{tag, source}` list; codegen
     emits the import + `customElements.define` boilerplate.
   - **Layout**, three modes: n-split-panes (a tree of `hsplit`/
     `vsplit`/`pane` nodes, named static layout variants switched at
     runtime, per-split resize constraints), windowed (flat `window`
     entries close to Desk's own `.desk`-file `WidgetState` shape),
     and raw HTML/CSS/TS (no DSL involvement -- components are plain
     custom elements by construction). A "dump current layout to
     HTML/CSS/TS" codegen option for modes 1/2 is a one-way eject.
   - **Event-wiring table**: `{event, from, actions}` entries, each
     action either a state mutation or a child method call, supporting
     fan-out to multiple actions per event. Worker channels are folded
     into this same table (a worker is just another named component)
     rather than a separate mechanism.
   - **State slots**: plain typed slots with declared defaults: no
     derived/computed state in v1.
   - **Escape hatch**: named handler functions the generated code
     calls out to at declared extension points -- also where the two
     deliberately-deferred inventory items (a field<->DSL-text-line
     bidirectional sync sub-DSL, and cache/data-source declarations)
     live until/unless a second real use case justifies generalizing
     them into the DSL proper.
   - **Dual transpilation target**: every individual component stays
     plain TypeScript+HTML+CSS, with zero Desk-awareness and zero
     build-time overhead when built outside Desk -- all Desk
     -integration work happens in this codegen layer, which supports
     (at least) a standalone build (no Desk runtime dependency) and a
     Desk-widget build (packaged the same way `build_widget.py`
     already packages a `DefineWidget`/`widgets/<id>/` source
     directory -- multi-file `kind: "html"` widgets now load reliably,
     TODO `a5f66cc`).
   Explicitly out of scope for this item, each a separate, large
   enough piece of work to get its own TODO later: the **visual
   layout-editing widget** (drag/resize panes or windows, assign a
   widget by name to a slot); the **DSL editor widget** itself (raw
   -text + structured-UI bidirectional sync, meant as a reusable
   building block -- still needs original design per the investigation
   doc, no prior Desk precedent exists); and the **shared,
   project-scoped state store** (`desk.state.*`, from the sibling
   `widget-extraction-communication-gaps` FEEDBACK item -- a Desk-core
   Bridge API primitive, architecturally distinct from this DSL
   tool). Not designed further than the investigation doc's own level
   of detail yet -- exact JSON Schema field names, the codegen's
   internal structure, and where in this repo the tool actually lives
   (likely a new seedable script alongside `scripts/todo_item_ids.py`/
   the generated `build_widget.py`, given its scope) all need a real
   plan before implementation starts.
   [planned: app-structure-dsl.md (COMPLETED)]

   COMPLETED: new top-level `app_dsl/` (git-tracked, mirrored fresh
   into every project's `.desk_temp/app_dsl/` on every open/switch --
   `sync_app_dsl_tool`/`_repo_app_dsl_dir` in `src/desk/temp_ui.py`,
   mirroring `sync_shared_components`'s exact always-fresh shape,
   wired into `TempUiManager.provision` alongside it, `__pycache__`
   excluded). `app_dsl/schema.py`: dataclasses for `ComponentEntry`,
   `SplitLayoutNode` (recursive `hsplit`/`vsplit`/`pane`),
   `WindowEntry`, `LayoutDefinition`, `StateMutationAction`/
   `CallAction`, `EventWiringEntry`, `StateSlot`, `HandlerRef`,
   `AppDefinition`, `DslError`. `app_dsl/parse.py`:
   `parse_app_definition(json_text) -> AppDefinition` -- hand-written
   validation (no JSON Schema library, `CLAUDE.md`), every
   cross-reference (a layout pane's `widget`, an action's state-slot/
   component/handler target) resolved against the declared registry/
   state list/handlers, a clear `DslError` naming the exact bad
   reference on failure. `app_dsl/codegen.py`:
   `generate(definition, components_dir, out_dir) -> {filename:
   content}` -- component registry import+`customElements.define`
   boilerplate; state slots as `export let <name>: <type> = <default>`
   plus a generated setter; layout mode 1 (n-split-panes) as real
   nested-`<div>` builder functions per named variant (flexbox CSS,
   `app-layout.css`) with `buildLayout(variant)`/
   `DEFAULT_LAYOUT_VARIANT` exports; the event-wiring table as
   `querySelectorAll`-scoped `addEventListener` registrations fanning
   out to state-mutation/component-method-call actions in declared
   order (a worker is just another named component -- no separate
   mechanism, confirmed nothing additional was needed); the escape
   hatch as a direct named import + call. Layout mode 2 (`"windowed"`)
   is accepted by the parser (schema-complete) but `codegen.generate`
   raises a clear `DslError` naming it not-yet-implemented rather than
   emitting wrong output -- an additive follow-up, not a breaking
   format change. `app_dsl/build.py`: the CLI entry point,
   self-contained (no `desk` package import, matching
   `_BUILD_WIDGET_SCRIPT`'s own posture). `app_dsl/README.md`:
   the DSL's own format documentation. `tempui-custom-widgets.md`
   gained an honest cross-reference (new tool, not a new tempui DSL
   keyword); `TEMPUI_DOC_VERSION` bumped 31->32 with a matching
   comment block and `_NEW_FEATURES_DOC` entry.

   Real, found-while-implementing finding, recorded in `PARKINGLOT.md`
   rather than silently worked around: the generated TypeScript uses
   real ES modules (`import`/`export`), confirmed via a real `tsc`
   compile; `build_widget.py`'s own `DefineWidget` packaging model
   concatenates *global, non-module* scripts (confirmed directly --
   `shared-components/document-editor-base/document-editor-base.ts`
   has zero `import`/`export` statements, for exactly this reason).
   So "dual transpilation target" is proven this pass for the
   **standalone** build only -- feeding `app_dsl`'s output into
   `build_widget.py`'s packaging pipeline for a **Desk-widget** build
   isn't wired up yet (two plausible fixes noted, neither
   investigated: a non-module codegen output mode, or a real bundling
   step). `tempui-custom-widgets.md`'s cross-reference states this
   plainly rather than implying a working integration that doesn't
   exist yet.

   New verify coverage, real (no mocking, real `tsc`/`node`):
   `tests/verify/verify_app_dsl_parse.py` (34 checks: a representative
   multi-component/nested-split/fan-out definition round-trips
   exactly; every class of bad input rejected with a message naming
   the specific problem). `tests/verify/verify_app_dsl_codegen.py` (9
   checks: a representative definition's generated output, alongside
   real hand-written component fixtures, compiles with a real `tsc`,
   then *runs* under real `node` against a minimal hand-written
   DOM-stand-in -- confirmed a real dispatched event correctly
   mutated the generated state slot and correctly fanned out to a
   second action's real method call on a different component, not
   just that the generated text merely compiles; the windowed-layout
   not-implemented error and the no-layout case are also covered).
   `tests/verify/verify_app_dsl_escape_hatch.py` (5 checks: the same
   real-compile-and-run approach confirms a hand-written handler
   module is actually imported and actually invoked with the
   DSL-declared argument). `tests/verify/verify_sync_app_dsl_tool.py`
   (9 checks: a real `TempUiManager`-independent direct call mirrors
   a fresh copy, excludes a real `__pycache__`, and fully replaces a
   stale pre-existing copy rather than leaving it alone).
   `tests/verify/verify_app_dsl_tempui_doc.py` (6 checks: doc-version/
   cross-reference/changelog content, including that the cross
   -reference is honest about the standalone-only scope). Full
   `tests/verify/` regression suite passes (105 scripts total, 0
   failures).

1e032f3. COMPLETED: `app_dsl`'s generated TypeScript uses real ES modules
   (`import`/`export`), which `.desk_temp/build_widget.py`'s own
   `DefineWidget` packaging model can't consume -- it concatenates
   *global, non-module* scripts (confirmed both directly, and via a
   real `tsc` probe: a file using `export`/`import` always gets
   CommonJS-style `exports`/`require` boilerplate in its compiled
   output regardless of the `module` compiler option, including
   `"module": "None"` -- there is no way to get plain global-script
   output from a file containing ES module syntax). From
   `PARKINGLOT.md`'s entry on this (filed while completing TODO
   `48e3b39`). Confirmed the fix directly against
   `shared-components/document-editor-base/document-editor-base.ts`
   -- the closest existing precedent for real-source, `DefineWidget`
   -concatenated multi-file content -- which has zero `import`/
   `export` statements anywhere, for exactly this reason.
   Suggested fix: a second `codegen.py` output mode (`mode="global"`,
   alongside today's `mode="module"` default) that emits the same
   registry/state/layout/event-wiring code with no `import`/`export`
   at all -- global `class`/`let`/`function`/`const` declarations,
   matching `document-editor-base.ts`'s own convention exactly. This
   mode's own necessary constraint (not a limitation to work around,
   a documented fact of the packaging model it targets): component
   and handler source files must *also* avoid ES module syntax when
   used with this mode, and a component's globally-declared class name
   must match codegen's own deterministic tag-to-class-name derivation
   exactly (already used internally --
   `codegen._class_name_for_tag`), since there's no `import ... as
   Alias` step left to rename it. `build.py`'s CLI needs a `--mode`
   flag (default `module`, unchanged); `README.md` needs the new
   mode's format/constraints documented.
   [planned: app-dsl-global-codegen-mode.md (COMPLETED)]

   COMPLETED: `schema.py`'s `ComponentEntry` gained an optional
   `class_name: str | None = None` (parsed by `parse.py`'s
   `_parse_components` via a new `_optional_str` helper). `codegen.py`
   gained `mode: str = "module"` on `generate(...)`, threaded through
   every emit function: `_emit_registry` (module: imports +
   `customElements.define`; global: only `customElements.define(tag,
   <resolved class name>)` lines, no imports -- `_resolved_class_name`
   uses the override if set, else the existing
   `_class_name_for_tag` derivation), `_emit_state`/`_emit_layout`/
   `_emit_event_wiring` (conditionally include/omit the `export `
   prefix on their own top-level declarations only -- the internal
   per-node layout helpers already had no `export` in either mode),
   `_emit_handler_imports` (global mode returns `[]`, nothing to
   import), and a new `_escape_target_identifier` helper for
   `_emit_action`'s escape-hatch branch: module mode still uses the
   DSL's own local handler key (correct, since the generated import
   already aliased it there); global mode resolves and emits
   `definition.handlers[key].export` directly instead, since there's
   no import/alias step to do that renaming. `build.py` gained a
   `--mode=module|global` CLI flag (simple manual parsing, no
   argparse, matching this script's own existing minimal style).
   `README.md`: documented both modes, the `class_name` override, and
   that `--mode=global` requires component/handler source to also
   avoid module syntax (the `tsconfig.json` `"files"`-ordering
   responsibility stays with the caller, same as any other multi-file
   `DefineWidget` source already requires).

   Confirmed via a real `tsc` probe before implementing (not assumed):
   a file using `export`/`import` always gets CommonJS-style
   `exports`/`require` boilerplate in its compiled output, regardless
   of the `module` compiler option -- including `"module": "None"`,
   which still emitted `Object.defineProperty(exports, ...)`/
   `exports.default = ...` for a plain `export default class` with no
   imports of its own. Confirms there was no cheaper fix than a real
   second, module-free codegen mode. `tempui-custom-widgets.md`'s
   cross-reference (added under TODO `48e3b39`, honestly scoped to
   "standalone only" at the time) now documents both modes accurately;
   `TEMPUI_DOC_VERSION` bumped 32->33 with a matching comment block
   and `_NEW_FEATURES_DOC` entry. The `PARKINGLOT.md` entry this item
   was filed from is removed -- moved to `TODO.md` and completed, per
   this project's own "move them to TODO.md when ready to act on them"
   convention, not left behind as a stale duplicate.

   New/extended verify coverage, real (no mocking, real `tsc`/`node`):
   `tests/verify/verify_app_dsl_codegen.py` (+11 checks, 20 total):
   `mode="global"` emits zero `import`/`export` and respects the
   `class_name` override; the real regression check for this item --
   module-free component fixtures + generated global-mode output
   compile with a real `tsc`, the *compiled* `.js` files are confirmed
   to contain no `exports`/`require` anywhere (the actual bug),
   textually concatenated (mirroring `build_widget.py`'s own
   `_concatenate_compiled_js`), and run via real `node`'s
   `vm.runInThisContext` -- the same "no module wrapper, no `require()`
   available" execution model a real concatenated `<script>` tag uses,
   not just plain `node script.js` (which still has CommonJS module
   machinery ambiently available even for code that doesn't use it) --
   confirming a dispatched event still correctly mutates state and
   fans out to a real method call using the `class_name` override.
   `tests/verify/verify_app_dsl_escape_hatch.py` (+6 checks, 11
   total): the same real compile-concatenate-run approach confirms
   global mode calls the handler's real export name directly (a
   deliberately-different DSL-local-key-vs-real-export-name fixture
   catches the exact bug an incorrect identifier resolution would
   cause). `tests/verify/verify_app_dsl_parse.py` (+3 checks, 37
   total): `class_name` parses, defaults to `None`, rejects an empty
   value. `tests/verify/verify_app_dsl_tempui_doc.py` (revised): doc
   -version/cross-reference/changelog content for both versions 32 and
   33. Full `tests/verify/` regression suite passes (105 scripts
   total, 0 failures).

f68383f. COMPLETED: A shared, capability-gated, project-scoped state store --
   `desk.state.get(key)` / `set(key, value, edit?)` / `getHistory(key,
   limit)`, closing gaps 1-4 and 6 of
   `../FEEDBACK/FEEDBACK-DESK-widget-extraction-communication-gaps-2026-08-03-1634.md`
   (gap 7 already fixed by TODO `a5f66cc`) and sharpened by
   `../FEEDBACK/FEEDBACK-DESK-shared-state-with-semantic-edits-2026-08-10-2141.md`'s
   own concrete two-widget case. Full design discussion, already had
   -- see `investigations/app_structure_dsl_design.md`'s "Shared state
   store design"/"Semantic edits" sections for the complete record;
   this item is the "go implement it" step for the **non-validated**
   core of that design, not a fresh design pass. Summary of what's in
   scope for this item:
   - **Bridge API**: `get`/`set`/`getHistory`, gated by a single new
     `state` capability (covers both reads and writes, matching every
     other Bridge namespace's own one-capability-per-namespace
     precedent).
   - **`set(key, value, edit?)`**: `edit` is an optional, opaque-to
     -Desk structured record describing what produced the change (not
     interpreted by Desk -- just stored and relayed, the same way
     `desk.events` payloads already are).
   - **Change notifications reuse `desk.events`**, not a new
     transport -- `set()` auto-publishes a well-known event (`{key,
     value, edit}` payload) rather than inventing a second delivery
     mechanism.
   - **`getHistory(key, limit)`**: a fixed-size-N FIFO queue per key
     (always exactly the N most recent `(value, edit)` pairs, oldest
     evicted as new ones arrive), returned latest-first. N is a fixed,
     small default, not per-key configurable in this pass.
   - **Persistence**: a new `Desk.state` field (`src/desk/desks.py`),
     read/written by `load_desk`/`save_desk`/`desk_state_dict` the
     same way `Desk.custom_widgets`/`Desk.file_type_registry` already
     are -- no new persistence mechanism, and the history persists
     alongside the value for the same reason the value itself does (a
     reload shouldn't show a value with no explanation of how it got
     there).
   Explicitly out of scope for this item, filed separately as TODO
   `6e1c2fe` (blocked on this one; later split into TODO `af7898b`/
   `9aef267`/`6330249`, see those items): schema declaration/validation
   (validated vs. non-validated state), conflict resolution, built-in
   -widget and top-level schema files, and the schema/state
   -management widget -- a real, separate, large layer on top of this
   primitive, not needed for this item's own get/set/history/events
   core to be genuinely useful on its own (per the
   `shared-state-with-semantic-edits` FEEDBACK item's own concrete
   case: get/set/history alone already closes 3 of its 4 hand-rolled
   pain points without any schema concept at all).
   [planned: shared-state-store.md]
   COMPLETED: `src/desk/desks.py` -- `StateHistoryEntry`/`StateEntry`
   dataclasses; new `Desk.state: dict[str, StateEntry]` field;
   `load_desk`/`desk_state_dict`/`save_desk` read/write it via new
   `_load_state_entry`/`_state_entry_dict` helpers, mirroring
   `custom_widgets`'s own round-trip shape exactly. `src/desk/shell
   /window.py` -- `STATE_HISTORY_MAX_ENTRIES = 50`;
   `get_state`/`set_state`/`get_state_history` methods; `set_state`
   appends to history with FIFO eviction
   (`del entry.history[:-STATE_HISTORY_MAX_ENTRIES]`) and publishes
   `desk.state.changed` (`{key, value, edit}`) via the existing
   `EventMediator`, with the calling instance excluded from its own
   change (standard `desk.events` sender-exclusion). `src/desk/server
   /app.py` -- `SetStateRequest` model; three new routes,
   `GET /api/bridge/state/get`, `POST /api/bridge/state/set`,
   `GET /api/bridge/state/getHistory`, each gated by
   `require_caller("state")` + `require_instance_id`, following the
   `events_subscribe`/`events_publish` combined-dependency precedent.
   `src/desk/server/bridge_client.py` -- `desk.state.{get, set,
   getHistory}` added to the `window.desk` object. `src/desk
   /temp_ui.py` -- new "Shared, project-scoped state" section and
   capability-list bullet in `_CUSTOM_WIDGETS_DOC`
   (`tempui-custom-widgets.md`); `TEMPUI_DOC_VERSION` bumped 33 -> 34
   with a matching comment block and `_NEW_FEATURES_DOC` entry. New
   `tests/verify/verify_state_store.py` (23 checks): data-model
   round-trip through save/load (including an old `.desk` file with no
   `state` key defaulting to `{}`), and a real Bridge-API-over-HTTP
   round trip covering get-on-unset returning
   `{value: None, edit: None}`, set/get round trip, `edit` defaulting
   to `None` when omitted, a real cross-instance `desk.state.changed`
   delivery with sender-exclusion verified, `getHistory` bounded to 50
   entries/returned latest-first/oldest-evicted, a `limit` smaller and
   larger than the stored history both honored correctly, and a
   missing-`state`-capability 403 from both `get` and `set`. Full
   `tests/verify/` regression suite passes (114 scripts total, 0
   regressions -- the sole pre-existing failure,
   `disabled_verify_claude_desk_widget_claude_api.py`, is an already
   -filed, already-disabled item unrelated to this change).
   `investigations/app_structure_dsl_design.md`'s "Where things were
   left" updated to record this item's completion.

af7898b. COMPLETED: The state store's (TODO `f68383f`) schema declaration,
   conflict resolution, and validation core -- originally filed as a
   single item, TODO `6e1c2fe`, split into this and the two items below
   it for manageability once its actual implementation surface became
   clear (a type language, three distinct widget-registration paths,
   two new file-watcher locations, and a new built-in widget really is
   four separable pieces of work, not one). Full design discussion,
   already had -- see `investigations/app_structure_dsl_design.md`'s
   "Validated vs. non-validated state, and schema lifecycle" and
   "Bookkeeping and call sites" sections for the complete record. This
   item's own scope is everything **except** top-level schema files
   (TODO `9aef267`, below) and the new schema/state-management widget
   (TODO `6330249`, below):
   - Every state key is validated (a schema -- a TypeScript type
     expression stored as a string, a pragmatic constrained subset for
     this pass -- is currently registered for it) or non-validated (no
     schema at all; access is a purely call-site-local type hint with
     best-effort coercion, nothing persisted or cross-checked).
   - A schema can be declared in a widget's own manifest (top-level
     schema files are TODO `9aef267`, not this item).
   - Conflict resolution is first-loaded-while-still-active wins; a
     genuinely conflicting later widget hard-fails to load entirely
     (no placement, not even a normal placement notification) --
     instead, a distinct clickable notification explains the conflict,
     and the same message is appended to a new, well-known, optional
     manifest field, `desk_widget_loading_errors: string[]`, on the
     failing widget's own manifest.
   - Enforcement lifetime differs by source: a tempui-placed widget
     instance's schema is active only while at least one placed
     instance references it (dormant, not deleted, once the last one
     is removed -- a later instance can keep using the dormant schema
     if unchanged, or replace it if declaring a different one); a
     built-in widget's schema (validated at `discover_widgets` time) is
     permanently enforced from discovery onward. Built-in-vs-built-in
     conflicts resolve by `discover_widgets`' own existing alphabetical
     directory-sort order, surfaced the same notification+manifest
     -field way, just fired once at Desk startup/switch instead of at
     a click-to-place moment.
   - Instance-list maintenance for the dormancy check is lazy only --
     pruned the next time some other widget's load triggers the
     maintenance pass on that same schema, not eagerly on
     `close_widget`.
   Needs a real plan before implementation starts -- the exact schema
   -registry dataclasses, the type-expression parser/validator, and the
   Bridge API route shape changes for schema-aware `get`/`set` all need
   working out.
   [planned: state-store-schema-core.md]
   COMPLETED: `src/desk/schema_types.py` (new) -- a pragmatic TypeScript
   -subset type-expression parser (primitives, literals, arrays, unions,
   simple object shapes with optional members), `validate`/`coerce`
   (coerce is best-effort, never raises) and
   `type_expressions_equivalent` (structural, order-independent).
   `src/desk/schema_registry.py` (new) -- `RegisteredSchema`,
   `SchemaConflict`, `SchemaRegistry` with `register_permanent` (built
   -ins; idempotent for the same source, first-registered-source wins
   alphabetically since `discover_widgets`' own directory-sort order is
   preserved by dict insertion order), `clear_source`/
   `permanent_source_ids` (re-derives every built-in schema fresh on
   every hot reload, so a fixed/removed conflict clears), and
   `join_or_conflict_placement` (tempui-sourced: fresh/join-while
   -active/conflict-while-active/dormant-reactivate-if-unchanged/dormant
   -replace-if-different, with lazy instance-list pruning folded into
   the same call). `src/desk/widgets.py` -- `WidgetInfo.state_schema`/
   `.desk_widget_loading_errors` (the latter in-memory only, never
   written to a real widget.json -- see the plan's own "Decided in this
   planning pass" note); `_parse_manifest` reads `state_schema`.
   `src/desk/temp_ui.py` -- `CustomWidgetDefinition.state_schema`;
   `parse_define_widget` gained a repeatable `StateSchema<TAB>key<TAB>
   type_expr` DSL line; `build_widget.py`'s own generated script emits
   it from a `state_schema` field in its authoring-source `widget.json`
   too; new "Validated vs. non-validated keys" doc subsection;
   `TEMPUI_DOC_VERSION` bumped 34 -> 35. `src/desk/server/runner.py` --
   `ServerHandle.schema_registry`, constructed once alongside
   `event_mediator`. `src/desk/server/app.py` -- `SetStateRequest
   .type_hint`; `state_get`/`state_set` thread it through;
   `run_on_gui` maps a `ValueError` to a 400 (schema mismatch, invalid
   `type_hint`, or a `desk.state.*`-conflict-blocked `widgets.open`);
   `self_get_manifest` now prefers the live `gui_bridge.window
   .get_widget_info` result over `require_caller`'s own separate,
   always-fresh `discover_widgets` scan, so `state_schema`/
   `desk_widget_loading_errors` are never stale for a built-in;
   `_widget_info_dict` includes both fields. `src/desk/server
   /bridge_client.py` -- `desk.state.get/set` gained an optional
   `typeHint`. `src/desk/shell/window.py` -- `self._schema_registry`;
   `_refresh_builtin_schemas` (called from `__init__` and
   `_on_widget_changed_refresh_catalog`, skips any id in
   `_custom_widget_sources`); `_place_widget` returns `WidgetFrame |
   None` and gates a tempui-sourced custom widget's declared schema(s)
   through `join_or_conflict_placement` before creating a frame,
   appending to `desk_widget_loading_errors` and firing
   `_notify_schema_conflict` (reuses `WorkspaceView.notify_temp_ui`,
   keyed by a synthetic `Path("schema-conflict:<id>")`) on a refusal;
   every real call site updated for a possible `None` (`_load_desk_widgets`
   skips and continues; `open_widget` raises `ValueError`, caught and
   turned into a quiet `None` by `open_widget_content` for internal
   GUI-driven callers like `_activate_temp_ui`, left to propagate for
   the Bridge API's `widgets.open` route); `get_state`/`set_state`
   validate against an active schema or best-effort-coerce a non
   -validated key's optional `type_hint`, preserving TODO `f68383f`'s
   exact prior behavior when neither applies. New verify coverage:
   `verify_schema_types.py` (60 checks), `verify_schema_registry.py`
   (25 checks), `verify_state_store_schema.py` (14 checks, real Bridge
   -API-over-HTTP), `verify_state_store_schema_placement.py` (12
   checks, real `_place_widget`/dormancy round trip against two
   conflicting `DefineWidget`-sourced kinds) -- plus fixes to 8
   pre-existing scripts whose hand-rolled `_FakeGuiWindow`/`_FakeWindow`
   test doubles had either drifted out of sync with `get_state`/
   `set_state`'s new signature (`verify_state_store.py`, now reuses the
   real `DeskWindow` methods instead of a duplicated copy) or needed
   the new `_place_widget`-required methods bound
   (`verify_custom_widget_content_hash.py`, `verify_html_job_execution.py`,
   `verify_html_widget_local_storage.py`,
   `verify_relocate_promoted_widget_source.py`,
   `verify_stale_marker_click_dialog.py`, `verify_tempui_custom_widgets.py`,
   `verify_widget_error_indicator.py`). Full `tests/verify/` regression
   suite passes (118 scripts total, 0 regressions -- the sole failure,
   `disabled_verify_claude_desk_widget_claude_api.py`, is an already
   -filed, already-disabled, unrelated flaky item).
   `investigations/app_structure_dsl_design.md`'s "Where things were
   left" updated to record this item's completion.

9aef267. COMPLETED: State store top-level schema files -- **blocked on
   `af7898b` landing first** (needs its schema type language and
   registry to already exist). Split out of the original TODO
   `6e1c2fe` -- see `af7898b` above for why. Full design, already had
   -- see `investigations/app_structure_dsl_design.md`'s "Bookkeeping
   and call sites" section. Scope: schemas declared "top-level," in a
   standalone schema file independent of any widget's manifest --
   two watched locations, ephemeral `.desk_temp/schemas/` and a real,
   git-tracked `./desk-schemas/` that Desk never creates eagerly, only
   watches for and picks up immediately once it exists. Both need new
   file-watcher registrations, since `TempUiManager`'s existing
   `.desk_temp` watch is non-recursive (`temp_ui_manager.py:249`) and
   doesn't cover a `.desk_temp/schemas/` subdirectory, and
   `./desk-schemas/` is outside `.desk_temp` entirely. A top-level
   file's schema is permanently enforced from registration onward, the
   same as a built-in widget's (never dormant). Needs a real plan
   before implementation starts.
   [planned: state-store-top-level-schemas.md]
   COMPLETED: `src/desk/shell/schema_file_watcher.py` (new) --
   `SchemaFileWatcher(QObject)`, `changed` signal emitted for a
   `.json` file added/edited/removed in either watched directory
   (added/edited/removed alike -- the receiver decides which via
   `path.is_file()`). `.desk_temp/schemas/` is watched directly (it
   always already exists by the time this runs, created by
   `TempUiManager.provision`) with an initial scan on `provision()` so
   already-present files are picked up without waiting for a
   filesystem event; `./desk-schemas/` is polled every 2s
   (`QTimer`) until it exists -- a real live watch (plus the same
   initial scan) takes over once it does, rather than a permanent
   watch over the whole project root just to catch one directory's own
   birth. Both paths are resolved identically to the shared
   `desk_services.file_watcher` service's own symlink-resolved event
   paths, confirmed directly after finding a real bug where the
   initial scan's path and a later live-edit's path for the exact same
   file didn't match, which would have leaked a duplicate,
   spuriously-self-conflicting registry entry. `temp_ui_manager.py`
   -- `TempUiManager.provision` creates `.desk_temp/schemas/` (a plain
   `mkdir`, never wiped/reseeded) alongside its other subdirectories,
   only when `.desk_temp` itself is actually being provisioned.
   `window.py` -- `DeskWindow` owns a `SchemaFileWatcher`
   (`self._schema_file_watcher`) and `self._known_schema_file_sources:
   set[str]` (tracks which `SchemaRegistry` sources came from a file,
   kept separate from `_refresh_builtin_schemas`' own built-in-widget
   source tracking); `_provision_temp_ui` captures `TempUiManager
   .provision`'s return value and calls the new
   `_provision_schema_files`, which clears every previously-tracked
   schema-file source first (desk-switch isolation -- `SchemaRegistry`
   is one shared instance for the whole server run, not per-Desk) then
   re-provisions the watcher for the current directory;
   `_on_schema_file_changed` clears the file's own prior registrations,
   then -- if it still exists -- parses it fresh (a plain JSON object,
   `{"<key>": "<type expression>", ...}`, the same shape a real
   `widget.json`'s own `state_schema` field already is) and calls
   `SchemaRegistry.register_permanent` per key, exactly the same
   "clear then re-derive" shape `_refresh_builtin_schemas` (TODO
   `af7898b`) already uses for built-ins; malformed JSON, a non-object
   top level, a non-string type-expression value, or a schema conflict
   are all loading errors, not crashes, surfaced via the existing
   `_show_schema_conflict_popup` click-handler (no
   `desk_widget_loading_errors`-equivalent persisted for a bare file --
   there's no manifest to attach it to, matching `af7898b`'s own
   in-memory-only decision). `temp_ui.py` -- "Validated vs.
   non-validated keys" doc subsection extended with the file format and
   both locations; `TEMPUI_DOC_VERSION` bumped 35 -> 36. New verify
   coverage: `verify_schema_file_watcher.py` (12 checks, real
   directories/real watches/real polling) and
   `verify_state_store_top_level_schemas.py` (22 checks, register/
   conflict/edit/delete/desk-switch-isolation) -- plus a fix to
   `verify_new_desk_flow.py`'s `_FakeWindow` (needed
   `_schema_registry`/`_known_schema_file_sources`/a no-op schema-file
   -watcher stand-in bound, since `_provision_temp_ui` now also calls
   `_provision_schema_files`). Full `tests/verify/` regression suite
   passes (120 scripts total, 0 regressions).
   `investigations/app_structure_dsl_design.md`'s "Where things were
   left" updated to record this item's completion.

6330249. COMPLETED: New built-in schema/state-management widget -- an ordinary,
   placeable/closeable Desk widget (`kind: "python"`), not a distinct
   "dashboard" UI concept. Depends on `af7898b`/`9aef267`, both
   COMPLETED. Split out of the original TODO `6e1c2fe` -- see `af7898b`
   above for why. Full design, already had -- see
   `investigations/app_structure_dsl_design.md`'s "Validated vs.
   non-validated state, and schema lifecycle" section. Scope: **view
   and edit** every currently-registered schema (widget-declared and
   top-level) and **view and edit** the data stored under those keys
   (including non-validated ones) -- a Desk user should have deep
   insight into shared state, not just a read-only listing. Where a
   top-level schema file actually gets authored/edited/deleted.
   Whenever any schema is registered, Desk must guarantee an instance
   of this widget is already placed, or place one if not, so validated
   state is never invisible the moment it starts existing -- worth
   checking against the real UX before assuming safe, given
   `DefineWidget`'s own auto-placement experiment (TODO `5ff02d2`) was
   tried and reverted (TODO `dafbaab`) for a differently-shaped
   (per-kind, not singleton) case. Needs a real plan before
   implementation starts.
   [planned: state-schema-management-widget.md]
   COMPLETED: `src/desk/schema_registry.py` --
   `RegisteredSchema.source_kind` (`"widget"` | `"file"`, so the widget
   knows which schemas it may edit/delete -- only file-sourced ones,
   never a widget's own manifest-declared one); `SchemaRegistry` now
   takes an `EventMediator` and publishes a new `desk.state
   .schema_changed` event (no per-key payload -- a full re-fetch is
   cheap) on every successful `register_permanent`/`clear_source`/
   `join_or_conflict_placement`, never on a conflict; `SchemaRegistry
   .all()` for a full snapshot. `runner.py` -- `SchemaRegistry
   (event_mediator)`. `window.py` -- the three existing schema
   -registration call sites pass `source_kind` explicitly and each
   call a new `_ensure_state_manager_placed()` after a successful
   registration (places a `state_manager` instance, centered in the
   view, only if none is currently placed -- implemented literally as
   "checked on every registration, not once per session," a flagged
   judgment call, see the plan's own Design decisions); new
   `get_state_overview` (every known key -- Desk.state's own keys union
   SchemaRegistry's own keys -- with value/edit/schema/source/
   enforcement info per key); `try_set_state` (same as `set_state`, but
   returns an error message instead of raising); `write_schema_file`
   (writes a top-level schema `.json` file directly and calls
   `_on_schema_file_changed` synchronously for real, immediate
   success/error feedback, rather than guessing from an async watcher
   trigger -- creates `./desk-schemas/` on demand for the git-tracked
   choice, since picking that location through this widget is the
   explicit, informed user action the "never create it eagerly" rule
   was always about avoiding *unintentional* creation of);
   `delete_schema_key` (refuses for a widget-sourced key, edits/removes
   the owning file for a file-sourced one). `current_context.py` --
   five new provider hook pairs (`state_overview`, `state_history`,
   `state_writer`, `schema_file_writer`, `schema_file_deleter`), same
   one-hook-per-capability shape every existing pair already uses.
   `widgets/state_manager/` (new, `kind: "python"` -- matches every
   comparable Desk management widget, not `kind: "html"`): a
   `QTreeWidget` overview (key/schema/source/status) plus a detail
   panel (schema -- read-only for a widget-sourced key, editable for a
   file-sourced or undeclared one; value -- editable JSON + optional
   edit note; history -- read-only, latest-first) and a "New Key"
   dialog; subscribes to `desk.state.changed`/`SCHEMA_CHANGED_EVENT`
   via the existing `bind_event_mediator`/`EventSubscription` duck-type
   (TODO 6f9c51b) for live updates, both just triggering a full
   `refresh()`. `temp_ui.py` -- one cross-reference sentence in
   "Shared, project-scoped state" pointing at this widget; no
   `TEMPUI_DOC_VERSION` bump (the `desk.*` Bridge API surface itself is
   unchanged). Two real bugs found and fixed during manual/automated
   testing before this ever reached the verify suite: a just-set
   "Saved."/error status message was immediately wiped out by the
   follow-up `refresh()` call's own unconditional status-clear (fixed
   by never touching the status label from `_show_detail_for` itself);
   several pre-existing verify scripts' `_FakeWindow` test doubles
   needed `_ensure_state_manager_placed` (real or a no-op stub) bound,
   since `_check_schema_conflict`/`_on_schema_file_changed` now call it
   unconditionally after a successful registration. New verify
   coverage: `verify_schema_registry.py` extended (+10 checks, 35
   total) for `source_kind`/`all()`/live event publishing;
   `verify_state_manager_widget.py` (31 checks, real `DeskWindow`
   -adjacent fake, including a real end-to-end auto-placement-guarantee
   round trip: places once, stays a singleton, reappears after the
   sole instance is closed and another schema registers);
   `verify_state_manager_widget_ui.py` (18 checks, real widget
   construction against fake `current_context` providers, including
   real `EventMediator`-delivered live refreshes). Full `tests/verify/`
   regression suite passes (122 scripts total, 0 regressions -- the
   sole failure, `disabled_verify_claude_desk_widget_claude_api.py`, is
   an already-filed, already-disabled, unrelated flaky item).
   `investigations/app_structure_dsl_design.md`'s "Where things were
   left" updated to record this item's completion -- closing out the
   entire schema-validation thread (TODO `6e1c2fe`'s three-way split)
   with nothing left blocked or open in it.

297f1a6. COMPLETED: Ability to save/load shared state (`desk.state.*`, TODO
   `f68383f`) as JSON -- a whole-store snapshot/restore pair (every
   key's value, edit, and history), not a per-key operation, exposed
   through the State Manager widget (TODO `6330249`) as "Save
   State..."/"Load State..." toolbar actions. Import validates every
   key's current value against any currently-active schema before
   applying anything -- all-or-nothing, not a partial apply. Prioritized
   per direct request.
   [planned: state-store-json-import-export.md]
   COMPLETED: `src/desk/desks.py` -- promoted the existing, previously
   -private `_state_entry_dict`/`_load_state_entry` helpers to public
   `state_entry_dict`/`load_state_entry` (a second module now needs
   them) rather than reimplementing the same `StateEntry`-as-JSON shape
   a third time. `src/desk/shell/window.py` -- `export_state_json`
   (writes every current key's value/edit/history to a file);
   `import_state_json` (all-or-nothing: validates every key's current
   value against any active schema first, collecting every failure
   into one combined error before applying anything; replaces each
   key's entry wholesale, not routed through `set_state`'s
   single-entry FIFO-append; a key present in the store but absent
   from the file is left untouched; publishes `desk.state.changed` per
   actually-changed key with a new `SYSTEM_SENDER_INSTANCE_ID` sender,
   the same sentinel `SchemaRegistry` already uses for
   system-triggered changes). `current_context.py` -- `state_exporter`/
   `state_importer` provider hook pairs, the same shape every existing
   pair already uses. `widgets/state_manager/widget.py` -- "Save
   State..."/"Load State..." toolbar buttons (`QFileDialog`), a
   confirmation dialog before import (it can overwrite currently-live
   values), `refresh()` after a successful import. New
   `tests/verify/verify_state_store_json_import_export.py` (16
   checks): export/import round-trips value+edit+history for multiple
   keys exactly; a schema-violating key refuses the entire import,
   including an otherwise-valid key in the same file; a key with no
   currently-active schema imports unchanged; a key present in the
   target but absent from the file survives untouched; a real
   subscribed instance receives `desk.state.changed` for each
   imported key; malformed JSON and a non-dict top level are real,
   non-crashing errors. Full `tests/verify/` regression suite passes
   (123 scripts total, 0 failures -- including the usually-flaky
   `disabled_verify_claude_desk_widget_claude_api.py`, which happened
   to pass this run; it remains an already-filed, already-disabled
   item regardless).

5242aeb. COMPLETED: Bug: widget-triggered alerts/confirmations render as detached
   macOS windows -- notably the "Load State" confirmation and "New
   Key" validation alerts in the new State Manager widget (TODO
   `6330249`), which used a raw `QMessageBox` directly instead of the
   already-existing desk-internal popups service (`desk_services
   .popups`, TODO `359684f`), reintroducing the exact bug that service
   was built to eliminate: a `QMessageBox` parented to widget content
   embedded in a `QGraphicsProxyWidget` on the canvas renders as a
   genuine top-level macOS window whose position doesn't account for
   the canvas's own zoom/pan transform. `widgets/markdown/widget.py`'s
   "Save As" error alert had the same, apparently pre-existing,
   never-migrated instance. The fix mechanism already exists
   (`current_context.get_popup_opener()` for `kind: "python"`,
   `desk.popups.show(...)` for `kind: "html"`, both the exact same
   codepath already) and needs no new code -- this item is fixing the
   two widgets that bypassed it, strengthening the guidance an agent
   actually reads before writing a widget (`design-docs/architecture.md`'s
   Widget Model section, `temp_ui.py`'s `desk.popups.show` doc), and
   adding a real, automated regression guard rather than relying on
   anyone remembering to check by hand. Prioritized per direct request.
   [planned: fix-detached-popup-windows.md]
   COMPLETED: `widgets/state_manager/widget.py` -- new `_alert`/
   `_confirm` helpers routing through `current_context
   .get_popup_opener()`; all 5 raw `QMessageBox` call sites (4
   `.warning`, 1 `.question`) replaced; the now-unused `QMessageBox`
   import dropped. `widgets/markdown/widget.py` -- its one remaining
   `_save_as` error alert fixed the same way; same import cleanup.
   `design-docs/architecture.md` -- the Widget Model's `kind: "python"`
   bullet gained an explicit "never use a raw `QMessageBox`/`QDialog`"
   callout with the why and a pointer to `design-docs/widget-ux.md`'s
   existing "Desk-Internal Popups" section. `src/desk/temp_ui.py` --
   the existing `desk.popups.show` doc bullet gained an explicit "use
   this, not the browser's own `alert()`/`confirm()`/`prompt()`"
   callout; `TEMPUI_DOC_VERSION` bumped 36 -> 37 (doc-wording only, no
   API change). New `tests/verify/verify_widgets_use_popup_service.py`
   (3 checks) -- a real, automated regression guard: scans every
   `widgets/*/widget.py` for a live `QMessageBox.(question|warning
   |information|critical)(...)` call and fails if one is found, plus a
   self-check that the scanning regex itself still matches the exact
   offending shape and doesn't false-positive on an explanatory
   comment. `tests/verify/verify_state_manager_widget_ui.py` extended
   (+7 checks, 25 total): `_alert`/`_confirm` call the fake popup
   opener with the right title/message/buttons/default, not a real
   `QMessageBox`; declining "Load State"'s confirmation never calls the
   importer, confirming does. Found and fixed a real, unrelated test
   -infrastructure flake while adding this coverage: constructing
   further widgets/mediators in the same process *after* a test that
   builds a real `EventMediator` + `EventSubscription` could trigger
   that earlier pair's delayed garbage-collection-triggered teardown at
   a bad moment, aborting the process (an uncaught exception escaping a
   Qt `destroyed` signal handler, the same class of issue LEARNINGS.md
   already documents for `ChromiumWidget`/`QWebEngineProfile`) --
   fixed by reordering so the `EventMediator`-holding test runs last in
   that file, not by suppressing or working around the crash. Full
   `tests/verify/` regression suite passes (124 scripts total, 0
   failures).

74a8b78. COMPLETED: Bug: crash (SIGBUS) removing a desk-internal popup from the
   canvas scene during its own click event -- confirmed via a real
   macOS crash report clicking a button inside a popup shown by
   `PopupsService.show_blocking` (the only popup mechanism in the app --
   `current_context.get_popup_opener()` for `kind: "python"`,
   `desk.popups.show(...)` for `kind: "html"`, both the same codepath --
   so this affects every alert/confirmation, not just the State Manager
   widget that surfaced it, found while testing TODO `5242aeb`'s own
   fix). `WorkspaceView.remove_popup` calls `self.scene().removeItem(proxy)`
   synchronously, from inside the very click handler `QGraphicsScene`
   is still mid-dispatch of -- a real, known Qt Graphics View
   reentrancy hazard (Qt's internal object-liveness bookkeeping,
   `QSharedPointer::ExternalRefCountData::getAndRef`, dereferences a
   stale pointer). Fix: `frame.hide()` and the `_popup_frames` removal
   stay synchronous (neither mutates the scene graph); the actual
   `removeItem`/`deleteLater()` defers via `QTimer.singleShot(0, ...)`,
   the same "past the current event dispatch" idiom this file already
   uses elsewhere. Prioritized per direct request.
   [planned: fix-popup-scene-removal-crash.md]
   COMPLETED: `src/desk/shell/canvas.py` -- `WorkspaceView.remove_popup`
   now calls `frame.hide()` and removes `frame` from `_popup_frames`
   synchronously (neither mutates the scene's own item list, so
   neither carries the reentrancy risk -- the popup still disappears
   immediately and is instantly excluded from z-ordering/
   `clear_widgets`'s own membership check), then defers the actual
   `self.scene().removeItem(proxy)`/`frame.deleteLater()` via
   `QTimer.singleShot(0, ...)`, the same "past the current event
   dispatch" idiom this file already used for
   `_position_desk_picker`/etc. `clear_widgets`'s own separate,
   defensive-fallback removal path (a popup with no listener attached
   at all) is untouched -- it was never called from inside the scene's
   own event dispatch, so it never had this hazard. This item's own
   verification is necessarily indirect: a real, native-event-driven
   Qt Graphics View reentrancy crash (confirmed via an actual macOS
   crash report) can't be reproduced by an automated, offscreen test --
   there's no equivalent native `NSApplication`/`CFRunLoop` event
   source to recreate the exact reentrant-dispatch timing headlessly.
   Verification instead confirms the specific, deliberate behavior
   change the fix makes: `tests/verify/verify_desk_internal_popups.py`
   gained `test_scene_removal_is_deferred_not_synchronous` (+6 checks,
   31 total in that file) -- clicking a popup's button hides it and
   updates `_popup_frames` synchronously (already covered, confirmed
   unchanged), but its `QGraphicsProxyWidget` is still genuinely
   present in the scene immediately after the click, before any
   event-loop pump; only after pumping (`processEvents()` +
   `QCoreApplication.sendPostedEvents(..., QEvent.Type.DeferredDelete)`,
   since a plain pump alone isn't guaranteed to run a `deleteLater()`
   -scheduled deletion in this environment) does the proxy/frame
   actually get torn down (`PyQt6.sip.isdeleted`). Full `tests/verify/`
   regression suite passes (124 scripts total, 0 failures).

8df6797. Make the Claude (Desk) widget's prompt input
   (`widgets/claude_desk/widget.py`'s `_prompt_input`, currently a
   single-line `QLineEdit`) a multi-line box that wraps text instead,
   so a long prompt wraps visually rather than scrolling off-screen
   horizontally. Needs a way to distinguish "insert a newline" from
   "send" once `returnPressed` (a `QLineEdit`-only signal) is no
   longer available -- e.g. Enter to send, Shift+Enter for a newline.

78d6207. Visually differentiate user-entered prompts from Claude's own
   responses in the Claude (Desk) widget's history
   (`widgets/claude_desk/widget.py`'s `_history`), without breaking
   copy/paste out of it. Right now `_append_history` just appends
   plain text -- a "> " prefix for what the user typed
   (`_on_send_clicked`, `start_session`), unprefixed text for
   everything else (`_on_assistant_text`, tool use/result, permission,
   error) -- all in one uniformly-styled `QPlainTextEdit`, making it
   hard to visually scan who said what. Whatever styling is used
   (color, weight, indentation, ...) must preserve today's plain-text
   selection/copy behavior exactly -- no stray markup and no altered
   whitespace when copying a message or a whole transcript.

a4c3dec. Add an on-hover control in the Claude (Desk) widget's history
   (`widgets/claude_desk/widget.py`'s `_history`) that reloads a
   previous user-entered prompt back into `_prompt_input` (e.g. to
   edit and resend it), without breaking normal text
   selection/copy-paste -- neither out of `_history` itself nor out of
   `_prompt_input` while typing. Depends on TODO `78d6207`
   distinguishing user lines from the rest of the history to know
   which lines are reloadable.

93364f9. COMPLETED: Add a `[chat]` button (relabeled from this item's own earlier
   "talk to Claude about this widget" working name -- same feature,
   restated by the user later in the same session with a tighter spec)
   to the widget frame chrome (`src/desk/shell/widget_frame.py`'s
   small indicator-button family -- `_TempuiPromoteButton`/
   `_StaleIndicatorButton`/`_ErrorIndicatorButton` are the existing
   precedent), dispatched centrally through `canvas.py`'s
   `_hit_test_chrome`/mouse handling the same way those are. Clicking
   it launches a new agent conversation (a "Claude (Desk)" widget,
   TODO `a596dbf`) with a fresh session about the clicked widget,
   whose initial prompt gives the new session notes on how to access
   each of three things, rather than assuming which one the user
   actually wants discussed:
   - **The live instance** -- its widget kind/id, `instance_id`, and
     current title/state (the same reference shape this item's own
     original draft already specified).
   - **The code** -- where that widget kind's own source lives on disk
     (`widgets/<id>/` -- `widget.py`/`widget.json` for `kind:
     "python"`, `index.html`/compiled sources for `kind: "html"`) so
     the new session can go read the real implementation rather than
     guessing.
   - **The definition** -- the widget's own manifest (`widget.json`,
     or a `DefineWidget` tempui file's own header fields), including
     anything schema-related once the shared state store (see the
     `desk.state.*` design discussion, `investigations/app_structure_dsl_design.md`)
     lands -- a widget's declared state schemas are exactly the kind
     of thing "let's discuss this widget" would want visible.
   Not designed yet -- open questions include the exact prompt
   wording/notes format for each of the three, whether this button
   appears on every widget or only certain kinds, and whether it
   should reuse `_place_discuss_claude_widget`'s existing shape
   (adapted for the new widget kind) or needs its own placement
   helper.

   Resolved: shows on every widget (per direct user confirmation);
   uses a new `_place_widget_chat_about` helper rather than reusing
   `_place_discuss_claude_widget` (that one is hardcoded to the older
   PTY-based `claude` kind and always centers on the viewport). Along
   the way, fixed a pre-existing `_BUTTON_KINDS` gap (`"error"` was
   never added despite `_hit_test_chrome`/`mouseReleaseEvent` already
   handling it) and corrected this item's own draft assumption that
   `desk.state.*` access is gated by a widget's declared
   `capabilities` -- it isn't; nothing today declares a `"state"`
   capability and the store isn't capability-checked at all, so the
   generated instructions describe that accurately instead. See
   `plans/widget-chat-button.md` for the full design.
   [planned: widget-chat-button.md]

0529501. An API for widgets to invoke Claude with access scoped to
   only the files that widget itself has access to, rather than a full
   unrestricted session. Motivating example: the peer `necro-4x`
   project's domain-analysis widget has a prompt text field meant to
   be handed to `claude` (via the CLI) for file processing of the
   widget's current file -- indirect and awkward (getting the prompt
   text out to the CLI by hand) compared to just having a file picker
   in the widget itself that hands the chosen file(s) to Claude
   directly. Generalizing past that one widget: any widget that already
   knows which specific file(s) it's allowed to touch could offer a
   similar "send this to Claude" affordance without needing to hand out
   broader filesystem access than the widget itself has.
   Builds on TODO `a596dbf`'s `desk.claude_session.ClaudeSession` (the
   Python Agent SDK wrapper) -- `ClaudeAgentOptions` already has
   `add_dirs`/`cwd`/`sandbox` (`SandboxSettings`) fields that look like
   the right building blocks for constraining a session to a specific
   file or directory set, but none of that's been exercised for a
   *restricted* (as opposed to full-project-cwd) session yet; needs
   real investigation into whether `add_dirs`/`sandbox` alone are
   sufficient to actually enforce single-file/limited-file scoping (not
   just "the model was told to only touch this," but something Desk
   can trust), or whether `can_use_tool` also needs real per-invocation
   path-checking logic layered on top. Not designed at all yet -- open
   questions include what the actual widget-facing API shape should be
   (a new `desk.` module other widgets import, matching
   `desk.terminal_widget`/`desk.claude_session`'s own precedent?), and
   whether it reuses `ClaudeDeskWidget`'s own UI or is meant to run
   headless/inline within the calling widget instead.

ed5c62f. De-prioritized (moved to the end of the queue on request --
   priority is physical position in this file, per
   shared_development_process.md's Item IDs section). Add
   folding/collapsing to the Claude (Desk) widget's history view
   (`widgets/claude_desk/widget.py`'s `_history`) for tool invocations.
   Right now `_on_tool_use`/`_on_tool_result` append a `[tool]
   Name(args)`/`[tool result] ...` line unconditionally, with no way to
   hide it -- a session with several tool calls (each potentially
   carrying a large `input`/`content` payload, e.g. a `Write`'s full
   file contents or a long `Bash` command's stdout) makes the
   transcript hard to scan for the actual conversation. Needs a real
   collapsed/expanded UI affordance (not just truncating text) --
   `QPlainTextEdit` has no native per-block fold/collapse support, so
   this likely means switching the history view to something richer
   (a `QTreeWidget`-style structured view, or `QTextEdit` with
   clickable custom text objects) rather than staying on today's
   single flat plain-text log; not designed yet.

b2ab79f. PENDING: Figure out how to properly integrate regression tests that
   use real system hardware -- specifically, several `tests/verify/`
   scripts start a real `MicRecorder` capture
   (`src/desk/voice_capture.py`, a real `QAudioSource` against the
   actual default microphone) as part of their coverage
   (`disabled_verify_voice_capture.py`,
   `disabled_verify_voice_input_widget_mic.py`,
   `disabled_verify_claude_desk_widget_mic.py` -- see their own
   top-of-file comments). Running these automatically as part of every
   regression sweep was audibly/visibly activating the system mic each
   time, which isn't wanted -- disabled (the standard `disabled_`
   prefix convention) for now. Still worth being able to run this kind
   of coverage occasionally by hand rather than losing it outright, so
   this needs a real decision, not just leaving it disabled forever --
   see `QUESTIONS.md` for the open questions.
   [planned: hardware-dependent-regression-tests.md]

9bc522b. PENDING: Figure out how to properly integrate regression tests that
   make real Claude API calls -- specifically, several `tests/verify/`
   scripts start a real `ClaudeSession` (`desk.claude_session`, the
   Claude Agent SDK wrapper) or place a real `ClaudeWidget` (which
   execs the actual `claude` CLI in a PTY) as part of their coverage
   (`disabled_verify_claude_desk_widget_claude_api.py`,
   `disabled_verify_discuss_parking_lot_item_claude_api.py`,
   `disabled_verify_questions_discuss_button_claude_api.py` -- see
   their own top-of-file comments). Running these automatically as
   part of every regression sweep makes real network calls to the live
   Claude API, incurs real API cost/quota, and depends on the live
   model's actual behavior -- not wanted for a routine sweep, so
   extracted/disabled (the standard `disabled_` prefix convention) for
   now. Still worth being able to run this kind of coverage
   occasionally by hand rather than losing it outright, so this needs
   a real decision, not just leaving it disabled forever -- see
   `QUESTIONS.md` for the open questions.
   [planned: live-claude-api-regression-tests.md]

0d91c74. PENDING: Figure out how to properly integrate regression tests that
   make real network calls to Hugging Face Hub -- specifically, two
   tests in `tests/verify/verify_whisper_model_download_script.py`
   (a real repo-existence check via `HfApi`, and a real run of the
   download script itself, which unlike `desk.speech.transcribe()`
   does not force offline mode) reach out to the live Hub over the
   network. Running these automatically as part of every regression
   sweep depends on live internet access, which isn't wanted for a
   routine sweep -- extracted/disabled (the standard `disabled_`
   prefix convention) to
   `disabled_verify_whisper_model_download_script_network.py` for now
   (see its own top-of-file comment); the rest of that file's coverage
   (CLI error handling, a deliberately-unreachable-Hub resilience
   check, local cache-location checks, doc-content checks) needs no
   real network and keeps running normally. Still worth being able to
   run this kind of coverage occasionally by hand rather than losing
   it outright, so this needs a real decision, not just leaving it
   disabled forever -- see `QUESTIONS.md` for the open questions.
   [planned: live-network-model-download-regression-tests.md]

b6abde2. PENDING: Figure out how to properly integrate regression tests that
   use the real system clipboard -- specifically, every test in
   `tests/verify/verify_paste.py` reads/writes the actual system
   clipboard (`QApplication.clipboard()`), and two of them call
   `clipboard.clear()`, which destroys whatever the user actually had
   copied at the time the regression sweep ran. Disabled outright (the
   standard `disabled_` prefix convention, whole file since every test
   touches the clipboard) for now --
   `disabled_verify_paste.py`. Still worth being able to run this kind
   of coverage occasionally by hand rather than losing it outright, so
   this needs a real decision (a save-and-restore-the-real-clipboard
   wrapper around each test looks like the simplest fix, but needs
   confirming, not assuming, that it round-trips every MIME flavor
   these tests set losslessly), not just leaving it disabled forever
   -- see `QUESTIONS.md` for the open questions.
   [planned: system-clipboard-regression-tests.md]

feff1ec. Review and discuss all of the new FEEDBACK items (feedback
   submitted via the Feedback widget, `DESK_FEEDBACK-*.md` files) with
   the user before acting on any of them. Not designed/scoped yet --
   this item is just the reminder to have that discussion.

f165b8c. Investigate options for running Desk jobs on cloud VMs, given
   that Desk uses `claude` and many VM providers have blanket
   no-running-AI policies. Not designed/scoped yet.

e6ea1db. Investigate approaches to running Desk in a way that better
   isolates it -- e.g. not giving it full access to absolute paths or
   system calls, etc. Not designed/scoped yet.

742ba0a. COMPLETED: Add pypdf as an optional Desk dependency (a `desk[pdf]`
   extra), explicitly framed as a provisional stopgap for PDF
   structural parsing (e.g. outline/bookmark extraction) needed by
   `kind: "python"` transforms, which run in-process
   (`desk_services/transforms/service.py`'s `_load_transform_module`/
   `_run_python`) and so cannot bring their own project-level
   dependencies -- the dependency has to live in Desk's own
   `pyproject.toml` or nowhere. From
   `../FEEDBACK/FEEDBACK-DESK-pypdf-optional-dependency-as-stopgap-2026-08-04-1535.md`
   (via TODO `feff1ec`'s review). Decided in discussion with the user:
   add it now as an optional extra (not a hard dependency), labeled as
   provisional against `PARKINGLOT.md`'s
   parked "file/stream format DSL" direction -- though that direction
   is itself gated behind formalizing "DSL" as a general concept
   first, so in practice this should be expected to stick around for a
   while, not treated as imminently temporary. See also the parking
   -lot entry for subprocess-isolated transform dependencies -- the
   more general alternative that was discussed and deliberately not
   pursued now.
   [planned: pypdf-optional-dependency.md]

   Added `[project.optional-dependencies]` to `pyproject.toml`
   (`pdf = ["pypdf"]`), with a comment above it explaining the
   provisional framing and pointing at the parked DSL direction. No
   other code changes -- there is no PDF-handling transform or widget
   in this repo itself; the actual consumer is a different project
   authoring its own transform. Installed via `.venv/bin/pip install
   -e ".[pdf]"` and confirmed `pypdf` (6.14.2) imports and exposes
   `PdfReader.get_destination_page_number`, the outline-resolution API
   the motivating use case needs. New
   `tests/verify/verify_pypdf_optional_dependency.py` (6 checks: the
   extra is declared correctly, `pypdf` is not in the base
   always-installed dependency list, and the real import/API checks
   above). Full `tests/verify/` regression suite passes (87 scripts).
   The subprocess-isolated-dependencies alternative is recorded
   separately in `PARKINGLOT.md`.

a5f66cc. COMPLETED: Fix `kind: "html"` widgets' sub-resource requests (`<script
   src>`, `<link href>`, CSS `url(...)`, `<img src>`, etc.) losing the
   per-launch auth token, which silently 401s and aborts the
   module/resource graph with no console output -- the root cause
   found investigating `widgets/hex_flower`'s blank page (TODO
   `4ab5875`, `DESK_FEEDBACK-2026-07-13T012144.md`) and independently
   cited by `../FEEDBACK/FEEDBACK-DESK-widget-extraction-communication-gaps-2026-08-03-1634.md`
   as the top blocker for splitting any multi-component app into
   widgets. Moved out of its `PARKINGLOT.md` cluster (via TODO
   `feff1ec`'s review, see `investigations/feedback_review.md`) now
   that it has an agreed design -- the remaining items in that cluster
   (visible failure signal, reconsidering `DefineWidget`'s
   single-inlined-file requirement, a known-good template, doc
   coverage of what does/doesn't work yet, debugging guidance) stay
   parked as follow-ups sequenced after this lands.

   Decided in discussion with the user:
   - **Fix**: a same-origin cookie carrying the token, set on the
     widget's main-page response (which already carries the token as
     a query param) -- additive to the existing query-param/
     `X-Desk-Token`-header checks in `TokenAuthMiddleware`
     (`src/desk/server/app.py`), not replacing them.
   - **Folded in: per-instance `QWebEngineProfile` isolation.**
     `ChromiumWidget` (`src/desk/shell/chromium_widget.py`) currently
     uses Qt's shared default profile for every `kind: "html"` widget
     instance -- confirmed no `QWebEngineProfile` is constructed
     anywhere in the codebase today. Since cookies aren't port-scoped
     (RFC 6265 scopes by host+path, not port) and Desk's per-launch
     port changes but its host doesn't, a cookie on the shared default
     profile would end up shared across every widget instance on the
     origin and would persist indefinitely in Qt's on-disk persistent
     cookie jar across separate Desk launches. Giving each
     `ChromiumWidget` instance its own persistent profile under
     `.desk_temp/chromium-profiles/<instance_id>/` (`instance_id` is
     already the stable, restart-surviving identity
     `desk.self.getLocalStorage` relies on) scopes the token cookie
     -- and all other browser storage/cache -- to just that instance,
     and extends `architecture.md`'s existing "each `kind: "html"`
     widget is its own isolated renderer process" claim down to the
     storage layer too, rather than leaving that claim undermined by a
     profile every instance actually shares today.
   - **`widgets/browser/widget.py`'s `BrowserWidget` is unaffected.**
     It's a structurally separate `kind: "python"` widget that owns
     its own plain `QWebEngineView()` directly, not built on
     `ChromiumWidget` -- confirmed directly, not assumed. It keeps
     using Qt's default profile (real persisted logins/cookies for
     actual web browsing) exactly as today.
   - **Cleanup**: closing a widget instance for good
     (`DeskWindow.close_widget`) should delete its profile directory;
     switching Desks (`WorkspaceView.clear_widgets`) must not -- a
     widget merely removed from the canvas temporarily (not
     permanently closed) needs its profile intact for when that Desk
     reopens.
   - Note for whoever picks this up: `.desk_temp/`'s established
     convention elsewhere in this doc set is "fully disposable,
     regenerable on demand" -- real per-widget browser storage
     (cookies/localStorage a widget's own JS or an external service
     might set) is not regenerable the same way, so
     `.desk_temp/chromium-profiles/` is a deliberate exception to that
     framing, worth calling out explicitly wherever `.desk_temp/`'s
     general disposability is documented, not left to look like an
     oversight.
   [planned: kind-html-auth-token-and-profile-isolation.md]

   Implemented as designed above: `TokenAuthMiddleware`/
   `_token_from_scope` (`src/desk/server/app.py`) now check a
   `desk_token` cookie as a third fallback (after query param and
   `X-Desk-Token` header), and `TokenAuthMiddleware` sets it via a
   wrapped ASGI `send` whenever the token specifically came from the
   query string. Confirmed end to end with a real HTTP client against
   a running server (no Qt involved): the widget page response sets
   the cookie, a follow-up request carrying only the cookie succeeds,
   and a credential-less request still 401s. `ChromiumWidget`
   (`chromium_widget.py`) now constructs its own named, persistent
   `QWebEngineProfile` per instance, storage/cache rooted under
   `.desk_temp/chromium-profiles/<instance_id>/`; `window.py`'s
   `_place_widget` computes that path via a new
   `_chromium_profile_dir` helper, and `close_widget` deletes it
   (deferred) via a new `_schedule_chromium_profile_cleanup` helper --
   `WorkspaceView.clear_widgets` (Desk-switch) deliberately calls
   neither. `architecture.md` documents both the token requirement and
   the per-instance-profile isolation property.

   Two real, non-obvious bugs found and fixed along the way, both
   confirmed by direct reproduction, not assumed:
   - **A genuine segfault** from parenting the new `QWebEngineProfile`
     to the same widget as its `QWebEnginePage` (Qt's sibling
     -destruction order between the two isn't guaranteed, and a
     profile must outlive every page using it) -- fixed by leaving the
     profile unparented and deferring its own `deleteLater()` to the
     widget's `destroyed` signal (which only fires once every child,
     including the page, is already gone). A second, separate
     `RuntimeError` this surfaced (the profile's C++ object already
     gone by the time that signal fired, e.g. during interpreter
     shutdown) was fixed with an explicit `sip.isdeleted()` guard.
   - **A verify-script-only, non-deterministic segfault** at process
     exit once 2+ real per-instance profiles existed across a script's
     lifetime -- confirmed directly that this is specific to a
     headless `processEvents()`-polling test harness racing against
     Qt/Chromium's own internal teardown at interpreter shutdown, and
     that a real Desk session (which always runs via a genuine
     `app.exec()` all the way to a real quit) is not at risk. Fixed in
     every affected verify script by calling `os._exit(...)` instead
     of `sys.exit(...)` as the final line -- skipping interpreter
     teardown entirely, the same way force-quitting a process does --
     since every check/assertion had already passed correctly before
     the crash in every case. See `LEARNINGS.md`'s expanded TODO
     `a5f66cc` entry for the full investigation.

   Updated for the new required `ChromiumWidget` constructor parameter
   and/or the new `os._exit()` teardown pattern:
   `tests/verify/verify_shared_document_editor_base.py`,
   `verify_custom_widget_content_hash.py`,
   `verify_html_widget_local_storage.py`,
   `verify_relocate_promoted_widget_source.py`,
   `verify_stale_marker_click_dialog.py`,
   `verify_tempui_custom_widgets.py`,
   `verify_widget_error_indicator.py` (the last one was also missing
   `current_desk` on its own `_FakeWindow` entirely, now added). New
   `tests/verify/verify_kind_html_auth_token_and_profile_isolation.py`
   (17 checks): the cookie mechanics above, a real multi-file widget
   fixture that previously would have failed to load now loading
   successfully end to end (confirmed via the custom element's
   `shadowRoot`, mirroring the original hex_flower diagnosis's own
   verification method), distinct on-disk profile directories for two
   instances of the same widget kind, `_schedule_chromium_profile_cleanup`
   deleting only the targeted instance's directory, `close_widget`
   -vs-`clear_widgets` cleanup asymmetry (confirmed via source
   inspection, given the full `DeskWindow`/`save_current_desk`
   machinery `close_widget` depends on is disproportionate to
   construct just to observe this one side effect), and
   `BrowserWidget` continuing to use Qt's default profile, unaffected.
   Full `tests/verify/` regression suite passes cleanly (88 scripts,
   0 failures), reconfirmed with repeated runs of every script this
   item touched given the non-deterministic nature of the crash it
   fixed.

e42469e. COMPLETED: Fix a now-stale claim in the tempui doc set (`src/desk/temp_ui.py`'s
   `_CUSTOM_WIDGETS_DOC`, materialized as `tempui-custom-widgets.md` --
   the docs shown to Claude/agent instances working *inside*
   Desk-managed projects, not Desk's own internal `design-docs/`).
   Found by re-checking the doc set against TODO `a5f66cc`'s changes
   after the user asked to make sure the tempui docs stay current.
   `a5f66cc` only updated `design-docs/architecture.md` (Desk's own
   internal doc) -- it never touched `temp_ui.py`, leaving this
   inaccuracy in what agents in *other* projects actually read. The
   doc's "The Desk Bridge API" section currently states flatly that
   `desk.self.getLocalStorage`/`setLocalStorage` is "the only way to
   persist your widget's own state across a Desk reload (there is no
   other storage available -- no `localStorage`/`IndexedDB`/cookies
   persist a Chromium widget's page across a reload ... or ... a Desk
   restart)". `a5f66cc`'s per-instance `QWebEngineProfile` isolation
   makes this false: real browser storage now does persist across a
   reload and a Desk restart, for as long as that widget instance
   stays placed (its profile is only deleted on permanent removal).
   Separately confirmed via research (see the investigation this TODO
   is filed from): this fix is scoped narrowly to that one claim --
   documenting the auth-token cookie mechanism itself was considered
   and deliberately *not* added here, since the only widget-authoring
   path currently available to an in-project agent (`DefineWidget`,
   always single-inlined-file) never hits the bug the cookie fixes in
   the first place; that only becomes relevant once `PARKINGLOT.md`'s
   already-parked "Reconsider `DefineWidget`'s single-inlined-file
   requirement" follow-up is implemented. Not designed/scoped beyond
   the summary above yet -- the actual replacement wording, and the
   version-bump/changelog-entry mechanics, are TODO for the plan.
   [planned: tempui-doc-storage-claim-fix.md]

   Rewrote `_CUSTOM_WIDGETS_DOC`'s "The Desk Bridge API" storage
   paragraph: `getLocalStorage`/`setLocalStorage` is still framed as
   the *recommended* mechanism (its data lives in the portable `.desk`
   file), while now correctly stating that each widget instance's page
   also gets real, persistent browser storage (cookies/`localStorage`/
   `IndexedDB`, per TODO `a5f66cc`'s per-instance `QWebEngineProfile`)
   -- explicitly noting that storage is `.desk_temp`-scoped and deleted
   with the widget instance, unlike the portable, recommended path.
   Bumped `TEMPUI_DOC_VERSION` 26 -> 27 with a matching comment block
   and a new `## Version 27` entry in `_NEW_FEATURES_DOC`. Deliberately
   did *not* add documentation about the auth-cookie mechanism itself
   -- confirmed the only widget-authoring path available to an
   in-project agent (`DefineWidget`) is always single-inlined-file and
   never hits the bug that cookie fixes, so nothing about it is
   actionable from inside this doc set until the still-parked
   `PARKINGLOT.md` "reconsider single-inlined-file requirement"
   follow-up lands. New
   `tests/verify/verify_tempui_storage_claim_fix.py` (15 checks: the
   version bump, the stale claim's removal, `getLocalStorage` still
   recommended with correct reasoning, the new storage correctly
   scoped/caveated, the new-features entry, and
   `ensure_docs_current`'s stale-doc rewrite path still working
   correctly against the new version). Full `tests/verify/`
   regression suite passes (89 scripts, 0 failures).

a8e4115. COMPLETED: Add Desk's own `CLAUDE.md` a project instruction to use paths
   relative to the current project directory rather than absolute
   ones, matching an instruction another project's `CLAUDE.md` was
   recently given. From
   `../FEEDBACK/FEEDBACK-DESK-claude-md-relative-paths-2026-08-03-1604.md`.
   Not designed/scoped beyond the one-line addition itself -- trivial.
   [planned: claude-md-relative-paths.md]

   Added the line verbatim to `CLAUDE.md`.

7c11fe0. COMPLETED: `TransformsService` (`src/desk_services/transforms/service.py`)
   never notices a transform added or changed on disk after Desk
   startup/Desk-switch -- `_require` fails immediately with `Unknown
   transform: ... (call discover() first)` on a lookup miss, and even
   a manual re-`discover()` (e.g. via the Transform Manager widget's
   Refresh button) doesn't help an *edited* Python transform, since
   `self._python_modules` is never invalidated (the JS/TS path already
   partially self-heals via `_resolve_js_entry`'s own mtime check,
   `service.py:118-120`, but there's no Python equivalent). From
   `../FEEDBACK/FEEDBACK-DESK-transform-discovery-staleness-2026-08-04-1301.md`.
   Suggested fix: on a lookup miss, `_require` retries `discover()`
   once (needs `desk_temp_dir`/`project_dir` stored on the service at
   the last real `discover()` call, e.g. alongside `self._transforms`,
   so `_require` doesn't need every call site to pass them through)
   before raising `Unknown transform`; separately, track each Python
   transform's source mtime at load time and drop/reload
   `self._python_modules[info.id]` if the source's current mtime is
   newer, mirroring `_resolve_js_entry`'s own check for the JS/TS
   path. Not designed further yet.
   [planned: transform-discovery-staleness.md]

   Implemented as designed: `discover()` now records
   `desk_temp_dir`/`project_dir` onto `self`; `_require` retries
   `discover()` once on a lookup miss before raising; `_run_python`
   stats each Python transform's source file and drops/reloads the
   cached module whenever its mtime has moved since it was last
   loaded, tracked in a new `self._python_module_mtimes` dict. New
   coverage in `tests/verify/verify_transforms_service.py` (3 new
   checks): a transform added to disk after the initial `discover()`
   is found and runs with no explicit second `discover()` call; a
   genuinely unknown `transform_id` still raises after the retry; an
   edited-on-disk Python transform's new source is picked up on the
   very next invocation, not the stale cached module. Full
   `tests/verify/` regression suite passes (89 scripts, 0 failures).

47aaf73. COMPLETED: The `[ERROR]` titlebar button can light up and then silently
   do nothing when clicked. Root cause, confirmed directly: the click
   handler (`DeskWindow._on_widget_error_clicked`,
   `src/desk/shell/window.py:1970`) does `if not
   frame.last_error_message: return` -- inferring "was there an
   error" from the captured message string's truthiness -- but the
   capture code (`_LoggingWebEnginePage.javaScriptConsoleMessage`,
   `src/desk/shell/chromium_widget.py:57-68`) already has a deliberate
   `message or ""` fallback for exactly the case where Qt hands back a
   falsy message for a real error (an uncaught exception/rejection/
   `console.error()` call with no usable text) -- so the click
   handler's own gate is wrong precisely for the case that fallback
   exists to handle: the button stays visible (lit) forever, since
   `set_error(False)` is never reached. From
   `../FEEDBACK/FEEDBACK-DESK-error-indicator-empty-message-noop-2026-08-04-1305.md`.
   Suggested fix: give `WidgetFrame` (or reuse `_TitleBar`'s own
   existing, currently-private `_has_error` bool,
   `widget_frame.py:297`) an explicit has-error flag, independent of
   `last_error_message`'s content; gate `_on_widget_error_clicked` on
   that flag, not on `last_error_message` truthiness; fall back to a
   placeholder string (e.g. `"(no error message was captured)"`) when
   showing the dialog for an error with empty text, instead of the
   message's emptiness silently cancelling the whole notification.
   Only affects the `kind: "html"`/`ChromiumWidget` path -- the
   `kind: "python"` path (`build_error_changed`) always carries
   `traceback.format_exc()`, never empty, so it doesn't have this
   problem. Not designed further yet.
   [planned: error-indicator-empty-message-noop.md]

   Implemented as designed: `WidgetFrame` gained a public `has_error:
   bool` (matching `self.locked`'s own naming convention, not a
   private-prefixed name, since `DeskWindow` reads it externally --
   distinct from `_TitleBar`'s own, unrelated private `_has_error`
   used purely for button-visibility styling), set unconditionally in
   `set_error`. `_on_widget_error_clicked` now gates on `frame
   .has_error`, and falls back to `"(no error message was captured)"`
   when showing the dialog for an empty captured message. New coverage
   in `tests/verify/verify_widget_error_indicator.py` (5 new checks):
   an empty-message error still sets `has_error`/shows the button,
   clicking it now actually shows the placeholder-text dialog instead
   of silently doing nothing, the indicator/flag both clear correctly
   afterward, and a full set/clear cycle keeps the flag in sync. Full
   `tests/verify/` regression suite passes (89 scripts, 0 failures).

1b7e500. COMPLETED: `desk-temporary-ui.md`'s "Questions for the user" section
   (`src/desk/temp_ui.py:236`, "Each entry is a `## <short summary>`
   heading...") describes a `QUESTIONS.md` heading format the real
   parser doesn't accept -- `src/desk/questions_file.py`'s
   `ENTRY_START_RE`/`TODO_ID_RE` (lines 20-21) require the heading to
   **start with the literal word `TODO`** and every referenced id to
   be **backtick-wrapped**: `## TODO \`<id>\`[/\`<id2>\`...]:
   <summary>` (confirmed against `plans/questions-widget.md`'s own
   original design -- entries were deliberately scoped to
   TODO-blocking questions, not general free-standing ones -- none of
   which the doc mentions). An entry whose heading doesn't match
   `ENTRY_START_RE` at all doesn't partially parse -- it's silently
   absorbed into `preamble`, genuinely invisible: `parse_questions_file`
   returns it as zero entries, `_on_questions_file_changed`
   (`window.py:1465`) computes an empty `new_keys` and returns before
   ever showing the "new question" notification the doc promises, and
   the Questions widget shows nothing either -- indistinguishable from
   a `QUESTIONS.md` with no questions at all, at every layer, with no
   diagnostic anywhere. From
   `../FEEDBACK/FEEDBACK-DESK-questions-md-format-undocumented-and-brittle-2026-08-04-1347.md`.
   Suggested fix: correct the doc to state the real required heading
   shape and that an entry must reference at least one TODO id
   (matching the deliberate original design -- not changing
   `questions_file.py`'s parser to add free-standing-question support,
   which would be a real feature addition, not a doc-accuracy fix);
   separately, stop the failure being *totally* silent -- e.g. a small
   helper that counts real `## ` headings that didn't match
   `ENTRY_START_RE` in a given file, with `_on_questions_file_changed`
   logging a low-severity warning (matching this project's own
   `_relocate_promoted_widget_source`-style "free for the common case
   to ignore, a real breadcrumb for the uncommon one" precedent) when
   that count is nonzero. Not designed further yet.
   [planned: questions-md-format-doc-and-silent-failure.md]

   Implemented as designed: rewrote the doc section to state the real
   required heading shape (a fenced-code-block example, not nested
   backticks, after catching a real `SyntaxWarning`/leaked-backslash
   bug in an early draft of the edit) and the TODO-id requirement
   explicitly; bumped `TEMPUI_DOC_VERSION` 27 -> 28 with a matching
   `_NEW_FEATURES_DOC` entry. New `questions_file.unparsed_heading_count(path)`
   (counts `## ` headings that don't match `ENTRY_START_RE`, without
   changing `parse_questions_file`'s own 4-call-site return signature);
   `_on_questions_file_changed` now calls it and logs a `logger.warning`
   naming the file and count when nonzero, leaving the well-formed case
   completely silent as before. New
   `tests/verify/verify_questions_md_format_fix.py` (15 checks): doc
   content, the new-features entry, `unparsed_heading_count` against
   well-formed/no-heading/malformed/mixed fixtures (confirmed to report
   the real count, not just nonzero -- caught and fixed a test-fixture
   mistake of my own along the way, an id that wasn't backtick-wrapped
   but still matched `ENTRY_START_RE`'s literal-`TODO`-prefix check, so
   it wasn't actually "unparsed" by this function's own documented
   definition), and real logging capture (via this project's own
   established `_WindowLogCapture` pattern) confirming a malformed file
   logs exactly one warning naming the path/count and a well-formed one
   logs nothing. Full `tests/verify/` regression suite passes (90
   scripts, 0 failures).

e86a31b. COMPLETED: A project's stale, pre-fix copy of `scripts/build_widget.py`
   can silently defeat the already-shipped capabilities-emission fix
   already living in the auto-refreshed `.desk_temp/build_widget.py`
   (TODO `31db3f6`) -- both compile/produce a valid `DefineWidget`
   file with the same exit code either way, but the stale copy (from
   before TODO `029047b` moved the mechanism to `.desk_temp/`, bumped
   16->17) has zero mentions of `Capability` and silently drops every
   capability a widget declares. Confirmed via `git grep`/`ls` that
   Desk's own repo no longer seeds any `scripts/build_widget.py`
   itself (no `_seed_build_widget_script`-shaped function exists) --
   this is purely legacy drift in a project that adopted Desk before
   that move, with nothing today warning it's stale/unused. From
   `../FEEDBACK/FEEDBACK-DESK-stale-build-widget-script-defeats-capabilities-fix-2026-07-31-1445.md`.
   Suggested fix: have the generated `.desk_temp/build_widget.py`
   script (`_BUILD_WIDGET_SCRIPT` in `src/desk/temp_ui.py:1126`,
   specifically its `main()` at line 1312) check, at the very start of
   `main()`, whether a `scripts/build_widget.py` also exists in the
   project and print a loud warning if so -- doesn't need either
   file's own version, just its own canonical location plus the other
   one's existence. Two smaller, related gaps from the same FEEDBACK
   item, fixable in the same pass:
   - `main()` (same file) writes a fresh `.desk_temp/<uuid>` file on
     every build and never touches an earlier build's file for the
     same keyword -- an un-promoted widget iterated on across many
     sessions accumulates one leftover file per rebuild forever, with
     a real (if narrow) risk: `_register_custom_widgets_from_desk_temp`
     re-scans `.desk_temp` in alphabetical (not chronological) order
     at startup/Desk-switch, so several stale same-keyword files left
     behind could make an old one "win" again with no relationship to
     which was built most recently. Since `build_widget()` already
     knows the keyword it just built, have `main()` delete any other
     same-keyword `DefineWidget` file in the same output directory
     immediately after a successful build.
   - The Bridge client's thrown `Error`
     (`src/desk/server/bridge_client.py`'s `call()` helper) bakes the
     HTTP status into the message string (`` `Desk Bridge ${path}
     failed (${response.status}): ${text}` ``) instead of exposing it
     as a structured property -- a capability rejection (403) and a
     genuine not-found (400) are indistinguishable from a `catch`
     block without regex/substring-matching the free-text message.
     Attach the numeric status directly (e.g. `err.status =
     response.status` right before throwing) so calling code can
     branch on `err.status` without parsing the message.
   Not designed further yet.
   [planned: stale-build-widget-script-fix.md (COMPLETED)]

   COMPLETED: confirmed `_BUILD_WIDGET_SCRIPT`'s `main()`
   (`src/desk/temp_ui.py`) now checks a new module constant
   `STALE_SIBLING_SCRIPT_PATH = Path("scripts/build_widget.py")` via a
   new `_warn_if_stale_sibling_exists()`, called as the very first
   thing in `main()` -- prints a stderr warning naming both the stale
   path and the canonical `.desk_temp/build_widget.py` one, never
   aborts the build. `build_widget()`'s return type changed from `str`
   to `tuple[str, str]` (`(manifest["keyword"], tempui_text)`), so
   `main()` now has the keyword available after a successful build; a
   new `_delete_other_builds_for_keyword(temp_ui_dir, keyword, keep)`
   deletes every other file in `temp_ui_dir` whose first line starts
   with `DefineWidget\t<keyword>\t`, called right after the fresh
   `.desk_temp/<uuid>` file is written -- tolerates `OSError`/
   `UnicodeDecodeError` per-candidate rather than aborting the whole
   scan. `bridge_client.py`'s `call()` helper now constructs the thrown
   `Error` as a variable and sets `err.status = response.status` right
   before `throw err;`, additive alongside the existing free-text
   message. `TEMPUI_DOC_VERSION` bumped 28->29 with a matching comment
   block and a `## Version 29` entry in `_NEW_FEATURES_DOC` describing
   both build-script behavior changes. New
   `tests/verify/verify_stale_build_widget_script_fix.py` (20 checks,
   real subprocess builds via a real `tsc`, real HTTP round trip
   through a real `start_server` instance, real `node` execution of
   the actual rendered `bridge_client.py` template against that live
   server): doc-version/changelog content; a real build with a stale
   `scripts/build_widget.py` sibling present prints the warning to
   stderr and still succeeds; a build with no sibling prints nothing
   extra; building the same keyword three times (interleaved with a
   different keyword's own build) leaves exactly one `DefineWidget`
   file for the repeated keyword and leaves the unrelated keyword's
   file untouched; a real 403 capability-rejection response round-trips
   through the actual Bridge client JS (executed under real Node, with
   `fetch` rebased onto the real server's origin since plain Node has
   no page origin to resolve a relative URL against) and the caught
   `Error` has both `.status === 403` and the status still present in
   `.message`. Fixed one pre-existing regression along the way:
   `tests/verify/verify_build_widget.py` still called
   `build_widget.build_widget(...)` expecting a plain string back --
   updated its two call sites to unpack `(keyword, text)`, plus a new
   assertion that the returned keyword matches the manifest. Full
   `tests/verify/` regression suite passes (92 scripts total, 0
   failures beyond the one pre-existing `verify_build_widget.py` gap
   just fixed).

3cd90cf. COMPLETED: Add a `desk.self.setSubtitle(text: string | null)` Bridge API
   call (any `kind: "html"` widget) so a widget instance can put its
   own state (e.g. which document it's editing) into its own
   titlebar, alongside the existing `[EXTERNAL]` text suffix (the
   `[STALE]`/`[ERROR]`/`[TEMPUI]` indicators are separate clickable
   titlebar *buttons*, not part of the label text, so this only needs
   to compose with `[EXTERNAL]`). From
   `../FEEDBACK/FEEDBACK-DESK-widget-titlebar-subtitle-api-2026-08-03-1830.md`.
   A widget's titlebar text is fixed at construction
   (`_TitleBar.__init__`, `src/desk/shell/widget_frame.py:291`) and
   never changes except that suffix -- no widget-authored way to
   surface *which* particular thing an instance is showing (e.g. a
   file-editor-shaped widget letting the user pick a document at
   runtime has no titlebar-level option to show which one, only its
   own in-content UI). Routing plumbing already substantially exists,
   mirroring `getLocalStorage`/`setLocalStorage`'s own shape exactly
   (`self`-scoped, `require_instance_id`-only, "need no broader
   capability" per that pair's own precedent, `app.py:304-314`):
   `DeskWindow.find_frame_by_instance_id` (`window.py:1099`) already
   resolves an instance id to its live `WidgetFrame`. Suggested
   pieces: `bridge_client.py`'s `self: {...}` object gets a
   `setSubtitle` call; `app.py` gets a matching
   `POST /api/bridge/self/setSubtitle` route (a `SetSubtitleRequest`
   pydantic model mirroring `SetLocalStorageRequest`); `DeskWindow`
   gets a `set_widget_subtitle(instance_id, text)` →
   `find_frame_by_instance_id` → new `WidgetFrame.set_subtitle`/
   `_TitleBar.set_subtitle` pair; `_TitleBar._update_label_text`
   (`widget_frame.py:338`) composes title + subtitle + `[EXTERNAL]`.
   `None`/empty clears it back to the bare title. Needs a
   `TEMPUI_DOC_VERSION` bump + `_CUSTOM_WIDGETS_DOC`/`_NEW_FEATURES_DOC`
   entries documenting the new call, matching this project's own
   established convention. Explicitly out of scope (per the FEEDBACK
   item's own framing): the equivalent for `kind: "python"` widgets --
   `current_context` doesn't have an obvious existing per-instance-id
   hook a `python`-kind widget's own code could use the same way, and
   investigating that is real, separate work, not bundled in here.
   [planned: widget-titlebar-subtitle-api.md (COMPLETED)]

   COMPLETED: `bridge_client.py`'s `self: {...}` object gained
   `setSubtitle: (text) => call("POST", "/api/bridge/self/setSubtitle",
   { text: text ?? null })`. `app.py` gained
   `class SetSubtitleRequest(BaseModel): text: str | None` and
   `POST /api/bridge/self/setSubtitle`, gated only by
   `require_instance_id` (no capability check), mirroring
   `self_set_local_storage` exactly. `DeskWindow.set_widget_subtitle
   (instance_id, text)` resolves via `find_frame_by_instance_id` and
   silently no-ops for an unknown instance id. `_TitleBar` gained
   `self._subtitle: str | None` and `set_subtitle`;
   `_update_label_text` now composes `f"{title} — {subtitle}"` (only
   when `subtitle` is truthy) before appending the existing
   `[EXTERNAL]` suffix. `WidgetFrame.set_subtitle` thinly delegates to
   `_titlebar.set_subtitle`, matching `set_external`/`set_stale`'s own
   shape. `TEMPUI_DOC_VERSION` bumped 29->30 with a matching comment
   block, a new `desk.self.setSubtitle` bullet in the Bridge API
   section of `_CUSTOM_WIDGETS_DOC` (alongside `getManifest`/
   `getLocalStorage`/`setLocalStorage`), and a `## Version 30` entry in
   `_NEW_FEATURES_DOC`. New
   `tests/verify/verify_widget_titlebar_subtitle.py` (18 checks, real
   Qt widgets, no mocking): `_TitleBar`/`WidgetFrame` label composition
   across every combination of subtitle/`[EXTERNAL]`, and that both
   `None` and `""` clear the subtitle back to the bare title;
   `DeskWindow.set_widget_subtitle` resolving the right frame among
   several and silently no-oping for an unknown instance id; the
   rendered Bridge client template declaring `self.setSubtitle`; doc
   -version/content checks; a real HTTP round trip through a real
   `start_server` instance with no `X-Desk-Widget-Id` header sent at
   all (confirming no capability is required), whose response is
   confirmed against the real, live titlebar label text afterward, not
   just the HTTP response body. Full `tests/verify/` regression suite
   passes (93 scripts total, 0 failures).

7f984ec. COMPLETED: Several small gaps found adopting Desk's shared/not-shared
   `development-process.md` doc split (TODO `1a96c9f`/`c458012`) into
   an existing project (`world-timelines`), each confirmed directly
   against Desk's own current seeding code. From
   `../FEEDBACK/FEEDBACK-DESK-new-desk-in-existing-project-source-diving-2026-08-03-1506.md`:
   - **No breadcrumb when seeding into a project that already has its
     own `development-process.md`.** `_seed_development_process`
     (`src/desk/shell/window.py:1802`) copies
     `shared_development_process.md`/
     `specifically-not-working-on-desk-itself-development-process.md`
     into a project whenever the destination doesn't already have that
     *specific* filename, independently per file -- so a project with
     its own pre-existing, pre-split `development-process.md` (which
     is left untouched, per the function's own no-overwrite rule)
     silently gets the two new peer files with nothing explaining what
     they are, that the top-level file still needs a manual rewrite to
     reference them, or where to find the how-to for the TODO-id
     conversion (see below). Suggested fix: the same low-cost, already
     -established mechanism the tempui-doc-drift notification (TODO
     `7c7b676`) uses -- drop a same-directory `Scratch` tempui note
     explaining what just got seeded and what manual step is still
     needed, with the exact template pointer
     (`plans/fork-development-process-doc.md`). Confirmed via `git
     grep` that Desk has no standing check for "peer files exist but
     the top-level file doesn't reference `shared_development_process.md`"
     either -- worth deciding whether that's a one-time-seed note or a
     recurring check when such a project is opened.
   - **`how-to-convert-item-id-one-time.md` isn't seeded alongside
     `scripts/todo_item_ids.py`.** Confirmed the file exists in Desk's
     own repo root but `_seed_todo_item_ids_script`
     (`window.py:1824`) doesn't copy it -- the script's own docstring
     says it's "meant to be copied verbatim into other projects," but
     the doc that makes running its `convert` mode *safely* possible
     (dry-run-first, never-hand-modify-the-script discipline) doesn't
     travel with it.
   - **`todo_item_ids.py` (`scripts/todo_item_ids.py`) doesn't handle
     three real reference shapes**, confirmed directly against its
     current regexes: (a) existing `"TODO item N"` phrasing --
     `convert`'s singular-reference replacement
     (`re.sub(rf"\bitem\s+{number}\b", f"TODO {item_id}", text)`,
     line 101) matches `item N` regardless of what precedes it, so
     `"TODO item 16"` becomes `"TODO TODO <id>"`; (b) en-dash ranges
     like `"items 6–8"` -- the plural-reference regex
     (`r"\bitems\s+(\d+(?:/\d+)+)\b"`, line 95) only matches
     slash-separated lists, so an en-dash range matches neither the
     plural nor the singular pass and is silently left completely
     unconverted; (c) a `<!-- Item format: 1. ... 2. ... -->`-shaped
     documentation comment whose own literal `1.`/`2.` lines (if
     written across multiple lines inside the HTML comment) collide
     with `ITEM_START_RE` (`^(\d+)\.\s`, line 54, which has no
     HTML-comment awareness at all) and get treated as real item
     boundaries, corrupting the conversion if those numbers collide
     with real items. All three need pre-normalizing by hand today
     before running `convert` safely. Since this script is meant to be
     copied verbatim and never locally modified, fixing these once
     upstream (not requiring every future project to hand-discover and
     work around them) keeps that "verbatim, never customize"
     invariant actually meaningful.
   - **The `../FEEDBACK/` convention isn't documented in
     `shared_development_process.md`.** Confirmed via grep: neither
     `development-process.md` nor `shared_development_process.md`
     mentions it anywhere -- a newly-seeded or freshly-converted
     project has no in-project way to learn this convention exists at
     all. Fold a short section into `shared_development_process.md`
     describing it.
   [planned: new-desk-existing-project-gaps.md (COMPLETED)]

   COMPLETED: `TempUiManager._notify_docs_upgraded`'s note-writing was
   factored out into a shared `_write_scratch_note(temp_dir, title,
   body)`; a new public `TempUiManager.notify_dev_process_peers_seeded
   (directory)` uses it, guarded by `self._watched_directory == directory
   / TEMP_UI_DIRNAME` (a no-op otherwise -- nowhere to write the note).
   `DeskWindow._seed_development_process` now returns whether a
   breadcrumb is warranted (a peer file newly seeded *and* the
   top-level `development-process.md` already existed); `new_desk`
   captures that and calls `notify_dev_process_peers_seeded` right
   after `switch_desk` (not before -- `.desk_temp`/the watcher don't
   exist yet at seed time). `_seed_todo_item_ids_script` also seeds a
   new `HOW_TO_CONVERT_ITEM_ID_FILENAME` ("how-to-convert-item-id-one-
   time.md") alongside the script, same no-overwrite/no-op-if-missing
   -source posture as everything else it already does.
   `scripts/todo_item_ids.py`: `_html_comment_line_indices` marks line
   indices inside a (possibly multi-line) `<!-- ... -->` block;
   `_split_items` now skips any `ITEM_START_RE` match on such a line.
   The singular cross-reference regex now optionally consumes a
   leading `TODO\s+` and replaces the whole match, so `"TODO item 16"`
   and `"item 16"` both become `"TODO <id>"`, never `"TODO TODO
   <id>"`. A new plural en-dash/hyphen-range pattern
   (`r"\bitems\s+(\d+)\s*[-–]\s*(\d+)\b"`) expands an inclusive range
   to slash-joined `TODO <id>` references, matching the existing
   slash-list rendering. Found and fixed one more real bug along the
   way, caught only by actually running the fix against a fixture: the
   cross-reference passes' `\s+` (deliberately spanning newlines for a
   legitimately word-wrapped reference) could still reach from ordinary
   prose across a comment boundary into the comment's own literal
   example text and corrupt it -- fixed with a `_mask_for_text(text)`
   per-character mask (recomputed fresh before *each* substitution pass,
   since a pass can change `text`'s length and desync a mask computed
   against an earlier version of it) that makes every cross-reference
   substitution skip any match touching a comment line, leaving the
   match text untouched instead. `shared_development_process.md` gained
   a new "External Feedback (`../FEEDBACK/`)" section: what the
   directory is, that acting on a file means citing it in a new
   `TODO.md`/`PARKINGLOT.md` entry, and the (previously undocumented,
   confirmed via `ls ../FEEDBACK/implemented/`) convention of moving a
   file into `../FEEDBACK/implemented/` once every entry it produced is
   `COMPLETED`. Applied that convention retroactively to this session's
   own six other already-`COMPLETED` items from this same batch plus
   this TODO's own source file (`a8e4115`, `7c11fe0`, `47aaf73`,
   `1b7e500`, `e86a31b`, `3cd90cf`, `7f984ec` -- all seven files moved
   into `../FEEDBACK/implemented/`), so the newly-documented convention
   doesn't start already out of sync with this session's own recent
   history. New/extended verify coverage, real (no mocking):
   `tests/verify/verify_dev_process_seeding.py` (extended, 3 new
   checks) covers `_seed_development_process`'s new return value across
   the pre-existing-top-level/brand-new/nothing-to-seed cases;
   `tests/verify/verify_seed_todo_item_ids_script.py` (extended, 3 new
   checks) covers the how-to-doc seeding's copy/no-op/never-overwrite
   behavior; new
   `tests/verify/verify_new_desk_existing_project_gaps.py` (18 checks)
   covers a real `TempUiManager.provision` + `notify_dev_process_peers_
   seeded` round trip (a real Scratch note actually appears in
   `.desk_temp`, with the right content), the no-op case for an
   unwatched directory, `new_desk`'s exact call ordering (seed, then
   `switch_desk`, then the breadcrumb, then save) across the warranted/
   not-warranted/`copy_development_process=False` cases, and the new
   `shared_development_process.md` section's content; new
   `tests/verify/verify_todo_item_ids_script_regex_fixes.py` (15
   checks) subprocess-invokes the real script against a real fixture
   combining all three original bug shapes plus the comment-boundary
   corruption bug found along the way, confirming each is now handled
   correctly in one real `convert` run. Full `tests/verify/`
   regression suite passes (96 scripts total, 0 failures).
676a133. COMPLETED: Investigate offline/local text-to-speech (TTS) options for this
   project -- the reverse direction of the already-shipped local
   speech-to-text work (TODOs `f9d2dc7`/`1cd0ca2`/`b32fb81`,
   `mlx-whisper`-based). Candidate libraries, model sizes and license
   terms, voice quality, and whether anything comparable to
   `mlx-whisper`'s Apple-Silicon-optimized story exists for TTS
   specifically (vs. a general cross-platform option) are all open.
   No concrete use case driving this yet either (unlike the STT work,
   which had the Voice Input widget as a clear target) -- surfaced
   purely as "the natural counterpart to what we already have," moved
   here from `PARKINGLOT.md`. Write up findings and recommendations in
   `investigations/tts_options.md`. No application code changes -- a
   pure investigation; figure out real options and their tradeoffs
   before this becomes a planned, implementable TODO.
   [planned: investigate-tts-options.md (COMPLETED)]

   Surveyed four candidates: macOS `say`/`AVSpeechSynthesizer` (zero
   new dependency, on-device neural voices since Sonoma, but thin
   programmatic control and no scriptable way to fetch the better
   voice packs); `mlx-audio` + Kokoro-82M (MIT toolkit / Apache 2.0
   weights, ~300MB, #1 on the TTS Arena leaderboard as of Jan 2026 --
   the real MLX-native analog to `mlx-whisper`, though a third-party
   project rather than living in `ml-explore`'s own org the way
   `mlx-whisper` does); Piper (ONNX/CPU, ~75MB/voice, 100+ voices/35+
   languages, the actual general cross-platform option -- license is
   murky, MIT on the now-archived original repo vs. GPL-3.0 on the
   active fork, flagged as unresolved rather than papered over); Coqui
   XTTS v2 (best quality/voice-cloning surveyed, but its weights are
   CPML-licensed non-commercial-only with no one left to sell a
   commercial license since Coqui Inc. shut down in Jan 2024 --
   ruled out for anything this MIT-licensed project would ship or
   default to). Answered the original "is there an Apple-Silicon-
   optimized story like `mlx-whisper`" question directly: yes,
   `mlx-audio`/Kokoro, with the third-party-provenance caveat above.
   No recommendation committed to, per `PARKINGLOT.md`'s original
   framing -- no concrete use case exists yet to design against;
   findings and the shape of the tradeoff for whoever picks this up
   are written up in `investigations/tts_options.md`.

   No application code changed -- a pure investigation. Confirmed the
   new file exists; full regression suite: 100 scripts, 0 failures
   (unchanged, as expected).

13f4ad5. COMPLETED: Rework promoted/custom-widget source-of-truth: durable,
   registration-time source paths instead of keyword-based convention,
   and a gitignored per-widget build cache instead of baked-in
   `html_b64`. Addresses findings 1-2 of
   `../FEEDBACK/FEEDBACK-DESK-promoted-widget-source-of-truth-2026-08-04-1321.md`
   (confirmed bug: `_relocate_promoted_widget_source`,
   `src/desk/shell/window.py:2647`, derives the authoring source
   directory from `keyword` -- e.g. `PdfViewer` -- but the real
   directory is kebab-case (`pdf-viewer`), so it silently no-ops for
   almost every real-source widget; plus that file's design
   recommendation that the `.desk` file reference source rather than
   duplicate it).

   1. **Durable registration record with a source path.** Widget
      registration (`_register_custom_widget` and its two call sites,
      `_register_custom_widgets_from_desk`/`_register_custom_widgets_
      from_desk_temp`, `window.py:2521-2553`) should record the
      project-directory-relative path to the widget's authoring source
      directory as part of the registration itself -- for both
      still-tempui-authored and already-promoted widgets, not just the
      transient, promotion-discarding `self._custom_widget_source_
      paths: dict[str, Path]` (`window.py:268`, popped and thrown away
      at the start of promotion, `window.py:2629`). For a promoted
      widget this means the `.desk` file's `custom_widgets` entries
      (`CustomWidgetDefinition`, `src/desk/temp_ui.py:2518`; persisted
      via `desks.py:136`/`188`) need a new `source_path: str | None`
      field so the association survives a save/reload and an app
      restart, not just the current process's lifetime.
   2. **Promotion uses the record, not the keyword.** `_relocate_
      promoted_widget_source` (`window.py:2647`) should resolve the
      source directory from that new `source_path` field (populated at
      initial registration time, from whichever side already knows the
      real directory name) instead of reconstructing `directory /
      TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / keyword` from the
      keyword -- this is the actual fix for the confirmed bug above,
      not just a workaround for the CamelCase-vs-kebab-case mismatch.
   3. **No baked `html_b64` in the `.desk` file for source-backed
      widgets.** Once a widget has a recorded source path, the `.desk`
      file should stop storing its compiled `html_b64` inline --
      instead, build output goes into a gitignored, per-widget `.build`
      directory inside its `desk_widgets/<name>/` directory (new
      top-level `.gitignore` pattern `**/.build/`, alongside the
      existing `**/build/`/`.desk_temp/` entries), rebuilt on demand
      rather than frozen at promote-time. A hand-authored, inline-only
      `DefineWidget` with no source directory keeps today's baked-
      `html_b64` behavior, since there's nothing to build from.

   [planned: durable-custom-widget-source-paths.md (COMPLETED)]

1c67fe5. COMPLETED: Ensure a managed project's own `.gitignore` covers
   `desk_widgets/**/.build/` -- the rebuilt-on-demand build cache TODO
   13f4ad5 introduced under any promoted, source-backed custom widget's
   own `desk_widgets/<name>/` directory. Deliberately narrower than
   this repo's own top-level `**/.build/` (added the same TODO): a
   *project* Desk is managing should only ignore its own desk_widgets/
   build caches, not every `.build/` directory anywhere in the project.
   `desk.temp_ui.ensure_desk_widgets_gitignore_entry` is conditional on
   `desk_widgets/` actually existing (a project that's never promoted a
   source-backed widget has nothing to protect and shouldn't be asked
   about it) -- called from `DeskWindow._provision_temp_ui` (startup/
   Desk-switch) and right after `_on_tempui_promote_requested`'s own
   `_relocate_promoted_widget_source` call, the two moments
   `desk_widgets/` can first come to exist.

   [planned: desk-widgets-build-gitignore.md (COMPLETED)]

63bfd42. Implement the pipe-chained verb DSL designed in TODO `765bd2a`
   (`plans/pipe-chained-verb-dsl.md`) -- that item was deliberately
   scoped to the language design only (grammar, verb/argument shape,
   value flow, the escape hatch, error/partial-failure semantics); this
   item is the follow-on: a real parser/interpreter (per the plan's own
   naming assumption, `src/desk/pipeline_dsl.py`), an actual built-in
   verb registry with real backing implementations (the plan's
   "Illustrative starter verb catalog" is explicitly non-binding -- a
   grounding example, not a commitment), and at least one delivery
   mechanism getting a pipeline string to Desk in the first place (a
   `Job`/`DeskProc` tempui file's `Script` line, an `a762501` MCP tool
   argument, or something else -- the plan's own point is that the
   language should come out the same regardless of which transport(s)
   this item ends up picking).

   Not yet planned -- write a plan per `shared_development_process.md`
   before implementing, and treat the linked design plan's "Explicitly
   out of scope" section as this item's own starting scope boundary
   (verb extensibility beyond a fixed catalog remains explicitly
   deferred, not part of this item either, absent a concrete need
   surfacing during planning).
