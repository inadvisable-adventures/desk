# Minimap widget for navigating the Desk canvas (TODO `669b690`) (COMPLETED)

## Summary
A `kind: "python"` widget showing a scaled-down map of every placed widget and
the current viewport, click/drag to pan, with **Organize by type**, **Nudge
apart**, **Tile** and **Undo** buttons.

## Affected files
- `src/desk/canvas_layout.py` (new): pure layout algorithms + snapshot/restore.
- `src/desk/shell/window.py`: `get_canvas_layout`, `pan_canvas_to`,
  `arrange_canvas`, `undo_canvas_arrangement`, `can_undo_canvas_arrangement`.
- `widgets/minimap/{widget.json,widget.py}` (new).
- `tests/verify/verify_canvas_layout.py`, `tests/verify/verify_minimap.py` (new),
  `TODO.md`, `design-docs/architecture.md`.

## Design
- **Pure algorithms** over rect dicts `{id, kind, x, y, w, h, locked}` in
  placement order, returning `{id: (x, y)}` for only the widgets that move
  (sizes never change):
  - `tile`: row-major grid, `ceil(sqrt(n))` columns, cell = largest widget +
    a gap, anchored at the current bounding box's top-left.
  - `organize_by_kind`: groups by `kind` in first-appearance order; each group
    is wrapped rows of its widgets, groups stacked vertically with a larger gap,
    anchored at the bounding box's top-left.
  - `nudge_apart`: repeatedly separates each overlapping pair along its
    minimum-translation axis (plus a small gap), half each way, until nothing
    overlaps (iteration-capped); **locked widgets never move** (the other one
    takes the whole push; two locked ones are left as they are). Unlike a
    re-tile, widgets that don't overlap anything stay put.
- **Window API** (the minimap reaches it via `get_main_window()`, like
  `desk_proc_runner` does -- no new `current_context` hook): `get_canvas_layout()`
  -> `{"frames": [...rects...], "view": {x, y, w, h}, "can_undo": bool}`;
  `pan_canvas_to(x, y)` (`centerOn`); `arrange_canvas(mode)` applies a layout,
  moving only unlocked frames, and pushes an undo snapshot `{instance_id:
  (x, y)}` of exactly the frames it moved; `undo_canvas_arrangement()` pops it
  and restores only ids **still present** -- closed widgets are skipped,
  widgets opened since are untouched (the TODO's requirement) -- and a snapshot
  that nothing moved is not pushed. Undo is a stack, so repeated arranges undo
  one at a time. (No undo infrastructure existed in Desk; this is scoped to
  arrangements, not drags.)
- **Live updates**: positions/sizes/pan/zoom change continuously with no
  signals, so the minimap polls `get_canvas_layout()` on a short timer *only
  while visible*, repainting only when the layout actually changed, and also
  refreshes immediately on `desk.widgets.overview_changed` (TODO `53779f4`).
- **Rendering**: map scaled uniformly to fit the widget, with margin; each
  widget a rect tinted by its `kind` (stable hash -> hue), stale ones outlined
  amber, titles drawn only when the rect is big enough; the viewport as a
  contrasting outline. Click or drag anywhere pans the canvas to that scene
  point (map point -> scene point inverse of the fit transform).

## Verification
Pure algorithms: no overlaps after nudge, locked fixed, tile/organize shapes,
anchors, undo-with-changed-widget-set semantics. Widget: transform math,
click -> pan call, button -> arrange call, undo enablement. Real
`WorkspaceView` frames for the window methods via a stub window. No live GUI.
