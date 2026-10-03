# Claude (Desk) widget: token-usage indicator + Interrupt button (TODO `db2402c`) (COMPLETED)

## Summary
(1) Surface `AssistantMessage.usage` as a `token_usage` signal/`session_event`
and show it live in the "Working..." status, plus the final tally from
`ResultMessage`. (2) An Interrupt button wired to `ClaudeSDKClient.interrupt()`,
with `ResultMessage.terminal_reason` telling an interrupted turn apart.

## Affected files
`src/desk/claude_session.py`, `widgets/claude_desk/widget.py`,
`tests/verify/verify_claude_desk_token_usage_interrupt.py`, `TODO.md`.

## Decisions
- Only top-level messages (`parent_tool_use_id is None`) report usage, so a
  sub-agent's calls don't double-count against the parent.
- Display: input = latest message's context size (input + cache read/creation
  -- each API call resends the whole context, so summing overcounts); output
  accumulates over the turn. Reset on `turn_started`.
- `turn_complete` payload gains `usage`, `model_usage`, `terminal_reason`;
  final tally goes to the status label tooltip.
- Interrupt: visible only while busy, disabled after click (status
  "Interrupting..."), re-enabled on the next `turn_started`. The CLI ends the
  turn with an aborted `terminal_reason`, which completes the pending turn via
  the normal path; status then reads "Interrupted." Queued messages still
  drain afterwards (unchanged queue semantics).

## Verification
New verify script (fake client/session); whole `tests/verify/` suite. No live
API run.
