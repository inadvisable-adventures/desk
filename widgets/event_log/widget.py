import json
import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desk.event_mediator import LOG_FILENAME, LOG_HEADER, MediatedEvent, parse_log
from desk.file_watch import SingleFileWatcher
from desk.shell import current_context
from desk.temp_ui import TEMP_UI_DIRNAME

COLUMN_HEADERS = ("Timestamp", "Event", "Sender", "Payload")
# Stashes the row's full MediatedEvent (TODO 0d2ebc1) on the Timestamp
# column's own QTableWidgetItem, the same Qt.ItemDataRole.UserRole
# pattern widgets/questions/widget.py's own ENTRY_ROLE already uses --
# _format_payload's table-row text is a truncated summary, so
# double-clicking to open the full Event Viewer needs the real event
# back, not just its displayed string.
EVENT_ROLE = Qt.ItemDataRole.UserRole

logger = logging.getLogger(__name__)


class EventLogWidget(QWidget):
    """Views MEDIATED-EVENT-LOG.tsv (desk.event_mediator, TODO 6f9c51b)
    -- the event mediator's own log of every published message -- as a
    read-only table, kept fresh by a SingleFileWatcher (same reused
    component the TODO widget watches TODO.md with) regardless of the
    Live Tail toggle; Live Tail controls only whether a refresh
    auto-scrolls to the bottom, matching this app's established
    preference for file-watching over a manual reload button (TODO
    d25e557 removed the TODO widget's outright). Clear Log truncates the
    log back to just its header row, after confirmation, going through
    the live EventMediator (current_context.get_event_mediator()) so the
    write is correctly serialized against a concurrent publish rather
    than racing it with a second, unlocked direct write."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._log_path: Path | None = None

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._table = QTableWidget(0, len(COLUMN_HEADERS))
        self._table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(
            len(COLUMN_HEADERS) - 1, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        self._table.itemDoubleClicked.connect(self._open_event_viewer)

        self._live_tail_button = QPushButton("Live Tail")
        self._live_tail_button.setCheckable(True)
        self._live_tail_button.setChecked(True)

        self._clear_button = QPushButton("Clear Log")
        self._clear_button.clicked.connect(self._clear_log)

        # TODO 593a464 originally fixed this toolbar's native-style
        # -painted chrome desyncing from its text under zoom by forcing
        # Fusion on just these two buttons. TODO 8afef71 superseded that
        # with a generic fix (WidgetFrame._ContentStyleGuard) that
        # applies to every widget's content automatically, so the
        # per-widget setStyle() calls that used to be here are gone.

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._live_tail_button)
        toolbar.addWidget(self._clear_button)
        toolbar.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._status_label)
        layout.addLayout(toolbar)
        layout.addWidget(self._table, stretch=1)

        self._watcher = SingleFileWatcher(self)
        self._watcher.changed.connect(self._reload)

        self._ensure_watching()

    # --- path / watching ----------------------------------------------

    def _ensure_watching(self) -> None:
        directory = current_context.get_current_desk_directory()
        if directory is None:
            self._log_path = None
            self._status_label.setText("No Desk directory available yet.")
            return
        self._log_path = directory / TEMP_UI_DIRNAME / LOG_FILENAME
        self._status_label.setText(str(self._log_path.relative_to(directory)))
        self._watcher.watch(self._log_path)
        self._reload()

    # --- table -----------------------------------------------------

    def _reload(self) -> None:
        if self._log_path is None or not self._log_path.is_file():
            self._set_events([])
            return
        try:
            text = self._log_path.read_text(encoding="utf-8")
        except OSError:
            return
        self._set_events(parse_log(text))

    def _set_events(self, events: list[MediatedEvent]) -> None:
        self._table.setRowCount(len(events))
        for row, event in enumerate(events):
            for column, text in enumerate(
                (event.timestamp, event.name, event.sender_instance_id, _format_payload(event.payload))
            ):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 0:
                    item.setData(EVENT_ROLE, event)
                self._table.setItem(row, column, item)
        if events and self._live_tail_button.isChecked():
            self._table.scrollToBottom()

    # --- event viewer ------------------------------------------------

    def _open_event_viewer(self, item: QTableWidgetItem) -> None:
        """Opens the Event Viewer widget (TODO 0d2ebc1) on the
        double-clicked row's full MediatedEvent -- reads it back off
        the Timestamp column's own item, same as project_files/widget
        .py's _open_index reaches the Editor widget."""
        event = self._table.item(item.row(), 0).data(EVENT_ROLE)
        if event is None:
            return
        opener = current_context.get_widget_opener()
        if opener is None:
            return
        widget = opener("event_viewer")
        if widget is not None and hasattr(widget, "set_event"):
            # A broken set_event() must never propagate out of here
            # (matching TODO 810a5d6's reasoning in project_files/
            # widget.py) -- this runs inside a Qt slot
            # (itemDoubleClicked), and an uncaught exception there is
            # fatal to the whole process in this PyQt6 setup.
            try:
                widget.set_event(event)
            except Exception:
                logger.error("Failed to open event in the Event Viewer widget", exc_info=True)

    # --- clear -----------------------------------------------------

    def _clear_log(self) -> None:
        if not self._confirm_clear():
            return
        mediator = current_context.get_event_mediator()
        if mediator is not None:
            mediator.clear_log()
        elif self._log_path is not None:
            try:
                self._log_path.write_text(LOG_HEADER + "\n", encoding="utf-8")
            except OSError:
                pass
        self._reload()

    def _confirm_clear(self) -> bool:
        """Split out so headless verification can monkeypatch just this
        one method instead of driving a real modal QMessageBox -- mirrors
        widgets/crash_log/widget.py's _confirm_delete and widgets/todo/
        widget.py's _ItemDialog._confirm_discard."""
        return (
            QMessageBox.question(
                self,
                "Clear Log",
                "Clear the entire event log? This can't be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )


def _format_payload(payload: object) -> str:
    return "" if payload is None else json.dumps(payload, separators=(",", ":"))


def build() -> QWidget:
    return EventLogWidget()
