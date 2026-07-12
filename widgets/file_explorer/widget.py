from pathlib import Path

from PyQt6.QtCore import QDir, QEvent, QModelIndex, QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QFileSystemModel, QPainter, QPolygonF, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QStyleFactory,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from desk.shell import current_context

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist"}
SEARCH_DEBOUNCE_MS = 200
_IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 1


def _build_search_model(root: Path, query: str) -> QStandardItemModel:
    """Walks `root` looking for entries whose name contains `query`
    (case-insensitive), building a tree of just the matches plus
    whatever ancestor directories lead to one -- e.g. searching "foo"
    under (a (b ...) (c (foo) ...) (d ...)) keeps only a -> c -> foo,
    dropping b and d entirely. Synchronous/eager: see
    plans/file-explorer-widget.md for why this doesn't use
    QFileSystemModel + QSortFilterProxyModel's own recursive filtering
    (verified directly that it only sees data QFileSystemModel has
    already lazily loaded, silently missing matches in never-expanded
    branches)."""
    model = QStandardItemModel()
    needle = query.lower()

    def make_item(entry: Path, is_dir: bool) -> QStandardItem:
        item = QStandardItem(entry.name)
        item.setEditable(False)
        item.setData(str(entry), Qt.ItemDataRole.UserRole)
        item.setData(is_dir, _IS_DIR_ROLE)
        return item

    def walk(dir_path: Path) -> list[QStandardItem]:
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return []
        items: list[QStandardItem] = []
        for entry in entries:
            if entry.name in SKIP_DIRS:
                continue
            self_match = needle in entry.name.lower()
            if entry.is_dir():
                children = walk(entry)
                if not (self_match or children):
                    continue
                item = make_item(entry, is_dir=True)
                for child in children:
                    item.appendRow(child)
                items.append(item)
            elif self_match:
                items.append(make_item(entry, is_dir=False))
        return items

    for item in walk(root):
        model.appendRow(item)
    return model


class _FileTreeView(QTreeView):
    """A plain QTreeView, except the expand/collapse branch indicator is
    painted by us instead of the native platform style. Reported: the
    native-drawn arrow visibly scales oddly and stops reliably
    responding to clicks once this widget is embedded in the Workspace
    Canvas's QGraphicsProxyWidget at a non-1.0 zoom -- a known category
    of issue with native-style-drawn elements composited through an
    offscreen widget buffer (see LEARNINGS.md's related note on
    QGraphicsProxyWidget-embedded coordinates). Qt's own click-to
    -toggle hit-testing is based purely on indentation geometry, not on
    whatever the style actually paints, so drawing our own arrow
    *within that same geometry* keeps the visible arrow and the real
    clickable region from ever drifting apart, regardless of the exact
    native-rendering root cause."""

    def drawBranches(self, painter: QPainter, rect, index: QModelIndex) -> None:
        if not index.model().hasChildren(index):
            return
        indent = self.indentation()
        arrow_rect = QRectF(rect.right() - indent, rect.top(), indent, rect.height())
        cx, cy = arrow_rect.center().x(), arrow_rect.center().y()
        size = min(arrow_rect.width(), arrow_rect.height()) * 0.28

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.palette().color(self.foregroundRole()))
        painter.setPen(Qt.PenStyle.NoPen)
        if self.isExpanded(index):
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


class FileExplorerWidget(QWidget):
    """A tree-view project directory/file explorer: `QFileSystemModel`
    for normal lazy browsing, swapped for a bespoke eager search
    -results model (see `_build_search_model`) while the filter box is
    non-empty. See plans/file-explorer-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._root = current_context.get_current_desk_directory() or Path.home()
        self._current_path: Path | None = None
        self._searching = False

        self._fs_model = QFileSystemModel()
        # Show normally-hidden entries (dotfiles/dotdirs, e.g. .git) --
        # QFileSystemModel's own default filter omits QDir.Filter.Hidden.
        self._fs_model.setFilter(
            QDir.Filter.AllEntries | QDir.Filter.AllDirs | QDir.Filter.Hidden | QDir.Filter.NoDotAndDotDot
        )
        self._fs_model.setRootPath(str(self._root))

        self._tree = _FileTreeView()
        self._tree.setHeaderHidden(True)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.doubleClicked.connect(self._open_index)
        self._tree.installEventFilter(self)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search…")
        self._search_box.textChanged.connect(self._on_search_text_changed)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(SEARCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._apply_search)

        open_folder_button = QPushButton("Open Folder")
        open_folder_button.clicked.connect(self._choose_root)

        # Native-style-painted button/line-edit chrome (background,
        # border) was reported to visually desync from its own text once
        # zoomed -- the same category of bug as _FileTreeView's
        # native-drawn branch arrow above, now fixed here the same way:
        # stop relying on native-style painting. Fusion paints its own
        # chrome as ordinary transform-respecting vector operations
        # instead of native macOS theme calls. setStyle() does not take
        # ownership of the QStyle, so it's kept alive as an instance
        # attribute -- otherwise Python's GC could free it out from
        # under the still-referencing widgets. See TODO 465c404.
        self._toolbar_style = QStyleFactory.create("Fusion")
        open_folder_button.setStyle(self._toolbar_style)
        self._search_box.setStyle(self._toolbar_style)

        toolbar = QHBoxLayout()
        toolbar.addWidget(open_folder_button)
        toolbar.addWidget(self._search_box, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._tree, stretch=1)

        self._show_browse_model()

    # -- model switching --------------------------------------------------

    def _show_browse_model(self) -> None:
        self._searching = False
        self._tree.setModel(self._fs_model)
        for column in range(1, 4):
            self._tree.setColumnHidden(column, True)
        self._tree.setRootIndex(self._fs_model.index(str(self._root)))
        self._tree.selectionModel().currentChanged.connect(self._on_current_changed)
        self._restore_selection()

    def _on_search_text_changed(self, _text: str) -> None:
        self._debounce.start()

    def _apply_search(self) -> None:
        query = self._search_box.text().strip()
        if not query:
            self._show_browse_model()
            return
        self._searching = True
        model = _build_search_model(self._root, query)
        self._tree.setModel(model)
        self._tree.selectionModel().currentChanged.connect(self._on_current_changed)
        self._tree.expandAll()

    def _restore_selection(self) -> None:
        if self._current_path is None:
            return
        index = self._fs_model.index(str(self._current_path))
        if index.isValid():
            self._tree.setCurrentIndex(index)
            self._tree.scrollTo(index)

    # -- selection / opening -----------------------------------------------

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        path = self._path_for_index(current)
        if path is not None:
            self._current_path = path

    def _path_for_index(self, index: QModelIndex) -> Path | None:
        if not index.isValid():
            return None
        if self._searching:
            raw = index.data(Qt.ItemDataRole.UserRole)
            return Path(raw) if raw is not None else None
        return Path(self._fs_model.filePath(index))

    def _is_dir_index(self, index: QModelIndex) -> bool:
        if self._searching:
            return bool(index.data(_IS_DIR_ROLE))
        return self._fs_model.isDir(index)

    def _open_index(self, index: QModelIndex) -> None:
        if not index.isValid() or self._is_dir_index(index):
            return
        path = self._path_for_index(index)
        if path is None:
            return
        opener = current_context.get_widget_opener()
        if opener is None:
            return
        widget = opener("editor")
        if widget is not None and hasattr(widget, "set_file"):
            widget.set_file(path)

    def _choose_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Open Folder", str(self._root))
        if not directory:
            return
        self._root = Path(directory)
        self._fs_model.setRootPath(str(self._root))
        self._current_path = None
        self._debounce.stop()
        self._search_box.blockSignals(True)
        self._search_box.clear()
        self._search_box.blockSignals(False)
        self._show_browse_model()

    def eventFilter(self, obj, event) -> bool:
        if (
            obj is self._tree
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            self._open_index(self._tree.currentIndex())
            return True
        return super().eventFilter(obj, event)


def build() -> QWidget:
    return FileExplorerWidget()
