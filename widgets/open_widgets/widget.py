from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desk.shell import current_context
from desk.shell.event_broker import EventSubscription
from desk.widget_overview import WIDGET_OVERVIEW_CHANGED_EVENT

COLUMNS = ["Widget", "Kind", "Instance", "Stale"]
STALE_TEXT = "STALE"
NOT_CONNECTED_STATUS = "Not yet connected to Desk."


class OpenWidgetsWidget(QWidget):
    """A live table of every placed widget instance (TODO 53779f4). Loaded
    once from the overview provider, then replaced from each overview event
    -- no polling. Double-click a row = that widget's eye button; the
    button reloads every stale widget after one confirmation. See
    plans/open-widgets-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []
        self._subscription: EventSubscription | None = None

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._reload_button = QPushButton("Reload all stale widgets")
        self._reload_button.clicked.connect(self._on_reload_clicked)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(0, self._table.horizontalHeader().ResizeMode.Stretch)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)

        top = QHBoxLayout()
        top.addWidget(self._status_label, stretch=1)
        top.addWidget(self._reload_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._table, stretch=1)

        provider = current_context.get_widget_overview_provider()
        self._set_rows(provider() if provider is not None else [], connected=provider is not None)

    def bind_event_mediator(self, instance_id: str, mediator) -> None:
        self._subscription = EventSubscription(mediator, instance_id, names=[WIDGET_OVERVIEW_CHANGED_EVENT], parent=self)
        self._subscription.message_received.connect(self._on_mediated_event)

    def _on_mediated_event(self, name: str, payload: object, _sender_instance_id: str) -> None:
        if name == WIDGET_OVERVIEW_CHANGED_EVENT and isinstance(payload, dict):
            self._set_rows(payload.get("widgets", []))

    def _set_rows(self, rows: list[dict], connected: bool = True) -> None:
        self._rows = list(rows)
        self._table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            values = [row.get("title", ""), row.get("kind", ""), row.get("instance_id", ""), STALE_TEXT if row.get("stale") else ""]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(index, column, item)
        stale = sum(1 for row in self._rows if row.get("stale"))
        self._reload_button.setEnabled(stale > 0)
        if not connected:
            self._status_label.setText(NOT_CONNECTED_STATUS)
        else:
            self._status_label.setText(f"{len(self._rows)} widget(s), {stale} stale.")

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if not 0 <= row < len(self._rows):
            return
        zoomer = current_context.get_widget_zoomer()
        if zoomer is not None:
            zoomer(self._rows[row]["instance_id"])

    def _on_reload_clicked(self) -> None:
        reloader = current_context.get_stale_widgets_reloader()
        if reloader is not None:
            reloader()


def build() -> QWidget:
    return OpenWidgetsWidget()
