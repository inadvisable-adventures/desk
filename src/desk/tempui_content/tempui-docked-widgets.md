# Docked sidebar (desk_dock_widget)

See `desk-temporary-ui.md` (in this same directory) for this directory's
own overview and its current set of tags. This is not a tempui-DSL file
type: it is three MCP tools on the `desk` server.

The main window has a **docked sidebar** down its left edge, outside the
zoomable Workspace Canvas: a docked widget stays put and at a fixed size
while the canvas pans and zooms behind it. The sidebar is **collapsed by
default** (a thin tab is all that shows: an arrow plus a rotated label per docked
widget, long titles cut with "..."). The whole tab is one click target: it
expands the collapsed sidebar and, with its arrow centred, collapses the open
one. That choice is not saved in the `.desk` file).
`desk_dock_widget` expands it so the result is visible; restoring a saved
Desk does not. It is for small, always-visible
panels (a list of the desk's areas, say), not for general work.

- Only `kind: "python"` widgets can be docked for now; an html /
  `DefineWidget` widget is refused with an error.
- A human docks one from the canvas right-click menu: expand "Dock in
  sidebar" and pick the widget. Each docked widget's title bar has a
  "move to canvas" button and a "remove" button. A human can also drag a
  placed python widget by its titlebar onto the sidebar (or its tab); a
  "Dock in sidebar" highlight shows when releasing will dock it. That is a
  move, not a removal: the instance keeps its id and widget-local storage,
  and nothing is added to Recently Removed. State a widget keeps only in
  memory (not in its widget-local storage) is lost in the move, as for
  "move to canvas".
- A docked widget has **no canvas frame**, so it has no titlebar markers
  (`[ERROR]`, `[STALE]`, ...), is **not** listed by
  `desk_list_widget_instances`, and cannot be screenshotted with
  `desk_screenshot_widget`. Use `desk_list_docked_widgets` to see what is
  docked; `desk.workspace.getState()` carries the same list as `docked`.
- It keeps its widget-local storage (`get_widget_local_storage` /
  `set_widget_local_storage`) and is saved in the `.desk` file.

## MCP tools

- `desk_dock_widget(widget_id, state?)` -- docks a new instance; the optional
  `state` object seeds its widget-local storage, exactly as for
  `desk_place_widget`. Returns the new `instance_id`.
- `desk_undock_widget(instance_id)` -- moves it onto the canvas, centered in
  the current view, keeping its state and `instance_id`.
- `desk_list_docked_widgets()` -- `[{instance_id, widget_id, name}]`, top to
  bottom.
