# "Open Widgets" widget (TODO `53779f4`) (COMPLETED)

## Summary
A table of every placed widget instance (title, widget, kind, instance id,
stale), kept live by events; double-click a row = the eye button (center and
raise); a "Reload all stale widgets" button.

## Affected files
- `src/desk/widget_overview.py` (new): the event name + payload shape.
- `src/desk/shell/widget_frame.py`: `WidgetFrame.stale_changed` signal.
- `src/desk/shell/canvas.py`: `WorkspaceView.frames_changed` signal.
- `src/desk/shell/current_context.py`: overview provider + stale-reloader hooks.
- `src/desk/shell/window.py`: `get_widget_overview`, coalesced publish,
  `reload_all_stale_widgets`, raise-on-zoom by instance id.
- `widgets/open_widgets/{widget.json,widget.py}` (new).
- `tests/verify/verify_open_widgets.py` (new), `TODO.md`,
  `design-docs/architecture.md`.

## Design
- **Read API**: `DeskWindow.get_widget_overview()` -> list of
  `{instance_id, widget_id, title, kind, stale}` in placement order, from the
  live frames (stale = the frame's own `[STALE]` bit, the same signal
  `get_state_dict` exposes for TODO `f0da2e9`). `title` is the existing
  `_display_name_for_instance` label.
- **Live updates, no polling**: `WorkspaceView.frames_changed` fires when a
  frame is added/removed/cleared and when any frame's `stale_changed` flips;
  `DeskWindow` coalesces bursts (a desk load places many) with a zero-delay
  single-shot timer and publishes `desk.widgets.overview_changed` with the full
  overview as payload (the `FILE_TYPE_REGISTRY_UPDATED_EVENT` shape), sender
  id "desk". The widget loads once from the provider, then replaces its table
  from each event.
- **Double-click** a row -> `get_widget_zoomer()(instance_id)`.
  `zoom_to_widget_by_instance_id` now also raises (TODO `d0a4c7b`), so the
  Event Subscribers / Claude (Desk) Status eye buttons gain it too.
- **Reload all stale**: the button asks the stale-reloader hook, which after
  ONE confirmation ("Reload N stale widgets?", split out for tests like the
  other confirms) does for each stale frame what `[STALE]` does: reload the
  content and refresh its placed hash; a promoted widget whose source is dirty
  is rebuilt once per keyword first. The per-frame reload is factored out of
  `_on_widget_stale_clicked` so both share it.
- The button is disabled when nothing is stale.

## Verification
Real `WorkspaceView`/frames for the signals and overview; a fake mediator and
providers for the widget; batch reload via the window's per-frame helper.
