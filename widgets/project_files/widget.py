import logging
from pathlib import Path

from PyQt6.QtCore import QDir, QEvent, QModelIndex, QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QFileSystemModel, QPainter, QPolygonF, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from desk.file_type_registry import (
    FILE_TYPE_REGISTRY_UPDATED_EVENT,
    entry_from_dict,
    find_edit_handler,
    find_view_handler,
    looks_like_text_file,
)
from desk.shell import current_context
from desk.shell.event_broker import EventSubscription

EDITOR_WIDGET_ID = "editor"
SCRATCH_WIDGET_ID = "scratch"

logger = logging.getLogger(__name__)

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


class ProjectFilesWidget(QWidget):
    """A tree-view project directory/file browser (formerly "File
    Explorer", renamed to "Project Files" -- TODO 8385dcc): `QFileSystemModel`
    for normal lazy browsing, swapped for a bespoke eager search
    -results model (see `_build_search_model`) while the filter box is
    non-empty. See plans/file-explorer-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._root = current_context.get_current_desk_directory() or Path.home()
        self._current_path: Path | None = None
        self._searching = False
        # TODO b5d52c0: an initial one-time read, kept fresh afterward by
        # bind_event_mediator's live subscription below -- never
        # re-fetched via the provider again after this.
        provider = current_context.get_file_type_registry_provider()
        self._file_type_registry: list[dict] = provider() if provider is not None else []

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

        # TODO 465c404 originally fixed this toolbar's native-style
        # -painted chrome desyncing from its text under zoom by forcing
        # Fusion on just these two controls. TODO 8afef71 superseded
        # that with a generic fix (WidgetFrame._ContentStyleGuard) that
        # applies to every widget's content automatically, so the
        # per-widget setStyle() calls that used to be here are gone.

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
        self._open_file(path)

    def _open_file(self, path: Path) -> None:
        """TODO efdad99: a viewer/editor/scrap fallback chain, using
        TODO b5d52c0's file type registry -- (1) a registered viewer,
        (2) a registered editor or (for a file the registry has no
        entry for at all) the built-in Editor widget, but only if the
        file is genuinely text, (3) a Scratch note explaining that
        nothing can open it. Whichever widget actually gets used is
        placed centered in the current view (get_centered_widget_opener,
        not get_widget_opener's own `(0, 0)` default)."""
        opener = current_context.get_centered_widget_opener()
        if opener is None:
            return
        registry = [entry_from_dict(d) for d in self._file_type_registry]
        widget_id = find_view_handler(registry, path) or find_edit_handler(registry, path)
        if widget_id is None and looks_like_text_file(path):
            widget_id = EDITOR_WIDGET_ID
        if widget_id is not None:
            self._open_in_widget(opener, widget_id, path)
            return
        self._open_as_unopenable_scrap(opener, path)

    def _open_in_widget(self, opener, widget_id: str, path: Path) -> None:
        widget = opener(widget_id)
        if widget is not None and hasattr(widget, "set_file"):
            # A broken set_file() must never propagate out of here
            # (TODO 810a5d6): this runs inside a Qt slot (doubleClicked),
            # and an uncaught exception there is fatal to the whole
            # process in this PyQt6 setup, not just to opening this one
            # file -- see plans/isolate-hot-reload-crash.md and
            # LEARNINGS.md.
            try:
                widget.set_file(path)
            except Exception:
                logger.error("Failed to open %s in the %r widget", path, widget_id, exc_info=True)

    def _open_as_unopenable_scrap(self, opener, path: Path) -> None:
        widget = opener(SCRATCH_WIDGET_ID)
        if widget is None or not hasattr(widget, "set_label") or not hasattr(widget, "body"):
            return
        widget.set_label(f"Can't open {path.name}")
        widget.body.setPlainText(
            f"No viewer or editor is registered for this file type "
            f"({path.suffix or 'no extension'}), and it doesn't look like plain text."
        )

    def bind_event_mediator(self, instance_id, mediator) -> None:
        """TODO b5d52c0: opts into `DeskWindow._bind_event_mediator`'s
        generic per-placed-python-widget hook (TODO 6f9c51b) to keep
        `self._file_type_registry` current after its own one-time
        initial read (see __init__) -- the published event's own
        payload carries the new registry directly, so this never needs
        to make a separate call to re-fetch it."""
        self._file_type_registry_subscription = EventSubscription(
            mediator, instance_id, names=[FILE_TYPE_REGISTRY_UPDATED_EVENT], parent=self
        )
        self._file_type_registry_subscription.message_received.connect(self._on_mediated_event)

    def _on_mediated_event(self, name: str, payload: object, _sender_instance_id: str) -> None:
        if name == FILE_TYPE_REGISTRY_UPDATED_EVENT and isinstance(payload, dict):
            self._file_type_registry = payload.get("entries", [])

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
    return ProjectFilesWidget()
