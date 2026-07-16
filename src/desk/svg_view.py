"""A shared, bare SVG display widget (TODO `a9e2ba7`).

Extracted from widgets/image_viewer/widget.py's own private
_AspectSvgView -- originally moved there verbatim from the retired
standalone SVG Viewer widget (TODO `c7d6e4d`, TODO `4d21e7c`; see
design-docs/svg-viewing-and-editing.md) -- so the Markdown widget's own
Mermaid-diagram-as-SVG rendering (TODO `a9e2ba7`, see
design-docs/transforms.md) can reuse the exact same implementation
instead of duplicating it a second time.
"""

from PyQt6.QtCore import QSizeF
from PyQt6.QtGui import QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QWidget

from desk.geometry import fit_rect


class SvgView(QWidget):
    """Renders the loaded SVG via a bare `QSvgRenderer` into a
    letterboxed, aspect-preserving target rect (see `desk.geometry
    .fit_rect`) instead of `QSvgWidget`'s own non-uniform
    stretch-to-fill."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._renderer = QSvgRenderer()

    def load(self, data: bytes) -> bool:
        ok = self._renderer.load(data)
        self.update()
        return ok

    def is_valid(self) -> bool:
        return self._renderer.isValid()

    def clear(self) -> None:
        self._renderer.load(bytes())
        self.update()

    def content_size(self) -> QSizeF:
        """The SVG's own natural size (from its `defaultSize`, falling
        back to its `viewBox`) -- public (not just used internally by
        `paintEvent`) so a caller embedding this in a layout that
        doesn't otherwise size it (e.g. the Markdown widget's own
        per-block height calculation) can compute a sensible widget
        size from the content's real aspect ratio."""
        default_size = self._renderer.defaultSize()
        if not default_size.isEmpty():
            return QSizeF(default_size)
        return QSizeF(self._renderer.viewBoxF().size())

    def paintEvent(self, event) -> None:
        if not self._renderer.isValid():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        target = fit_rect(self.content_size(), QSizeF(self.size()))
        self._renderer.render(painter, target)
