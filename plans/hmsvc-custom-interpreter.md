# TODO 0375f64: hmsvc service.json custom interpreter (venv/python)

## Summary

Let `desk_hmsvc/<name>/service.json` optionally name its own Python
interpreter for that service's subprocess, instead of `HmsvcManager.start()`
always launching under `sys.executable` (Desk's own interpreter). Two new,
optional, mutually-exclusive manifest fields:

- `"venv"` (string) -- a project-relative venv directory, resolved to
  `<venv>/bin/python`.
- `"python"` (string) -- an absolute interpreter path, for a venv that
  lives outside the project entirely.

Neither given: unchanged behavior (`sys.executable`). `"python"` takes
precedence if both are somehow set. This only applies to `hmsvc` services
-- the one Desk Python extension point with a real subprocess boundary to
redirect (`kind: "python"` widgets and Installed Jobs are `exec_module`'d
in-process, per the cited feedback).

Motivating case: porting `receipts` needs `opencv-python-headless`,
`numpy`, and macOS-only `pyobjc-framework-Vision` importable by an `hmsvc`
service, without adding that native, platform-specific stack to Desk's own
shared `pyproject.toml`.

## Affected files

- `src/desk/hmsvc.py` -- `_read_manifest`, `_Service`, `refresh()`,
  `start()`; new `_resolve_interpreter` helper.
- `design-docs/architecture.md` -- item 31 (Desk-hosted microservices).
- `src/desk/temp_ui.py` -- new tag in `CURRENT_TAGS`, new `_NEW_FEATURES`
  entry (this changes `service.json`'s documented schema, which is the
  only place that schema is documented for an agent working inside a
  Desk project).
- `tests/verify/verify_hmsvc_custom_interpreter.py` (new).

## Design decisions

- **Resolve `venv` against the project directory, not the service's own
  subdirectory.** Matches the cited feedback's own phrasing
  ("project-relative") and existing precedent (`desk_hmsvc/` itself is
  resolved against `self._directory`, the currently-open Desk project).
- **Fail loudly on a misconfigured interpreter**, rather than silently
  falling back to `sys.executable`. If `venv`/`python` is set but the
  resolved path isn't an existing file, `start()` returns `False` with a
  clear message and the service is marked `crashed` with the reason in its
  log -- a service that's supposed to use its own native deps but silently
  runs under Desk's interpreter instead would be a confusing, hard-to-spot
  failure mode (import errors far from the actual misconfiguration).
- **No existence/importability check beyond "is this a file that
  exists."** Actually invoking the interpreter to check it has `uvicorn`
  installed would slow down every `start()` call; a bad venv still fails
  immediately and visibly, just as a subprocess crash with a normal
  `ModuleNotFoundError` traceback in the service's own log (already
  captured by `_read_output`), same as any other service crash today.
- **Document the `uvicorn` requirement.** `desk.hmsvc_host` (the module
  that actually serves the ASGI app) imports `uvicorn` itself, so a
  configured interpreter needs it installed too, in addition to whatever
  `service.py` imports. Called out in the manifest docs and the TODO item
  itself so this isn't discovered the hard way.
- **No new `_info()` fields / widget changes.** Out of scope for this
  item; the feedback only asked for the launch mechanism. The chosen
  interpreter is visible in the service's own startup log line instead
  (`_read_output`'s existing log tail already surfaces it).

## Implementation approach

1. `src/desk/hmsvc.py`:
   - `_read_manifest(directory)` returns two more values, `venv: str |
     None` and `python: str | None`, read from `service.json` the same
     defensive way as the other fields (missing/wrong-typed -> `None`).
   - `_Service` gains `venv: str | None = None` and `python: str | None =
     None`.
   - `refresh()` unpacks and stores the two new fields alongside the
     existing ones.
   - New module-level `_resolve_interpreter(project_dir, python, venv) ->
     tuple[str, str | None]` (interpreter path, error-or-None):
     `python` set -> `Path(python).expanduser()`; else `venv` set ->
     `project_dir / venv / "bin" / "python"`; else -> `sys.executable`
     (no error). If a candidate was chosen (not the `sys.executable`
     fallback) and it isn't `Path.is_file()`, return `("", "configured
     interpreter not found: <path>")`.
   - `start()` calls `_resolve_interpreter` right after the "already
     running" check; on error, marks the service `crashed`, appends the
     error to its log, notifies listeners, and returns `(False, error)`
     without spawning anything. Otherwise the resolved interpreter
     replaces the hardcoded `sys.executable` in the `subprocess.Popen`
     argv. The `"[desk] starting on ..."` log line gets a trailing
     `" using <interpreter>"` when it isn't the default, so a service's
     own log tail shows what actually launched it.

2. `design-docs/architecture.md` item 31: add a sentence noting the
   optional `venv`/`python` manifest fields, what they resolve to, and the
   `uvicorn`-must-be-installed caveat.

3. `src/desk/temp_ui.py`: mint a tag with `generate_tag` (recorded here
   since the hash is timestamp-derived, computed when actually writing the
   code), append it to `CURRENT_TAGS`, and add a matching entry to
   `_NEW_FEATURES` (newest-first, i.e. prepended) describing the new
   `service.json` fields for an agent working inside a Desk project.

4. `tests/verify/verify_hmsvc_custom_interpreter.py`: a real subprocess
   test, no mocks --
   - Build a tiny interpreter stand-in: a shell script (`#!/bin/sh`) that
     appends a marker line to a file and then `exec`s the real
     `sys.executable "$@"` -- lets the test prove *which* interpreter
     actually ran without needing a second real Python install.
   - Case 1 (`"venv"`): place that script at
     `<project>/fake_venv/bin/python` (chmod +x), `service.json` ->
     `{"venv": "fake_venv"}`. Start the service, confirm it becomes
     `running`, answers HTTP normally (proves `uvicorn`/`desk.hmsvc_host`
     still work since the script ultimately execs the real interpreter),
     and the marker file shows it ran.
   - Case 2 (`"python"`): same script at an arbitrary absolute path
     outside `desk_hmsvc/`, `service.json` -> `{"python": "<abs path>"}`.
     Same assertions.
   - Case 3 (misconfigured): `service.json` -> `{"venv":
     "does_not_exist"}`. `start()` returns `(False, <message mentioning
     the missing path>)`, service status is `crashed`, no subprocess ever
     spawned (nothing to kill/wait on).
   - Case 4 (default/backward-compat): no `venv`/`python` field ->
     unaffected, already covered by the existing `verify_hmsvc.py`, but
     assert here too (cheap) that `service.json` with only `{"description":
     ...}` still resolves to `sys.executable`.

## Verification

Run `.venv/bin/python3 tests/verify/verify_hmsvc_custom_interpreter.py`
and the existing `.venv/bin/python3 tests/verify/verify_hmsvc.py` (to
confirm the refactor didn't change default behavior), both to `0`
failures.
