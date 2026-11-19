# Desk-hosted microservices (hmsvc)

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags. Like Installed
Jobs, hmsvc is **not** a tempui-DSL file type: you author a directory
under `desk_hmsvc/`, not a file dropped here.

A Desk-hosted microservice is a long-running Python process Desk starts,
supervises, logs and restarts for you -- the answer for "this project
needs a local backend" (an API over a database, a file indexer, a
bridge to some device). Each runs in its own subprocess, so a crashing
or blocking service can't stall Desk.

## Layout

```
<project>/desk_hmsvc/<name>/service.py     required: the ASGI app
<project>/desk_hmsvc/<name>/service.json   optional: settings
```

A directory without a `service.py` is not a service. Other files beside
`service.py` can be imported by it (`import helper`; the service's own
directory is first on `sys.path`).

## `service.py`

It must expose a module-level ASGI callable named `app` (FastAPI works,
and so does a raw ASGI function). Desk serves it with
`uvicorn.run(app, host, port)`, so **`uvicorn` must be importable under
whichever interpreter runs the service** (Desk's own by default -- see
`venv`/`python` below). Bind nothing yourself: Desk allocates the port
and passes it as `DESK_SERVICE_PORT` (and the bind address as
`DESK_SERVICE_HOST`). A file with no `app` exits with an error in the
service's log.

Also set in the environment: `DESK_SERVICE_NAME`, `DESK_PROJECT_DIR`,
`DESK_BRIDGE_URL`, `DESK_BRIDGE_TOKEN` (the last two let the service
call Desk itself -- see below). A service that doesn't start accepting
connections within 15 seconds is killed and marked `crashed`.

## `service.json`

Every key is optional. A missing, unparseable or non-object file just
means all defaults.

- `description` (string): shown in the Microservices widget and in
  `desk.hmsvc.list()`.
- `autostart` (bool, default `false`): start whenever this project opens.
- `external` (bool, default `false`): `false` binds loopback only
  (`127.0.0.1`); `true` binds all interfaces so other devices on the
  local network can reach it (the widget then also shows its LAN URL).
  Either way the port is **unauthenticated** -- add your own auth to an
  external service.
- `capabilities` (list, default `["state", "events"]`; `workspace` and
  `experts` are also available -- `experts` lets the service register as an
  expert and answer questions, see `tempui-experts.md`): which Bridge capabilities the service's own calls to
  Desk hold. A call needing one it lacks fails with HTTP 403.
- `venv` (string): a project-relative venv directory; the service runs
  under `<venv>/bin/python`.
- `python` (string): an absolute interpreter path (for a venv outside
  the project). Wins over `venv` if both are set. Neither set: Desk's
  own interpreter. A configured-but-missing interpreter fails
  immediately, naming the path, with no silent fallback. The interpreter
  needs `uvicorn` installed.

## Discovery and lifecycle

Services are found by a plain filesystem scan of `desk_hmsvc/` -- there
is no approval prompt. The scan runs when the project opens or switches,
and **Desk also watches `desk_hmsvc/` live**: adding, editing or removing
a service directory (its `service.py` or `service.json`) is picked up
within a moment, with no reopen needed, and a service Desk hasn't seen
before in this project raises a top-right notification ("New
microservice available: `<name>` -- `<description>`"); clicking it places
(or focuses) the Microservices widget so the user can start it. Desk
never starts a service just because it appeared (only `autostart` does,
at project open). The widget's **Rescan** button still forces a rescan.
Services with `autostart` start when the project opens; switching to a
different project stops every running service of the old one.

Statuses: `stopped`, `starting`, `running`, `exited` (ended on its own
with code 0), `crashed` (non-zero exit, or never became ready). A stop
request gives the process a short grace period, then kills it.

## Calling a service from an agent

An agent does not need a widget to reach a service. Two MCP tools on the
`desk` server work against the current project's services:

- `desk_list_hmsvcs()` -- each service's `name`, `description`, `status` and,
  while `running`, its loopback `url`. Read-only; it never starts anything.
- `desk_call_hmsvc(name, method?, path?, json?, body?, headers?, timeout?)` --
  one HTTP request to the *running* service `name`; `path` is the route on
  that service (starting with `/`, query string included), `method` defaults
  to `GET`. For `POST`/`PUT`/`PATCH` give `json` (any JSON value) or `body`
  (text). It returns `{status, content_type, truncated, body}`.

You never pass a host or port (the port is new on every launch), and
redirects are reported rather than followed. An HTTP error status such as 404
or 500 comes back as a normal result so you can read the service's own error
message; only a stopped or unreachable service, or a malformed request, is a
tool error. The body is text, capped at 100 KB, and binary responses are not
shown. A stopped service has no address: ask the user to start it from the
Microservices widget. The routes are whatever the service's `service.py`
defines, so read it first. The port is unauthenticated unless the service adds
its own auth, so do not send secrets.

## Reaching a service from a widget -- the networking model

`desk.hmsvc.*` is **management only**; it does not proxy requests into
the service. A `kind: "html"` widget with the `hmsvc` capability:

**Only need a service's URL? Skip this and read `desk.state`
(next section) -- it needs no `hmsvc` capability.** Use `desk.hmsvc.*`
when the widget manages services (list them all, start/stop/restart,
read logs).

1. calls `await desk.hmsvc.list()` -- it resolves to an **object**,
   `{ services: [...] }` (not a bare array), so destructure it:
   `const { services } = await desk.hmsvc.list();`. Each entry is `{name, description,
   status, port, pid, url, external, lan_url, capabilities, autostart,
   started_at, exit_code}`; `url` (e.g. `http://127.0.0.1:53211/`) is
   `null` unless the service is `running`, and **the port is new on
   every launch**, so never hard-code or cache it across restarts;
2. then does its own direct `fetch()` against that `url`.

Also available: `desk.hmsvc.logs(name, limit)` (resolves to
`{ lines: [...] }`), and `start(name)`, `stop(name)`, `restart(name)`
(each resolves to `{ ok, message }`). Every status change is broadcast as the
mediated event `desk.hmsvc.changed` (`{"services": [...]}`), so a widget
can subscribe instead of polling. The `hmsvc` capability covers every
service in the project; it is broader than "tell me one URL" -- for just
that, see the next section.

### Just need the URL? Read `desk.state` instead

Desk mirrors each service's current `{status, url}` into the shared state
store as the key **`desk.hmsvc.<name>`** and updates it on every status
change, so a widget holding only the `state` capability (which most
cross-widget widgets already do) needs no `hmsvc` capability to find a
service:

```js
const { value } = await desk.state.get("desk.hmsvc.hello");   // value: {status, url}, or null
await desk.events.subscribe(["desk.state.changed"]);   // then watch key === "desk.hmsvc.hello"
```

`status` is one of `starting`, `running`, `stopped`, `exited`, `crashed`
(or `removed` if the service directory is gone); `url` is non-null only
while `running`. A stopped or crashed service keeps its key (with `url`
null) so subscribers hear the change. Use the `hmsvc` capability only if
the widget needs start/stop/restart/logs. These keys are runtime-only:
never saved to the `.desk` file, so a freshly opened project has them
only once its services have been scanned.

### CORS is mandatory

A widget page is served from a different origin than the service's own
port (each placed `kind: "html"` instance is its own browser origin), so
every `fetch()` is cross-origin. **The service must send CORS headers
itself** -- at minimum `Access-Control-Allow-Origin` on every response,
and an answer to the `OPTIONS` preflight (with
`Access-Control-Allow-Methods`/`-Headers`) for any non-simple request
such as a JSON `POST`. Without this the widget's `fetch()` fails with an
opaque network error and nothing in Desk's log says why.

## Calling Desk from inside a service

`from desk.hmsvc_client import desk` (stdlib only, blocking calls --
wrap in `asyncio.to_thread` inside an `async def` handler):
`desk.state_get(key)`, `desk.state_set(key, value)`,
`desk.events_subscribe(names)`, `desk.events_publish(name, payload)`,
`desk.events_poll(timeout)`, and (with the `workspace` capability)
`desk.workspace_get_state()`. Events use the same mediated channel
widgets use, under sender id `hmsvc:<name>`.

## Logs

A service's stdout and stderr, plus Desk's own `[desk]` lines, are kept
in memory only -- the last 500 lines -- not in
`.desk_temp/logs/desk.log`. View them in the Microservices widget or via
`desk.hmsvc.logs(name, limit)`.

## Minimal worked example

`desk_hmsvc/hello/service.json`:

```json
{"description": "Says hello", "autostart": true}
```

`desk_hmsvc/hello/service.py` (raw ASGI, no dependencies, CORS wired in):

```python
import json

CORS = [
    (b"access-control-allow-origin", b"*"),
    (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
    (b"access-control-allow-headers", b"content-type"),
]


async def app(scope, receive, send):
    if scope["type"] != "http":
        return  # (a real service also answers the "lifespan" scope)
    if scope["method"] == "OPTIONS":
        await send({"type": "http.response.start", "status": 204, "headers": CORS})
        await send({"type": "http.response.body", "body": b""})
        return
    body = json.dumps({"hello": "world", "path": scope["path"]}).encode()
    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"application/json"), *CORS],
    })
    await send({"type": "http.response.body", "body": body})
```

In a widget that only needs the URL (the `state` capability):

```js
const { value } = await desk.state.get("desk.hmsvc.hello");   // {status, url}, or null
if (value && value.url) {
  const reply = await (await fetch(value.url + "greet")).json();
}
```

In a widget that manages services (the `hmsvc` capability) -- note
`list()` resolves to `{ services }`, not a bare array:

```js
const { services } = await desk.hmsvc.list();
const hello = services.find(s => s.name === "hello");
if (hello && hello.url) {
  const reply = await (await fetch(hello.url + "greet")).json();
}
```
