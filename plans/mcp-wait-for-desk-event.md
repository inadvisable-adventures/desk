# MCP tool `desk_wait_for_event`: an agent listens for an arbitrary desk event [COMPLETED]

TODO item `30069f6`. Related: TODO `71d11da` (the raising tool, done), `361b4f8` (docs callout).
Source: `../FEEDBACK/FEEDBACK-DESK-agent-qa-file-polling-2026-10-13-1845.md`.

## Summary

The other half of the agent/widget round trip: the agent blocks until a named desk event
arrives (for example a widget publishing the user's answer) and gets its name and payload.
It is meant to run on a background thread (a background sub-agent), so it may wait with no
timeout. Because a blocking call on the main conversation would freeze it, the plan adds a
programmatic guard, not only a description.

## What was investigated (the "can Claude (Desk) tell the calling context?" question)

- `claude_agent_sdk` `PreToolUseHookInput` (and the other tool-lifecycle hook inputs) carry
  `agent_id`, "present only when the hook fires from inside a Task-spawned sub-agent; absent on
  the main thread". `ToolPermissionContext.agent_id` (the `can_use_tool` context) says the same.
- A PreToolUse hook fires for every tool call regardless of permission mode, so it is a more
  reliable gate than `can_use_tool` (which is skipped for auto-approved calls).
- There is **no** foreground/background flag on the hook input, and no mapping from `agent_id`
  to a `TaskStartedMessage` that would reveal whether the task was backgrounded.
  **Consequence: the strongest check available is "called from inside a sub-agent"; a
  *foreground* sub-agent that calls the tool will still block the main conversation.** The
  tool description and the docs say to use a *background* sub-agent; the hook rules out the
  commonest mistake (calling it directly from the main conversation).
- Not tried against a live session: whether the SDK really populates `agent_id` for an MCP
  tool call made by a sub-agent. The SDK source says the four tool-lifecycle hooks do. Noted in
  the plan's Status as unverified live.

## Design decisions

1. **Shape.** `desk_wait_for_event(name: str, timeout_seconds?: number)`. One name per call.
   `timeout_seconds` omitted = wait indefinitely (until an event, a cancel, a Desk switch, or the
   session ending). Result is JSON text with a `status`: `"event"` (plus `name`, `payload`,
   `sender`, `timestamp`), `"timeout"`, or `"ended"` (Desk was switched, so every subscription
   was dropped). Timeout/ended are not errors.
2. **Mechanism.** A synthetic listener instance id `agent-listener:<uuid>` is subscribed to
   `name` on the shared `EventMediator`; the tool waits on the mediator's queue and always
   unsubscribes in a `finally`. Unlike the raise tool's `agent` sender, the listener is a real
   subscriber.
3. **No clamp, no leak.** `EventMediator.poll` clamps to 30 s, so the wait loops over short
   (1 s) polls on a dedicated thread, checking a cancel flag. An `asyncio.CancelledError` (the
   session stopping or the call being interrupted) sets the flag so the thread exits within a
   second and the subscription is removed. After `EventMediator.clear_all()` (a Desk switch)
   the subscription is gone, which the loop detects and reports as `"ended"`.
4. **Thread budget.** A dedicated `ThreadPoolExecutor` (cap `MAX_CONCURRENT_EVENT_LISTENERS`,
   8) so listeners can never exhaust the default executor that GUI-thread hops use. Beyond the
   cap the call returns an error.
5. **Gap between calls (documented, not fixed).** A subscription exists only while a call is
   in flight, so an event published between two consecutive calls is missed. The docs say
   so and advise: have the widget write a file/state for anything that must not be lost and
   make the event only a nudge, or re-check after each return. A persistent per-name
   subscription is a possible follow-up, deliberately not built (it would accumulate events
   with no consumer).
6. **Guard.** `desk_mcp_server.wait_for_event_hook` decides (pure function, testable): deny
   when the PreToolUse input has no `agent_id`, with a reason that explains how to proceed (spawn
   a background sub-agent). Wired in `ClaudeSession` as a `PreToolUse` hook with a matcher for the
   fully-qualified tool name (built from `WAIT_FOR_EVENT_TOOL_NAME`, like
   `RUN_INSTALLED_JOB_TOOL_NAME`), only for non-scoped sessions (scoped ones have no Desk MCP
   server). The scoped path-check hook is unchanged.
7. **Approval.** Unchanged (`can_use_tool` as for the other tools). Note the sub-agent's
   call surfaces its approval prompt like any other.
8. **Docs.** Extend `tempui-agent-events.md` with a "Listening" section (the background-
   sub-agent rule and what is and is not enforced, the three statuses, the between-calls
   gap, the worked round trip with the raise tool and a widget answering by publishing),
   new changelog tag + `_NEW_FEATURES` entry, link from the same places as the raise tool, one
   sentence in `design-docs/architecture.md`.

## Affected files

`src/desk/shell/desk_mcp_server.py`, `src/desk/claude_session.py`, `src/desk/temp_ui.py`,
`design-docs/architecture.md`, `tests/verify/verify_desk_wait_for_event_tool.py` (new),
`tests/verify/verify_desk_mcp_server.py` (tool count), `TODO.md`, this plan.

## Verification

`verify_desk_wait_for_event_tool.py`, with a real `EventMediator`:
- an event published from another thread while the call waits is returned (name, payload,
  sender, timestamp); a payload-free event gives a `None` payload;
- an event raised through `desk_raise_event` is received (round trip);
- `timeout_seconds` expires into `"timeout"`; the subscription is gone afterward, as it is
  after an event;
- `clear_all()` while waiting gives `"ended"` within about a second;
- cancelling the task (`asyncio` cancel) removes the subscription and frees the thread;
- the concurrent-listener cap returns an error without subscribing;
- the hook decision denies without `agent_id` and allows with it; `ClaudeSession`'s options
  register the hook for the right matcher (non-scoped) and not for a scoped session;
- docs and changelog assertions as for the raise tool.

## Status

COMPLETED 2026-10-17. Verified headless with a real `EventMediator` and the real `ClaudeSession`
hook registration. Not verified in a live Desk session: that the SDK populates `agent_id` for an MCP
tool call made by a sub-agent (the SDK source says it does), and that the harness tolerates a
multi-hour tool call. A foreground sub-agent is not refused (no signal available).
