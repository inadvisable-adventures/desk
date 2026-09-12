# Installed Jobs (TODO `7dca383`)

## Summary

A durable, versioned alternative to the ephemeral `Job` tempui
mechanism (TODO `d7e66f6`). An agent writes real source to
`desk-installed-jobs/<name>/main.py` (project-root-relative, sibling
to `.desk_temp`, not inside it), then calls a new MCP tool to install
it. Installation is registered both in-memory on `DeskWindow` and in
the current `.desk` file's new `installed_jobs` section, kept in sync
via the existing `save_current_desk()` write path. Once installed, an
agent can request a run (with an optional config-file path) via a
second MCP tool with **no further approval prompt** -- the only
approval happens at install time. An "Installed Jobs" widget lists
what's installed, opens editor widget(s) on the current source, and
lets a user uninstall.

## Affected files

- `src/desk/installed_jobs.py` (new) -- `InstalledJobDefinition`
  dataclass, `INSTALLED_JOBS_DIRNAME`/`ENTRY_FILENAME` constants,
  `installed_job_dir()`, `compute_version_hash()`,
  `INSTALLED_JOBS_UPDATED_EVENT`.
- `src/desk/desks.py` -- `Desk.installed_jobs` field;
  `_load_installed_job`/`_installed_job_dict`; wired into `load_desk`/
  `desk_state_dict`.
- `src/desk/shell/window.py` -- `DeskWindow.install_job`,
  `.uninstall_job`, `.get_installed_job`, `.get_installed_jobs_dicts`;
  `_capture_desk_state` carries `installed_jobs` over unchanged;
  `_refresh_picker` registers the two new `current_context` hooks
  (same choke point `file_type_registry_provider` already uses).
- `src/desk/shell/current_context.py` -- `set/get_installed_jobs_provider`,
  `set/get_installed_job_uninstaller` (mirror `file_type_registry_provider`'s
  shape).
- `src/desk/shell/desk_mcp_server.py` -- `desk_install_job(name)`,
  `desk_run_installed_job(name, config_path=None)`.
- `src/desk/claude_session.py` -- `_can_use_tool` bypass branch for
  `mcp__desk__desk_run_installed_job`.
- `widgets/installed_jobs/widget.json`, `widgets/installed_jobs/widget.py` (new).
- `src/desk/temp_ui.py` -- `INSTALLED_JOBS_DOC_FILENAME`,
  `_INSTALLED_JOBS_DOC`, `SPLIT_DOC_CONTENT` entry, `DOC_TEMPLATE`'s
  "a few more files" paragraph, `TEMPUI_DOC_VERSION` 39 -> 40,
  `_NEW_FEATURES_DOC` new entry.
- `tests/verify/verify_installed_jobs.py`,
  `tests/verify/verify_installed_job_permission_bypass.py`,
  `tests/verify/verify_installed_jobs_widget.py`,
  `tests/verify/verify_tempui_installed_jobs_doc.py` (new); extend
  `tests/verify/verify_desk_mcp_server.py`.

## Implementation approach

1. **`src/desk/installed_jobs.py`**
   - `INSTALLED_JOBS_DIRNAME = "desk-installed-jobs"`, `ENTRY_FILENAME = "main.py"`.
   - `installed_job_dir(project_directory: Path, name: str) -> Path`.
   - `compute_version_hash(job_dir: Path) -> str`: walk every regular
     file under `job_dir` (`sorted(job_dir.rglob("*"))`, filter
     `is_file()`), fold `relative_path.as_posix().encode() + b"\0" +
     file_bytes + b"\0"` into one `hashlib.md5`, `.hexdigest()[:12]`.
   - `InstalledJobDefinition`: `name: str`, `version_hash: str`,
     `installed_at: str` (ISO 8601, `datetime.now().isoformat()`,
     display-only).
   - `INSTALLED_JOBS_UPDATED_EVENT = "desk.installed_jobs.updated"`.

2. **`src/desk/desks.py`**
   - `Desk.installed_jobs: list[InstalledJobDefinition] = field(default_factory=list)`.
   - `_load_installed_job(data) -> InstalledJobDefinition` /
     `_installed_job_dict(job) -> dict`, mirroring
     `_load_custom_widget`/`_custom_widget_dict` exactly.
   - `load_desk`: `installed_jobs = [_load_installed_job(j) for j in data.get("installed_jobs", [])]`.
   - `desk_state_dict`: add `"installed_jobs": [_installed_job_dict(j) for j in desk.installed_jobs]`.

3. **`src/desk/shell/window.py`**
   - `install_job(self, name: str) -> tuple[bool, str]`:
     `directory = installed_job_dir(self.current_desk.directory, name)`;
     if missing or no `main.py` -> `(False, "...")`; else
     `version_hash = compute_version_hash(directory)`; upsert (by
     name) into `self.current_desk.installed_jobs`; `self.save_current_desk()`;
     `self._event_mediator.publish(INSTALLED_JOBS_UPDATED_EVENT,
     {"jobs": self.get_installed_jobs_dicts()}, "")`; return
     `(True, f"installed (version {version_hash})")`.
   - `uninstall_job(self, name: str) -> bool`: remove matching entry if
     present; if removed, `save_current_desk()` + publish event;
     return whether anything was removed.
   - `get_installed_job(self, name: str) -> InstalledJobDefinition | None`.
   - `get_installed_jobs_dicts(self) -> list[dict]`: `[{"name", "version_hash",
     "installed_at"}]` sorted by name.
   - `_capture_desk_state`: add `installed_jobs=self.current_desk.installed_jobs`
     to the returned `Desk(...)` (same carry-over comment shape as
     `custom_widgets`/`file_type_registry` immediately above it).
   - `_refresh_picker`: add
     `current_context.set_installed_jobs_provider(self.get_installed_jobs_dicts)`
     and `current_context.set_installed_job_uninstaller(self.uninstall_job)`,
     same choke point/comment shape as the existing
     `set_file_type_registry_provider` call.

4. **`src/desk/shell/current_context.py`**
   - Add `_installed_jobs_provider`/`_installed_job_uninstaller` module
     globals + get/set pairs, mirroring `file_type_registry_provider`'s
     docstring shape (cite TODO `7dca383`).

5. **`src/desk/shell/desk_mcp_server.py`**
   - `desk_install_job(args: {"name": str}) -> dict`: `await
     _call_on_gui_thread(lambda: window.install_job(args["name"]))`
     -> `(ok, message)`; `_text_result(message, is_error=not ok)`.
   - `desk_run_installed_job(args: {"name": str, "config_path": str | None}) -> dict`:
     1. `job = await _call_on_gui_thread(lambda: window.get_installed_job(args["name"]))`;
        `None` -> error result ("not installed").
     2. `directory = current_context.get_current_desk_directory()`;
        `job_dir = installed_job_dir(directory, args["name"])`.
     3. `current_hash = compute_version_hash(job_dir)`; if it doesn't
        equal `job.version_hash` -> error result telling the caller to
        `desk_install_job` again.
     4. Resolve `config_path`: `None` if omitted; else `Path(config_path)`,
        resolved against `directory` if relative (matches
        `desk_screenshot_widget`'s own path-resolution convention).
     5. Read `(job_dir / ENTRY_FILENAME).read_text()`.
     6. Run on a background thread via
        `await loop.run_in_executor(None, _run_installed_job, script_text, job_dir, resolved_config_path)`
        -- a new module-level function mirroring
        `widgets/job_runner/widget.py`'s `_run_python_job` (temporarily
        inserts `str(job_dir)` at `sys.path[0]`, execs into
        `{"__name__": "__installed_job__", "CONFIG_PATH": resolved_config_path_str_or_None}`,
        captures stdout/stderr/traceback via `contextlib.redirect_stdout/stderr`,
        removes the `sys.path` entry in a `finally`) -- returns
        `(ok, stdout, stderr, traceback)` directly (no signal/relay
        needed, since this isn't a Qt widget and the async handler can
        just await the executor future).
     7. `_text_result(json.dumps({"ok": ok, "stdout": stdout, "stderr": stderr, "traceback": tb}))`.
   - Both added to `_TOOLS`.

6. **`src/desk/claude_session.py`**
   - At the top of `_can_use_tool`, before creating the pending-permission
     future:
     ```python
     if tool_name == "mcp__desk__desk_run_installed_job":
         return sdk.PermissionResultAllow(behavior="allow", updated_input=None, updated_permissions=None)
     ```
     with a comment citing TODO `7dca383` and explaining why (approval
     happens once, at install).

7. **`widgets/installed_jobs/`**
   - `widget.json`: `{"name": "Installed Jobs", "kind": "python", "entry": "widget.py", "capabilities": [], "default_size": {"width": 420, "height": 320}}`.
   - `widget.py`: `InstalledJobsWidget(QWidget)` -- `QListWidget` +
     `setItemWidget` per row (mirrors `widgets/parking_lot/widget.py`):
     a non-selectable `QLabel` (`name` + `version_hash`), a "View
     Source" `QPushButton`, an "Uninstall" `QPushButton`.
     - `__init__`: `self._jobs = current_context.get_installed_jobs_provider()()`
       if a provider is registered, else `[]`; populate the list.
     - `bind_event_mediator(instance_id, mediator)`: subscribe via
       `EventSubscription(mediator, instance_id, names=[INSTALLED_JOBS_UPDATED_EVENT], parent=self)`,
       refresh `self._jobs` from the event payload on receipt (mirrors
       `widgets/project_files/widget.py`'s `_on_mediated_event`).
     - View Source: resolve the job's directory via
       `current_context.get_current_desk_directory()` +
       `installed_job_dir`; for each file under it (sorted), call
       `current_context.get_editor_or_scrap_opener()`.
     - Uninstall: confirm via `current_context.get_popup_opener()`
       ("Uninstall '<name>'? Its source in desk-installed-jobs/ is kept."),
       then call `current_context.get_installed_job_uninstaller()`.

8. **`src/desk/temp_ui.py`**
   - `INSTALLED_JOBS_DOC_FILENAME = "tempui-installed-jobs.md"`.
   - `_INSTALLED_JOBS_DOC`: explain the whole mechanism (storage
     convention, versioning, `desk_install_job`/`desk_run_installed_job`
     tool signatures, `CONFIG_PATH` global convention, "config
     generally lives in `.desk_temp/` unless otherwise specified", the
     widget, the one-approval-at-install/no-reapproval-at-run model,
     and the stale-hash-refuses-to-run safety check) -- same tone/
     structure as `_JOBS_DOC`.
   - Add to `SPLIT_DOC_CONTENT`.
   - Extend `DOC_TEMPLATE`'s "A few more files live here too, but
     aren't DSL file types" paragraph with a link to
     `tempui-installed-jobs.md` (not the "ten built-in file types"
     list -- installation is MCP-tool-driven, not a dropped tempui
     file).
   - `TEMPUI_DOC_VERSION = 40`; add a new `_NEW_FEATURES_DOC` "##
     Version 40" entry.

9. **Verify scripts**
   - `verify_installed_jobs.py`: `compute_version_hash` determinism +
     changes-when-a-file-changes + multi-file; `install_job`/
     `uninstall_job` against a fake `DeskWindow`-shaped object (or a
     real minimal `Desk`); `.desk` file round-trip (`load_desk`/
     `save_desk`/`desk_state_dict` include `installed_jobs`
     correctly).
   - Extend `verify_desk_mcp_server.py`: `desk_install_job`
     success/missing-directory/missing-`main.py`; `desk_run_installed_job`
     success (stdout captured), script-raises (traceback captured),
     not-installed error, stale-hash-refuses-to-run, relative
     `config_path` resolution.
   - `verify_installed_job_permission_bypass.py`: a real
     `ClaudeSession`, call `_can_use_tool("mcp__desk__desk_run_installed_job", {}, None)`
     directly and confirm it returns `PermissionResultAllow` without
     ever touching `_pending_permissions`; confirm
     `mcp__desk__desk_install_job` still creates a pending future (not
     bypassed) -- resolve it manually to avoid hanging the test.
   - `verify_installed_jobs_widget.py`: list rendering from a fake
     provider; View Source calls the editor opener once per file;
     Uninstall calls the popup opener then the uninstaller only on
     confirm.
   - `verify_tempui_installed_jobs_doc.py`: doc-set completeness/version
     bump, mirroring `verify_tempui_desk_proc_doc.py`.
   - Full `tests/verify/` suite run at the end; investigate (not just
     note) any pre-existing failure per `development-process.md`.

## Key design decisions

- **`python`-kind only, no manifest file.** `Job`'s own unrestricted,
  no-sandboxing `kind: "python"` is already the right trust level;
  there's no capability list to scope and no metadata beyond a name +
  version hash, so no `job.json` is needed for v1. An `html`-kind
  installed job is a plausible future extension, not in scope here.
- **Uninstall never deletes the source directory.** Only unregisters
  from the in-memory registry / `.desk` file -- keeps uninstall
  reversible via a later `desk_install_job` call and avoids surprising
  data loss from what's otherwise a low-friction, single-click widget
  action.
- **The stale-hash re-check in `desk_run_installed_job` is required,
  not optional.** It's the only thing that keeps the "approve once at
  install, never again at run" model safe against `main.py` being
  edited on disk after install without a fresh `desk_install_job` call.
- **No `desk_uninstall_job`/`desk_list_installed_jobs` MCP tools.**
  Matches the user's own scope exactly: install + run are agent
  -initiated via MCP; listing/uninstalling are user-initiated via the
  widget. Revisit only if asked.
- **Running never places a widget instance.** Unlike `Job`/`DeskProc`,
  a run is a synchronous MCP tool call/response (`(ok, stdout, stderr,
  traceback)`) -- there's no ceremony to place a runner widget for
  something that's supposed to be low-friction on every run.

## Verification

Run the new/extended verify scripts individually, then the full
`tests/verify/` suite. Manually confirm in a live Desk (browser/GUI
launch) if practical: install a trivial job, run it via a real Claude
(Desk) session (confirm no approval prompt on run, one prompt on
install), edit its `main.py` and confirm a subsequent run is refused
until reinstalled, place the Installed Jobs widget and confirm View
Source/Uninstall.
