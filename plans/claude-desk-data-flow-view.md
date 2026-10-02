# Claude (Desk) widget: live data-flow view (TODO `eb50b84`) (COMPLETED)

## Summary

A toggleable panel, in the same expand-from-the-bottom style as the
background-tasks panel, that draws an abstracted pipeline and animates
markers along it for every `ClaudeSession.session_event`, so queue depth,
the in-flight turn, unsolicited output, stalls and protocol violations are
visible as they happen. Debug-grade by intent (the widget's observability
principle, design-docs/architecture.md item 30).

## Affected files

- `src/desk/claude_flow_view.py` (new): `FlowView`, plain `QPainter`, no
  new dependency.
- `widgets/claude_desk/widget.py`: "Flow" toggle button + panel, feeds the
  view from `_on_session_event`, pushes queue depth.
- `tests/verify/verify_claude_desk_flow_view.py` (new).
- `design-docs/architecture.md` item 30, `TODO.md`.

## Design

- Nodes, two lanes: outbound `Prompt -> Queue -> Session(lock) -> SDK/CLI`,
  inbound `CLI -> Stream -> Reader -> History` (CLI sits above Stream).
- Event -> marker: `turn_started` travels the outbound path; every other
  event travels the inbound path. Blue = solicited, orange = unsolicited,
  green = `turn_complete`; `protocol_violation`/`session_error` flash the
  Reader node red.
- Node annotations: Queue shows depth (pushed by the widget), Session shows
  the in-flight turn id or "idle", CLI shows active background task count
  (from `task_event` patches, terminal statuses removed), Reader shows
  events seen.
- Animation: `advance(dt)` is the whole simulation (deterministic, tested
  directly); a `QTimer` calls it at ~30 fps and runs only while the panel is
  visible and markers or flashes exist.
- Colors come from the widget palette plus a few fixed accent colors.

## Verification

Offscreen: marker creation/paths/colors per event kind, advance/expiry,
annotations, flash, timer start/stop, paint doesn't raise (grab), widget
integration (toggle, feeding, queue depth). Screenshot reviewed. Live GUI
run skipped.
