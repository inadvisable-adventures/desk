"""HUD render mode (TODO 9ae13c0, plans/hud-render-mode.md).

A `kind: "python"` widget can pin a declared sub-region of itself fixed to
the *viewport* instead of the scene, so a control whose job is to pan the
canvas (the Minimap) doesn't slide out from under its own pointer. This is
a render/input mode of the shell, not a new widget kind: the widget stays in
its ordinary scene frame (same instance, same state, never reparented) and
the shell paints a live copy of the region in a `HudOverlay` -- a plain
child of the view's viewport, the same kind of thing the zoom control and
Desk picker are -- and forwards mouse events on the overlay to the real
region widget.

A widget opts in two ways:
- declaratively: a `hud_trigger()` method returning the sub-widget whose
  presses should enter HUD mode (decided before the gesture starts, so the
  very first press is routed to the HUD presentation -- see
  `HudController.trigger_press`);
- programmatically: `current_context.get_hud_controller().enter(region)`.
Either way the widget stays pinned until it is returned, by the widget
(`leave`), by the overlay's right-click "Return to canvas", or by the HUD
manager widget. HUD state is runtime-only; it is not saved in the `.desk`.
"""
import logging
import weakref

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from desk.shell.widget_frame import WidgetFrame

logger = logging.getLogger(__name__)

DEFAULT_OPACITY = 0.5
SYNC_INTERVAL_MS = 100
BORDER_COLOR = QColor("#3daee9")
_FORWARDED_BUTTONS = (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton)


def _frame_of(widget: QWidget) -> WidgetFrame | None:
    while widget is not None and not isinstance(widget, WidgetFrame):
        widget = widget.parentWidget()
    return widget


class HudOverlay(QWidget):
    """A viewport-fixed, live, scaled copy of `region` that forwards mouse
    events to it. Sized at the on-screen size the region had when it
    entered HUD mode (`scale` is the view's zoom at that moment) and kept
    that size however the view zooms afterwards."""

    def __init__(self, controller: "HudController", frame: WidgetFrame, region: QWidget, scale: float, opacity: float, parent: QWidget) -> None:
        super().__init__(parent)
        self.controller = controller
        self.frame = frame
        self.region = region
        self.scale_factor = scale or 1.0
        self.opacity = opacity
        self.anchor = QPoint(0, 0)
        self.setMouseTracking(False)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._grabbing = False
        self.sync_size()

    def sync_size(self) -> None:
        size = QSize(
            max(1, round(self.region.width() * self.scale_factor)),
            max(1, round(self.region.height() * self.scale_factor)),
        )
        if size != self.size():
            self.resize(size)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setOpacity(self.opacity)
        painter.save()
        painter.scale(self.scale_factor, self.scale_factor)
        self.region.render(painter)
        painter.restore()
        painter.setPen(QPen(BORDER_COLOR, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()

    def forward_mouse(self, event_type, position: QPointF, button, buttons, modifiers, global_position: QPointF) -> None:
        """Sends a mouse event to the real region at the matching local
        point (the overlay shows the region scaled by scale_factor)."""
        local = QPointF(position.x() / self.scale_factor, position.y() / self.scale_factor)
        QApplication.sendEvent(self.region, QMouseEvent(event_type, local, global_position, button, buttons, modifiers))

    def _forward(self, event) -> None:
        self.forward_mouse(event.type(), event.position(), event.button(), event.buttons(), event.modifiers(), event.globalPosition())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.show_menu(event.globalPosition().toPoint())
        elif event.button() in _FORWARDED_BUTTONS:
            self._grabbing = True
            self._forward(event)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        self.mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._grabbing:
            self._forward(event)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._grabbing and event.button() in _FORWARDED_BUTTONS:
            self._grabbing = False
            self._forward(event)
        event.accept()

    def wheelEvent(self, event) -> None:
        # Swallowed: a wheel over a HUD must not zoom whatever is behind it.
        event.accept()

    def show_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction("Return to canvas", lambda: self.controller.leave(self.frame))
        menu.exec(global_pos)


class HudController(QObject):
    """Owns every HUD overlay of one WorkspaceView (one per pinned frame)."""

    changed = pyqtSignal()

    def __init__(self, view) -> None:
        super().__init__(view)
        # A weak reference: a strong one makes a view <-> controller cycle,
        # so a discarded WorkspaceView would linger (shown, stealing focus)
        # until the cyclic GC ran -- confirmed to break the focus tests.
        self._view_ref = weakref.ref(view)
        self._overlays: dict[WidgetFrame, HudOverlay] = {}
        # The overlay a scene-originated press was routed to: until the
        # button comes up the *view* still receives the moves/release (it
        # got the press), and forwards them here.
        self.active_press: HudOverlay | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(SYNC_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    @property
    def _view(self):
        return self._view_ref()

    # -- queries ------------------------------------------------------

    def is_pinned(self, widget: QWidget) -> bool:
        frame = widget if isinstance(widget, WidgetFrame) else _frame_of(widget)
        return frame in self._overlays

    def overlay_for(self, widget: QWidget) -> HudOverlay | None:
        frame = widget if isinstance(widget, WidgetFrame) else _frame_of(widget)
        return self._overlays.get(frame)

    def entries(self) -> list[dict]:
        """Each pinned widget's fixed on-screen rect (viewport pixels)."""
        return [
            {
                "instance_id": frame.instance_id,
                "title": frame.title,
                "x": overlay.x(),
                "y": overlay.y(),
                "w": overlay.width(),
                "h": overlay.height(),
            }
            for frame, overlay in self._overlays.items()
        ]

    # -- enter / leave ------------------------------------------------

    def enter(self, region: QWidget, opacity: float = DEFAULT_OPACITY) -> HudOverlay | None:
        """Pins `region` (a descendant of a placed widget's frame) to the
        viewport, exactly where it is on screen now. Returns the overlay,
        or None if the region isn't inside a placed frame. A second call
        for an already-pinned frame returns the existing overlay."""
        frame = _frame_of(region)
        proxy = frame.graphicsProxyWidget() if frame is not None else None
        if frame is None or proxy is None:
            return None
        existing = self._overlays.get(frame)
        if existing is not None:
            return existing
        scale = self._view._scale
        scene_pos = proxy.mapToScene(QPointF(region.mapTo(frame, QPoint(0, 0))))
        overlay = HudOverlay(self, frame, region, scale, opacity, self._view.viewport())
        overlay.anchor = self._view.mapFromScene(scene_pos)
        self._overlays[frame] = overlay
        frame.set_hud_pinned(True)
        region.destroyed.connect(lambda *_: self.leave(frame))
        self.reposition()
        overlay.show()
        overlay.raise_()
        self._timer.start()
        self.changed.emit()
        return overlay

    def leave(self, widget: QWidget) -> bool:
        """Returns the widget to normal scene placement. False if it
        wasn't pinned."""
        frame = widget if isinstance(widget, WidgetFrame) else _frame_of(widget)
        overlay = self._overlays.pop(frame, None)
        if overlay is None:
            return False
        if self.active_press is overlay:
            self.active_press = None
        if not sip.isdeleted(frame):
            frame.set_hud_pinned(False)
        overlay.hide()
        overlay.deleteLater()
        if not self._overlays:
            self._timer.stop()
        self.changed.emit()
        return True

    def leave_instance(self, instance_id: str) -> bool:
        for frame in list(self._overlays):
            if frame.instance_id == instance_id:
                return self.leave(frame)
        return False

    def clear(self) -> None:
        for frame in list(self._overlays):
            self.leave(frame)

    # -- layout -------------------------------------------------------

    def reposition(self) -> None:
        """Re-asserts each overlay's fixed position: QWidget.scroll() (how
        QGraphicsView pans) moves viewport children by the scroll delta
        (TODO 82d66c0), which would drag a HUD along with the canvas --
        exactly what HUD mode exists to prevent. Also keeps one inside the
        viewport after a resize."""
        viewport = self._view.viewport()
        for overlay in self._overlays.values():
            x = min(max(0, overlay.anchor.x()), max(0, viewport.width() - overlay.width()))
            y = min(max(0, overlay.anchor.y()), max(0, viewport.height() - overlay.height()))
            overlay.anchor = QPoint(x, y)
            overlay.move(overlay.anchor)

    def _tick(self) -> None:
        for frame, overlay in list(self._overlays.items()):
            if sip.isdeleted(overlay.region):
                self.leave(frame)
                continue
            overlay.sync_size()
            overlay.update()
        self.reposition()

    # -- the mode-entry trigger ---------------------------------------

    def trigger_press(self, view_pos: QPointF, event) -> bool:
        """Called by the view for a left press that landed in a placed
        widget's own content (not chrome). If it landed in the widget's
        declared `hud_trigger()` region, enters HUD mode and routes the
        press to the new overlay (True: handled). A press in the in-scene
        copy of a region that is already pinned is swallowed -- panning
        against the sliding copy is the very bug this fixes."""
        frame = self._view._frame_at(view_pos)
        if frame is None:
            return False
        region = self._declared_region(frame)
        if region is None:
            return False
        proxy = frame.graphicsProxyWidget()
        local = proxy.mapFromScene(self._view.mapToScene(view_pos.toPoint())).toPoint()
        if not region.rect().contains(region.mapFrom(frame, local)):
            return False
        overlay = self._overlays.get(frame)
        if overlay is not None:
            return True
        overlay = self.enter(region)
        if overlay is None:
            return False
        self.active_press = overlay
        overlay.forward_mouse(
            event.type(), view_pos - QPointF(overlay.pos()), event.button(), event.buttons(), event.modifiers(), event.globalPosition()
        )
        overlay._grabbing = True
        return True

    @staticmethod
    def _declared_region(frame: WidgetFrame) -> QWidget | None:
        host = getattr(frame, "content", None)
        widget = getattr(host, "current", None)
        hook = getattr(widget, "hud_trigger", None)
        if not callable(hook):
            return None
        try:
            region = hook()
        except Exception:
            logger.error("hud_trigger() failed on a widget", exc_info=True)
            return None
        if region is None or sip.isdeleted(region) or not region.isVisible():
            return None
        return region

    def forward_view_event(self, event) -> bool:
        """The view's own move/release while a scene-originated press is
        being routed to an overlay (see active_press). True if consumed."""
        overlay = self.active_press
        if overlay is None:
            return False
        overlay.forward_mouse(
            event.type(), event.position() - QPointF(overlay.pos()), event.button(), event.buttons(), event.modifiers(), event.globalPosition()
        )
        if event.type() == QEvent.Type.MouseButtonRelease:
            overlay._grabbing = False
            self.active_press = None
        return True
