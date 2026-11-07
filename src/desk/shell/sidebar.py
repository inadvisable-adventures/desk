"""Chrome for the docked sidebar (TODO 4ff712c): the always-visible tab that
collapses/expands it, and the drop indicator shown while a placed widget is
being dragged toward it.

`DeskWindow` owns the behaviour (which docks exist, the expanded flag, the
drop); this module is just the two small widgets.
"""
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QToolBar, QToolButton, QWidget

TAB_WIDTH_PX = 18
# The drop zone is never narrower than the tab plus this much canvas, so an
# empty or collapsed sidebar is still a target you can hit.
MIN_DROP_ZONE_PX = 40
DEFAULT_SIDEBAR_WIDTH = 300  # a freshly docked widget's width, unless a saved Desk says otherwise


class SidebarTab(QToolBar):
    """A thin fixed strip on the left edge holding one arrow button."""

    def __init__(self, parent=None) -> None:
        super().__init__("Sidebar", parent)
        self.setObjectName("sidebar-tab")
        self.setMovable(False)
        self.setFloatable(False)
        self.setOrientation(Qt.Orientation.Vertical)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.button = QToolButton()
        self.button.setAutoRaise(True)
        self.button.setFixedWidth(TAB_WIDTH_PX)
        font = self.button.font()
        font.setPixelSize(14)
        self.button.setFont(font)
        self.addWidget(self.button)
        self.setFixedWidth(TAB_WIDTH_PX + 6)

    def show_state(self, expanded: bool, count: int) -> None:
        self.button.setText("◂" if expanded else "▸")
        noun = "widget" if count == 1 else "widgets"
        self.button.setToolTip(
            ("Collapse the sidebar" if expanded else "Expand the sidebar") + f" ({count} {noun})"
        )


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
