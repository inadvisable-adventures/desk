# Plan: TODO 54d8c18 (COMPLETED) — Transforms core infrastructure + the Desk Service

See `design-docs/transforms.md` for the full design and rationale. This
plan is the concrete implementation breakdown.

## New files

- **`src/desk/transforms.py`** — manifest parsing & discovery, no Qt
  dependency (mirrors `desk.file_type_registry`'s own shape: plain
  dataclasses + functions, importable from anywhere including a
  headless script).
  - `TEMP_TRANSFORMS_DIRNAME = "transforms"` (full path:
    `.desk_temp/transforms/`), `PROJECT_TRANSFORMS_DIRNAME =
    "desk_transforms"` (full path: `desk_transforms/`, project root),
    `TRANSFORM_MANIFEST_FILENAME = "transform.json"`,
    `VALID_KINDS = ("python", "typescript", "javascript")`.
  - `@dataclass TransformInfo`: `id`, `path` (its own directory),
    `kind`, `entry`, `name`, `input_type`, `output_type`, `has_config`,
    `has_identity`, `location` (`"desk_temp"` or `"project"`).
  - `TransformDiscoveryError(Exception)`.
  - `discover_transforms_with_errors(desk_temp_dir: Path | None,
    project_dir: Path | None) -> tuple[dict[str, TransformInfo],
    dict[str, str]]` — scans both directories directly (`iterdir()`,
    each subdirectory's own `transform.json`), project-level wins an
    id collision (scanned second, dict assignment overwrites). A
    directory whose manifest is missing a required key, has an invalid
    `kind`, or is `kind: "python"` under `.desk_temp` is recorded in
    the *errors* dict (surfaced by the Transform Manager, TODO
    `b5e15cf`), not raised.
  - `discover_transforms(...) -> dict[str, TransformInfo]` — the
    common case, errors dict discarded.

- **`src/desk_services/transforms/service.py`** + `__init__.py` —
  follows `file_watcher`/`popups`' shared shape (plain class,
  module-level lazily-constructed `get_service()` singleton,
  `__init__.py` one-line re-export). Like `popups`, not Qt-agnostic:
  Python-transform in-process execution needs nothing Qt-specific
  itself, but the JS/TS execution path needs `QObject`/`pyqtSignal`
  (background-thread-to-GUI-thread marshaling) and `run_blocking`/
  `identity_blocking` need `QEventLoop`.
  - `TransformError(Exception)`.
  - `TransformsService.__init__`: `self._transforms: dict[str,
    TransformInfo] = {}`, `self._python_modules: dict[str, ModuleType]
    = {}` (imported once per Desk session, not reloaded per call --
    deliberately different from `PythonWidgetHost`'s always-fresh
    hot-reload convention; transforms aren't being live-edited in the
    same interactive loop), `self._js_relay = _JsRelay()` connected to
    an internal slot that just calls the stashed `on_result`.
  - `discover(desk_temp_dir, project_dir) -> dict[str, TransformInfo]`
    — calls `desk.transforms.discover_transforms_with_errors`, stores
    the result as `self._transforms` (this is what `run`/`identity`
    resolve `transform_id` against), returns `(transforms, errors)`.
  - `run(transform_id, input_data, config, on_result: Callable[[str |
    None, str | None], None]) -> None` — non-blocking. Looks up
    `self._transforms[transform_id]` (raises `TransformError` via
    `on_result(None, msg)` if unknown). `kind == "python"`: lazily
    `importlib`-loads the module (mirrors `desk.shell.python_widget
    ._load_widget_module`'s exact `spec_from_file_location`/
    `module_from_spec`/`exec_module` shape, including the
    `sys.dont_write_bytecode` suppression), calls its `run(input_data,
    config)`, calls `on_result(output, None)` -- all synchronously, on
    whichever thread called `run` (see design doc: required, not just
    simplest, since Qt-touching Python transforms must run on the GUI
    thread). Any exception -> `on_result(None, str(exc))`, never
    propagated up (mirrors `open_editor_or_scrap`'s "a broken call must
    never propagate out of a Qt slot" discipline). `kind in
    ("typescript", "javascript")`: spawns a background
    `threading.Thread` running a module-level `_run_js_transform`
    function that (a) resolves/builds the JS entry (`tsc -p <dir>` for
    `typescript`, on demand, only if the `.ts` source's mtime is newer
    than the compiled output or the output doesn't exist yet -- *this
    build step runs on the background thread too*, not before
    dispatching it, so a stale/first-run TypeScript transform's `tsc`
    invocation never blocks the GUI thread either), (b) writes
    `{"action": "run", "input": ..., "config": ...}` as JSON to a
    `node <entry>.js` subprocess's stdin (`subprocess.run(...,
    input=request, capture_output=True, text=True, timeout=30.0)`),
    (c) parses stdout as JSON, extracting `output` or `error`, (d)
    emits `self._js_relay.finished` with `(on_result, output, error)`
    -- Qt auto-marshals the QObject-owning slot's execution onto the
    GUI thread, which then calls `on_result(output, error)` there, the
    same net effect as calling it directly.
  - `run_blocking(transform_id, input_data, config=None) -> str` —
    nested `QEventLoop`, quit by the same `on_result` callback `run`
    already wires up (identical shape to `PopupsService
    .show_blocking`). Raises `TransformError` if `on_result` was
    called with an error.
  - `identity(...)`/`identity_blocking(...)` — same two shapes, calling
    the module's `identity(input_data, config)` function (Python) /
    `{"action": "identity", ...}` (JS/TS) instead of `run`. Built and
    tested at the service level in this TODO; **not** wired out to
    `current_context`/the Bridge API yet -- nothing consumes it (both
    Mermaid transforms declare `has_identity: false`), and adding an
    unused external surface now would be exactly the kind of
    abstraction-beyond-what's-needed CLAUDE.md warns against. Revisit
    when a real consumer shows up (see design doc's Future Work).
  - `promote(transform_id, desk_temp_dir, project_dir) -> None` --
    `shutil.move(desk_temp_dir / transform_id, project_dir /
    transform_id)` (mirrors `_relocate_promoted_widget_source`'s own
    shape); raises `TransformError` if the source doesn't exist or the
    destination already does, rather than silently overwriting.

## Changed files

- **`src/desk/shell/current_context.py`**: `set_transform_runner_blocking`/
  `get_transform_runner_blocking` pair (`Callable[[str, str, dict |
  None], str]`), same paired-functions shape as
  `set_editor_or_scrap_opener`. Only the *blocking* variant is exposed
  here -- no `kind:"python"` consumer needs the raw callback style
  (only the Bridge API route does, and it calls `DeskWindow
  .run_transform` directly, not through `current_context`).
- **`src/desk/shell/window.py`**:
  - `self._transforms_service = get_transforms_service()` constructed
    in `__init__` (alongside `self._popups_service`).
  - `_refresh_picker()` (the existing "per-desk state refresh choke
    point" `file_type_registry_provider`/`event_mediator` already use)
    gets one more line: `self._refresh_transforms()`, a small new
    method calling `self._transforms_service.discover(directory /
    TEMP_UI_DIRNAME / TEMP_TRANSFORMS_DIRNAME, directory /
    PROJECT_TRANSFORMS_DIRNAME)`.
  - `run_transform_blocking(transform_id, input_data, config=None) ->
    str`: thin delegation to `self._transforms_service.run_blocking`,
    bound to `current_context.set_transform_runner_blocking` at
    startup (same place as the other openers).
  - `run_transform(transform_id, input_data, config, on_result) ->
    None`: thin delegation to `self._transforms_service.run`, used by
    the Bridge API route below (not exposed via `current_context` --
    the Bridge route needs the raw callback style directly).
- **`src/desk/server/app.py`**: `TransformsRunRequest` (`transform_id:
  str`, `input: str`, `config: dict | None = None`) Pydantic model;
  `POST /api/bridge/transforms/run`, `require_caller("transforms")`,
  using `run_on_gui_async` (the same "GUI-thread operation that's
  itself asynchronous" pattern `introspect/snapshot` already
  established) since a transform invocation can genuinely take a
  while (a `node` subprocess) and must not block the FastAPI event
  loop or the GUI thread: `await run_on_gui_async(lambda resolve:
  gui_bridge.window.run_transform(body.transform_id, body.input,
  body.config, lambda output, error: resolve({"output": output,
  "error": error})))`.

## Verification

- New `tests/verify/verify_transform_discovery.py`: manifest parsing
  (valid entry, missing required key, invalid `kind`), the
  Python-rejected-under-`.desk_temp` rule, project-level winning an id
  collision with the same id under `.desk_temp`, `errors` dict
  population.
- New `tests/verify/verify_transforms_service.py`:
  - A real, hand-written Python transform (`run`/`identity`
    functions) invoked via `run`/`run_blocking`/`identity`/
    `identity_blocking` against a real temp directory -- not mocked.
  - A real, hand-written JavaScript transform (following
    `verify_build_widget.py`'s "no mocking `tsc`/subprocess, use the
    real toolchain" precedent -- confirmed `tsc`/`node` are both on
    this machine's `PATH`) invoked via `run`/`run_blocking`, confirming
    the stdin/stdout JSON protocol round-trips for real.
  - A real, hand-written TypeScript transform, confirming the on-demand
    `tsc` build actually runs, produces the expected compiled output,
    and is skipped (not rebuilt) on a second invocation with an
    unchanged source mtime, then *is* rebuilt after the source is
    touched with a newer mtime.
  - Error propagation: a transform that raises/exits non-zero/prints
    non-JSON stdout surfaces as a `TransformError`
    (`run_blocking`)/an `error` value (`run`'s callback), never crashes
    the caller.
  - `promote`: real `shutil.move`, source-missing and
    destination-exists error cases.
  - Confirm `run`/`run_blocking` genuinely don't block the calling
    thread's event loop for the JS/TS case (pump `app.processEvents()`
    concurrently with a deliberately slow test transform and confirm
    other queued Qt events still get processed before the transform
    resolves) -- not just asserted by code inspection.
- Bridge API route: exercise `DeskWindow.run_transform`/
  `run_transform_blocking` directly (same style prior Bridge-API-route
  verify scripts in this repo use -- calling the `DeskWindow` method the
  route delegates to, not spinning up a real HTTP server).
- Full `tests/verify/` regression suite.
