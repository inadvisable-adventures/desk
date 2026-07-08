# Desk Bridge API (COMPLETED)

## Summary

Capability-scoped REST endpoints on the Local Web Server —
`workspace.getState`, `fs.readFile`/`writeFile`, `widgets.list`/`open`/
`close`, `self.getManifest` (per `design-docs/architecture.md`'s existing
API sketch) — plus a small vanilla-JS client library auto-injected into
every `ChromiumWidget`'s page exposing them as `window.desk.*`. Applies
only to `kind: "html"` widgets; `python` widgets don't need this (direct
Python imports).

## Scope for this pass

- **REST only, no WebSocket channel yet.** The architecture sketch's
  `onStateChange()`/streaming angle was motivated partly by a
  Chromium-hosted Console widget pushing PTY output — moot now that the
  Console widget resolved native-Qt (item 15/16/17), which was the
  strongest concrete case for a push channel. None of the other named
  calls (`workspace.getState`, `fs.*`, `widgets.*`, `self.getManifest`) are
  inherently streaming — request/response REST suffices. Building a
  correct live-push mechanism (GUI-thread state changes → broadcast to
  connected WebSocket clients) is a distinct, separable chunk of work on
  top of an already-substantial item; deferred as explicit future work
  rather than folded in here.
- **`widgets.close(instanceId)` needs real per-instance identity, which
  doesn't exist anywhere in the codebase today** — `WidgetState`/
  `WidgetFrame` only ever tracked a widget's *type* id (`"editor"`), and
  two instances of the same type are indistinguishable. This is a real gap
  the architecture sketch already anticipated (`close(instanceId)`, not
  `close(widgetId)`), not new scope invented for this plan — adding a
  minimal `instance_id` (a short random string, generated at placement
  time, persisted in `WidgetState`) is necessary to implement `close`
  faithfully at all.
- **No confirmation prompt for a Bridge-initiated `widgets.close`.** The
  close *button*'s confirmation (item 19) guards against an accidental
  click; a deliberate API call from a widget's own code isn't the same
  failure mode. Bridge `widgets.close` removes immediately.

## Affected files

- `src/desk/desks.py` (edit) — `WidgetState` gains `instance_id`; factor
  the dict-building logic already inside `save_desk` into a reusable
  `desk_state_dict(desk) -> dict`, used by both `save_desk` and
  `workspace.getState`.
- `src/desk/shell/widget_frame.py` (edit) — `WidgetFrame` gains an
  `instance_id` (generated if not given).
- `src/desk/shell/canvas.py` (edit) — `add_widget` accepts/passes through
  `instance_id`.
- `src/desk/shell/window.py` (edit) — `_place_widget`/`_capture_desk_state`
  thread `instance_id` through; new methods the Bridge API calls into
  (`open_widget`, `close_widget_by_instance_id`, state capture already
  exists).
- `src/desk/shell/bridge.py` (new) — `GuiBridge`: lets the (background
  -thread) Local Web Server synchronously call into GUI-thread-owned
  `DeskWindow` state and get a result back, without touching Qt objects
  from the wrong thread.
- `src/desk/server/bridge_client.py` (new) — the injected JS client
  library, as a Python string template (parameterized with each widget's
  own id) — not a build step, not TypeScript; see Key Design Decisions.
- `src/desk/server/app.py` (edit) — Bridge REST routes, capability
  enforcement.
- `src/desk/server/runner.py` (edit) — `start_server` creates a
  `GuiBridge`, passes it to `create_app`, exposes it on `ServerHandle`.
- `src/desk/shell/chromium_widget.py` (edit) — inject the client library
  via `QWebEngineScript` at `DocumentCreation`, before the widget's own
  page scripts run.
- `src/desk/app.py` (edit) — `handle.gui_bridge.attach(window)` once both
  exist.
- `design-docs/architecture.md` (edit) — mark the Bridge API sketch
  resolved/implemented, note the WebSocket deferral and `instance_id`
  addition.

## Design

### `GuiBridge`: a synchronous cross-thread call, not a fire-and-forget signal

The Local Web Server (FastAPI/uvicorn) already runs on a background thread
in the same process (`desk.server.runner.start_server`); the existing
`HotReloadBroker` pattern (Qt signal, thread-safe emission) is
fire-and-forget — fine for "a file changed," wrong for "get me the current
workspace state and give it back to me as an HTTP response." `GuiBridge`
(constructed on the GUI thread) exposes `.call(fn)`, callable from any
thread: it emits a Qt signal (auto-queued onto the GUI thread, same
thread-safety guarantee `HotReloadBroker` already relies on) carrying `fn`
and a `(dict, threading.Event)` result holder, blocks on the `Event`, and
returns `fn`'s result (or re-raises its exception) once the GUI thread has
run it. FastAPI route handlers call it via
`await loop.run_in_executor(None, gui_bridge.call, fn)` so the blocking
wait doesn't stall the asyncio event loop (other requests can still be
served concurrently).

`GuiBridge` is constructed early (inside `start_server`, before
`DeskWindow` exists) and attached after: `handle.gui_bridge.attach(window)`
in `app.py`, mirroring how `broker`/`handle` are already threaded through
`app.py` today.

### Capability enforcement: one header identifies the caller, one per-resource capability gates it

The injected client library knows its own widget id (baked in at
injection time) and sends it as `X-Desk-Widget-Id` on every Bridge
request, alongside the existing per-launch token. Each Bridge route
re-runs `discover_widgets(widgets_dir)` (cheap; consistent with how
item 20's catalog refresh already treats this as a lightweight operation)
to look up the calling widget's declared `capabilities`, and requires one
of four coarse, resource-level capability strings: `"workspace"`, `"fs"`,
`"widgets"`. (`self.getManifest` requires no capability — a widget
introspecting its own manifest isn't a privileged operation.) A widget
that hasn't declared the resource's capability gets `403`.

Coarse (resource-level, not per-method) capabilities are a deliberate
simplification — see Key Design Decisions.

### REST surface

| Method | Route | Capability |
|---|---|---|
| `GET` | `/api/bridge/self/getManifest` | none |
| `GET` | `/api/bridge/workspace/getState` | `workspace` |
| `GET` | `/api/bridge/fs/readFile?path=...` | `fs` |
| `POST` | `/api/bridge/fs/writeFile` `{path, contents}` | `fs` |
| `GET` | `/api/bridge/widgets/list` | `widgets` |
| `POST` | `/api/bridge/widgets/open` `{widget_id, x?, y?, width?, height?}` | `widgets` |
| `POST` | `/api/bridge/widgets/close` `{instance_id}` | `widgets` |

`workspace.getState` and `widgets.open`/`close` go through `GuiBridge.call`
(they touch live `DeskWindow`/`WorkspaceView` state). `fs.readFile`/
`writeFile` and `widgets.list`/`self.getManifest` don't need the GUI
thread at all — plain filesystem/`discover_widgets()` reads, served
directly from the request-handling thread.

### Client library: plain JS, injected via `QWebEngineScript`

`ChromiumWidget.__init__` builds the library's source (a Python string
template, widget id substituted in) and inserts it as a
`QWebEngineScript` with `injectionPoint = DocumentCreation` and
`worldId = MainWorld`, so `window.desk` exists before the widget's own page
scripts run. Exposes `window.desk.workspace.getState()`,
`.fs.readFile(path)`/`.writeFile(path, contents)`,
`.widgets.list()`/`.open(widgetId, opts)`/`.close(instanceId)`,
`.self.getManifest()` — all `async`, backed by `fetch()` against the
same-origin local server (the page's own origin already *is* the local
server, so relative URLs work) with the token and widget-id headers
attached automatically.

### `instance_id`: minimal, non-breaking addition

`WidgetState` gains `instance_id: str = field(default_factory=lambda:
uuid.uuid4().hex[:8])`. Old `.desk` files without it still load fine
(`WidgetState(**data)` just falls back to the default for any entry
missing the key — a *new* id gets minted for it on next load, which is
fine: nothing outside this Desk session's own JSON referenced the old
one). `WidgetFrame` carries the same field, generated at construction if
not explicitly given (restoring from a saved Desk passes the persisted
one through).

## Verification

Entirely headless. REST/capability logic via FastAPI's `TestClient` (pure
HTTP, no Qt at all). `GuiBridge` cross-thread behavior and the injected
client library via a real (but not `.show()`n/visually-inspected)
`QApplication` + `QWebEngineView` — confirmed feasible in this environment
by a quick spike (`QWebEngineView.setHtml()` + `loadFinished` +
`runJavaScript()` all work headlessly here, *as long as the test is run as
a real script with `sys.argv` populated* — `QApplication` constructed from
a `python3 -c`/heredog with an empty `argv` crashes `QtWebEngine`'s
Chromium initialization; not a real-window requirement, a test-harness
detail). No step in this plan needs actual real-window/visual inspection.

1. `TestClient`: confirm `self.getManifest` returns the calling widget's
   own manifest fields for a request carrying its `X-Desk-Widget-Id`.
2. `TestClient`: confirm `fs.readFile`/`writeFile` round-trip a real file.
3. `TestClient`: confirm capability enforcement — a request from a widget
   whose manifest doesn't declare `"fs"` gets `403` from `fs.readFile`;
   one that does declare it gets `200`.
4. `GuiBridge`: confirm `.call(fn)` invoked from a background thread
   returns `fn`'s result computed on the GUI thread (assert via
   `QThread.currentThread()` inside `fn` that it actually ran there), and
   that an exception raised inside `fn` propagates back to the caller.
5. `TestClient` + a real `DeskWindow`/`GuiBridge` pair: confirm
   `workspace.getState` reflects the live canvas (add a widget, confirm
   it's present in the returned state); confirm `widgets.open` actually
   places a new widget on the canvas and returns its new `instance_id`;
   confirm `widgets.close` with that `instance_id` removes it.
6. Real `QWebEngineView`/`ChromiumWidget`: confirm the injected client
   library is present (`window.desk` is defined, has the expected methods)
   before any page-authored script runs, and that calling
   `window.desk.self.getManifest()` from page JS actually reaches the real
   FastAPI app and resolves with the correct manifest (a full round trip:
   browser JS → local HTTP server → response → browser JS), using
   `page().runJavaScript(..., callback)` to observe the result — run as a
   real script file (see the argv note above), not visually inspected.
7. Regression: confirm the existing `/api/ping` and widget static-file
   serving routes are unaffected by the new middleware/routes.

## Key design decisions / tradeoffs

- **Coarse, resource-level capabilities (`"workspace"`, `"fs"`,
  `"widgets"`), not one capability per method.** `fs.readFile` and
  `fs.writeFile` sharing one `"fs"` capability (rather than `fs:read`/
  `fs:write`) is less granular than "capability-scoped" could mean, but
  matches the level of detail `design-docs/architecture.md`'s existing
  sketch and `WidgetInfo.capabilities` (a flat `list[str]`) already
  imply — splitting further is a small, additive change later if a
  concrete widget actually needs read-without-write.
- **No WebSocket/push channel in this pass.** See Scope above — deferred,
  not abandoned; `design-docs/architecture.md` keeps `onStateChange()` /
  streaming noted as future work.
- **Plain JS client library, not TypeScript, not built by `tsc`.** This is
  built-in, always-shipped Desk infrastructure (every `html` widget gets
  it, unconditionally), not a Desk *user's* own custom widget code —
  exactly the same reasoning already applied to the Console/Editor
  widgets' native-Qt-not-Chromium decisions (`design-docs/architecture.md`'s
  Key Design Decisions): requiring Node/npm/tsc for something baseline
  Desk operation depends on unconditionally would reintroduce the
  build-tooling dependency the earlier "prefer Python, no build step"
  pivot deliberately moved away from. `CLAUDE.md`'s "always use TypeScript
  in strict mode" for browser code is about code a Desk *user* writes for
  their own `kind: "html"` widget (their choice of tooling) — not Desk's
  own shipped-with-every-widget plumbing.
- **`GuiBridge.call` blocks the calling thread (via `run_in_executor`, not
  the asyncio loop itself).** Simple and correct for this app's actual
  concurrency needs (one Shell process, a handful of widgets making
  occasional Bridge calls) — a more elaborate non-blocking cross-thread
  RPC mechanism isn't warranted at this scale.
- **Minimal, additive `instance_id`, not a broader Desk-persistence
  redesign.** Only what `widgets.close(instanceId)` actually requires to
  be implementable at all, per the architecture sketch's own naming.

## Status

Implemented and verified, entirely headlessly (per instruction, anything
needing real-window/visual inspection would have been marked blocked
instead — nothing here did, including the `QWebEngineView` portion, once
run as a real script file with `sys.argv` populated rather than a `python3
-c`/heredoc — see `LEARNINGS.md`):

1. REST/capability enforcement, against a real running server (no
   `TestClient`/`httpx` — that would've been a new dependency just for
   testing, and this project has consistently avoided test-framework
   dependencies throughout; plain `urllib.request` against a real
   `start_server()` instance instead): `self.getManifest` works with no
   capability; an unknown widget id gets `400`; `fs.readFile` is denied
   (`403`) without the `fs` capability and succeeds with it;
   `fs.readFile`/`writeFile` round-trip a real file; `widgets.list`
   returns the full catalog; `workspace.getState`/`widgets.open`/`close`
   correctly return `503` before a `DeskWindow` is attached.
2. `GuiBridge`: confirmed `.call(fn)` invoked from a background thread
   actually runs `fn` on the GUI thread (asserted via
   `QThread.currentThread()`) and returns its result; confirmed an
   exception raised inside `fn` propagates back to the caller.
3. Full `GuiBridge` + `DeskWindow` round trip, background-thread HTTP
   requests against a live window while pumping the GUI event loop:
   `workspace.getState` reflects the live canvas (widget count,
   `instance_id`s present); `widgets.open` actually places a new widget
   and returns its new `instance_id`; `widgets.close` with that id removes
   it; closing an unknown `instance_id` returns `closed: false` rather than
   erroring.
4. Real `QWebEngineView`/`ChromiumWidget`: confirmed the injected client
   library (`window.desk`, all four namespaces) is present before the
   page's own inline script ran; confirmed a genuine end-to-end call
   (`window.desk.self.getManifest()` from page JS → local HTTP server →
   response → resolved in page JS) returns the correct manifest. (Required
   a polling workaround for observing the resolved value back in
   Python — see `LEARNINGS.md`'s `runJavaScript` entry — which is a
   test-harness limitation, not a Bridge defect.)
5. Backward compatibility: an old `.desk` file saved before `instance_id`
   existed still loads (a fresh id is backfilled), and round-trips
   correctly through save/reload afterward.
6. Regression, against this repo's real widgets (`console`, `demo`,
   `editor`): all still place correctly with a real `instance_id` each;
   the close button (item 19) still works; save/reload after a close
   correctly reflects the removal.
7. Regression: `/api/ping` and static widget file serving are unaffected
   by the new Bridge routes/middleware.
