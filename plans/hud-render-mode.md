# HUD render mode (TODO `9ae13c0`) (COMPLETED)

Cites `../FEEDBACK/FEEDBACK-DESK-minimap-pan-attached-to-own-position-hud-render-mode-2026-10-09-1918.md`.

## Summary

A placed `kind: "python"` widget can pin a declared sub-region of itself to
the viewport. Needed because a widget that pans the canvas (the Minimap) is
itself a scene item: every pan moves it, so a drag's widget-local pointer
coordinates stop meaning the same scene point mid-gesture.

## Decisions (with the user)

- **Ghost overlay**, not reparenting: the widget stays in its scene frame;
  `desk.shell.hud.HudOverlay` (a child of `view.viewport()`) paints
  `region.render()` live at 50% opacity, no titlebar, and forwards
  press/move/release to the real region.
- **Stay pinned** until returned (not auto-return on mouse-up).
- **`kind: "python"` only**; html/Bridge API is a later TODO.

## Decisions (mine)

- **Trigger**: a widget declares `hud_trigger()` returning its region.
  `WorkspaceView.mousePressEvent`, in its content-press branch (chrome is
  already excluded), calls `HudController.trigger_press`; a press inside the
  region enters HUD mode and the press is forwarded to the overlay at once.
  The overlay is created exactly over the region's current on-screen rect
  (clamped into the viewport), at the zoom in force then, and keeps that size
  however the view zooms, so there is no visual jump. Because the *view*
  received that press, it forwards the following move/release itself
  (`active_press`); once pinned the overlay receives its own events.
- A press on the **scene's own copy** of an already-pinned region is
  swallowed (panning against the sliding copy is the bug). The scene copy is
  otherwise left as is.
- **Greeking**: a pinned frame keeps its normal content page at any zoom
  (`WidgetFrame.hud_pinned`); the overlay renders live content and a hidden
  page would freeze it and stop visible-only timers (the Minimap's).
- **Position drift**: QGraphicsView pans via `QWidget.scroll`, which drags
  viewport children (TODO `82d66c0`'s lesson), so `scrollContentsBy` and
  `resizeEvent` call `HudController.reposition()`.
- **Wheel** over an overlay is swallowed (never zooms what is behind it);
  right-click shows "Return to canvas"; middle/left forward.
- **Programmatic** entry: `current_context.get_hud_controller()` with
  `enter(region, opacity)` / `leave(widget)` / `is_pinned(widget)`.
- Runtime-only (not in the `.desk` file): a restart always returns to normal
  placement, so nothing can be stuck pinned across sessions.
- Cleanup: `remove_widget`, `clear_widgets` (desk switch), region destroyed
  (hot-reload rebuild) all leave HUD mode.
- Not agent-visible (internal python-widget hook), so no tempui changelog tag.

## Files
`src/desk/shell/hud.py` (new), `canvas.py`, `widget_frame.py`, `window.py`
(`get_hud_layout`, `leave_hud`, hook registration), `current_context.py`,
`design-docs/architecture.md`, `tests/verify/verify_hud_mode.py`.

## Verification
`verify_hud_mode.py`: real `WorkspaceView` and a real Minimap in a frame,
presses synthesized onto the view. Headless (offscreen) only: real OS mouse
grabbing and rendering were not exercised.
