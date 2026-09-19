# Job-to-job invocation: `RUN_INSTALLED_JOB` for `python`-kind Installed Jobs (TODO `0959ff1`)

## Summary

Per `../FEEDBACK/FEEDBACK-DESK-no-job-to-job-invocation-2026-09-18-1600.md`:
a `python`-kind Installed Job's own running code has no way to invoke
another Installed Job -- every existing entry point
(`desk_run_installed_job`, `desk.installedJobs.run`) needs something a
plain job process never has (an MCP-driving agent, or a
`kind: "html"` widget's Bridge API access). This plan adds a new
global, `RUN_INSTALLED_JOB(name, config_path=None) -> {"ok", "stdout",
"stderr", "traceback"}`, alongside `CONFIG_PATH`/`NEEDS_PATH` (TODO
`94a2fa2`) -- available to every `python`-kind job, uniformly runnable
against a target of either kind. Scoped down exactly per the feedback:
a `rust`-kind job invoking anything is explicitly out of scope.

## Design decisions

- **Split `run_installed_job`'s existing GUI-thread validation/
  resolution step out from its execution-dispatch step**, so both the
  top-level entry point (MCP/Bridge API) and the new nested,
  job-invokes-job path can share the exact same logic instead of a
  second, drifting copy. `_prepare_installed_job_run(name,
  config_path)` (new) does the GUI-thread-only part (validate via
  `get_installed_job_for_run`, `resolve_config_path`,
  `_resolve_job_needs`, `detect_installed_job_kind`) and returns
  `(kind, job_dir, resolved_config_path, resolved_needs_path)`; a new
  module-level `_dispatch_installed_job_run(kind, job_dir, config_path,
  needs_path, run_installed_job_callable)` does the actual kind-based
  execution (no GUI-thread requirement, this is exactly the part that
  must run on a background thread, current or new).
- **Reuse the existing "background thread needs a synchronous
  GUI-thread result" primitive** (`current_context
  .get_gui_thread_caller()`, TODO `97bd090`) for the nested case,
  rather than inventing a second one -- `desk.pipeline_dsl._call_gui`
  and `desk_mcp_server._call_on_gui_thread` already solve this exact
  problem (a background-thread caller needing a GUI-thread-owned
  result) the same way. A `python`-kind job's own script always runs
  on a background thread (spawned by `run_installed_job` itself, never
  the GUI thread), so `RUN_INSTALLED_JOB`'s implementation calling
  `caller(lambda: self._prepare_installed_job_run(...))` is always a
  legitimate background-thread-calling-GUI-thread use, never
  GUI-thread-calling-itself (which would deadlock `GuiBridge.call`'s
  own blocking `done.wait()`). Only the fast prepare step goes through
  this bridge (bounded by `GuiBridge.call`'s own 5s default timeout,
  ample for filesystem/hash checks) -- the actual job execution
  (`_dispatch_installed_job_run`) always runs directly on the calling
  job's own thread, never routed through the GUI thread, so it keeps
  the same "no artificial timeout" property every Installed Job run
  already has.
- **`_RUN_LOCK` must become an `RLock`.** Confirmed by reasoning
  through the exact call sequence (and then verified with a real test,
  see Verification): a `python`-kind job A invoking `python`-kind job
  B via `RUN_INSTALLED_JOB` calls `run_script` *again*, reentrantly, on
  the *same thread* that's already inside `run_script`'s own `with
  _RUN_LOCK:` block for A. A plain `threading.Lock` is not reentrant --
  this would deadlock the very first time a `python`-kind job invoked
  another `python`-kind job. `_RUN_LOCK`'s own stated purpose (stop two
  *different* threads' `sys.path` manipulations from interleaving) is
  fully preserved by an `RLock`; only unblocks the specific case of the
  same thread re-entering, which is exactly what's needed here.
- **The callable is self-referential, not rebuilt per nesting level.**
  `_make_run_installed_job_callable` returns a closure that, for a
  `python`-kind target, passes *itself* as that nested call's own
  `run_installed_job_callable` -- arbitrary invocation depth falls out
  of ordinary Python closures/recursion, no depth bookkeeping needed. A
  `rust`-kind target gets `None` (it has no `RUN_INSTALLED_JOB`
  equivalent at all -- out of scope per the feedback).
- **No new capability gate, no cycle detection, no new timeout.**
  A `python`-kind job already has "the same unrestricted, no-sandboxing
  in-process access any other Python code already running in this
  process has" (existing doc language) -- being able to invoke another
  *already-installed* job (itself gated by the existing one-time
  `desk_install_job` approval) doesn't expand that trust boundary; a
  job could already do far more via a plain `subprocess`/`importlib`
  import. A cycle (A invokes B invokes A) behaves exactly like ordinary
  Python recursion (eventually a `RecursionError`, or an intentional
  base case) -- not specially guarded against, matching how nothing
  else about a `python`-kind job's own code is restricted either.
  Not asked for by the feedback; adding it would be scope creep.
- **Return shape matches `desk_run_installed_job`'s own JSON exactly**
  (`{"ok", "stdout", "stderr", "traceback"}`), per the feedback's own
  explicit ask -- a validation failure (not installed / stale source)
  is caught and returned this same way, not raised as a Python
  exception into the calling job's own code (that would be a different,
  harder-to-use contract than "check `result["ok"]`").

## Affected files

- `src/desk/installed_jobs.py` -- `_RUN_LOCK` becomes an `RLock`;
  `run_script` gains a `run_installed_job_callable` parameter, added to
  the `exec()` globals as `"RUN_INSTALLED_JOB"`.
- `src/desk/shell/window.py` -- `_prepare_installed_job_run` (new,
  factored out of `run_installed_job`); `_make_run_installed_job_callable`
  (new); module-level `_dispatch_installed_job_run` (new, factored out
  of `run_installed_job`'s three-way kind branch); `run_installed_job`
  itself now just calls these three pieces.
- `src/desk/temp_ui.py` -- `_INSTALLED_JOBS_DOC` gets a new
  "Invoking another job from a `python`-kind job" section; new tag,
  `_NEW_FEATURES` entry.
- `src/desk/shell/desk_mcp_server.py` -- `desk_install_job`'s
  description mentions `RUN_INSTALLED_JOB` briefly (agents authoring a
  `python`-kind job should know it exists).
- `tests/verify/` -- new coverage, including the specific
  same-thread-reentrancy case that would deadlock without the `RLock`
  fix.
- `LEARNINGS.md` -- if the `RLock` reasoning turns out to need a real
  repro to confirm (see Verification) rather than being obviously
  correct by inspection alone.

## Step-by-step implementation

1. `installed_jobs.py`: `_RUN_LOCK = threading.RLock()` (was `Lock()`).
2. `run_script`: add `run_installed_job_callable:
   Callable[[str, str | None], dict] | None = None` parameter; add
   `"RUN_INSTALLED_JOB": run_installed_job_callable` to the `exec()`
   globals dict.
3. `window.py`: extract `_prepare_installed_job_run(self, name,
   config_path) -> tuple[str | None, Path, str | None, str | None]`
   from `run_installed_job`'s current first half (validate/resolve/
   detect kind), unchanged logic, just factored out.
4. `window.py`: add module-level `_dispatch_installed_job_run(kind,
   job_dir, config_path, needs_path, run_installed_job_callable) ->
   tuple[bool, str, str, str]` -- the current three-way `if kind ==
   "rust" / elif "python" / else` branch, factored out (the python
   branch now passes `run_installed_job_callable` through to
   `run_installed_job_script`).
5. `window.py`: add `_make_run_installed_job_callable(self) ->
   Callable[[str, str | None], dict]` per Design decisions -- builds
   the self-referential closure, using `current_context
   .get_gui_thread_caller()` for the prepare step.
6. `window.py`: rewrite `run_installed_job` to: call
   `_prepare_installed_job_run`, build
   `run_installed_job_callable = self._make_run_installed_job_callable()
   if kind == "python" else None`, spawn a background thread whose
   `_run()` calls `_dispatch_installed_job_run(...)` then `on_result`.
7. `temp_ui.py`: new doc section + tag + `_NEW_FEATURES` entry.
8. `desk_mcp_server.py`: one-line addition to `desk_install_job`'s
   description.
9. Verification (below).

## Key tradeoffs / deliberately out of scope

- **`rust`-kind jobs cannot invoke anything** -- no `RUN_INSTALLED_JOB`
  equivalent is exposed to a `rust`-kind job's environment variables at
  all. Exactly the feedback's own stated scope; revisit only if
  actually asked for later.
- **No new capability/opt-in mechanism** -- see Design decisions.
- **No cycle detection or invocation-depth limit** -- see Design
  decisions.
- **`GuiBridge.call`'s default 5-second timeout applies to the prepare
  step only**, not to the invoked job's own execution -- if that 5s
  ever turns out to be too tight for an unusually slow
  `_resolve_job_needs` (e.g. a huge `needs` list), it's a pre-existing
  bound this change doesn't introduce, just reuses.

## Verification

1. A `python`-kind job invoking another `python`-kind job via
   `RUN_INSTALLED_JOB` -- confirms the result shape, confirms no
   deadlock (the specific `_RUN_LOCK` reentrancy scenario Design
   decisions reasons through), confirms nested `sys.path`
   insert/remove still composes correctly (A's own directory stays
   importable after B returns).
2. A `python`-kind job invoking a `rust`-kind job via
   `RUN_INSTALLED_JOB` -- real build+run, confirms the uniform
   interface actually hides the kind difference (the calling job's
   code is identical either way).
3. Invoking a not-installed name, and a stale-source name, both return
   `{"ok": false, ...}` rather than raising into the calling job.
4. `config_path` passed through `RUN_INSTALLED_JOB` reaches the invoked
   job correctly for both kinds.
5. Two levels of nesting (A invokes B invokes C, all `python`-kind)
   to confirm the self-referential closure actually supports depth
   greater than one.
6. Full `tests/verify/` regression suite (including the existing
   `rust`-kind coverage from TODO `94a2fa2`) still passes, 0 failures.
