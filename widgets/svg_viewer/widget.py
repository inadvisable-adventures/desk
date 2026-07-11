from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QSizeF
from PyQt6.QtGui import QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.file_watch import SingleFileWatcher
from desk.shell import current_context

SVG_FILTER = "SVG (*.svg *.svgz);;All files (*)"


def _fit_rect(content_size: QSizeF, container_size: QSizeF) -> QRectF:
    """A centered rect scaling `content_size` to fit within
    `container_size` while preserving aspect ratio (letterboxed on
    whichever axis has slack) -- `QSvgWidget`'s own default rendering
    doesn't do this (confirmed directly while planning this: it
    stretches non-uniformly to fill its whole rect), so callers render
    into this instead of the widget's raw geometry."""
    if (
        content_size.width() <= 0
        or content_size.height() <= 0
        or container_size.width() <= 0
        or container_size.height() <= 0
    ):
        return QRectF(0, 0, container_size.width(), container_size.height())
    scale = min(
        container_size.width() / content_size.width(),
        container_size.height() / content_size.height(),
    )
    width = content_size.width() * scale
    height = content_size.height() * scale
    x = (container_size.width() - width) / 2
    y = (container_size.height() - height) / 2
    return QRectF(x, y, width, height)


class _AspectSvgView(QWidget):
    """Renders the loaded SVG via a bare `QSvgRenderer` into a
    letterboxed, aspect-preserving target rect (see `_fit_rect`)
    instead of `QSvgWidget`'s own non-uniform stretch-to-fill."""

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

    def _content_size(self) -> QSizeF:
        default_size = self._renderer.defaultSize()
        if not default_size.isEmpty():
            return QSizeF(default_size)
        return QSizeF(self._renderer.viewBoxF().size())

    def paintEvent(self, event) -> None:
        if not self._renderer.isValid():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        target = _fit_rect(self._content_size(), QSizeF(self.size()))
        self._renderer.render(painter, target)


class SvgViewerWidget(QWidget):
    """Opens and displays a single SVG file, scaled to fit the widget
    while preserving aspect ratio, auto-reloading on changes -- the
    same shape as the plain Markdown widget. See
    plans/svg-viewer-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_path: Path | None = None
        self._last_dir = current_context.get_current_desk_directory() or Path.home()

        self._view = _AspectSvgView()

        self._label = QLabel()
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        open_button = QPushButton("Open")
        open_button.clicked.connect(self._open_file)

        toolbar = QHBoxLayout()
        toolbar.addWidget(open_button)
        toolbar.addStretch()
        toolbar.addWidget(self._label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._view, stretch=1)

        self._watcher = SingleFileWatcher(self)
        self._watcher.changed.connect(self._reload)
        # Capture the watcher (not self) so the teardown closure never
        # touches this widget's Qt state during destruction -- mirrors
        # the Markdown/Markdown (Extended) widgets' own teardown pattern.
        watcher = self._watcher
        self.destroyed.connect(lambda: watcher.stop())

        self._show_placeholder()

    def _show_placeholder(self) -> None:
        self._label.setText("(no file — click Open to choose an SVG file)")
        self._view.clear()

    def _open_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open SVG File", str(self._last_dir), SVG_FILTER
        )
        if filename:
            self.set_file(Path(filename))

    def set_file(self, path: Path) -> None:
        """Point the widget at `path`: render it and watch it for
        changes. Public so other widgets can open a file here
        programmatically, matching the plain Markdown widget."""
        self._current_path = path
        self._last_dir = path.parent
        self._watcher.watch(path)
        self._reload()

    def _reload(self) -> None:
        path = self._current_path
        if path is None:
            self._show_placeholder()
            return
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self._label.setText(f"`{path.name}` no longer exists.")
            self._view.clear()
            return
        except OSError as error:
            self._label.setText(f"Could not read `{path.name}`: {error}.")
            self._view.clear()
            return
        if self._view.load(data):
            self._label.setText(path.name)
        else:
            self._label.setText(f"`{path.name}` is not a valid SVG file.")


def build() -> QWidget:
    return SvgViewerWidget()
