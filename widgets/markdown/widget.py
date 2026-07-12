import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from desk.file_watch import SingleFileWatcher
from desk.shell import current_context

logger = logging.getLogger(__name__)

PLACEHOLDER = "*No file open — click **Open** to choose a Markdown file.*"
MARKDOWN_FILTER = "Markdown (*.md *.markdown *.mdown *.mkd *.mdwn);;All files (*)"


class MarkdownWidget(QWidget):
    """Renders a Markdown file with Qt's native QTextBrowser.setMarkdown()
    and auto-reloads it when the file changes on disk (via
    desk.file_watch.SingleFileWatcher). The Open dialog's initial
    directory seeds from the current Desk's directory (via
    desk.shell.current_context, resolved once at construction -- same
    shape as the editor/TODO widgets), falling back to home. The chosen
    file is not persisted across a reload (the widget contract has no
    per-instance state payload yet -- see PARKINGLOT.md), matching the
    editor widget. See plans/markdown-renderer-widget.md."""

    external_path_changed = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_path: Path | None = None
        self._last_dir = current_context.get_current_desk_directory() or Path.home()

        self._view = QTextBrowser()
        self._view.setOpenExternalLinks(True)

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
        # touches this widget's Qt state during destruction; stop() only
        # tears down the background watchdog Observer. Mirrors the TODO
        # widget's own teardown pattern.
        watcher = self._watcher
        self.destroyed.connect(lambda: watcher.stop())

        self._show_placeholder()

    def _show_placeholder(self) -> None:
        self._label.setText("(no file)")
        self._view.setMarkdown(PLACEHOLDER)

    def _open_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Markdown File", str(self._last_dir), MARKDOWN_FILTER
        )
        if filename:
            self.set_file(Path(filename))

    def set_file(self, path: Path) -> None:
        """Point the widget at `path`: render it and watch it for changes.
        Public so other widgets can open a file here programmatically
        (e.g. the TODO widget's 'open plan' button, TODO b25412e)."""
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
        self._label.setText(path.name)
        try:
            self._view.setMarkdown(path.read_text())
        except FileNotFoundError:
            # Deleted out from under us -- keep watching so a recreate
            # reloads it, rather than clearing the target.
            self._view.setMarkdown(f"*`{path.name}` no longer exists.*")
        except OSError as error:
            self._view.setMarkdown(f"*Could not read `{path.name}`: {error}.*")


def build() -> QWidget:
    return MarkdownWidget()
