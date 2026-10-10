import colorsys
import zlib

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from desk.shell import current_context
from desk.shell.event_broker import EventSubscription
from desk.widget_overview import WIDGET_OVERVIEW_CHANGED_EVENT

POLL_INTERVAL_MS = 150
MARGIN = 10.0
MIN_TITLE_PIXELS = 60.0
STALE_COLOR = QColor("#e8a33d")
VIEW_COLOR = QColor("#3daee9")


def kind_color(kind: str) -> QColor:
    """A stable tint per widget kind."""
    hue = (zlib.crc32(kind.encode()) % 360) / 360
    r, g, b = colorsys.hsv_to_rgb(hue, 0.45, 0.85)
    return QColor(int(r * 255), int(g * 255), int(b * 255), 170)


class _MapView(QWidget):
    """The scaled-down map. `layout` is get_canvas_layout()'s dict; the
    fit transform is a uniform scale of the union of every widget and the
    viewport into this widget minus a margin (see `transform`)."""

    def __init__(self, on_pan, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(160, 120)
        self.layout_data: dict = {"frames": [], "view": {"x": 0, "y": 0, "w": 1, "h": 1}, "can_undo": False}
        self._on_pan = on_pan

    def bounds(self) -> QRectF:
        rects = [QRectF(f["x"], f["y"], f["w"], f["h"]) for f in self.layout_data["frames"]]
        v = self.layout_data["view"]
        rects.append(QRectF(v["x"], v["y"], v["w"], v["h"]))
        union = rects[0]
        for r in rects[1:]:
            union = union.united(r)
        return union

    def transform(self) -> tuple[float, float, float]:
        """(scale, offset_x, offset_y): map = (scene - bounds.topLeft) * scale + offset."""
        b = self.bounds()
        avail_w = max(1.0, self.width() - 2 * MARGIN)
        avail_h = max(1.0, self.height() - 2 * MARGIN)
        scale = min(avail_w / max(b.width(), 1.0), avail_h / max(b.height(), 1.0))
        return scale, MARGIN + (avail_w - b.width() * scale) / 2, MARGIN + (avail_h - b.height() * scale) / 2

    def to_map(self, x: float, y: float) -> QPointF:
        b = self.bounds()
        scale, ox, oy = self.transform()
        return QPointF((x - b.left()) * scale + ox, (y - b.top()) * scale + oy)

    def to_scene(self, point: QPointF) -> tuple[float, float]:
        b = self.bounds()
        scale, ox, oy = self.transform()
        return (point.x() - ox) / scale + b.left(), (point.y() - oy) / scale + b.top()

    def map_rect(self, x: float, y: float, w: float, h: float) -> QRectF:
        top_left = self.to_map(x, y)
        scale = self.transform()[0]
        return QRectF(top_left.x(), top_left.y(), w * scale, h * scale)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.color(palette.ColorRole.Base))
        for f in self.layout_data["frames"]:
            rect = self.map_rect(f["x"], f["y"], f["w"], f["h"])
            painter.setBrush(kind_color(f["kind"]))
            painter.setPen(QPen(STALE_COLOR if f.get("stale") else palette.color(palette.ColorRole.Mid), 2 if f.get("stale") else 1))
            painter.drawRect(rect)
            if rect.width() >= MIN_TITLE_PIXELS:
                painter.setPen(palette.color(palette.ColorRole.Text))
                painter.drawText(rect.adjusted(3, 2, -3, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, f.get("title", ""))
        v = self.layout_data["view"]
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(VIEW_COLOR, 2))
        painter.drawRect(self.map_rect(v["x"], v["y"], v["w"], v["h"]))
        painter.end()

    def _pan_from(self, event) -> None:
        self._on_pan(*self.to_scene(event.position()))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pan_from(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._pan_from(event)


class MinimapWidget(QWidget):
    """A scaled-down live map of the canvas (TODO 669b690): click/drag to
    pan, plus Organize by type / Nudge apart / Tile / Undo. Talks to the
    main window directly (get_main_window(), as desk_proc_runner does);
    polls its layout only while visible (positions and the viewport change
    with no signals) and also refreshes on the overview event. See
    plans/minimap-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._subscription: EventSubscription | None = None
        self._map = _MapView(self._pan_to)

        self._organize_button = QPushButton("Organize by type")
        self._organize_button.clicked.connect(lambda: self._arrange("organize"))
        self._nudge_button = QPushButton("Nudge apart")
        self._nudge_button.clicked.connect(lambda: self._arrange("nudge"))
        self._tile_button = QPushButton("Tile")
        self._tile_button.clicked.connect(lambda: self._arrange("tile"))
        self._undo_button = QPushButton("Undo")
        self._undo_button.clicked.connect(self._undo)
        self._undo_button.setEnabled(False)

        buttons = QHBoxLayout()
        for button in (self._organize_button, self._nudge_button, self._tile_button, self._undo_button):
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(self._map, stretch=1)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def bind_event_mediator(self, instance_id: str, mediator) -> None:
        self._subscription = EventSubscription(mediator, instance_id, names=[WIDGET_OVERVIEW_CHANGED_EVENT], parent=self)
        self._subscription.message_received.connect(lambda *_: self.refresh())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start()
        self.refresh()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _window(self):
        return current_context.get_main_window()

    def hud_trigger(self):
        """TODO 1ce5130 (HUD render mode, desk.shell.hud): a press on the
        map pins it fixed to the viewport, so a drag-to-pan tracks 1:1
        instead of the map sliding away under the pointer as the canvas
        (and this frame with it) pans. The buttons are deliberately not
        part of it."""
        return self._map

    def refresh(self) -> None:
        window = self._window()
        if window is None:
            return
        layout = window.get_canvas_layout()
        if layout != self._map.layout_data:
            self._map.layout_data = layout
            self._map.update()
        self._undo_button.setEnabled(bool(layout.get("can_undo")))

    def _pan_to(self, x: float, y: float) -> None:
        window = self._window()
        if window is not None:
            window.pan_canvas_to(x, y)

    def _arrange(self, mode: str) -> None:
        window = self._window()
        if window is not None:
            window.arrange_canvas(mode)
            self.refresh()

    def _undo(self) -> None:
        window = self._window()
        if window is not None:
            window.undo_canvas_arrangement()
            self.refresh()


def build() -> QWidget:
    return MinimapWidget()
