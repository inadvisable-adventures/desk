# Sidebar: left side, collapsible, drag-and-drop docking (TODO `4ff712c`) (COMPLETED)

## Summary

Three changes to the docked sidebar from TODO `6413e58`, requested by the user:

1. The dock moves from the right edge to the **left** edge.
2. It is **collapsible and collapsed by default**; a small always-visible tab (a thin non-movable left `QToolBar` with
   one arrow button) toggles it. The docks sit to the right of the tab.
3. A placed `kind: "python"` widget instance can be **dragged by its titlebar into the sidebar**. While dragging, a drop
   indicator ("Dock in sidebar") is shown over the drop zone exactly when releasing there will dock the widget.

## Decisions

- Collapse = hide every `QDockWidget` (they keep running; the area then has zero width). Expanded/collapsed is
  session state (not saved in the `.desk` file): every launch starts collapsed, a Desk switch keeps the user's choice.
- Docking something on purpose (`dock_widget_by_id` from the menu / MCP / drag-drop) **expands** the sidebar so the result
  is visible; restoring a saved Desk does not (`reveal=False`).
- The tab is shown even when nothing is docked (discoverability, and the drop target for an empty sidebar).
- Drop zone (global coordinates): from the tab's left edge to the right edge of the docks, never narrower than the tab
  plus 40px of canvas, full height of the canvas. Computed fresh on every drag move, so it is right whichever way the
  sidebar is open. A drag keeps the view's mouse grab, so moves outside the viewport still arrive; the cursor's global
  position decides.
- Only a titlebar *move* drag (not a resize edge) of an unlocked python frame participates; an html frame never shows
  the indicator and never docks.
- Dropping = `DeskWindow.dock_placed_widget(instance_id)`: capture the frame's widget-local storage, remove the frame
  **without** tombstoning or deleting a Scratch backing file (it is a move, not a removal), then `dock_widget_by_id` with
  the same instance id and state. Same recreate-from-state limits as "↗ move to canvas" (in-memory-only state is lost).
  Deferred with `QTimer.singleShot(0)` because it runs inside the view's mouse-release handling.
- The indicator is a click-through child widget of the main window (so it can cover the sidebar, which is outside the
  view), in new module `src/desk/shell/sidebar.py` alongside the tab-toolbar factory.
- New MCP tool is NOT added; `desk_dock_widget` is unchanged apart from it now expanding the sidebar.

## Affected files

`src/desk/shell/sidebar.py` (new), `src/desk/shell/canvas.py` (drag signals), `src/desk/shell/window.py` (left area, tab,
expand/collapse, drop zone, `dock_placed_widget`), `src/desk/temp_ui.py` (doc + changelog), `design-docs/architecture.md`
(item 36), `tests/verify/verify_docked_sidebar.py` (+ fakes that mirror these methods), `TODO.md`.

## Verification

Offscreen: left area; collapsed by default and the tab; toggling hides/shows docks and flips the arrow; reveal on dock
but not on restore; drop-zone geometry; drag signals from a real `WorkspaceView` (press titlebar, move out of the
viewport, release) incl. locked/html/resize-edge non-participation; `dock_placed_widget` keeps id and state and does not
tombstone; indicator shown only inside the zone. No live visual check is possible headless.
