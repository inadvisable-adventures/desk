import colorsys
import zlib

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QVBoxLayout, QLabel, QWidget

from desk.shell import current_context

POLL_INTERVAL_MS = 200
MARGIN = 12.0
MIN_TITLE_PIXELS = 50.0
VIEW_COLOR = QColor("#3daee9")


def title_color(title: str) -> QColor:
    hue = (zlib.crc32(title.encode()) % 360) / 360
    r, g, b = colorsys.hsv_to_rgb(hue, 0.45, 0.85)
    return QColor(int(r * 255), int(g * 255), int(b * 255), 190)


class _Schematic(QWidget):
    """The viewport as a rectangle, each HUD-pinned widget as a smaller
    one at its fixed on-screen position. `layout_data` is
    get_hud_layout()'s dict; a click on a pinned widget calls `on_leave`
    with its instance id."""

    def __init__(self, on_leave, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(200, 140)
        self.layout_data: dict = {"view": {"w": 1, "h": 1}, "overlays": []}
        self._on_leave = on_leave

    def scale_and_origin(self) -> tuple[float, float, float]:
        v = self.layout_data["view"]
        avail_w = max(1.0, self.width() - 2 * MARGIN)
        avail_h = max(1.0, self.height() - 2 * MARGIN)
        scale = min(avail_w / max(v["w"], 1), avail_h / max(v["h"], 1))
        return scale, MARGIN + (avail_w - v["w"] * scale) / 2, MARGIN + (avail_h - v["h"] * scale) / 2

    def overlay_rect(self, overlay: dict) -> QRectF:
        scale, ox, oy = self.scale_and_origin()
        return QRectF(ox + overlay["x"] * scale, oy + overlay["y"] * scale, overlay["w"] * scale, overlay["h"] * scale)

    def view_rect(self) -> QRectF:
        scale, ox, oy = self.scale_and_origin()
        v = self.layout_data["view"]
        return QRectF(ox, oy, v["w"] * scale, v["h"] * scale)

    def overlay_at(self, point: QPointF) -> dict | None:
        for overlay in reversed(self.layout_data["overlays"]):
            if self.overlay_rect(overlay).contains(point):
                return overlay
        return None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.color(palette.ColorRole.Base))
        painter.setPen(QPen(VIEW_COLOR, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.view_rect())
        for overlay in self.layout_data["overlays"]:
            rect = self.overlay_rect(overlay)
            painter.setBrush(title_color(overlay["title"]))
            painter.setPen(QPen(palette.color(palette.ColorRole.Mid), 1))
            painter.drawRect(rect)
            if rect.width() >= MIN_TITLE_PIXELS:
                painter.setPen(palette.color(palette.ColorRole.Text))
                painter.drawText(rect.adjusted(3, 2, -3, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, overlay["title"])
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            overlay = self.overlay_at(event.position())
            if overlay is not None:
                self._on_leave(overlay["instance_id"])


class HudManagerWidget(QWidget):
    """TODO 93f79ca (HUD render mode, desk.shell.hud): a schematic of the
    viewport with every HUD-pinned widget at its fixed on-screen position;
    click one to return it to normal scene placement. The safety valve for
    HUD mode -- a pinned widget no longer sits among the scene-placed ones,
    so this is where to find and undo it. Talks to the main window directly
    (get_main_window(), as the Minimap does); polls only while visible."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._schematic = _Schematic(self._leave)
        self._hint = QLabel()
        self._hint.setWordWrap(True)
        self._hint.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout = QVBoxLayout(self)
        layout.addWidget(self._schematic, stretch=1)
        layout.addWidget(self._hint)
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start()
        self.refresh()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _window(self):
        return current_context.get_main_window()

    def refresh(self) -> None:
        window = self._window()
        if window is None:
            return
        layout = window.get_hud_layout()
        if layout != self._schematic.layout_data:
            self._schematic.layout_data = layout
            self._schematic.update()
        count = len(layout["overlays"])
        self._hint.setText(
            "Click a pinned widget to return it to the canvas." if count else "No widgets are pinned to the viewport."
        )

    def _leave(self, instance_id: str) -> None:
        window = self._window()
        if window is not None:
            window.leave_hud(instance_id)
            self.refresh()


def build() -> QWidget:
    return HudManagerWidget()
