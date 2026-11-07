# Docked sidebar region (TODO `6413e58`) (COMPLETED)

## Summary

From the desk-areas feedback ("a side-bar docked widget that lists the areas"), chosen with the user as a real docked
sidebar. `DeskWindow` is a `QMainWindow` whose central widget is the canvas, so a **right-hand `QDockWidget` region**
hosts widgets outside the zoomable canvas. Consumer: the Areas list widget (TODO `747806b`).

## Decisions

- **`kind: "python"` widgets only** in this pass (an html widget's `QWebEngineView` + Bridge credential + per-instance
  profile is a separate concern; docking one raises a clear error).
- A docked widget is the raw `PythonWidgetHost` in a `QDockWidget`, **not** a `WidgetFrame` (frame chrome is drawn and
  hit-tested by the canvas, so it cannot live outside it). Consequences, accepted for a first pass: no titlebar
  `[EXTERNAL]`/`[ERROR]`/`[STALE]` markers, not listed by `desk_list_widget_instances` or screenshot-able by
  `desk_screenshot_widget`; it is listed under `docked` in `desk_state_dict`/`workspace.getState()` and by a new MCP tool.
  Bound: event mediator (`bind_event_mediator`) and widget-local storage, exactly as a placed widget.
- Always the right dock area, stacked top-to-bottom; fixed (not draggable between sides) so the custom title bar
  (name, "↗ move to canvas", "✕ close") stays simple. Docked widgets are **not tombstoned** to Recently Removed on close
  (the state is the sidebar's, and "move to canvas" is the non-destructive exit).
- **Human entry point:** the canvas right-click menu gains a collapsed **"Dock in sidebar"** group listing the python
  widgets (no new titlebar button: the titlebar's width budgeting is delicate). Moving an already-placed widget into the
  dock is not offered in this pass. **Agent entry points:** `desk_dock_widget(widget_id, state?)`,
  `desk_undock_widget(instance_id)`, `desk_list_docked_widgets()`.
- Persistence: `Desk.docked: list[DockedWidgetState(widget_id, instance_id, state, width)]` in the `.desk` file
  (absent in older files -> none); `_capture_desk_state` rebuilds it from the live docks (state pulled from each widget's
  `get_widget_local_storage`, width from the dock). Restored after the canvas widgets on load / Desk switch; cleared on a
  Desk switch.
- Undock: capture state, remove the dock, place a fresh instance (same instance id) centered in the view with that state.

## Affected files

`src/desk/desks.py` (model, load/save/state dict), `src/desk/shell/window.py` (dock registry and methods, capture/load/
switch), `src/desk/shell/widget_spawn_menu.py` + `canvas.py` (the "Dock in sidebar" group and signal),
`src/desk/shell/desk_mcp_server.py` (three tools), `src/desk/temp_ui.py` (doc `tempui-docked-widgets.md`, tag + entry,
links), `design-docs/architecture.md`, `tests/verify/verify_docked_sidebar.py`.

## Verification

Offscreen: dock/undock/close/list on a real `DeskWindow`-method stand-in plus a real `QMainWindow` with a real
`PythonWidgetHost` on a tiny test widget (state round trip through dock -> undock, event-mediator bind), `.desk` round
trip and old-file load, the spawn-menu group (filter, activation, collapsed default, hidden when empty), MCP handlers,
docs. A live visual check is not possible headless.

## Implementation notes

- The two python local-storage helpers became module-level functions in `window.py` (shared by placed frames and docks);
  several existing verify fakes borrow `DeskWindow._capture_desk_state`, so they gained a `_capture_docked` stub, and the
  fake spawn menu in `verify_tempui_custom_widgets.py` accepts the new `dockable` argument.
