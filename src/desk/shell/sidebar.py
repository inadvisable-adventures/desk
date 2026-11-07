"""Chrome for the docked sidebar (TODO 4ff712c): the always-visible tab that
collapses/expands it, and the drop indicator shown while a placed widget is
being dragged toward it.

`DeskWindow` owns the behaviour (which docks exist, the expanded flag, the
drop); this module is just the two small widgets.
"""
from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QSizePolicy, QToolBar, QWidget

TAB_WIDTH_PX = 26
MAX_LABEL_CHARS = 16
# The drop zone is never narrower than the tab plus this much canvas, so an
# empty or collapsed sidebar is still a target you can hit.
MIN_DROP_ZONE_PX = 40
DEFAULT_SIDEBAR_WIDTH = 300  # a freshly docked widget's width, unless a saved Desk says otherwise


def label_for(title: str) -> str:
    """A docked widget's title as shown on the collapsed tab: at most
    MAX_LABEL_CHARS characters, the last three replaced by "..." when cut."""
    title = title.strip() or "(untitled)"
    if len(title) <= MAX_LABEL_CHARS:
        return title
    return title[: MAX_LABEL_CHARS - 3] + "..."


class _TabBody(QWidget):
    """The whole strip: one click target that paints the arrow (vertically
    centred) and, while collapsed, a rotated label per docked widget above it."""

    clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.expanded = False
        self.titles: list[str] = []
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setFixedWidth(TAB_WIDTH_PX)

    def sizeHint(self) -> QSize:
        return QSize(TAB_WIDTH_PX, 120)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        palette = QApplication.palette()
        painter = QPainter(self)
        if self._hover:
            tint = QColor(palette.highlight().color())
            tint.setAlpha(40)
            painter.fillRect(self.rect(), tint)
        painter.setPen(palette.windowText().color())
        font = QFont(painter.font())
        font.setPixelSize(20)
        painter.setFont(font)
        mid = self.height() // 2
        painter.drawText(QRect(0, mid - 12, self.width(), 24), int(Qt.AlignmentFlag.AlignCenter), "◂" if self.expanded else "▸")
        if self.expanded:
            return
        font.setPixelSize(12)
        painter.setFont(font)
        fm = QFontMetrics(font)
        baseline_x = self.width() / 2 - (fm.ascent() - fm.descent()) / 2
        y = 8
        limit = mid - 20  # never run into the arrow
        for title in self.titles:
            text = label_for(title)
            length = fm.horizontalAdvance(text)
            if y + length > limit:
                break
            painter.save()
            painter.translate(baseline_x, y)
            painter.rotate(90)
            painter.drawText(0, 0, text)
            painter.restore()
            y += length + 14


class SidebarTab(QToolBar):
    """A thin fixed strip on the left edge (TODO 4ff712c) that is one big
    click target: it opens the collapsed sidebar and collapses the open one."""

    def __init__(self, parent=None) -> None:
        super().__init__("Sidebar", parent)
        self.setObjectName("sidebar-tab")
        self.setMovable(False)
        self.setFloatable(False)
        self.setOrientation(Qt.Orientation.Vertical)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.setStyleSheet("QToolBar { padding: 0px; spacing: 0px; border: 0px; }")
        self.setContentsMargins(0, 0, 0, 0)
        self.body = _TabBody()
        self.clicked = self.body.clicked
        self.addWidget(self.body)
        self.setFixedWidth(TAB_WIDTH_PX)

    def show_state(self, expanded: bool, titles: list[str]) -> None:
        self.body.expanded = expanded
        self.body.titles = list(titles)
        count = len(titles)
        noun = "widget" if count == 1 else "widgets"
        tip = ("Collapse the sidebar" if expanded else "Expand the sidebar") + f" ({count} {noun})"
        if not expanded and titles:
            tip += "\n" + "\n".join(titles)
        self.body.setToolTip(tip)
        self.body.update()


class DockDropIndicator(QWidget):
    """A translucent, click-through highlight laid over the drop zone."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.hide()

    def show_over(self, rect: QRect) -> None:
        self.setGeometry(rect)
        self.show()
        self.raise_()

    def paintEvent(self, event) -> None:
        palette = QApplication.palette()
        accent = palette.highlight().color()
        painter = QPainter(self)
        fill = QColor(accent)
        fill.setAlpha(60)
        painter.fillRect(self.rect(), fill)
        pen = QPen(accent, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(2, 2, -3, -3))
        painter.setPen(palette.windowText().color())
        painter.drawText(
            self.rect().adjusted(6, 6, -6, -6),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            "Dock in sidebar",
        )
