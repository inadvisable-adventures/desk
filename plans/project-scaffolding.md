# Project scaffolding & dependency management (COMPLETED)

## Summary

Set up the Python project so that Desk is an installable/runnable package:
a `pyproject.toml` declaring the runtime dependencies called out in
`design-docs/architecture.md` (PyQt6, PyQt6-WebEngine, FastAPI, uvicorn,
watchdog, websockets), a `src/desk` package layout, and an entry point
(`python -m desk`) that is currently a stub — it should start up and prove
the process boots cleanly, but does not yet need to open a window or serve
anything (that's TODO items 2/3). This item only establishes the skeleton
everything else builds on.

## Affected files

- `pyproject.toml` (new) — project metadata, dependencies, `desk` console
  script entry point.
- `src/desk/__init__.py` (new) — package marker, version.
- `src/desk/__main__.py` (new) — `python -m desk` entry point stub.
- `src/desk/app.py` (new) — `main()` function the entry point calls; stub
  that logs startup and exits (real Shell/server wiring lands in later
  TODO items).
- `.gitignore` (new) — Python build artifacts, venv, `__pycache__`, etc.
- `README.md` (edit) — add a short "Development setup" section (create
  venv, install, run).

## Implementation approach

1. Create `pyproject.toml` using a standard `src/` layout
   (`setuptools`/`hatchling` build backend), declaring:
   - `[project]` name `desk`, version `0.0.1`, requires-python >= 3.10.
   - Dependencies: `PyQt6`, `PyQt6-WebEngine`, `fastapi`, `uvicorn[standard]`,
     `watchdog`, `websockets`.
   - `[project.scripts]` entry: `desk = "desk.app:main"`.
2. Create `src/desk/__init__.py` with `__version__`.
3. Create `src/desk/app.py` with a `main()` that, for now, just prints/logs
   that Desk started and returns 0 — enough to prove the package/entry point
   wiring works before the Shell and web server exist.
4. Create `src/desk/__main__.py` that calls `desk.app.main()` and exits with
   its return code, so `python -m desk` works during development without
   installing the console script.
5. Add `.gitignore` covering `__pycache__/`, `*.pyc`, `.venv/`, `build/`,
   `dist/`, `*.egg-info/`.
6. Add a "Development setup" section to `README.md`: create a venv, `pip
   install -e .`, run via `python -m desk`.
7. Verify: create a venv, `pip install -e .`, run `python -m desk` (and the
   installed `desk` console script), confirm both exit 0 with the expected
   log output. No GUI/browser involved at this stage, so no verification
   steps need to be skipped.

## Key design decisions / tradeoffs

- **`src/` layout over a flat package.** Keeps the installable package
  namespace (`desk`) separate from repo-root files (`README.md`,
  `design-docs/`, `plans/`), avoiding accidental imports of the wrong thing
  and matching common modern Python packaging practice.
- **`pyproject.toml`-only (no `setup.py`).** No reason to support legacy
  packaging workflows for a new project.
- **Stub `main()` rather than wiring the Shell/server now.** Keeps this TODO
  item scoped to "the project installs and runs"; the Local Web Server
  (item 2) and Desk Shell (item 3) are separate TODO items with their own
  plans, per `development-process.md`'s one-plan-per-TODO-item rule.
- **Dependencies pinned loosely (no exact versions) for now.** Exact
  pins/lockfile can be introduced once the app has enough surface area for
  version drift to matter; premature pinning here would just be guesswork.
