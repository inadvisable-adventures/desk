"""Tree views whose expand/collapse branch indicator is painted by us
rather than by the native platform style.

Native-style-drawn branch arrows composite wrongly through the
Workspace Canvas's `QGraphicsProxyWidget` at a non-1.0 zoom (wrong
position and size; see LEARNINGS.md, "A native-style-drawn control ...
can visually desync"). Plain `QPainter` drawing within the same
indentation rect Qt's click hit-testing uses can't drift from it.
TODO 333bebf (Markdown TOC), originally TODO b927389 (Project Files).
"""

from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QPointF, QRectF, Qt
from PyQt6.QtGui import QPainter, QPolygonF
from PyQt6.QtWidgets import QTreeView, QTreeWidget


def paint_branch_indicator(view: QTreeView, painter: QPainter, rect, index: QModelIndex) -> None:
    if not index.model().hasChildren(index):
        return
    indent = view.indentation()
    arrow_rect = QRectF(rect.right() - indent, rect.top(), indent, rect.height())
    cx, cy = arrow_rect.center().x(), arrow_rect.center().y()
    size = min(arrow_rect.width(), arrow_rect.height()) * 0.28

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(view.palette().color(view.foregroundRole()))
    painter.setPen(Qt.PenStyle.NoPen)
    if view.isExpanded(index):
        polygon = QPolygonF(
            [
                QPointF(cx - size, cy - size * 0.6),
                QPointF(cx + size, cy - size * 0.6),
                QPointF(cx, cy + size * 0.7),
            ]
        )
    else:
        polygon = QPolygonF(
            [
                QPointF(cx - size * 0.6, cy - size),
                QPointF(cx - size * 0.6, cy + size),
                QPointF(cx + size * 0.7, cy),
            ]
        )
    painter.drawPolygon(polygon)
    painter.restore()


class PaintedBranchTreeView(QTreeView):
    def drawBranches(self, painter: QPainter, rect, index: QModelIndex) -> None:
        paint_branch_indicator(self, painter, rect, index)


class PaintedBranchTreeWidget(QTreeWidget):
    def drawBranches(self, painter: QPainter, rect, index: QModelIndex) -> None:
        paint_branch_indicator(self, painter, rect, index)
