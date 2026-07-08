# Fix hover UI (Desk picker / zoom control) drifting on zoom/pan (COMPLETED)

## Summary

TODO 82d66c0: the top-left Desk picker and bottom-right zoom control
are meant to stay pinned to the app window's corners, in screen space,
"no matter the zoom level, scroll/pan, or window-resize." TODO 4adfcad/
TODO 1f9bd34 already fixed the window-*resize* case. This item reports
the same class of drift still happening for zoom and pan/scroll — and
directly reproducing it confirms that's real: panning the view (e.g.
`centerOn(...)`, the same call `set_view_state`/a real click-drag pan
both exercise) drifted the Desk picker from `(12, 12)` all the way to
`(-535, -816)` — clear off-screen — and `zoom_to_fit`/`reset_zoom`
(zoom operations that re-center the view) reproduced the identical
drift.

## Root cause (more precise than the earlier fixes' theory)

The earlier fixes (see `plans/fix-desk-picker-positioning.md`/
`plans/fix-zoom-control-positioning.md`) attributed the resize-time
drift to a vaguely-described "recurring internal Qt layout pass,
plausibly `QGraphicsView`'s own scrollbar/viewport geometry
recalculation," fixed generically by reasserting position after the
fact rather than identifying the actual mechanism.

Instrumenting `WorkspaceView.scrollContentsBy` (the `QAbstractScrollArea`
virtual Qt calls whenever the viewport's visible content shifts)
confirms the actual mechanism directly: `QAbstractScrollArea` (which
`QGraphicsView` is) uses `QWidget.scroll(dx, dy)` as a fast-scroll
optimization for its viewport, and — per `QWidget.scroll`'s own
documented behavior — **scrolling a widget also moves any of its child
widgets whose geometry is fully inside the scrolled area, by the same
delta**. The Desk picker and zoom control are plain, manually-`.move()`d
`QWidget` children of `self.viewport()` (not scene items), so *any*
operation that shifts the view's scroll position moves them right along
with it, silently, via this Qt-internal fast path. Confirmed directly:

- Simple panning (`centerOn`) fires `scrollContentsBy` with large
  nonzero deltas and drifts both HUD widgets by exactly that delta.
- `zoom_to_fit`/`reset_zoom` (both re-center the view as part of
  changing scale) fire it too, with the same resulting drift — this is
  the "zoom level" case from the TODO's wording.
- The very first resize/show already fires `scrollContentsBy` several
  times with nonzero deltas (the infinite scene rect means resizing the
  viewport changes how far it needs to scroll to keep the same content
  centered) — meaning this is *also* very likely the real, previously
  -unidentified mechanism behind TODO 4adfcad/TODO 1f9bd34's resize-time
  drift, not a separate, vaguer "layout pass."

This is a far more precise and directly-actionable finding than the
previous "reassert after the fact, don't worry why" approach — it means
the fix can hook the exact Qt callback responsible, rather than
reasserting on every plausible trigger site individually (which would
otherwise mean separately patching pan, wheel-zoom, pinch-zoom,
`zoom_to_fit`, and `reset_zoom`).

## Design

Override `WorkspaceView.scrollContentsBy(self, dx, dy)`: call
`super().scrollContentsBy(dx, dy)` (required — this is what actually
performs the scroll), then reassert both HUD widgets' positions via the
existing `_position_desk_picker()`/`_position_zoom_control()` methods.

Must guard against firing before `self.desk_picker`/`self.zoom_control`
exist yet: confirmed directly that `QGraphicsView.__init__` itself can
invoke `scrollContentsBy` during its own internal setup, which in
`WorkspaceView.__init__` runs *before* the Desk picker/zoom control are
constructed — an unguarded override crashes with `AttributeError`
immediately on construction. Guard with `hasattr` (both attributes are
set unconditionally, once, right after `super().__init__()` in the
existing constructor, so a plain existence check is sufficient — no
separate "am I initialized" flag needed).

Confirmed directly that reasserting *synchronously* inside
`scrollContentsBy` (unlike `resizeEvent`, where a synchronous
reassertion was confirmed too early and needed `QTimer.singleShot(0,
...)` deferral) sticks correctly with no further drift — `scrollContentsBy`
is the actual mechanism doing the moving, not a step ahead of some later
pass, so there's nothing further to be preempted by. The existing
`resizeEvent` + deferred-`singleShot` fix for TODO 4adfcad/TODO 1f9bd34
is left untouched (it's still needed regardless: the zoom control's
target *x*/*y* depend on the viewport's current width/height, so a
resize still needs its own recompute, and there's no reason to risk the
already-working, separately-verified fix while addressing a different
trigger).

## Affected files

- `src/desk/shell/canvas.py` — add `WorkspaceView.scrollContentsBy`.

## Verification

Entirely headless, using a real, `.show()`n `WorkspaceView` (matching
the existing positioning plans' approach):

1. Reproduce the bug directly against the unfixed code: confirm
   panning (`centerOn`) and `zoom_to_fit`/`reset_zoom` each drift the
   Desk picker away from `(12, 12)`.
2. Apply the fix; confirm the Desk picker stays at `(12, 12)` and the
   zoom control stays at its correct bottom-right position after
   panning, after `zoom_to_fit`, after `reset_zoom`, and after wheel
   -zoom (`_apply_zoom`).
3. Regression: confirm the existing resize-time fix (TODO 4adfcad/TODO
   1f9bd34) still works — both HUD widgets correctly positioned after
   first `.show()` and after a subsequent explicit resize.
4. Regression: confirm widget drag/resize interaction and a real Desk
   switch (`clear_widgets()`/`set_view_state()`) are unaffected.

## Status

Implemented and verified, entirely headlessly (real, `.show()`n
`WorkspaceView`):

1. Confirmed correct positioning of both HUD widgets after initial
   show/resize (regression, pre-existing fix).
2. Confirmed both stay pinned after panning (`centerOn`), including a
   second, larger pan.
3. Confirmed both stay pinned after `zoom_to_fit` and `reset_zoom`.
4. Confirmed the Desk picker stays pinned after wheel-style zoom
   (`_apply_zoom`).
5. Regression: a subsequent explicit resize still repositions both
   correctly.
6. Regression: widget proxy positioning (`moveBy`) unaffected.
