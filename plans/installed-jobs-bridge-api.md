# Installed Jobs Bridge API (TODO `888b537`) (COMPLETED)

## Summary

Let a `kind: "html"` widget run an already-Installed Job (TODO
`7dca383`) too, via `desk.installedJobs.run(name, configPath)`
(capability `installed_jobs`) — mirroring the existing agent-facing
`desk_run_installed_job` MCP tool. Requires refactoring `7dca383`'s own
implementation first: its stale-hash safety check and execution logic
currently live only inside the MCP tool handler, and must become a
single shared implementation both entry points call, not two
independent copies of security-critical logic.

## Affected files

- `src/desk/installed_jobs.py` — `run_script()` (moved from
  `desk_mcp_server.py`'s `_run_installed_job`, same body), `_RUN_LOCK`
  (moved), `resolve_config_path()` (new, extracted from the MCP tool's
  inline resolution), `INSTALLED_JOB_RUN_TIMEOUT_SECONDS` (new
  constant).
- `src/desk/shell/window.py` — `DeskWindow.get_installed_job_for_run(name)`
  (raises `ValueError`), `DeskWindow.run_installed_job(name,
  config_path, on_result)` (non-blocking, mirrors `run_transform`).
- `src/desk/shell/desk_mcp_server.py` — `_run_installed_job_tool`
  rewritten as a thin adapter over `window.run_installed_job`; the old
  `_run_installed_job`/`_RUN_LOCK` removed (moved to `installed_jobs.py`).
- `src/desk/server/app.py` — `InstalledJobsRunRequest`, the new
  `POST /api/bridge/installedJobs/run` route, `run_on_gui_async` gains
  an optional `timeout` parameter (default unchanged).
- `src/desk/server/bridge_client.py` — `installedJobs: { run }` in
  `BRIDGE_CLIENT_TEMPLATE`.
- `src/desk/temp_ui.py` — new Bridge API doc bullet, `_JOBS_DOC`'s
  closed capability list gains `installed_jobs`, `TEMPUI_DOC_VERSION`
  bump + `_NEW_FEATURES_DOC` entry.
- `tests/verify/verify_desk_mcp_server.py` — updated for the refactored
  call shape (same behavior/wording).
- `tests/verify/verify_installed_jobs_bridge_api.py` (new) — mirrors
  `tests/verify/verify_bridge_api_transforms_run.py`'s exact shape
  (real `start_server`, a fake `DeskWindow`-shaped object with a
  QTimer-delayed `run_installed_job`, real HTTP requests).
- `tests/verify/verify_tempui_jobs_doc.py` — capability-name-list check
  gains `installed_jobs`.
- `tests/verify/verify_tempui_installed_jobs_doc.py` — extended to
  cover the new Bridge API mention.

## Implementation approach

1. **`installed_jobs.py`**: move `_run_installed_job`'s body (renamed
   `run_script`) and `_RUN_LOCK` here verbatim from
   `desk_mcp_server.py` (needs `contextlib`, `io`, `sys`, `threading`,
   `traceback` imports added here, removed from `desk_mcp_server.py`
   if no longer used there). Add:
   ```python
   def resolve_config_path(directory: Path, raw: str | None) -> str | None:
       if not raw:
           return None
       path = Path(raw)
       if not path.is_absolute():
           path = directory / path
       return str(path)
   ```
   `INSTALLED_JOB_RUN_TIMEOUT_SECONDS = 120.0` (documented: bounds only
   the Bridge API's synchronous wait; the MCP path has no such bound).

2. **`window.py`**:
   ```python
   def get_installed_job_for_run(self, name: str) -> InstalledJobDefinition:
       job = self.get_installed_job(name)
       if job is None:
           raise ValueError(f"{name!r} is not installed.")
       job_dir = installed_job_dir(self.current_desk.directory, name)
       current_hash = compute_version_hash(job_dir)
       if current_hash != job.version_hash:
           raise ValueError(
               f"{name!r}'s source on disk (version {current_hash}) no longer matches the installed "
               f"version ({job.version_hash}) -- call desk_install_job again before running it."
           )
       return job

   def run_installed_job(self, name: str, config_path: str | None, on_result: Callable[[bool, str, str, str], None]) -> None:
       job = self.get_installed_job_for_run(name)  # raises ValueError synchronously
       job_dir = installed_job_dir(self.current_desk.directory, name)
       resolved_config_path = resolve_config_path(self.current_desk.directory, config_path)
       script_text = (job_dir / INSTALLED_JOB_ENTRY_FILENAME).read_text()

       def _run() -> None:
           ok, stdout, stderr, tb = run_script(script_text, job_dir, resolved_config_path)
           on_result(ok, stdout, stderr, tb)

       threading.Thread(target=_run, daemon=True).start()
   ```
   Keep exact error-message wording from the current implementation so
   existing verify assertions (`"is not installed"`, `"no longer
   matches"`, `"desk_install_job"`) still pass unchanged.

3. **`desk_mcp_server.py`** — `_run_installed_job_tool` becomes:
   ```python
   async def _run_installed_job_tool(args):
       window = current_context.get_main_window()
       if window is None:
           return _text_result(_NOT_READY_MESSAGE, is_error=True)
       loop = asyncio.get_event_loop()
       result_future = loop.create_future()

       def _on_result(ok, stdout, stderr, tb):
           loop.call_soon_threadsafe(result_future.set_result, (ok, stdout, stderr, tb))

       try:
           await _call_on_gui_thread(
               lambda: window.run_installed_job(args["name"], args.get("config_path") or None, _on_result)
           )
       except RuntimeError as e:
           return _text_result(str(e), is_error=True)
       except ValueError as e:
           return _text_result(str(e), is_error=True)
       ok, stdout, stderr, tb = await result_future
       return _text_result(json.dumps({"ok": ok, "stdout": stdout, "stderr": stderr, "traceback": tb}))
   ```
   Remove the now-unused `ENTRY_FILENAME`/`compute_version_hash`/
   `installed_job_dir`/`_run_installed_job`/`_RUN_LOCK` imports/defs
   from this file (moved to `installed_jobs.py` and `window.py`).

4. **`app.py`**:
   ```python
   class InstalledJobsRunRequest(BaseModel):
       name: str
       config_path: str | None = None
   ```
   ```python
   async def run_on_gui_async(starter, timeout: float = 10.0):
       ...
       return await loop.run_in_executor(None, gui_bridge.call_async, starter, timeout)
   ```
   ```python
   @app.post("/api/bridge/installedJobs/run")
   async def installed_jobs_run(
       body: InstalledJobsRunRequest, widget: WidgetInfo = Depends(require_caller("installed_jobs"))
   ):
       try:
           return await run_on_gui_async(
               lambda resolve: gui_bridge.window.run_installed_job(
                   body.name, body.config_path,
                   lambda ok, stdout, stderr, tb: resolve(
                       {"ok": ok, "stdout": stdout, "stderr": stderr, "traceback": tb}
                   ),
               ),
               timeout=INSTALLED_JOB_RUN_TIMEOUT_SECONDS,
           )
       except ValueError as e:
           raise HTTPException(400, str(e)) from e
   ```

5. **`bridge_client.py`**: add right after the `transforms` entry:
   ```js
   installedJobs: {
     run: (name, configPath) =>
       call("POST", "/api/bridge/installedJobs/run", { name, config_path: configPath ?? null }),
   },
   ```

6. **`temp_ui.py`**:
   - `_CUSTOM_WIDGETS_DOC`: new bullet after the `transforms` bullet,
     documenting the call, capability, return shape, timeout caveat,
     and a cross-reference to `tempui-installed-jobs.md`.
   - `_JOBS_DOC`'s closed capability list gains `installed_jobs`.
   - `tempui-installed-jobs.md` (`_INSTALLED_JOBS_DOC`): add a short
     section noting the Bridge API route now exists too, for an
     `html`-kind... no — Installed Jobs themselves are still
     `python`-only; this just means an *unrelated* `kind: "html"`
     widget can trigger a run. Cross-reference `tempui-custom-widgets.md`.
   - `TEMPUI_DOC_VERSION` bump, `_NEW_FEATURES_DOC` entry.

7. **Verify**:
   - `verify_installed_jobs_bridge_api.py`: mirrors
     `verify_bridge_api_transforms_run.py` exactly — a fake window with
     a `run_installed_job(name, config_path, on_result)` that resolves
     via `QTimer.singleShot` (proves the async plumbing genuinely
     waits); success, a raising-job case, not-installed (400),
     missing-capability (403), and the Bridge client declares
     `installedJobs.run`.
   - `verify_desk_mcp_server.py`: update the fake window (it currently
     defines `install_job`/`get_installed_job`; needs a
     `run_installed_job(name, config_path, on_result)` matching the new
     call shape) and re-verify all existing assertions still pass
     unchanged.
   - `verify_tempui_jobs_doc.py`: add `"installed_jobs"` to the
     capability-name-list check.
   - `verify_tempui_installed_jobs_doc.py`: add a check for the new
     cross-reference.

## Key design decisions

- **One shared implementation, not two.** The stale-hash refusal is
  the whole reason "no reapproval on every run" is safe; it must be
  impossible for the Bridge and MCP paths to diverge on it. Hence the
  `window.run_installed_job`-centered refactor rather than a second,
  independent Bridge-side implementation.
- **Bad request (400) vs. ran-but-failed (200, `ok: false`).** Matches
  the MCP tool's own `is_error` vs. `{ok: false, ...}` split.
- **A bounded Bridge-side timeout, an unbounded MCP-side one.** A
  genuine, documented difference between the two transports, not
  something to paper over by inventing a new mechanism.
- **No new capability semantics beyond what already exists.** Capability
  gating is itself already the "approval" for `kind: "html"` widgets
  (declared once, at widget-definition time) — consistent with "no
  reapproval on every MCP run," no new approval UI needed here.

## Verification

Run the new/extended verify scripts individually, then the full
`tests/verify/` suite.
