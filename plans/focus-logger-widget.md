# Focus Logger widget (TODO 00ea6b3) -- COMPLETED

Part of the text-focus-stability investigation (`investigations/text-focus-stability.md`).
Follows TODO `b4d99a1` (focus logging inside Desk, COMPLETED). Precedes TODO `9e74c40`
(agent guidance doc).

## Summary

A new `kind: "python"` widget, `widgets/focus_logger/`, that is the one piece of UI for
controlling and watching `desk.focus_logger.FocusLogger` (owned by `DeskWindow`, reached via
`current_context.get_focus_logger()`):

- A Start/Stop button that calls `enable()`/`disable()` by hand.
- A live, read-only view of new `desk-focus` log entries as they're appended, via
  `current_context.get_widget_log_store()` (same `WidgetLogStore` the `desk_query_widget_log`
  MCP tool reads).
- Subscribes (via `bind_event_mediator`, the existing duck-typed hook `DeskWindow._bind_event_mediator`
  calls automatically for any placed python widget) to the `recording`/`stopped_recording` desk
  events (`desk.widget_logs.RECORDING_EVENT`/`STOPPED_RECORDING_EVENT`) so focus logging
  automatically brackets the user's dictation, tagged with the `recording_id` via
  `FocusLogger.set_tag`/`enable(tag=...)`.

## Key design decisions

- **Manual vs. auto-started are tracked separately, so one never clobbers the other.** The
  widget keeps one bool, `_auto_started`: true only when a `recording` event itself turned the
  logger on (it had been off). On `stopped_recording`:
  - if `_auto_started`, call `disable()` (end the session this widget started);
  - otherwise (logger was already on by hand before the recording began) just `set_tag(None)`
    and leave it running -- the user's manual session keeps going after the recording stops.
  On `recording`, if the logger is already enabled (manual session in progress), only the tag
  changes (`enable()` already does this -- see `FocusLogger.enable`'s early-return branch);
  `_auto_started` stays `False` in that case so `stopped_recording` won't stop a session the
  button, not this event, started.
- **No ownership assumption beyond one instance's own actions.** The underlying `FocusLogger` is
  a single process-wide object; multiple placed Focus Logger widgets (or `DESK_FOCUS_LOG=1` at
  startup) are all possible. `enable()`/`disable()` are already idempotent (see
  `FocusLogger.enable`'s `if self._enabled: return` branch), so a second widget's button or a
  second widget's `recording` handler double-calling either is harmless. Each widget only tracks
  whether *it itself* was the one that flipped off->on, for its own `stopped_recording` decision
  above -- it never assumes it's the only controller.
- **Live view is polled, not pushed.** `WidgetLogStore` has no change signal (by design --
  Qt-free, shared with the non-GUI MCP/server code). Matches the existing poll pattern in
  `widgets/claude_desk_status/widget.py` (`QTimer`, `POLL_INTERVAL_MS`): a `QTimer` queries
  `store.query(FOCUS_LOG_NAME, start_ms=<last seen + 1>, limit=200)` every 500ms and appends any
  new rows (formatted `format_time_iso(t) + "  " + text`) to a `QPlainTextEdit`, read-only,
  auto-scrolled to the end. Also used to keep the Start/Stop button's label/state in sync when
  the logger was toggled from somewhere else (another instance, `DESK_FOCUS_LOG=1`, a
  `recording` event), by also polling `logger.is_enabled()` each tick.
- **Leaving the widget running vs. closing it.** If this widget's own button turned the logger
  on (not an env-var start, not an already-on session it merely observed), closing the widget
  turns it back off (`destroyed` -> `disable()` if `_started_by_button`) so logging doesn't keep
  running invisibly forever with nothing watching it. A session this widget only *observed*
  (already on when placed, or on via `DESK_FOCUS_LOG=1`) is left alone on close.
- **Status label and button text use `NoTextInteraction`** (`CLAUDE.md`: labels aren't
  user-selectable by default); the log view itself is content, kept as a normal read-only
  `QPlainTextEdit` (selectable, matching `widgets/event_viewer/widget.py`'s payload view).

## Affected files

- new `widgets/focus_logger/widget.json`, `widgets/focus_logger/widget.py`
- new `tests/verify/verify_focus_logger_widget.py`
- `design-docs/widget-ux.md` (short mention alongside the existing Focus Logger / `b4d99a1` entry)
- `LEARNINGS.md` only if something surprising turns up while implementing/verifying.

## Verification

Headless `verify_focus_logger_widget.py` against the real `FocusLoggerWidget` class and a real
`FocusLogger`/`WidgetLogStore`/`EventMediator` (no full `DeskWindow`, same style as
`verify_focus_logger.py`):
- starting the widget with the logger off shows "off"; clicking Start enables it and new entries
  (appended directly to the store, simulating real focus activity) show up in the view within one
  poll tick; clicking Stop disables it.
- `recording` event: logger off -> widget turns it on with `tag=recording_id`, `_auto_started`
  True; `stopped_recording` -> logger turns back off.
- `recording` event when the logger is already on by hand: tag changes, `_auto_started` stays
  False; `stopped_recording` leaves it running (tag cleared).
- two widget instances sharing one `FocusLogger`/`EventMediator`: both reflect the same on/off
  state; a `recording` event only marks `_auto_started` True on whichever instance(s) actually
  flipped it off->on (idempotent `enable()` on the rest).
- closing a widget that started the logger via its own button turns it back off; closing one that
  only observed an already-on session (started elsewhere) leaves it running.
- no printable text ever reaches the view by a path other than what `FocusLogger` already wrote
  (the widget never formats/echoes raw key events itself -- it only renders store rows).

Real-app interactive use (placing the widget in a running Desk, narrating while two frames sit
close together) is deferred to actually running the investigation with TODO `9e74c40`'s guidance in
hand -- noted as skipped here, matching `plans/focus-logging-in-desk.md`'s own note for its
Qt-level `verify_focus_logger.py`.

## Not in scope

Agent guidance doc + changelog tag (TODO `9e74c40` -- not yet agent-visible since nothing exposed
the widget before now), any fix of the underlying caret bug.
