# Claude (Desk): idle "no response for" counter (TODO `0dcbbc5`) (COMPLETED)

## Summary

`ClaudeSession._dispatch` opens an unsolicited turn for ANY message that arrives with no turn outstanding. The
turn is closed only by a `ResultMessage`; the staleness tracker treats an open unsolicited turn as "outstanding".
Messages that never lead to a result (task bookkeeping, hook/system messages) leave it open: the widget is idle but
the counter runs. Also, a lingering `_unsolicited_turn_id` makes the next solicited turn's messages be tagged unsolicited.

## Affected files

- `src/desk/claude_session.py`: `_dispatch`, `_handle_message`/`_emit_task_event` accept `turn_id: int | None`.
- `tests/verify/verify_claude_desk_staleness.py`: regression test.

## Approach

1. In `_dispatch`'s no-turn branch, open an unsolicited turn only for `AssistantMessage`/`StreamEvent`. Any other message
   is handled with `turn_id=None, solicited=False` and opens nothing (as `RateLimitEvent` already does).
2. Tests: idle + `TaskNotificationMessage` leaves tracker idle; assistant output while idle still opens a turn that
   a result closes; solicited turn after a bookkeeping message is attributed solicited and completes.

## Caveat

Cause inferred from code; not reproduced against the live CLI.
