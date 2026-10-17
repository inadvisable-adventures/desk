"""A combo box that survives being embedded in the zoomable Workspace
Canvas (TODO 0f2c458, 5303de6).

`QComboBox` draws its frame/text/arrow with the native platform style
(which desyncs under a non-1.0 `QGraphicsProxyWidget` scale) and opens its
list as a separate top-level popup positioned with `mapToGlobal`, which
ignores the canvas transform -- so the list appears detached from the
control. This one paints itself with plain `QPainter` calls and positions
and sizes its popup from the control's real on-screen rect via the owning
`QGraphicsView`. It implements only the subset of the `QComboBox` API
Desk's widgets use; add to it as needed.

Three things here are load-bearing, each learned the hard way (see
LEARNINGS.md, "QComboBox in a zoomed QGraphicsProxyWidget"):

- The popup is constructed with `parent=None`. Parenting a
  `Qt.WindowType.Popup` to the embedded (alien) `WidgetFrame` makes macOS
  interpret its `move()` relative to that parent's screen origin, not
  globally, so it lands a constant offset away from the control.
- The popup emits `index_chosen` synchronously right after `close()` and
  never touches itself afterward; the deferral lives on this control's own
  connection (`desk.shell.qt_utils.deferred`). A `QTimer` closure capturing
  the popup crashes once `WA_DeleteOnClose` has deleted it.
- The wheel is ignored so it zooms the canvas rather than changing the
  selection. The popup is a real OS window that never moves on its own, so
  a pan/zoom while it is open closes it (`_check_drift`).
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QKeyEvent, QPainter, QPalette, QPolygonF
from PyQt6.QtWidgets import QAbstractItemView, QGraphicsView, QListWidget, QSizePolicy, QVBoxLayout, QWidget

from desk.shell.qt_utils import deferred

_PAD_X = 8
_PAD_Y = 4
_ARROW_W = 16
_DRIFT_POLL_MS = 150
# Sub-pixel rounding means the recomputed rect can differ from the popup's
# position by a pixel with no real pan/zoom; only a larger move counts.
_DRIFT_TOLERANCE_PX = 2


class _ComboPopup(QWidget):
    index_chosen = pyqtSignal(int)

    def __init__(self, items: list[str], current: int) -> None:
        # parent=None on purpose; see the module docstring.
        super().__init__(None, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.addItems(items)
        self.list.setCurrentRow(current)
        self.list.itemClicked.connect(self._choose)
        self.list.itemActivated.connect(self._choose)
        layout.addWidget(self.list)

    def _choose(self, _item) -> None:
        # Same shape as desk_picker's _DeskListPopup._activate_item: close,
        # emit synchronously, never touch self again.
        row = self.list.currentRow()
        self.close()
        self.index_chosen.emit(row)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


class PaintedComboBox(QWidget):
    currentIndexChanged = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[str] = []
        self._data: list[object] = []
        self._current = -1
        self._popup: _ComboPopup | None = None
        # The control's on-screen rect when the open popup was placed;
        # None while no popup is open.
        self._popup_open_rect: QRectF | None = None
        self._drift_timer: QTimer | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    # -- QComboBox subset ---------------------------------------------

    def addItem(self, text: str, userData: object = None) -> None:
        self._items.append(text)
        self._data.append(userData)
        if self._current < 0:
            self._current = 0
        self.updateGeometry()
        self.update()

    def count(self) -> int:
        return len(self._items)

    def currentIndex(self) -> int:
        return self._current

    def itemText(self, index: int) -> str:
        return self._items[index] if 0 <= index < len(self._items) else ""

    def itemData(self, index: int) -> object:
        return self._data[index] if 0 <= index < len(self._data) else None

    def currentData(self) -> object:
        return self.itemData(self._current)

    def currentText(self) -> str:
        return self.itemText(self._current)

    def setCurrentIndex(self, index: int) -> None:
        if not 0 <= index < len(self._items) or index == self._current:
            return
        self._current = index
        self.update()
        self.currentIndexChanged.emit(index)

    # -- geometry / painting ------------------------------------------

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        width = max((fm.horizontalAdvance(t) for t in self._items), default=40)
        return QSize(width + 2 * _PAD_X + _ARROW_W, fm.height() + 2 * _PAD_Y)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        text_color = pal.color(group, QPalette.ColorRole.Text)
        frame = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(pal.base())
        painter.setPen(pal.highlight().color() if self.hasFocus() else pal.mid().color())
        painter.drawRoundedRect(frame, 3, 3)
        text_rect = QRectF(_PAD_X, 0, self.width() - 2 * _PAD_X - _ARROW_W, self.height())
        painter.setPen(text_color)
        elided = QFontMetrics(self.font()).elidedText(
            self.currentText(), Qt.TextElideMode.ElideRight, int(text_rect.width())
        )
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), elided)
        cx, cy, r = self.width() - _ARROW_W / 2 - 2, self.height() / 2, 4.0
        painter.setBrush(text_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(
            QPolygonF([QPointF(cx - r, cy - r * 0.5), QPointF(cx + r, cy - r * 0.5), QPointF(cx, cy + r * 0.6)])
        )

    # -- interaction --------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self._open_popup()
            event.accept()
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:
        event.ignore()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F4):
            self._open_popup()
        elif key == Qt.Key.Key_Up:
            self.setCurrentIndex(self._current - 1)
        elif key == Qt.Key.Key_Down:
            self.setCurrentIndex(self._current + 1)
        else:
            super().keyPressEvent(event)

    def _screen_rect_and_scale(self) -> tuple[QRectF, float]:
        """This control's on-screen rect (global coords) and the view's
        zoom, accounting for the canvas transform when embedded."""
        frame = self.window()
        proxy = frame.graphicsProxyWidget() if frame is not None else None
        scene = proxy.scene() if proxy is not None else None
        views = scene.views() if scene is not None else []
        if not views:
            top_left = self.mapToGlobal(QPoint(0, 0))
            return QRectF(top_left.x(), top_left.y(), self.width(), self.height()), 1.0
        view: QGraphicsView = views[0]

        def to_global(local: QPoint) -> QPointF:
            scene_pt = proxy.mapToScene(QPointF(self.mapTo(frame, local)))
            return QPointF(view.viewport().mapToGlobal(view.mapFromScene(scene_pt)))

        tl = to_global(QPoint(0, 0))
        br = to_global(QPoint(self.width(), self.height()))
        return QRectF(tl, br).normalized(), view.transform().m11()

    def _open_popup(self) -> None:
        if self._popup is not None or not self._items:
            return
        rect, scale = self._screen_rect_and_scale()
        popup = _ComboPopup(self._items, self._current)
        font = self.font()
        font.setPointSizeF(font.pointSizeF() * scale)
        popup.list.setFont(font)
        row_h = QFontMetrics(font).height() + 6
        popup.list.setFixedHeight(row_h * len(self._items) + 4)
        popup.setFixedWidth(max(int(rect.width()), 40))
        popup.adjustSize()
        popup.move(int(rect.left()), int(rect.bottom()))
        # Container-side half of the popup-signal pattern; see _choose.
        popup.index_chosen.connect(deferred(self.setCurrentIndex))
        popup.destroyed.connect(self._popup_gone)
        self._popup = popup
        self._popup_open_rect = rect
        popup.show()
        popup.list.setFocus()

        self._drift_timer = QTimer(self)
        self._drift_timer.setInterval(_DRIFT_POLL_MS)
        self._drift_timer.timeout.connect(self._check_drift)
        self._drift_timer.start()

    def _check_drift(self) -> None:
        """Close the open popup if the control has moved on screen since
        the popup was placed (a canvas pan/zoom while it was open)."""
        if self._popup is None or self._popup_open_rect is None:
            return
        rect, _scale = self._screen_rect_and_scale()
        moved = (
            abs(rect.left() - self._popup_open_rect.left()) > _DRIFT_TOLERANCE_PX
            or abs(rect.top() - self._popup_open_rect.top()) > _DRIFT_TOLERANCE_PX
            or abs(rect.width() - self._popup_open_rect.width()) > _DRIFT_TOLERANCE_PX
        )
        if moved:
            self._popup.close()

    def _popup_gone(self) -> None:
        self._popup = None
        self._popup_open_rect = None
        if self._drift_timer is not None:
            self._drift_timer.stop()
            self._drift_timer = None
