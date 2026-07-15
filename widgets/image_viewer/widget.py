import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QSizeF, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.file_watch import SingleFileWatcher
from desk.geometry import fit_rect
from desk.shell import current_context

logger = logging.getLogger(__name__)

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff *.ico);;All files (*)"


class _AspectImageView(QWidget):
    """Renders the loaded image into a letterboxed, aspect-preserving
    target rect (see `desk.geometry.fit_rect`) instead of
    `QLabel.setScaledContents(True)`'s own non-uniform stretch-to-fill
    -- same shape as `widgets/svg_viewer/widget.py`'s `_AspectSvgView`,
    a `QPixmap` in place of a `QSvgRenderer`."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap()

    def load(self, data: bytes) -> bool:
        pixmap = QPixmap()
        ok = pixmap.loadFromData(data)
        self._pixmap = pixmap if ok else QPixmap()
        self.update()
        return ok

    def is_valid(self) -> bool:
        return not self._pixmap.isNull()

    def clear(self) -> None:
        self._pixmap = QPixmap()
        self.update()

    def paintEvent(self, event) -> None:
        if self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        target = fit_rect(QSizeF(self._pixmap.size()), QSizeF(self.size()))
        painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))


class ImageViewerWidget(QWidget):
    """Opens and displays a single image file, scaled to fit the widget
    while preserving aspect ratio, auto-reloading on changes -- the
    same shape as `widgets/svg_viewer/widget.py`. See
    plans/image-drop-tempui.md (TODO 6e731c1)."""

    external_path_changed = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_path: Path | None = None
        self._last_dir = current_context.get_current_desk_directory() or Path.home()

        self._view = _AspectImageView()

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
        # the Markdown/SVG viewer widgets' own teardown pattern.
        watcher = self._watcher
        self.destroyed.connect(lambda: watcher.stop())

        self._show_placeholder()

    def _show_placeholder(self) -> None:
        self._label.setText("(no file — click Open to choose an image file)")
        self._view.clear()

    def _open_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Image File", str(self._last_dir), IMAGE_FILTER
        )
        if filename:
            self.set_file(Path(filename))

    def set_file(self, path: Path) -> None:
        """Point the widget at `path`: render it and watch it for
        changes. Public so other widgets can open a file here
        programmatically, matching the plain Markdown/SVG viewer
        widgets."""
        self._current_path = path
        self._last_dir = path.parent
        self._watcher.watch(path)
        self._reload()
        self.refresh_external_path_status()

    def refresh_external_path_status(self) -> None:
        """Re-emits `external_path_changed` for the currently loaded file
        (TODO a053e3a) -- called here after every load, and once more by
        DeskWindow right after wiring the signal, since the file may
        already have been loaded before that connection existed.

        Wrapped defensively (TODO 810a5d6): this is a purely cosmetic
        titlebar feature reached from a Qt-signal-invoked slot chain
        where an uncaught exception is fatal to the whole process in
        this PyQt6 setup -- see plans/isolate-hot-reload-crash.md and
        LEARNINGS.md."""
        try:
            is_external = self._current_path is not None and current_context.path_is_external(
                self._current_path
            )
        except Exception:
            logger.error("Failed to compute external-path status for %s", self._current_path, exc_info=True)
            return
        self.external_path_changed.emit(is_external)

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
            self._label.setText(f"`{path.name}` is not a valid image file.")


def build() -> QWidget:
    return ImageViewerWidget()
