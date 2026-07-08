# Python-native Workspace Canvas & Chromium Widget hot-reload backend (COMPLETED)

## Summary

Replace the Vite-based Workspace SPA (TODO 4, now superseded — see
`plans/workspace-spa-shell.md`) with the architecture described in the
revised `design-docs/architecture.md`:

- The zoomable/pannable **Workspace Canvas** becomes a native
  `QGraphicsView`/`QGraphicsScene` owned by the Desk Shell — pan/zoom
  implemented directly in Qt, no browser page involved.
- The **Local Web Server** (already Python/FastAPI, already part of the Desk
  process) stops serving one big Workspace SPA and instead serves
  individual widgets' static assets under their own paths, and gains a
  `watchdog`-based source watcher.
- A new **`ChromiumWidget`** primitive — a `QWebEngineView` embedded on the
  canvas via `QGraphicsProxyWidget` — is the generic mechanism for hosting
  any hot-loaded SPA. For now there's exactly one such widget (a minimal
  demo SPA under `widgets/demo/`), proving the mechanism end-to-end; the
  manifest-driven multi-widget system is later TODO items (6-8).
- A **Hot Reload Broker** (`QObject` with a Qt signal) connects the
  watcher thread to the GUI-thread `ChromiumWidget`, so editing the demo
  widget's source causes its browser view to reload in place.

This is an override to work on this next, ahead of TODO items 6+ (Widget
manifest & loader, etc.), per updated requirements.

## Affected files

- `frontend/` (deleted) — the entire Vite-based Workspace SPA project;
  removed outright per "remove the Workspace SPA shell."
- `src/desk/server/app.py` (edit) — drop the single Workspace-SPA
  `StaticFiles` mount; add per-widget static mounts (discovered by scanning
  a `widgets_dir` for immediate subdirectories) and a minimal `/` response
  (no SPA to serve at the root anymore).
- `src/desk/server/widgets.py` (new) — `discover_widgets(widgets_dir) ->
  dict[str, Path]` (widget id → its directory) and `WidgetWatcher`: starts a
  `watchdog` `Observer` over `widgets_dir`, and on any filesystem event,
  determines which top-level widget id it belongs to and notifies the Hot
  Reload Broker.
- `src/desk/hotreload.py` (new) — `HotReloadBroker(QObject)` with
  `widget_changed = pyqtSignal(str)`. Lives at the `desk` package's top
  level (not under `server/` or `shell/`) since it's the shared connective
  piece between those two areas, per the design doc's Hot Reload section.
- `src/desk/server/runner.py` (edit) — `start_server()` takes `widgets_dir`
  and `broker` params and threads them through to `create_app()`.
- `src/desk/shell/canvas.py` (new) — `WorkspaceView(QGraphicsView)`: a
  `QGraphicsScene`-backed view with `DragMode.ScrollHandDrag` panning and
  wheel-driven zoom via view-transform scaling (clamped to a sane range);
  `add_widget(widget: QWidget, pos) -> QGraphicsProxyWidget` helper.
- `src/desk/shell/chromium_widget.py` (new) — `ChromiumWidget(QWebEngineView)`:
  takes a `widget_id`, a `url`, and the `HotReloadBroker`; loads the URL;
  connects to `broker.widget_changed` and calls `self.reload()` when the
  signal's id matches its own.
- `src/desk/shell/window.py` (edit) — `DeskWindow` now builds a
  `WorkspaceView` as its central widget (instead of a single
  `QWebEngineView`) and places one `ChromiumWidget` per discovered widget
  onto it.
- `src/desk/app.py` (edit) — construct the `HotReloadBroker`, pass
  `widgets_dir` (defaulting to a repo-root `widgets/` directory) into
  `start_server()`, and pass the discovered widget id→URL mapping plus the
  broker into `DeskWindow`.
- `widgets/demo/` (new) — a minimal demo widget SPA to prove the mechanism:
  `index.html`, `tsconfig.json` (`strict: true`, per `CLAUDE.md`),
  `package.json` (only `typescript` as a devDependency — no bundler/
  framework, per `CLAUDE.md`'s "avoid adding dependencies, prefer bespoke
  solutions"), `src/main.ts` compiling to `dist/main.js`. `main.ts` only
  updates `textContent` of an element that already exists in `index.html`
  (no HTML strings built in TS, per `CLAUDE.md`), and marks that element
  `user-select: none` since it's a label, not editable content.
- `.gitignore` — already ignores `node_modules/`/`dist/` broadly; no change
  needed (covers `widgets/demo/node_modules` and `widgets/demo/dist` too).
- `README.md` (edit) — replace the `frontend/`-build development-setup
  step with a description of the new architecture (native canvas,
  Chromium-hosted SPA widgets, Python local server with hot reload) and
  the demo widget's own build step (`cd widgets/demo && npm install && npm
  run build`).

## Implementation approach

1. Delete `frontend/` entirely (`git rm -r frontend`).
2. `src/desk/hotreload.py`: define `HotReloadBroker(QObject)` with
   `widget_changed = pyqtSignal(str)`. A single instance is constructed once
   in `desk.app.main()` (on the GUI thread, before starting the server) and
   shared by reference with both the server (for emitting) and the Shell
   window (for connecting `ChromiumWidget`s).
3. `src/desk/server/widgets.py`:
   - `discover_widgets(widgets_dir: Path) -> dict[str, Path]`: lists
     immediate subdirectories of `widgets_dir`, keyed by directory name.
   - `class WidgetWatcher`: wraps a `watchdog.observers.Observer` recursively
     watching `widgets_dir`; its event handler maps a changed path back to
     the owning widget id (first path component under `widgets_dir`) and
     calls `broker.widget_changed.emit(widget_id)`. Debounce rapid
     successive events for the same id (e.g. a 200ms coalescing timer) so a
     multi-file save doesn't cause multiple reloads.
4. `src/desk/server/app.py`:
   - `create_app(token, widgets_dir, broker)`: for each discovered widget,
     `app.mount(f"/widgets/{id}", StaticFiles(directory=path, html=True))`.
   - Root `/` returns a small JSON status (e.g. `{"status": "ok", "widgets":
     [...]}`) — there's no single-page app to serve there anymore.
   - Keep `/api/ping` and `/ws` (unchanged, from TODO 2) and the
     `TokenAuthMiddleware` (unchanged).
5. `src/desk/server/runner.py`: thread `widgets_dir`/`broker` through
   `start_server()` into `create_app()`; also start the `WidgetWatcher` here
   (alongside the uvicorn server thread) and stop it in `ServerHandle.stop()`.
6. `src/desk/shell/canvas.py`: `WorkspaceView` — `setDragMode(ScrollHandDrag)`,
   override `wheelEvent` to scale the view (clamped, e.g. 0.1x–4x, mirroring
   the zoom range the old JS canvas used), `add_widget()` calls
   `scene().addWidget(widget)` (returns the `QGraphicsProxyWidget`) and
   `.setPos(*pos)`.
7. `src/desk/shell/chromium_widget.py`: `ChromiumWidget.__init__(widget_id,
   url, broker, parent=None)` — `super().__init__(parent)`, `self.load(QUrl(url))`,
   `broker.widget_changed.connect(self._on_widget_changed)`, and
   `_on_widget_changed(self, changed_id)` reloads if `changed_id ==
   self.widget_id`.
8. `src/desk/shell/window.py`: `DeskWindow(widgets: dict[str, str], broker)` —
   builds a `WorkspaceView`, sets it as central widget, and for each
   `(widget_id, url)` pair creates a `ChromiumWidget` and calls
   `view.add_widget(chromium_widget, pos=(next slot))` (simple left-to-right
   placement for now — real layout/persistence is TODO 10).
9. `src/desk/app.py`: build `broker = HotReloadBroker()`, resolve
   `widgets_dir` (repo-root `widgets/`), `handle = start_server(widgets_dir,
   broker)`, `widgets = discover_widgets(widgets_dir)` mapped to
   `{id: f"{handle.url_base}/widgets/{id}/?token=..."}` (or similar), build
   `DeskWindow(widgets, broker)`.
10. `widgets/demo/`: minimal strict-TypeScript demo widget as described
    above; `npm install && npm run build` produces `dist/main.js`.
11. Update `README.md`.

## Verification

1. `cd widgets/demo && npm install && npm run build` succeeds, producing
   `dist/main.js`.
2. `python -m desk` (headless-style, via `curl`/`urllib` with the
   per-launch token, as used in prior TODO items' verification) confirms:
   - `GET /widgets/demo/` (with token) returns the demo widget's
     `index.html`.
   - `GET /widgets/demo/dist/main.js` (with token) returns the compiled JS.
3. Launch `python -m desk` for real (not headless) and confirm via `ps`
   that a `QtWebEngineProcess` renderer starts (as in `plans/desk-shell.md`)
   — proof the `ChromiumWidget` actually loaded a page. Visual confirmation
   of the rendered content and interactive pan/zoom is expected to be
   **skipped** per `development-process.md` step 5 and the precedent in
   `plans/desk-shell.md`/`plans/workspace-spa-shell.md` (screenshots haven't
   reliably shown this app's window contents in this environment).
4. Hot reload: with the app running, edit `widgets/demo/src/main.ts`,
   rebuild (`npm run build` in `widgets/demo/`), and confirm — via a log
   line added to `ChromiumWidget._on_widget_changed` — that the watcher
   detected the change and the broker's signal fired for `demo`. (Confirming
   the *visual* result of the reload is subject to the same screenshot
   limitation as above.)
5. Quit the app (as in `plans/desk-shell.md`, via a `quit` Apple Event) and
   confirm the process exits and the widget watcher/server both stop
   cleanly (no lingering threads/observer).

### Status (verification notes)

- `npm install && npm run build` in `widgets/demo/` succeeded (0
  vulnerabilities), producing `dist/main.js`.
- Headless check via `urllib`, with the per-launch token: `GET /api/ping`
  returned `{"status": "ok", "widgets": ["demo"]}`; `GET /widgets/demo/`
  returned the demo widget's `index.html`; `GET /widgets/demo/dist/main.js`
  returned the compiled JS — confirms the server now serves per-widget
  assets instead of a single Workspace SPA.
- Launched `python -m desk` for real and confirmed via `ps` that a
  `QtWebEngineProcess` renderer started, matching the precedent in
  `plans/desk-shell.md`. A screenshot again did not show this app's window
  contents (Terminal was frontmost in the capture instead) — same
  environment limitation noted in `plans/desk-shell.md` and
  `plans/workspace-spa-shell.md`, so the visual pan/zoom/rendered-content
  check is **skipped** here too, per `development-process.md` step 5.
- Hot reload verified functionally while the app was running: edited
  `widgets/demo/src/main.ts`, ran `npm run build`, and the process log
  showed `desk.shell.chromium_widget: Reloading widget demo` — confirming
  the watcher → `HotReloadBroker` → `ChromiumWidget.reload()` path works
  end-to-end across the server thread → GUI thread boundary.
- Quit via a `quit` Apple Event (as in `plans/desk-shell.md`); confirmed via
  `ps` that the process exited and via `curl` that the server's port
  stopped accepting connections.

## Key design decisions / tradeoffs

- **`QGraphicsView`/`QGraphicsScene` for the canvas, not custom painting.**
  Qt's graphics view framework provides pan/zoom and item-based composition
  (including embedding real widgets via `QGraphicsProxyWidget`) out of the
  box — writing custom hit-testing/transform code from scratch would just
  re-implement what Qt already gives for free, cutting against `CLAUDE.md`'s
  "prefer bespoke solutions" in the sense of *not reaching for more
  machinery than needed*, but Qt's own built-in framework isn't an "added
  dependency" (it ships with PyQt6, already a project dependency).
- **One `ChromiumWidget` (one `QWebEngineView`) per SPA widget, not one
  shared Workspace SPA hosting iframes.** See the updated
  `design-docs/architecture.md#key-design-decisions--tradeoffs` for the full
  rationale — in short, this removes the need for the Workspace SPA's own
  build tooling entirely and gives each widget stronger isolation for free.
- **Hot reload via a Qt signal (Hot Reload Broker), not a WebSocket message
  to a browser-side listener.** Now that the thing reacting to a file
  change is native Qt code (`QWebEngineView.reload()`), the simplest
  correct mechanism is Qt's own thread-safe signal delivery, not a
  round-trip through the Bridge API's WebSocket into JS that would then
  need its own way to reload its containing page.
- **Demo widget is plain strict TypeScript with no bundler.** A single
  `.ts` file compiled directly by `tsc` is enough to prove the hot-reload
  pipeline; adding a bundler (e.g. reintroducing Vite just for this widget)
  would be exactly the kind of unnecessary dependency `CLAUDE.md` asks to
  avoid for something this simple. Individual widgets that grow complex
  enough to want one can add that later, per-widget.
- **Demo widget's markup lives in `index.html`, not built via `innerHTML`
  in TS.** Matches `CLAUDE.md`'s "avoid putting HTML and CSS directly in
  code that will run in the browser" — `main.ts` only does
  `element.textContent = ...` against an element that already exists in the
  static HTML.
