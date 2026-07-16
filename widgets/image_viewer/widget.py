import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QSizeF, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from desk.file_watch import SingleFileWatcher
from desk.geometry import fit_rect
from desk.shell import current_context
from desk.svg_view import SvgView

logger = logging.getLogger(__name__)

IMAGE_FILTER = (
    "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff *.ico *.svg *.svgz);;"
    "All files (*)"
)

# TODO 4d21e7c: extensions dispatched to the vector (desk.svg_view.SvgView)
# page rather than the raster (_AspectImageView) one -- extension-based, not
# content-sniffed, matching how file_type_registry.py's own view-handler
# dispatch already works (an SVG's XML preamble isn't cheaply
# distinguishable from other XML-ish text formats).
VECTOR_SUFFIXES = {".svg", ".svgz"}


def _is_vector(path: Path) -> bool:
    return path.suffix.lower() in VECTOR_SUFFIXES


class _AspectImageView(QWidget):
    """Renders the loaded raster image into a letterboxed, aspect
    -preserving target rect (see `desk.geometry.fit_rect`) instead of
    `QLabel.setScaledContents(True)`'s own non-uniform stretch-to-fill
    -- same shape as `desk.svg_view.SvgView`, a `QPixmap` in place of a
    `QSvgRenderer`."""

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
    while preserving aspect ratio, auto-reloading on changes. Handles
    both raster formats (`_AspectImageView`, a `QPixmap`) and vector
    (`desk.svg_view.SvgView`, a `QSvgRenderer` -- shared with the
    Markdown widget's own Mermaid-diagram-as-SVG rendering, TODO
    `a9e2ba7`) -- TODO `4d21e7c` folded in the formerly-standalone SVG
    Viewer widget's rendering path so this is the one widget for
    viewing both. See `design-docs/svg-viewing-and-editing.md` and
    plans/image-drop-tempui.md (TODO 6e731c1)."""

    external_path_changed = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_path: Path | None = None
        self._last_dir = current_context.get_current_desk_directory() or Path.home()

        self._raster_view = _AspectImageView()
        self._vector_view = SvgView()

        self._stack = QStackedLayout()
        self._stack.addWidget(self._raster_view)
        self._stack.addWidget(self._vector_view)
        self._view_container = QWidget()
        self._view_container.setLayout(self._stack)

        self._label = QLabel()
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        open_button = QPushButton("Open")
        open_button.clicked.connect(self._open_file)

        # TODO da4f9c0: disabled until a file is actually loaded --
        # there's nothing to edit yet.
        self._edit_button = QPushButton("Edit")
        self._edit_button.setEnabled(False)
        self._edit_button.clicked.connect(self._edit_current_file)

        toolbar = QHBoxLayout()
        toolbar.addWidget(open_button)
        toolbar.addWidget(self._edit_button)
        toolbar.addStretch()
        toolbar.addWidget(self._label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._view_container, stretch=1)

        self._watcher = SingleFileWatcher(self)
        self._watcher.changed.connect(self._reload)
        # Capture the watcher (not self) so the teardown closure never
        # touches this widget's Qt state during destruction -- mirrors
        # the Markdown widget's own teardown pattern.
        watcher = self._watcher
        self.destroyed.connect(lambda: watcher.stop())

        self._show_placeholder()

    def _active_view(self):
        return self._vector_view if self._current_path is not None and _is_vector(self._current_path) else self._raster_view

    def _show_placeholder(self) -> None:
        self._label.setText("(no file — click Open to choose an image file)")
        self._raster_view.clear()
        self._vector_view.clear()

    def _open_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Image File", str(self._last_dir), IMAGE_FILTER
        )
        if filename:
            self.set_file(Path(filename))

    def set_file(self, path: Path) -> None:
        """Point the widget at `path`: render it and watch it for
        changes. Public so other widgets can open a file here
        programmatically, matching the plain Markdown widget."""
        self._current_path = path
        self._last_dir = path.parent
        self._stack.setCurrentWidget(self._active_view())
        self._watcher.watch(path)
        self._reload()
        self._edit_button.setEnabled(True)
        self.refresh_external_path_status()

    def _edit_current_file(self) -> None:
        """TODO da4f9c0: reuses the same shared editor-or-scrap service
        Project Files' own double-click fallback chain (TODO efdad99)
        uses, rather than a second copy of that logic. For a `.svg`
        this resolves to the SVG Editor widget once TODO `7076af5`
        registers it as the built-in edit handler -- nothing here needs
        to know that directly."""
        if self._current_path is None:
            return
        opener = current_context.get_editor_or_scrap_opener()
        if opener is not None:
            opener(self._current_path)

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
            self._active_view().clear()
            return
        except OSError as error:
            self._label.setText(f"Could not read `{path.name}`: {error}.")
            self._active_view().clear()
            return
        if self._active_view().load(data):
            self._label.setText(path.name)
        else:
            self._label.setText(f"`{path.name}` is not a valid image file.")


def build() -> QWidget:
    return ImageViewerWidget()
