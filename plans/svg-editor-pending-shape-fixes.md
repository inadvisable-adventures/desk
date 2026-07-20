# Plan: TODO ebf641d (COMPLETED) — SVG Editor pending polygon/polyline drawing fixes

Three related fixes to the multi-click (polyline/polygon/path) drawing
flow, all from direct user feedback:

4. Add a "Complete (ENTER)" button, visible only while a
   polygon/polyline is pending, at the bottom-right of the editor
   view, doing exactly what Enter already does
   (`_EditorView.keyPressEvent` → `_finish_pending()`).
5. A drawn polyline currently renders visually indistinguishable from
   a closed/filled polygon ("completed it like a polygon"). Investigate
   and fix.
6. While a polygon/polyline is pending, changing Fill/Stroke/Stroke
   width in the property panel currently edits `self._selected_object`
   — whatever was selected *before* the current draw started, not the
   shape being drawn — since a pending shape has no `SvgObject`/element
   of its own until `_finish_pending()` creates one.

## Investigation for (5)

`PolylineObject.create_default` already builds an open `_PolylineItem`
(its `_rebuild` never calls `path.closeSubpath()`, unlike a
`QGraphicsPolygonItem`), and `PolylineObject.sync_to_element` writes a
plain `points` attribute with no implied "Z" close — so the *data
model* is already correctly open, this isn't a bug in how the shape is
stored. The actual issue is purely visual: `_apply_default_style` gives
every new shape, polylines included, both a fill brush and a stroke
pen. Qt (like every real SVG renderer, per the SVG spec's own
`polyline`-filling rule) fills an *open* path as if a straight closing
segment connected the last point back to the first — the stroke has no
such closing segment, but the fill region does. The default blue fill
therefore visually closes the shape even though the underlying path
and serialized `points` stay open, which is exactly what reads as "it
completed it like a polygon."

Answer to the user's question: no, a polyline is conceptually an open,
typically unfilled shape (SVG still supports giving it an explicit
fill, and this remains fully editable via the Fill button after
creation) — but defaulting a *newly drawn* polyline to `fill="none"`
matches both the common convention (polylines are usually used for
open, stroke-only lines like a chart connector) and removes the
visual "looks closed" impression. Fix: `PolylineObject.create_default`
applies `_apply_default_style` as before (for its stroke), then
explicitly sets `item.setBrush(QBrush(Qt.BrushStyle.NoBrush))`. Loading
an existing polyline from a file (`from_element`) is unaffected — it
already respects whatever `fill` attribute (or absence of one) the
file itself declares via `_style_from_element`.

## Design

### (4) Complete (ENTER) button

`self._complete_button = QPushButton("Complete (ENTER)", parent=self._view)`,
hidden by default, `clicked.connect(self._finish_pending)`. Since it's
a floating child widget of the view rather than something placed by a
layout, it's positioned imperatively:

- `_reposition_complete_button()`: if not `has_pending_points()`, hide
  and return; otherwise `adjustSize()` then `move()` it to the view's
  own bottom-right corner (a fixed margin in from
  `self._view.width()`/`height()`), and `raise_()` so it stays above
  the viewport.
- Called from: `_add_pending_point` (a pending draw just started or
  grew), `_finish_pending`/`_cancel_pending` (pending draw just ended
  — repositioning with nothing pending just hides it), and a new
  `_EditorView.resizeEvent` override (view resized while a shape is
  pending) that calls `super().resizeEvent(event)` then
  `self._editor._reposition_complete_button()`.

### (5) Polyline default fill

As described in the Investigation section above —
`PolylineObject.create_default` only.

### (6) Pending shape style routing

Three new `SvgEditorWidget` attributes, reset alongside
`self._pending_points`:

```
self._pending_fill: str | None = None
self._pending_stroke: str | None = None
self._pending_stroke_width: float | None = None
```

`None` means "not touched during this draw — let the finished object's
own type-level default apply" (this is what makes fix (5) and fix (6)
compose correctly: an untouched pending polyline still ends up
`fill="none"`; an untouched pending polygon still gets the ordinary
default fill; explicitly touching Fill while drawing either shape
overrides that default either way).

- `_pick_fill`/`_pick_stroke`/`_on_stroke_width_changed`: check
  `self.has_pending_points()` first. If pending, read/write
  `self._pending_fill`/`_pending_stroke`/`_pending_stroke_width`
  instead of `self._selected_object`, then
  `self._refresh_property_panel()` (no change to the preview dots/
  lines themselves, which stay a fixed in-progress-indicator color as
  today — not a live WYSIWYG preview of the eventual shape's exact
  style, which is out of scope here). Otherwise, fall through to the
  existing `self._selected_object`-based behavior unchanged.
- `_refresh_property_panel`: if `has_pending_points()`, enable the
  panel and show `self._pending_fill or DEFAULT_FILL` /
  `self._pending_stroke or DEFAULT_STROKE` /
  `self._pending_stroke_width if is not None else DEFAULT_STROKE_WIDTH`
  as the swatch/spinbox values (generic placeholders when untouched,
  not attempting to predict the finished object's exact type-specific
  default) — this is also what fixes the panel being *disabled*
  outright while drawing with nothing previously selected, which is
  the other half of item 6 (there's currently no path that enables it
  during a pending draw at all). Otherwise, existing
  `self._selected_object`-based behavior unchanged.
- `_add_pending_point`: call `self._refresh_property_panel()` (in
  addition to the existing `_refresh_pending_preview()`) so the panel
  enables/updates the moment a pending draw starts.
- `_finish_pending`: capture the three pending-style values before
  clearing pending state; after `TAG_TO_CLASS[tool].create_default(points)`,
  apply each captured value that isn't `None` via
  `obj.set_fill`/`set_stroke_color`/`set_stroke_width` (overriding
  whatever `create_default` applied by default) before `_add_object`.
  Also reset the three pending-style attributes to `None` here.
  `_add_object` already re-selects the new object, which re-triggers
  `_refresh_property_panel()` via `selectionChanged` — but the early
  `len(points) < 2` return path doesn't reach `_add_object`, so call
  `self._refresh_property_panel()` explicitly on that path too.
- `_cancel_pending`: also reset the three pending-style attributes to
  `None`, and call `self._refresh_property_panel()` (falls back to
  reflecting `self._selected_object`, unchanged by a tool switch).

## Verification

Extend `tests/verify/verify_svg_editor_widget.py`:

- `_complete_button` is hidden with no pending points; becomes visible
  after the first pending point is added (polygon and polyline tools);
  clicking it produces the same finished object Enter would (same
  point count, same tag); hides again afterward.
- A freshly created `PolylineObject` (via the pending-points flow)
  has `fill="none"` in its serialized element; a freshly created
  `PolygonObject` is unaffected (still the ordinary default fill).
- With some other object selected, switching to the polygon/polyline
  tool and adding pending points, then changing Fill/Stroke/Stroke
  width via the property panel, does **not** change the
  previously-selected object — and the values are correctly applied to
  the shape once `_finish_pending()`/Enter completes it.
- The property panel is enabled (not stuck disabled) as soon as a
  pending draw starts with nothing previously selected.
- Full `tests/verify/` regression suite.
