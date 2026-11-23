"""Mapping a point inside widget content embedded in the Workspace
Canvas (via `QGraphicsProxyWidget`) to the real on-screen global
position a `Qt.WindowType.Popup`-style window (a `QMenu`, in
particular) needs to open at.

This is the same "proxy -> scene -> view" chain `PaintedComboBox`'s own
popup already uses (`_screen_rect_and_scale` in `painted_combo.py`),
generalized from "this control's own rect" to an arbitrary point --
for a popup that opens from a point inside a control's content (a
right-click position inside a list, say) rather than anchored to the
whole control. See `python-widget-conventions.md`'s "Popups from
embedded widgets" for why plain `mapToGlobal` is wrong here: the canvas
can be panned and zoomed, and `mapToGlobal` knows nothing about that
transform, so it lands a popup a constant offset away from the actual
click once the view isn't at its default pan/zoom.

A `QMenu` itself needs no custom painting the way `PaintedComboBox`
does -- it already renders as a real, separate, unscaled top-level OS
window (same as `_ComboPopup`/`WidgetSpawnMenu`), so the "native style
desyncs under a non-1.0 scale" half of this package's own problem
doesn't apply to it. Only its *position* does, and only when it is
opened from code running inside embedded content.
"""
from PyQt6.QtCore import QPoint, QPointF
from PyQt6.QtWidgets import QGraphicsView, QWidget


def canvas_popup_point(widget: QWidget, local: QPoint) -> QPoint:
    """`local` is a position in `widget`'s own coordinates (e.g. a
    `customContextMenuRequested` signal's own point). Returns the real
    global screen point to open a popup at that same spot, accounting
    for the canvas's pan/zoom when `widget` is embedded there via a
    `QGraphicsProxyWidget`. Falls back to a plain `mapToGlobal` when it
    isn't (no real `QGraphicsView` found -- a headless/offscreen test,
    or a widget used outside the canvas entirely)."""
    frame = widget.window()
    proxy = frame.graphicsProxyWidget() if frame is not None else None
    scene = proxy.scene() if proxy is not None else None
    views = scene.views() if scene is not None else []
    if not views:
        return widget.mapToGlobal(local)
    view: QGraphicsView = views[0]
    scene_pt = proxy.mapToScene(QPointF(widget.mapTo(frame, local)))
    return view.viewport().mapToGlobal(view.mapFromScene(scene_pt))
