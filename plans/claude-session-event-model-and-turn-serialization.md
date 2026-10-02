# Claude (Desk) session: turn serialization, event model, mismatch detection (TODO `20ca851`) (COMPLETED)

## Summary

`ClaudeSDKClient` has exactly one shared, unlabeled message stream per
connection (`Query._message_receive`; `receive_response()` is a bare
`async for` over it that stops at the first `ResultMessage`). Today
`ClaudeSession._query_and_stream` is the only consumer, started once per
prompt, and nothing but the widget's `_busy`/`_message_queue` keeps two
of them from overlapping. There is also a second, subtler failure mode
the feedback did not name: **anything the CLI emits while no consumer is
iterating** (a `ScheduleWakeup` continuation, a background-task
notification) just sits in the buffer, and the *next* `receive_response()`
consumes it -- including its stale `ResultMessage`, which ends the new
turn early and leaves the real answer queued for the turn after. That
produces exactly the feedback's permanent constant offset, with no
overlapping consumers needed.

Fix: one **persistent reader** per session is the only consumer of the
stream; turns are serialized by a lock; every message is tagged with
provenance and emitted as a structured event.

## Affected files

- `src/desk/claude_session.py` -- reader task, turn lock, event model.
- `tests/verify/verify_claude_session_event_model.py` -- new coverage.
- `tests/verify/verify_claude_session_oversized_message.py` -- its fake
  client gains `receive_messages()` (the reader's entry point).
- `LEARNINGS.md`, `design-docs/architecture.md` (item 30), `TODO.md`.

## Design

- **Persistent reader** (`_reader_loop`, started lazily by
  `_ensure_reader`, so connect-time and direct `_query_and_stream` calls
  both get it): `async for m in client.receive_messages()` dispatching
  each message via `_dispatch`. Stream end or exception fails any
  pending turn and emits `session_error`.
- **Turn lock** (`asyncio.Lock`, FIFO): `_query_and_stream` holds it from
  before `query()` until that turn's `ResultMessage` (or failure), so
  queries never overlap in the CLI. Turn ids come from a monotonically
  increasing counter assigned under the lock.
- **Attribution in `_dispatch`**: a message belongs to an open
  *unsolicited* turn if one is open, else to the pending (solicited)
  turn, else it opens a new unsolicited turn (emits
  `unsolicited_turn_started`). A `ResultMessage` closes the unsolicited
  turn if open (it is ahead of ours in the CLI's queue), else completes
  the pending turn, else is a **protocol violation**: `session_event`
  kind `protocol_violation` plus `session_error`.
- **Event shape** (new `session_event = pyqtSignal(dict)`):
  `{"seq", "ts", "turn_id", "solicited", "kind", "data"}`; `kind` is one of
  `turn_started`, `unsolicited_turn_started`, `assistant_text`, `tool_use`,
  `tool_result`, `turn_complete`, `task_event`, `protocol_violation`,
  `session_error`. `seq` is a global monotonic counter; task events carry
  the turn they arrived under (informational, not a guarantee). Usage/
  context data (TODOs `db2402c`, `db1cd65`) will go in `data` of
  `turn_complete`/new kinds.
- **Legacy signals unchanged** so the widget keeps working
  (`assistant_text`, `tool_use`, ... ). Exception: `turn_complete` is
  emitted only for solicited turns -- an unsolicited result must not
  flip the widget to idle mid-turn. Unsolicited output still renders via
  the other signals (it now appears immediately instead of at the next
  prompt).
- Known limit: if the CLI starts an unsolicited turn *after* our query is
  sent but runs it first, its output is attributed to our turn;
  undetectable without CLI-side request ids.

## Verification

Fake client with a controllable `receive_messages()`: serialized turns
(two concurrent `_query_and_stream` calls never have two queries
outstanding; results pair in order), turn ids/seq monotonic, unsolicited
messages while idle tagged unsolicited and not leaked into the next turn
(the stale-result scenario), stray `ResultMessage` -> `protocol_violation`,
stream failure fails the pending turn. Run all `tests/verify/` scripts
and compare to baseline. Live-API verification skipped (no API access).
