# Local web server (COMPLETED)

## Summary

Build the in-process local web server described in
`design-docs/architecture.md`: a FastAPI app, run via uvicorn in a
background thread, bound to `127.0.0.1` on an OS-assigned port, protected by
a per-launch auth token, capable of serving static assets and exposing a
minimal REST + WebSocket surface. This item does not yet serve the real
Workspace SPA (TODO 4) or implement any real Bridge API calls (TODO 8) — it
establishes the server infrastructure (startup/shutdown, binding, auth,
static serving, one placeholder REST route, one placeholder WebSocket route)
that those later items build on.

## Affected files

- `src/desk/server/__init__.py` (new) — package marker.
- `src/desk/server/app.py` (new) — `create_app(token: str) -> FastAPI`:
  builds the FastAPI app, mounts a `static/` directory (placeholder `index
  .html` for now — real SPA assets land in TODO 4), adds token-auth
  middleware, one `GET /api/ping` REST route, one `WS /ws` echo route (both
  placeholders proving the transport works end-to-end).
- `src/desk/server/runner.py` (new) — `ServerHandle` / `start_server()`:
  picks a free loopback port, generates a per-launch token, starts uvicorn
  in a background thread, exposes `.url`, `.token`, and `.stop()`.
- `src/desk/server/static/index.html` (new) — placeholder page ("Desk
  server is running") so `GET /` returns something meaningful before the
  real SPA exists.
- `src/desk/app.py` (edit) — `main()` now starts the server via
  `start_server()`, logs the bound URL, and (for this item, since there's no
  Shell/window yet) blocks until interrupted (Ctrl-C) then stops the server
  cleanly, so the server is independently runnable/verifiable before TODO 3
  wires it into the Qt shell.
- `pyproject.toml` (edit, if needed) — no new deps expected; FastAPI/uvicorn
  are already declared per TODO 1.

## Implementation approach

1. `runner.py`: bind a socket to `("127.0.0.1", 0)` to obtain a free port,
   close it, and pass that port to uvicorn (accepting the small TOCTOU race
   as standard practice for "find a free port" — uvicorn will fail fast and
   loudly if it loses the race, which is fine for a local dev tool).
   Generate the auth token with `secrets.token_urlsafe(32)`.
2. Run `uvicorn.Server` in a background `threading.Thread` (daemon thread)
   so it doesn't block the caller; `ServerHandle.stop()` calls the server's
   `should_exit` flag and joins the thread with a timeout.
3. `app.py` (server package): token-auth as FastAPI middleware — reject
   requests without a matching `X-Desk-Token` header (or `?token=` query
   param, since the `QWebEngineView` load URL and WebSocket connections
   need it too) with 401. Exempt nothing; the shell always has the token
   because it generated/received it locally.
4. Add `GET /api/ping` returning `{"status": "ok"}` and a `WS /ws` endpoint
   that echoes any received text frame back, as minimal proof the REST and
   WebSocket transports both work through the auth layer.
5. Serve `static/` via FastAPI's `StaticFiles` mount at `/`.
6. Wire `desk.app.main()` to call `start_server()`, log the URL (including
   token) at INFO level, and block on a `threading.Event` set by a
   `SIGINT`/`SIGTERM` handler, then call `.stop()` — this lets a developer
   run `python -m desk` right now and hit the server with `curl`/`websocat`
   even before the Qt shell exists.

## Verification

1. `python -m desk` starts, logs a `http://127.0.0.1:<port>/?token=...`
   URL.
2. `curl` `GET /` (with token) returns the placeholder HTML; without the
   token returns 401.
3. `curl` `GET /api/ping` (with token) returns `{"status": "ok"}`.
4. A WebSocket client (e.g. Python `websockets` one-liner) connects to
   `/ws?token=...`, sends a message, receives the same message back.
5. Ctrl-C stops the process cleanly (no hung thread / nonzero-looking
   traceback beyond the expected KeyboardInterrupt handling).

No browser/GUI is involved in this item, so nothing needs to be skipped in
verification.

## Key design decisions / tradeoffs

- **Per-launch token over no auth / OS-level socket permissions.** Binding
  to loopback already limits exposure to local processes, but any local
  process (or a browser tab) could otherwise hit the server; a token
  shared only between the Shell and the URL it loads closes that gap
  cheaply, matching the Security Considerations section of the design doc.
- **Background thread over a separate process for the server.** Keeps
  startup/shutdown simple (no IPC needed to coordinate lifecycle) and
  matches "part of Desk" from the README — the server is a component of
  the Desk process, not a standalone daemon. Revisit only if the GIL/thread
  model becomes a real bottleneck (unlikely for a local UI backend).
- **`main()` blocks/serves standalone for now, ahead of the Qt shell.**
  TODO 3 will replace this blocking loop with the Qt event loop owning
  process lifetime instead; this is a deliberately temporary shape so the
  server is independently testable before the Shell exists, consistent with
  working through TODO items in order.
