import logging
import uuid
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.file_watch import SingleFileWatcher
from desk.parking_lot_file import ParkingLotEntry, find_nearest_parking_lot_file, parse_parking_lot_file
from desk.shell import current_context
from desk.temp_ui import MARKDOWN_KEYWORD, TEMP_UI_DIRNAME

logger = logging.getLogger(__name__)

ENTRY_ROLE = Qt.ItemDataRole.UserRole
PARKING_LOT_SOURCE_LABEL = "PARKINGLOT.md"

ITEM_LIST_STYLE = """
QListWidget::item {
    border: 1px solid #888;
    border-radius: 4px;
    padding: 0px;
}
"""
ITEM_LIST_SPACING = 3
DISCUSS_BUTTON_WIDTH = 70


class _TitleLabel(QLabel):
    """A QLabel that also reports its own double-clicks -- plain
    QLabel content placed via QListWidget.setItemWidget never reaches
    the list's own itemDoubleClicked (mouse events over a child widget
    go straight to that child, not the QListView underneath it), so
    each row's title needs to report this itself."""

    double_clicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event) -> None:
        super().mouseDoubleClickEvent(event)
        self.double_clicked.emit()


class ParkingLotWidget(QWidget):
    """Reads the nearest PARKINGLOT.md relative to the current Desk's
    directory (desk.shell.current_context) and displays it as a
    scrollable list of item titles. See plans/parking-lot-widget.md --
    mirrors widgets/questions/widget.py's overall shape (file watching,
    external-path indicator) but read-only: this widget never edits
    PARKINGLOT.md itself.

    Each row has a "Discuss" button in a fixed-width column on the
    right, which starts a new claude session to discuss that item (the
    same flow as the tempui DiscussParkingLotItem keyword, TODO
    c0875bc, referencing the item by line number the same reliable way
    TODO 624ff3a introduced -- not by splicing in its full text).
    Double-clicking a row's title instead opens just that item in a
    Markdown widget, by writing a `Markdown <title>` tempui file (the
    same keyword/format `OpenMarkdown`'s sibling already defines, see
    desk.temp_ui.parse_markdown_tempui) to .desk_temp/ -- reusing
    Desk's existing tempui notification/placement flow rather than
    placing a Markdown widget directly."""

    external_path_changed = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Plain dict (not Qt state), same rationale as TodoWidget's/
        # QuestionsWidget's own _state -- safe to read from the
        # destroyed-triggered teardown closure after this widget is
        # gone.
        self._state: dict = {"parking_lot_path": None, "entries": []}

        self._watcher = SingleFileWatcher(self)
        self._watcher.changed.connect(self._on_external_change)

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._timestamp_label = QLabel()
        self._timestamp_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._timestamp_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self._list.setStyleSheet(ITEM_LIST_STYLE)
        self._list.setSpacing(ITEM_LIST_SPACING)

        status_row = QHBoxLayout()
        status_row.addWidget(self._status_label, 1)
        status_row.addWidget(self._timestamp_label)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list, stretch=1)
        layout.addLayout(status_row)

        self.reload()

        watcher = self._watcher

        def _flush_on_teardown() -> None:
            watcher.stop()

        self.destroyed.connect(_flush_on_teardown)

    def reload(self) -> None:
        directory = current_context.get_current_desk_directory()
        parking_lot_path = find_nearest_parking_lot_file(directory) if directory is not None else None
        self._ensure_watcher(parking_lot_path)
        if parking_lot_path is None:
            self._state.update(parking_lot_path=None, entries=[])
            self._status_label.setText("No PARKINGLOT.md found near the current Desk's directory.")
            self._list.clear()
            self.refresh_external_path_status()
            return

        _preamble, entries = parse_parking_lot_file(parking_lot_path)
        self._state.update(parking_lot_path=parking_lot_path, entries=entries)
        self._status_label.setText(str(parking_lot_path))
        self._touch_timestamp("Reloaded")
        self._populate_list()
        self.refresh_external_path_status()

    def refresh_external_path_status(self) -> None:
        """Re-emits `external_path_changed` for the currently loaded
        PARKINGLOT.md -- mirrors QuestionsWidget.refresh_external_path_status,
        including the same defensive wrapping (TODO 810a5d6): an
        uncaught exception escaping a Qt-signal-invoked slot is fatal to
        this whole process."""
        parking_lot_path = self._state["parking_lot_path"]
        try:
            is_external = parking_lot_path is not None and current_context.path_is_external(parking_lot_path)
        except Exception:
            logger.error("Failed to compute external-path status for %s", parking_lot_path, exc_info=True)
            return
        self.external_path_changed.emit(is_external)

    def _touch_timestamp(self, verb: str) -> None:
        self._timestamp_label.setText(f"{verb} {datetime.now().strftime('%H:%M:%S')}")

    def _ensure_watcher(self, parking_lot_path: Path | None) -> None:
        if parking_lot_path is None:
            self._watcher.stop()
        else:
            self._watcher.watch(parking_lot_path)

    def _on_external_change(self) -> None:
        # No self-write-echo check needed -- this widget never writes
        # PARKINGLOT.md itself, and SingleFileWatcher already suppresses
        # `changed` for any write it was told about via record_own_write
        # (unused here).
        parking_lot_path = self._state["parking_lot_path"]
        if parking_lot_path is None or not parking_lot_path.is_file():
            return
        _preamble, entries = parse_parking_lot_file(parking_lot_path)
        self._state.update(entries=entries)
        self._status_label.setText(str(parking_lot_path))
        self._touch_timestamp("Reloaded")
        self._populate_list()

    def _populate_list(self) -> None:
        self._list.clear()
        for entry in self._state["entries"]:
            list_item = QListWidgetItem()
            list_item.setData(ENTRY_ROLE, entry)
            list_item.setToolTip(entry.title)
            row = self._build_row(entry)
            list_item.setSizeHint(row.sizeHint())
            self._list.addItem(list_item)
            self._list.setItemWidget(list_item, row)

    def _build_row(self, entry: ParkingLotEntry) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        title_label = _TitleLabel(entry.title)
        title_label.setWordWrap(True)
        title_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        title_label.double_clicked.connect(lambda entry=entry: self._open_item(entry))
        layout.addWidget(title_label, 1)

        discuss_button = QPushButton("Discuss")
        discuss_button.setFixedWidth(DISCUSS_BUTTON_WIDTH)
        discuss_button.clicked.connect(lambda checked=False, entry=entry: self._discuss_item(entry))
        layout.addWidget(discuss_button, 0, Qt.AlignmentFlag.AlignVCenter)

        return row

    def _open_item(self, entry: ParkingLotEntry) -> None:
        directory = current_context.get_current_desk_directory()
        if directory is None:
            return
        temp_dir = directory / TEMP_UI_DIRNAME
        temp_dir.mkdir(parents=True, exist_ok=True)
        content = f"{MARKDOWN_KEYWORD} {entry.title}\n{entry.raw_text}\n"
        (temp_dir / str(uuid.uuid4())).write_text(content)

    def _discuss_item(self, entry: ParkingLotEntry) -> None:
        starter = current_context.get_discuss_starter()
        if starter is None:
            return
        starter(PARKING_LOT_SOURCE_LABEL, "", entry.line_number)


def build() -> QWidget:
    return ParkingLotWidget()
