# Claude (Desk) widget: rate-limit status + API error status (TODO `c1eb687`) (COMPLETED)

## Summary
Stop dropping two CLI signals the SDK already parses: `RateLimitEvent`
(connection-level throttling status) and `ResultMessage.api_error_status`.

## Affected files
`src/desk/claude_session.py`, `src/desk/claude_flow_view.py`,
`widgets/claude_desk/widget.py`, `tests/verify/verify_claude_desk_rate_limit.py`,
`tests/verify/verify_widget_chat_button.py` (fake signal), `TODO.md`.

## Decisions
- `RateLimitEvent` is handled at the top of `_dispatch`, *before* turn
  attribution: it is not turn output, so it must never open an unsolicited
  turn (it can arrive while idle). It is tagged with whichever turn is
  current, emitted as `session_event` kind `rate_limit` and a `rate_limit`
  signal with the flattened `RateLimitInfo` fields.
- Widget: a dedicated top-row `_rate_limit_label` (amber warning / red
  rejected, tooltip with window type and utilization, reset time as local
  HH:MM), hidden when `allowed`; a one-line notice entry in the history on
  each transition away from `allowed`. A separate label (not the status
  text) because the status label is rewritten constantly.
- Flow view: no marker (not a message in flight); the SDK/CLI node gets an
  amber or red border and a "throttled"/"RATE LIMITED" annotation.
- `turn_complete` gains `api_error_status`; an errored turn with one shows
  "Error (HTTP 429)." and an error history entry with the result text.
- The prolonged-outage silence that motivated the request is not solved by
  these; staleness detection is TODO `5ce8447`.

## Verification
New verify script; whole `tests/verify/` suite; no live API.
