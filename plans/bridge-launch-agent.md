# Bridge API `launch_agent` (TODO `507b8d5`) (COMPLETED)

## Summary

A `kind:"html"` widget had no way to start a Claude (Desk) session with
its own seeded context (e.g. a "chat about this result" button).
`desk.widgets.open` forwarded extra opts, but `OpenWidgetRequest`
silently dropped them and `DeskWindow.open_widget` has no such
parameter. Rather than bolting `extra_instructions` onto `widgets.open`
behind a capability, this adds a dedicated Bridge API:
`desk.agents.launch(instructions, { x, y })`, capability `launch_agent`
(`POST /api/bridge/agents/launch`). Source feedback:
`FEEDBACK-DESK-no-bridge-api-capability-lets-a-kind-html-widget-launch-a-cl-2026-11-06-2320.md`.

## Design

- Its own capability + route: starting an agent that can act on the
  project is a different trust level from placing a widget, so
  declaring `launch_agent` is the boundary. `widgets.open` is unchanged.
- `DeskWindow.launch_agent(instructions, source_instance_id, pos)`:
  same placement as the `[CHAT]` button (right of the calling frame,
  else viewport center, `pos` overrides); instructions go into a
  `launch-instructions-<uuid>.md` file in `.desk_temp` via
  `_write_claude_instructions_file` (never on the launch command line;
  the prefix keeps the file from being mistaken for a bare-UUID temp-ui
  file). Returns the new instance id; ValueError -> HTTP 400.
- Route: blank `instructions` -> 400, missing -> 422; the caller's
  `X-Desk-Instance-Id` locates the frame to place beside. Fire-and-forget:
  nothing is routed back to the widget.
- Out of scope: the "ask an expert" and cross-agent MCP feedback items
  (registry/notification layers) -- they can build on this route.

## Files

`src/desk/shell/window.py` (`launch_agent`), `src/desk/server/app.py`
(`LaunchAgentRequest`, route), `src/desk/server/bridge_client.py`
(`agents.launch`), `src/desk/temp_ui.py` (tag `#507b8d5`, changelog,
Bridge API bullet, capability list),
`tests/verify/verify_bridge_agents_launch.py` (new, 15 checks),
`tests/verify/verify_tempui_jobs_doc.py` (capability list).

## Status

Implemented; verified headless (real HTTP server + fake window, and the
real `DeskWindow.launch_agent` against a stub). Not exercised in the live
app with an actual session start.
