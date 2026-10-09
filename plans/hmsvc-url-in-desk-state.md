# Publish hmsvc service URL via `desk.state` (TODO `8925b2e`) (COMPLETED)

Cites `../FEEDBACK/FEEDBACK-DESK-hmsvc-discovery-friction-and-promoted-widget-capabilities-2026-10-09-1351.md`
(finding 3, the user's own design).

## Summary

Desk mirrors each microservice's `{status, url}` into the state store as
`desk.hmsvc.<name>` on every status change, so a widget holding only
`state` can find a service's URL without the broad `hmsvc` capability.

## Decisions (with the user)

- One key per service; value `{status, url}`.
- A stopped/crashed/restarting service keeps its key (`url` null), so
  subscribers receive a change event.

## Decisions (mine)

- Status strings are the manager's own (`starting`, `running`, `stopped`,
  `exited`, `crashed`) rather than a coarser `stopped`/`error` pair; a
  service whose directory is gone gets `removed` (the key is kept).
- Only changed values are written; the sender is the system id, so every
  widget hears the change.
- **Runtime-only**: `desks.RUNTIME_STATE_KEY_PREFIXES` keeps these keys out
  of the `.desk` file (a persisted port would be wrong on reload and
  churn the file). They are still in the live state dict.
- Status changes arrive on supervisor threads, so the manager listener
  emits a Qt signal (`DeskWindow.hmsvc_state_dirty`) whose slot runs on
  the GUI thread, where the state store lives. Also synced at every desk
  open/switch.
- Schema-rule interaction: no schema is registered for these keys, and
  they are written by Desk itself; a widget that declares a schema for a
  `desk.hmsvc.*` key would make Desk's write fail validation -- left
  unhandled deliberately (reserved namespace, documented).

## Affected files

`src/desk/hmsvc.py`, `src/desk/desks.py`, `src/desk/shell/window.py`,
`src/desk/temp_ui.py` (doc + tag `#095433`),
`tests/verify/verify_hmsvc_state_keys.py`.
