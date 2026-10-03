# Staleness must not tick while waiting on the user (TODO `f8da2c5`) (COMPLETED)

## Summary
A pending permission request or `AskUserQuestion` leaves `_turn_open` true, so
`StalenessTracker` reported "no response for Ns" (and lit the Flow view's amber
state, and could start the network probe) while the widget was just waiting on
a human.

## Affected files
`src/desk/claude_staleness.py`, `widgets/claude_desk/widget.py`,
`tests/verify/verify_claude_desk_staleness.py`, `TODO.md`.

## Decision
Take the TODO's second option: the widget passes its already-computed
"waiting on user" state into the tracker (`set_waiting_on_user`), rather than
routing `permission_request`/`question_request` through `session_event` --
the widget's pending queues are the source of truth for when the panel is
actually up (they also drive TODO `a7d7c0a`'s status event), and the session
signals fire before the panel's queue is updated. While waiting, `outstanding()`
is false, so no clock, no stale label, no flow amber, no probe. The panel is
itself the visible explanation, so no replacement text. When the user answers,
the silence clock restarts from that moment so the wait doesn't count.
The hook is `_publish_status`, which every pending-queue handler already calls,
placed before its mediator guard so it works unbound.

## Verification
Tracker-level and widget-level checks added to the staleness verify script.
