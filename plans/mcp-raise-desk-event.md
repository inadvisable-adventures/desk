# MCP tool `desk_raise_event`: an agent raises an arbitrary desk event [COMPLETED]

TODO item `71d11da`. Related: TODO `30069f6` (the listening tool), `361b4f8` (the
inter-widget-communication docs callout). Source:
`../FEEDBACK/FEEDBACK-DESK-agent-qa-file-polling-2026-10-13-1845.md`.

## Summary

Today an agent that wants to tell a running widget something has to write a file the widget
polls. A widget can already receive named desk events (`desk.events.subscribe` /
`onMessage`, capability `events`; python widgets via `EventSubscription`), but only other
widgets can publish them. Add one MCP tool on the `desk` server that lets the agent publish a
named event, with an optional JSON payload, onto that same channel. Generic on purpose: no
question/answer schema, no per-widget targeting (a widget subscribes to a name, as for any
other event).

## What already exists (verified in the code)

- `desk.event_mediator.EventMediator`: Qt-free, thread-safe. `publish(name, payload,
  sender_instance_id)` logs to `MEDIATED-EVENT-LOG.tsv`, then queues the event for every
  subscribed instance except the sender. `list_subscriptions()` snapshots subscribers.
- `desk.shell.current_context.get_event_mediator()` hands the one shared mediator to code
  outside a widget (set by `DeskWindow`'s mediator binding).
- `desk_mcp_server.py`: `@tool` async handlers collected in `_TOOLS`. `tempui` docs for the
  sibling feature are `tempui-widget-logs.md` (`WIDGET_LOGS_DOC_FILENAME`,
  `SPLIT_DOC_CONTENT`), with a changelog tag in `CURRENT_TAGS` and an entry in
  `_NEW_FEATURES`.

## Design decisions

1. **Tool shape.** `desk_raise_event(name: str, payload?: any JSON)`. Hand-written JSON Schema
   (as `desk_screenshot_widget` does) so `payload` is genuinely optional and unconstrained.
2. **Sender id.** The mediator never echoes to the sender and the Event Log shows the sender
   column, so the agent publishes as the fixed synthetic id `"agent"`
   (`AGENT_EVENT_SENDER_ID`). It is never a subscribed instance, so no widget is skipped.
3. **Reserved names.** Reject names starting with `desk.` (Desk's own, e.g.
   `desk.state.changed`) and the two recording events (`recording`, `stopped_recording`,
   from `desk.widget_logs`). An agent forging those would make widgets act on events Desk did
   not emit. Everything else is allowed. (Flag to the user in the summary: "arbitrary" was
   the request; this is the one restriction I added.)
4. **Limits.** Name: non-empty string, at most 200 characters. Payload: at most 64 KiB of
   encoded JSON, as a hard backstop (queues and the TSV log live in memory/disk for every
   subscriber). The docs recommend files over about 1 KiB (that guidance lands in TODO
   `361b4f8`); the tool description states the recommendation too.
5. **Result.** Text such as `Raised "foo"; 2 subscribed widget instance(s) at publish time.`
   so an agent learns when nobody is listening. The count comes from `list_subscriptions()`
   just before publishing, so it is informational, not a delivery guarantee (stated in the
   doc). `publish` does file I/O for the log, so it runs via `run_in_executor`.
6. **Approval.** Unchanged: the tool goes through the normal `can_use_tool` gate like the
   other `desk_*` tools. No bypass.
7. **Docs.** New dedicated doc `tempui-agent-events.md` (`AGENT_EVENTS_DOC_FILENAME`,
   registered in `SPLIT_DOC_CONTENT`), written now for this tool, extended by TODO `30069f6`
   for the listening tool. Linked from the changelog entry and from the `desk.events` bullets
   in `tempui-custom-widgets.md`, the overview in `desk-temporary-ui.md`, and the porting
   doc's inter-widget list. New changelog tag + `_NEW_FEATURES` entry.
   `design-docs/architecture.md` (the MCP-tools paragraph near the widget logs mention) gets
   a sentence.

## Affected files

- `src/desk/shell/desk_mcp_server.py` (tool, constants, `_TOOLS`)
- `src/desk/temp_ui.py` (new doc, tag, entry, links)
- `design-docs/architecture.md`
- `tests/verify/verify_desk_raise_event_tool.py` (new)
- `TODO.md`, this plan

## Steps

1. Add `AGENT_EVENT_SENDER_ID`, the reserved-name and size checks, and `_raise_event`; add to
   `_TOOLS`.
2. Write `tempui-agent-events.md`, register it, mint the tag, add the changelog entry, add
   the links.
3. Update `design-docs/architecture.md`.
4. Write the verify script (below), run it plus the neighbouring tempui/MCP scripts, then the
   whole `tests/verify/` set against the baseline.
5. Mark `71d11da` COMPLETED, mark this plan COMPLETED, commit.

## Verification

`verify_desk_raise_event_tool.py`:
- With a real `EventMediator` registered in `current_context`, a subscribed instance receives
  the event (name, payload, sender `"agent"`) via `drain`; a payload-free call delivers
  `None`.
- Reserved names and oversize payloads return `is_error` and publish nothing.
- With no mediator registered, a clear `is_error` result.
- The result text reports the subscriber count.
- The event is written to the TSV log with sender `agent`.
- `desk_raise_event` is in `_TOOLS`; the doc exists, is registered, names the tool, limits,
  and reserved names, and the changelog entry links it.
- The Qt-offscreen end-to-end path (html widget receiving the event over `/events/poll`) is
  covered by an HTTP check the same way `verify_widget_log_bridge_and_mcp.py` does it, if the
  server fixture is cheap; otherwise noted as skipped in this plan.

## Status

COMPLETED 2026-10-17. The Qt-offscreen HTTP `/events/poll` end-to-end check was skipped; the
tool is verified against a real `EventMediator` (the same object that route polls). Not tried
live in a running Desk with a real Claude (Desk) session. The approval prompt per call is the
default `can_use_tool` behaviour, not changed.
