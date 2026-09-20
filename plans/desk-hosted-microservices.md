# COMPLETED: Desk-hosted microservices (TODO e75b165)

## Summary

User-authored Python services that Desk launches and supervises, living
in `./desk_hmsvc/<name>/` (project-relative). Each runs as its own
subprocess on its own loopback port. A manager widget lists them
(status, port, pid, URL, start/stop/restart, logs). Services can use
Desk's event channel and `desk.state.*` through a small client library,
and custom `html` widgets can manage services through a new `hmsvc`
Bridge capability.

## Service contract

- `desk_hmsvc/<name>/service.py` -- must expose a module-level ASGI app
  named `app` (FastAPI/Starlette or any ASGI callable; FastAPI/uvicorn
  are already Desk dependencies, no new ones).
- optional `desk_hmsvc/<name>/service.json`:
  `{"description": str, "capabilities": ["state", "events", ...],
  "autostart": bool}`. Defaults: no description, `["state", "events"]`,
  `autostart: false`.
- Desk allocates the port and passes it to the host process; the service
  never picks its own. Bound to `127.0.0.1` only.
- Environment given to the subprocess: `DESK_SERVICE_NAME`,
  `DESK_SERVICE_PORT`, `DESK_PROJECT_DIR`, `DESK_BRIDGE_URL`,
  `DESK_BRIDGE_TOKEN`; `PYTHONPATH` includes Desk's `src/`.
- In service code: `from desk.hmsvc_client import desk`, then
  `desk.state_get(key)`, `desk.state_set(key, value)`,
  `desk.events_subscribe([names])`, `desk.events_publish(name, payload)`,
  `desk.events_poll(timeout)`. A stdlib-only (`urllib`) client over the
  existing Bridge REST API.

## Affected files

- `src/desk/hmsvc.py` (new) -- Qt-free, thread-safe `HmsvcManager`:
  discovery, spawn/stop/restart, status tracking, log ring buffer,
  change listeners.
- `src/desk/hmsvc_host.py` (new) -- `python -m desk.hmsvc_host <dir>
  <port>`: loads `service.py`, runs uvicorn.
- `src/desk/hmsvc_client.py` (new) -- the in-service client above.
- `src/desk/server/runner.py`, `app.py`, `bridge_client.py` -- manager
  on `ServerHandle`; `require_caller` accepts `X-Desk-Widget-Id:
  hmsvc:<name>` (capabilities from `service.json`) so services reuse the
  existing state/events routes unchanged; new `/api/bridge/hmsvc/*`
  routes (capability `hmsvc`) and `desk.hmsvc.*` JS client.
- `src/desk/shell/window.py`, `current_context.py` -- point the manager
  at the current Desk's directory (in `_refresh_picker`, the existing
  choke point), publish `desk.hmsvc.changed`, autostart, stop on quit.
- `widgets/hmsvc_manager/` (new) -- python widget.
- `src/desk/temp_ui.py` -- changelog tag/entry (new Bridge capability).
- `design-docs/architecture.md`, `tests/verify/verify_hmsvc*.py`.

## Key decisions

- Subprocess, not in-process: isolation (a crashing/blocking service
  can't stall Desk's GUI or server), killability, its own port.
- Reuse Bridge routes for state/events via a synthetic caller identity,
  rather than a parallel API surface. Instance id `hmsvc:<name>` is also
  the mediator subscription id.
- Services are trusted the same way Installed Jobs are (user-authored
  code in the project). Their own port has no token, but is
  loopback-only; noted in Security Considerations.
- Switching Desks stops the old Desk's services; `autostart` ones start
  for the new Desk.
- Events: `desk.hmsvc.changed` with `{"services": [...]}` on any status
  change, so manager/custom widgets stay live without polling.

## Verification

Real subprocess test: temp project dir with a tiny FastAPI service;
start, confirm port answers HTTP, service round-trips a state value and
an event through a real Desk server (`running_server`) is out of scope
for the offscreen GUI, so state/events go through a stub-window
`GuiBridge` if feasible, else are checked at the client/route level.
Stop, restart, crash detection, log capture, widget rows. Full
`tests/verify/` run. Live app launch: skipped if no GUI available.

## Status

Completed. `tests/verify/verify_hmsvc.py` (31 checks) exercises real
subprocesses, a real Local Web Server with a stub window, state and
event round-trips in both directions, capability denial, restart/stop/
crash, log capture, the widget, directory switching/autostart, and
shutdown. Skipped: launching the real GUI app to eyeball the widget
(offscreen widget construction only). Decision made during
implementation: the manager widget appends its own failure messages to
the service log (`HmsvcManager.append_log`) rather than a separate error
surface.
