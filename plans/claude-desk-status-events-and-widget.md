# Claude (Desk) status events + status widget (TODO `a7d7c0a`) (COMPLETED)

## Summary
(a) `ClaudeDeskWidget` publishes `CLAUDE_DESK_STATUS_EVENT` on the Desk event
mediator whenever its busy/idle or waiting-on-user state changes. (b) A new
`kind: "python"` widget, `widgets/claude_desk_status/`, lists every live
`claude_desk` instance with its current status and a jump-to-instance eye
button, as a place for agent-specific "this instance needs you" notices.

## Affected files
- `src/desk/claude_session.py`: the event-name constant (next to the other
  shared claude_desk machinery, like `INSTALLED_JOBS_UPDATED_EVENT` lives with
  its feature).
- `widgets/claude_desk/widget.py`: `bind_event_mediator`, `_publish_status`.
- `widgets/claude_desk_status/{widget.json,widget.py}` (new).
- `tests/verify/verify_claude_desk_status_events.py` (new), `TODO.md`,
  `design-docs/architecture.md` (one paragraph).

## Design
- Event `desk.claude_desk.status_changed`, payload `{"busy": bool,
  "waiting_on_user": bool, "detail": str | None}`; two independent booleans so
  the consumer decides how to summarize co-occurring states. `detail` = first
  pending permission's tool name or first pending question's text.
- Publisher only: `bind_event_mediator(instance_id, mediator)` just stores
  both and publishes the current status once (so an already-open status widget
  learns of a new instance right away). `_publish_status()` is called from
  `_set_busy` and from every handler that changes the pending
  permission/question queues; it is guarded on the mediator being set (the
  constructor's own `_set_busy(False)` runs before binding) and **deduplicated**
  against the last published payload, which yields exactly one publish per
  busy/idle transition and per waiting-state edge rather than per queued item.
- Status widget: membership by polling `get_main_window().get_state_dict()
  ["widgets"]` every 1 s, filtered to `widget_id == "claude_desk"` (there is no
  push for placement/removal); status by an `EventSubscription` to the event,
  keeping the latest payload per sender instance id. Statuses of instances
  that disappeared are dropped. Rows needing attention sort first and are
  emphasized; others read "Working" / "Idle"; an instance that hasn't
  published yet reads "no status yet" -- per the item's resolved decision there
  is deliberately no request/reply to learn current state, this widget shows
  attention-needed state, not a log.
- Eye button -> `current_context.get_widget_zoomer()(instance_id)`, same as
  Event Subscribers; inherits the known "zoom doesn't raise" wrinkle (TODO
  `d0a4c7b`), not fixed here.

## Verification
Fake mediator interaction through the real `EventMediator`; stub main window
for membership; widget row rendering. Whole `tests/verify/` suite. No live GUI
session.
