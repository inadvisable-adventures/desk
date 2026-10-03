# Claude (Desk) widget: context-window awareness + Compact now (TODO `db1cd65`) (COMPLETED)

## Summary
(a) Poll `ClaudeSDKClient.get_context_usage()` after each turn and show how full
the context window is, marking it as it nears the auto-compact threshold.
(b) A confirmed "Compact now" button.

## Findings (real session, claude-haiku-4-5, scratch cwd, 2026-10-03)
- `get_context_usage()` returns, among others, `totalTokens`, `maxTokens`
  (200000), `rawMaxTokens`, `percentage` (0-100 of maxTokens),
  `autoCompactThreshold` (an **absolute token count**, 167000 -- compare against
  `totalTokens`, not `percentage`), `isAutoCompactEnabled`, `model`.
- **Sending the literal `/compact` through `client.query()` works**: the stream
  is a few `SystemMessage`s, two `UserMessage`s (the summary), then a
  `ResultMessage` with `result == ""`, `subtype == "success"`,
  `terminal_reason is None`; context usage afterward reflects the compacted
  conversation. So no upstream feature request is needed (the TODO's fallback
  branch); the persistent reader/turn lock handle it as an ordinary turn.

## Affected files
`src/desk/claude_session.py` (poll + `context_usage` signal/event),
`widgets/claude_desk/widget.py` (label, button, confirm row),
`investigations/claude-agent-sdk-upstream-requests.md` (note #3 resolved),
`tests/verify/verify_claude_desk_context_compact.py`,
`tests/verify/verify_widget_chat_button.py` (fake signal), `TODO.md`.

## Design
- Poll inside the turn lock right after a turn completes (never races a query);
  any failure is swallowed -- context awareness must never break a turn.
  Emits a `context_usage` signal and a `context_usage` `session_event`
  (`totalTokens`, `maxTokens`, `percentage`, `autoCompactThreshold`,
  `isAutoCompactEnabled`, `model`).
- Widget: a top-row label "Context N%" (hidden until the first reading),
  amber at >= 85% of `autoCompactThreshold`, red at >= the threshold; tooltip
  has the exact tokens and whether auto-compact is on.
- "Compact now" sits next to the model dropdown, disabled while busy. Clicking
  shows a label-plus-buttons confirmation row modeled on `_permission_row`
  ("Compact the conversation now? Earlier context is summarized." Compact /
  Cancel), not a modal. Confirming sends `/compact` through the normal send
  path, so the history shows exactly what was sent and the turn completes
  like any other (and triggers a fresh context reading).

## Verification
Fake client for the poll (success and failure), widget label thresholds,
confirm flow, disabled-while-busy; whole suite. The live findings above were
gathered by a one-off probe script (not kept: it needs live API access).
