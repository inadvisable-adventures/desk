"""A desk area's scene item (TODO 0460b4c).

An area is a named rectangle drawn on the canvas background, behind every
widget. It is a plain `QGraphicsObject`, not a widget frame: only its
chrome (the title strip, which holds the eye button, and a thin band along
the border for resizing) is part of its `shape()`, so the interior is
click-through by construction -- clicks, drags and scrolls there reach the
canvas background and any widget sitting on top, never the area. The
chrome is sized in *screen* pixels (divided by the view scale) so it stays
usable and readable when the canvas is zoomed far out, which is where areas
are most useful.

The item owns no persistent state: `DeskWindow` creates it from an
`AreaState`, listens to `geometry_changed` to write user edits back, and
pushes programmatic edits in through `set_geometry`/`set_title`.
"""
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QCursor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsObject,
    QGraphicsProxyWidget,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QLineEdit,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

# Far below any widget frame: frames start near 0 and send_to_back only ever
# goes one below the lowest *frame*, so this can never be reached.
AREA_Z = -1_000_000_000.0
TITLE_STRIP_PX = 26.0
BORDER_BAND_PX = 7.0
BORDER_PX = 2.0
MIN_AREA_SIZE = 80.0  # scene units, so an area can't be dragged to nothing
EYE_PAD_PX = 4.0

_LEFT, _RIGHT, _TOP, _BOTTOM = "l", "r", "t", "b"


class AreaItem(QGraphicsObject):
    # Emitted once at the end of a user move/resize: (area_id, x, y, w, h).
    geometry_changed = pyqtSignal(str, float, float, float, float)
    view_requested = pyqtSignal(str)
    title_edited = pyqtSignal(str, str)  # area_id, new title: an inline edit committed
    delete_requested = pyqtSignal(str)

    def __init__(self, area_id: str, title: str, x: float, y: float, width: float, height: float) -> None:
        super().__init__()
        self.area_id = area_id
        self._title = title
        self._width = max(MIN_AREA_SIZE, width)
        self._height = max(MIN_AREA_SIZE, height)
        self._view_scale = 1.0
        self._drag_mode: str | None = None  # "move" or "resize"
        self._drag_edges: set[str] = set()
        self._drag_start_scene = QPointF()
        self._drag_start_rect = QRectF()
        self._eye_pressed = False
        self._press_in_title = False
        self._editor: QLineEdit | None = None
        self._editor_proxy: QGraphicsProxyWidget | None = None
        self.setPos(x, y)
        self.setZValue(AREA_Z)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)

    # -- geometry ---------------------------------------------------------

    @property
    def title(self) -> str:
        return self._title

    def scene_rect(self) -> QRectF:
        return QRectF(self.pos().x(), self.pos().y(), self._width, self._height)

    def set_title(self, title: str) -> None:
        self._title = title
        self.update()

    def set_geometry(self, x: float, y: float, width: float, height: float) -> None:
        self.prepareGeometryChange()
        self._width = max(MIN_AREA_SIZE, width)
        self._height = max(MIN_AREA_SIZE, height)
        self.setPos(x, y)
        self.update()

    def set_view_scale(self, scale: float) -> None:
        if scale <= 0 or scale == self._view_scale:
            return
        self._finish_edit(commit=True)  # the editor is laid out for one scale
        self.prepareGeometryChange()
        self._view_scale = scale
        self.update()

    def _px(self, pixels: float) -> float:
        return pixels / self._view_scale

    def _strip_height(self) -> float:
        return min(self._px(TITLE_STRIP_PX), self._height / 2)

    def _title_strip(self) -> QRectF:
        return QRectF(0, 0, self._width, self._strip_height())

    def _eye_rect(self) -> QRectF:
        strip = self._strip_height()
        pad = min(self._px(EYE_PAD_PX), strip / 4)
        side = strip - 2 * pad
        return QRectF(self._width - pad - side, pad, side, side)

    def _border_bands(self) -> list[QRectF]:
        b = self._px(BORDER_BAND_PX)
        w, h = self._width, self._height
        return [QRectF(0, 0, b, h), QRectF(w - b, 0, b, h), QRectF(0, 0, w, b), QRectF(0, h - b, w, b)]

    def boundingRect(self) -> QRectF:
        pad = self._px(BORDER_PX)
        return QRectF(-pad, -pad, self._width + 2 * pad, self._height + 2 * pad)

    def shape(self) -> QPainterPath:
        """Chrome only -- the interior is deliberately absent so it never
        takes part in hit-testing."""
        path = QPainterPath()
        # Winding, not the default odd-even: the strip overlaps the border
        # bands, and odd-even would cut those overlaps out of the shape.
        path.setFillRule(Qt.FillRule.WindingFill)
        path.addRect(self._title_strip())
        for band in self._border_bands():
            path.addRect(band)
        return path

    # -- painting ---------------------------------------------------------

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        palette = QApplication.palette()
        accent = palette.highlight().color()
        text_color = palette.windowText().color()
        rect = QRectF(0, 0, self._width, self._height)

        fill = QColor(accent)
        fill.setAlpha(22)
        painter.fillRect(rect, fill)
        border = QColor(accent)
        border.setAlpha(150)
        pen = QPen(border, self._px(BORDER_PX))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

        strip = self._title_strip()
        strip_fill = QColor(accent)
        strip_fill.setAlpha(60)
        painter.fillRect(strip, strip_fill)

        eye = self._eye_rect()
        # Text is laid out in screen pixels: scale the painter back up by
        # the view scale so the font is an ordinary pixel-sized one.
        k = self._view_scale
        painter.save()
        painter.scale(1.0 / k, 1.0 / k)
        font = QFont(painter.font())
        font.setPixelSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_color)
        pad_px = 8.0
        avail_px = max(0.0, (eye.left() - self._px(pad_px)) * k - pad_px)
        text_rect = QRectF(pad_px, 0, avail_px, strip.height() * k)
        elided = QFontMetricsF(font).elidedText(self._title or "(untitled area)", Qt.TextElideMode.ElideRight, avail_px)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), elided)
        painter.restore()

        self._paint_eye(painter, eye, text_color)

    def _paint_eye(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._eye_pressed:
            hover = QColor(color)
            hover.setAlpha(60)
            painter.fillRect(rect, hover)
        pen = QPen(color, self._px(1.6))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        center = rect.center()
        lens = QRectF(0, 0, rect.width() * 0.8, rect.height() * 0.5)
        lens.moveCenter(center)
        painter.drawEllipse(lens)
        pupil = rect.width() * 0.2
        painter.setBrush(QBrush(color))
        painter.drawEllipse(center, pupil / 2, pupil / 2)
        painter.restore()

    # -- interaction ------------------------------------------------------

    def _edges_at(self, pos: QPointF) -> set[str]:
        """Which border edges a local position is within the grab band of
        (two for a corner), excluding the title strip's interior so a title
        drag is a move, not a resize -- except along the very top edge."""
        b = self._px(BORDER_BAND_PX)
        edges = set()
        if pos.x() <= b:
            edges.add(_LEFT)
        elif pos.x() >= self._width - b:
            edges.add(_RIGHT)
        if pos.y() <= b:
            edges.add(_TOP)
        elif pos.y() >= self._height - b:
            edges.add(_BOTTOM)
        return edges

    def _cursor_for(self, pos: QPointF) -> Qt.CursorShape:
        if self._eye_rect().contains(pos):
            return Qt.CursorShape.PointingHandCursor
        edges = self._edges_at(pos)
        if edges in ({_LEFT, _TOP}, {_RIGHT, _BOTTOM}):
            return Qt.CursorShape.SizeFDiagCursor
        if edges in ({_RIGHT, _TOP}, {_LEFT, _BOTTOM}):
            return Qt.CursorShape.SizeBDiagCursor
        if edges & {_LEFT, _RIGHT}:
            return Qt.CursorShape.SizeHorCursor
        if edges & {_TOP, _BOTTOM}:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.OpenHandCursor

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self.setCursor(QCursor(self._cursor_for(event.pos())))

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        pos = event.pos()
        if self._eye_rect().contains(pos):
            self._eye_pressed = True
            self.update()
            event.accept()
            return
        edges = self._edges_at(pos)
        self._press_in_title = not edges and self._title_strip().contains(pos)
        self._drag_start_scene = event.scenePos()
        self._drag_start_rect = self.scene_rect()
        if edges:
            self._drag_mode, self._drag_edges = "resize", edges
        else:
            self._drag_mode, self._drag_edges = "move", set()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._drag_mode is None:
            event.ignore()
            return
        delta = event.scenePos() - self._drag_start_scene
        r = QRectF(self._drag_start_rect)
        if self._drag_mode == "move":
            r.translate(delta.x(), delta.y())
        else:
            if _LEFT in self._drag_edges:
                r.setLeft(min(r.left() + delta.x(), r.right() - MIN_AREA_SIZE))
            if _RIGHT in self._drag_edges:
                r.setRight(max(r.right() + delta.x(), r.left() + MIN_AREA_SIZE))
            if _TOP in self._drag_edges:
                r.setTop(min(r.top() + delta.y(), r.bottom() - MIN_AREA_SIZE))
            if _BOTTOM in self._drag_edges:
                r.setBottom(max(r.bottom() + delta.y(), r.top() + MIN_AREA_SIZE))
        self.set_geometry(r.x(), r.y(), r.width(), r.height())
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._eye_pressed:
            self._eye_pressed = False
            self.update()
            if self._eye_rect().contains(event.pos()):
                self.view_requested.emit(self.area_id)
            event.accept()
            return
        if self._drag_mode is not None:
            moved = self.scene_rect() != self._drag_start_rect
            was_title_click = self._drag_mode == "move" and not moved and self._press_in_title
            self._drag_mode = None
            self._drag_edges = set()
            if moved:
                r = self.scene_rect()
                self.geometry_changed.emit(self.area_id, r.x(), r.y(), r.width(), r.height())
            elif was_title_click:
                self.begin_edit()
            event.accept()
            return
        event.ignore()

    # -- inline title editing ------------------------------------------

    def begin_edit(self) -> None:
        """Replaces the title text with a line edit (a click on the title, or
        "Rename…"). Enter or focus loss commits, Escape cancels."""
        if self._editor is not None:
            return
        k = self._view_scale
        strip_px = self._strip_height() * k
        eye = self._eye_rect()
        edit = _TitleEdit(self._title)
        edit.setFixedSize(max(60, int(eye.left() * k) - 12), max(16, int(strip_px) - 4))
        edit.editingFinished.connect(lambda: self._finish_edit(commit=True))
        edit.cancelled.connect(lambda: self._finish_edit(commit=False))
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(edit)
        proxy.setScale(1.0 / k)
        proxy.setPos(self._px(6), self._px(2))
        self._editor, self._editor_proxy = edit, proxy
        edit.selectAll()
        edit.setFocus()
        proxy.setFocus()

    def _finish_edit(self, commit: bool) -> None:
        edit, proxy = self._editor, self._editor_proxy
        if edit is None:
            return
        self._editor = self._editor_proxy = None
        text = edit.text().strip()
        if commit and text and text != self._title:
            self.set_title(text)
            self.title_edited.emit(self.area_id, text)

        def _dispose() -> None:
            if proxy.scene() is not None:
                proxy.scene().removeItem(proxy)
            proxy.deleteLater()

        # Deferred: this can run from inside the editor's own signal.
        QTimer.singleShot(0, _dispose)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        menu = QMenu()
        view = menu.addAction("View area")
        rename = menu.addAction("Rename…")
        delete = menu.addAction("Delete area")
        chosen = menu.exec(event.screenPos())
        if chosen is view:
            self.view_requested.emit(self.area_id)
        elif chosen is rename:
            self.begin_edit()
        elif chosen is delete:
            self.delete_requested.emit(self.area_id)
        event.accept()


class _TitleEdit(QLineEdit):
    """The inline title editor; Escape cancels."""

    cancelled = pyqtSignal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)
