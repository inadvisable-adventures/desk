# Python-backed widgets (interim, in-process) (COMPLETED, SUPERSEDED)

## Superseded

Per updated requirements ("widgets should be written in python and they
should render directly in the app, with no local web server in-between"),
the HTTP-rendered-HTML approach this plan describes has been replaced by
native `QWidget` rendering. See `plans/python-native-widget-hosting.md` and
TODO item 8. This file is kept for historical record only; the
`src/desk/server/python_widget.py` module and the HTTP route registration
it describes no longer exist in the codebase.

## Summary

Per updated requirements: prefer Python for widget code; the `ChromiumWidget`
mechanism (built in TODO 5) is meant more for *Desk users* who choose to
build custom SPA-based widgets than for Desk's own development; building
and running Desk itself must not require Node/npm/`tsc`, even though Desk
should still be able to run those tools on behalf of a widget that needs
them.

Concretely, this item:

1. Adds `kind: "python"` widget support to the Local Web Server: a widget
   directory containing `widget.py` (exposing `render() -> str`) is served
   by calling that function in-process on every `GET /widgets/<id>/` — no
   subprocess, no build step. Re-executing the module fresh each request
   means edits take effect on the very next request, with no caching to
   invalidate.
2. Replaces the TypeScript/Vite-based `widgets/demo/` (built for TODO 5)
   with a Python one at the same path/id, so `pip install -e . && python -m
   desk` needs zero Node/npm/tsc involvement by default.
3. Keeps the existing `kind: "html"` static-serving path (unchanged) for
   widgets that do want a custom SPA — that's still available, just no
   longer the default/example.

This is an interim simplification of the `python` kind as originally
specified in `design-docs/architecture.md` (which called for subprocess
isolation per widget); see that doc's Key Design Decisions for why
in-process rendering is the right starting point and what's deferred.

## Affected files

- `src/desk/server/widgets.py` (edit) — `discover_widgets` now classifies
  each discovered directory as `kind: "python"` (has `widget.py`) or
  `kind: "html"` (has `index.html`), returning a small `WidgetInfo`
  (`id`, `path`, `kind`) instead of a bare `Path`.
- `src/desk/server/python_widget.py` (new) — `render_python_widget(widget_dir:
  Path) -> str`: loads `widget_dir / "widget.py"` fresh via
  `importlib.util.spec_from_file_location`/`module_from_spec`/
  `exec_module`, calls its `render()`, returns the resulting HTML string.
- `src/desk/server/app.py` (edit) — for each discovered widget: `kind ==
  "python"` registers a `GET /widgets/{id}/` route calling
  `render_python_widget`; `kind == "html"` keeps the existing `StaticFiles`
  mount.
- `src/desk/server/runner.py` (edit) — `ServerHandle.widgets` type changes
  from `dict[str, Path]` to `dict[str, WidgetInfo]`; `widget_url()` is
  unaffected (still just builds a `/widgets/<id>/?token=...` URL regardless
  of kind).
- `src/desk/app.py` (edit) — `sorted(handle.widgets)` still iterates ids
  (dict keys), so no change needed there beyond what TODO 5 already did.
- `widgets/demo/` — remove `index.html`, `package.json`,
  `package-lock.json`, `tsconfig.json`, `src/main.ts`, `dist/`,
  `node_modules/` (the TypeScript/Vite version); add `widget.py` with a
  `render()` returning a small self-contained HTML string (inline `<style>`,
  a `user-select: none` label div, no client-side JS/TS at all — a
  server-rendered widget doesn't need any).
- `README.md` (edit) — remove the `cd widgets/demo && npm install && npm
  run build` step from Development setup (no longer needed); keep a short
  note that a Desk user's own `kind: "html"` widget would still bring its
  own build step, run by that widget's author, not by Desk itself.

## Implementation approach

1. `src/desk/server/widgets.py`: add
   ```python
   @dataclass
   class WidgetInfo:
       id: str
       path: Path
       kind: str  # "python" | "html"
   ```
   and rewrite `discover_widgets` to build `dict[str, WidgetInfo]`,
   skipping directories that have neither `widget.py` nor `index.html`.
2. `src/desk/server/python_widget.py`: implement `render_python_widget` as
   described. No caching of the loaded module — deliberately re-executed
   every call (see Key Design Decisions).
3. `src/desk/server/app.py`: loop over `discover_widgets(widgets_dir)`
   results; branch on `.kind`. For `"python"`, use a small factory function
   to avoid Python's late-binding-closure-in-a-loop pitfall:
   ```python
   def _make_python_widget_route(widget_dir: Path):
       async def handler() -> HTMLResponse:
           return HTMLResponse(render_python_widget(widget_dir))
       return handler
   ```
   registered via `app.add_api_route(f"/widgets/{id}/", handler,
   methods=["GET"])`.
4. `src/desk/server/runner.py`: update the `ServerHandle.widgets` type
   annotation to `dict[str, WidgetInfo]`; `discover_widgets(widgets_dir)`
   call site unaffected otherwise.
5. Delete the TypeScript demo widget's files; add `widgets/demo/widget.py`.
6. Update `README.md`'s Development setup to drop the npm/tsc step.

## Verification

1. `pip install -e .` and `python -m desk` require no `npm`/`node`/`tsc`
   invocation anywhere in the startup path — confirmed by there being no
   `node_modules`/`dist`/`package.json` under `widgets/demo/` at all
   anymore, and by the server successfully serving that widget without any
   such step having been run.
2. Headless check via `urllib` with the per-launch token: `GET
   /widgets/demo/` returns HTML containing the expected label text (proves
   the in-process Python render path works, not the old static-file path).
3. Edit `widgets/demo/widget.py`'s rendered text and, without any build
   step, `GET /widgets/demo/` again (no app restart) — confirm the new text
   appears immediately, proving re-execution-per-request needs no cache
   invalidation.
4. With the app running for real, edit `widgets/demo/widget.py` and confirm
   (via the existing `desk.shell.chromium_widget: Reloading widget demo`
   log line, as verified in TODO 5) that the file watcher still fires and
   the `ChromiumWidget` still reloads — the hot-reload plumbing from TODO 5
   is reused unchanged.
5. Visual confirmation of the rendered widget content is expected to be
   **skipped** per the precedent in `plans/desk-shell.md` and
   `plans/python-native-workspace-canvas.md` (screenshots haven't reliably
   shown this app's window contents in this environment).
6. Quit the app (via a `quit` Apple Event, as before) and confirm the
   process exits and the server's port stops accepting connections.

### Status (verification notes)

- Confirmed `widgets/demo/` now contains only `widget.py` — no
  `package.json`/`node_modules`/`dist`/`tsconfig.json` anywhere in the repo
  under `widgets/`, i.e. `pip install -e . && python -m desk` genuinely
  needs zero Node/npm/tsc involvement.
- `discover_widgets` correctly classifies `widgets/demo` as `kind:
  "python"` (verified directly in a Python shell).
- Headless check via `urllib` with the per-launch token: `GET
  /api/ping` reports `widgets: ["demo"]`; `GET /widgets/demo/` returns
  HTML with the expected `<div id="label">...</div>` content, rendered
  in-process (not served as a static file).
- Edited `widgets/demo/widget.py`'s rendered text with the real app
  running (no rebuild/restart) and re-fetched `/widgets/demo/` — the new
  text appeared immediately, confirming re-execution-per-request needs no
  cache invalidation.
- Confirmed the existing hot-reload plumbing from TODO 5 is unaffected:
  editing `widget.py` while the app was running produced the same
  `desk.shell.chromium_widget: Reloading widget demo` log line as before,
  so the file watcher → `HotReloadBroker` → `ChromiumWidget.reload()` path
  works identically for a Python-kind widget.
- Quit via a `quit` Apple Event; confirmed via `ps` the process exited and
  via `curl` the server's port stopped accepting connections.
- Visual confirmation of the rendered content was **skipped**, per the
  same environment screenshot limitation noted in
  `plans/desk-shell.md`/`plans/python-native-workspace-canvas.md`.

## Key design decisions / tradeoffs

See `design-docs/architecture.md`'s Key Design Decisions for the full
rationale; in short:

- In-process re-execution (no subprocess, no caching) is the simplest thing
  that is simultaneously correct and gets hot-editing "for free" — deferring
  subprocess isolation until there's a real need for it (a widget
  ecosystem large/untrusted enough that one widget's crash affecting the
  shared server process actually matters).
- Swapping the shipped demo widget from TypeScript to Python directly
  demonstrates the new requirement (`python -m desk` needs no Node/npm/tsc)
  rather than just asserting it in prose.
