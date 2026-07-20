# Plan: TODO 1fb365e — SVG Editor selection delete affordances

Two related additions, both direct user feedback:

7. When a shape is selected in the Shapes tool, show a delete icon
   hovering on/near it.
8. When a point is selected in the Points tool, show a delete button
   near it.

Neither concept exists as UI today: there's no on-canvas delete
affordance at all (only whatever the surrounding app provides, e.g. a
keyboard shortcut elsewhere), and there's no notion of a single
"selected point" in the Points tool distinct from "currently being
dragged" (`_dragging_handle_index` resets to `None` the instant a drag
ends).

## Design

### Floating buttons, not scene items

Both delete affordances are implemented the same way the "Complete
(ENTER)" button (TODO `ebf641d`) is: a `QPushButton` parented directly
on `self._view`, positioned imperatively via `move()` (mapping a scene
point to view coordinates with `self._view.mapFromScene(...)`) rather
than added to the `QGraphicsScene` — this keeps them a constant
on-screen size regardless of zoom (a scene item would scale with the
document), matching `design-docs/widget-ux.md`'s "counter-scaled
chrome" convention for exactly this kind of overlay affordance, without
needing the extra bookkeeping of a real counter-scaled `QGraphicsItem`
for something this simple. Both use a small `"✕"` glyph (not the
platform-specific/emoji `🗑`) with a `setFixedSize` + a light "delete"
tinted stylesheet.

- `self._shape_delete_button` (item 7): visible whenever
  `current_tool == "shapes"` and `self._selected_object is not None`;
  positioned near the selected object's `sceneBoundingRect()` top-right
  corner. Click → `_delete_selected_object()`.
- `self._point_delete_button` (item 8): visible whenever
  `current_tool == "points"`, an object is selected, a point is
  selected (see below), and that object reports the point as
  deletable. Positioned just off to the side of that point. Click →
  `_delete_selected_point()`.

### A new "selected point" concept

`self._selected_point_index: int | None`, reset to `None` alongside
the other selection/handle state (`__init__`, `_rebuild_scene_from_root`,
`_on_selection_changed`, `_set_tool`). Set in `_begin_handle_drag`
(called from `_EditorView.mousePressEvent` on a successful handle hit)
when `current_tool == "points"` — this makes clicking a point handle
both start the drag (existing behavior, unchanged) and mark that point
as the selected one (new), and the selection naturally survives after
the drag ends (unlike `_dragging_handle_index`), so the delete button
stays anchored to the last point the user interacted with until they
click elsewhere, switch tools, or change the object selection.

### Per-object point deletion

Not every point-bearing object can safely lose an arbitrary point (a
`LineObject` always needs exactly its 2 endpoints). Add to `SvgObject`:

```
def can_delete_point(self, index: int) -> bool:
    return False

def delete_point(self, index: int) -> None:
    pass
```

- `LineObject`: no override (stays non-deletable — removing either
  endpoint would leave a degenerate line, not a smaller line).
- `PolylineObject`: `can_delete_point` true when more than 2 points
  remain after deletion would still leave >= 2 (i.e. `len(points) > 2`);
  `delete_point` removes it from the underlying `_PolylineItem`
  (`_PolylineItem` gets a new `remove_point(index)` mirroring its
  existing `set_point`).
- `PolygonObject`: `can_delete_point` requires more than 3 points
  (a polygon needs >= 3 vertices to remain a real polygon);
  `delete_point` rebuilds its `QPolygonF` with that index removed.
- `PathObject`: same rule as `PolylineObject`/`PolygonObject`,
  branching on `self._closed` (mirroring `_local_points`'s existing
  branch on `isinstance(self.item, QGraphicsPolygonItem)`).

`_delete_selected_point()` checks `obj.can_delete_point(index)` before
calling `obj.delete_point(index)` — belt-and-suspenders alongside the
button itself only being shown when deletion is valid, since
`_refresh_point_delete_button` and the click handler share that same
check rather than trusting the button's mere visibility.

### Wiring into the existing refresh cascade

`_refresh_handles()` (already the single place that rebuilds handle
state after a selection change, a tool switch, or a drag step) gets
two more calls at the end: `_refresh_shape_delete_button()` and
`_refresh_point_delete_button()` — so both buttons automatically track
live resizing/dragging with no extra call sites needed beyond the ones
`_refresh_handles()` already has. `_reset_view()` also calls
`_refresh_handles()` at the end (view transform changed, so any
floating button's on-screen position needs recomputing) — cheap enough
here since Reset View isn't a hot path. `_EditorView.resizeEvent`
(new override, needed anyway for TODO `ebf641d`'s Complete button) also
repositions both delete buttons after `super().resizeEvent(event)`.

### Object/point deletion mechanics

```
def _delete_selected_object(self) -> None:
    obj = self._selected_object
    if obj is None:
        return
    self._scene.removeItem(obj.item)
    self._root.remove(obj.element)
    self._objects.remove(obj)
    self._selected_object = None
    self._selected_point_index = None
    self._scene.clearSelection()
    self._refresh_handles()
    self._refresh_property_panel()

def _delete_selected_point(self) -> None:
    obj = self._selected_object
    index = self._selected_point_index
    if obj is None or index is None or not obj.can_delete_point(index):
        return
    obj.delete_point(index)
    self._selected_point_index = None
    self._refresh_handles()
```

## Verification

Extend `tests/verify/verify_svg_editor_widget.py` (following the
existing `widget.resize(...)`/`widget.show()` pattern already used by
`test_reset_view_shows_the_document_bounds` for other view-geometry-
dependent checks):

- Selecting an object in the Shapes tool shows `_shape_delete_button`;
  clicking it removes the object from the scene, `self._objects`, and
  `self._root`, and hides the button again.
- Selecting a point (via `_begin_handle_drag`, mirroring how
  `_EditorView` itself invokes it) in the Points tool on a polyline/
  polygon shows `_point_delete_button`; clicking it removes just that
  point, keeping the rest of the object intact.
- `PolylineObject`/`PolygonObject`/`PathObject`'s `can_delete_point`
  correctly refuses once at their respective minimum point count
  (2/3/2-or-3), and `_point_delete_button` is correspondingly hidden
  at that minimum even with a point "selected".
- A `LineObject`'s points are never deletable (`can_delete_point`
  always `False`), so no delete button ever appears for it in the
  Points tool.
- Switching tools or selection clears `self._selected_point_index` and
  hides both buttons appropriately.
- Full `tests/verify/` regression suite.
