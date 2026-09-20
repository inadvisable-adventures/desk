import threading

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.hmsvc import (
    HMSVC_CHANGED_EVENT,
    HMSVC_DIRNAME,
    SERVICE_ENTRY_FILENAME,
    STATUS_CRASHED,
    STATUS_RUNNING,
    STATUS_STARTING,
)
from desk.shell import current_context
from desk.shell.event_broker import EventSubscription

ITEM_LIST_STYLE = """
QListWidget::item {
    border: 1px solid #888;
    border-radius: 4px;
    padding: 0px;
}
"""
ITEM_LIST_SPACING = 3
ROW_BUTTON_WIDTH = 70
LOG_REFRESH_INTERVAL_MS = 500
LOG_LINES_SHOWN = 300
STATUS_COLORS = {STATUS_RUNNING: "#2e7d32", STATUS_STARTING: "#b26a00", STATUS_CRASHED: "#c62828"}


class HmsvcManagerWidget(QWidget):
    """Monitors/manages Desk-hosted microservices (TODO e75b165) --
    the user-authored Python services under `desk_hmsvc/<name>/`
    (see desk.hmsvc). One row per service: status, port, pid, URL,
    Start/Stop/Restart, Logs (selects it for the log pane below) and
    Source (opens service.py). Start/Stop/Restart run on a worker
    thread since stopping can block for a few seconds; the row list
    refreshes off the manager's own `desk.hmsvc.changed` event, and the
    selected service's log pane on a short timer."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._services: list[dict] = []
        self._selected: str | None = None
        self._subscription: EventSubscription | None = None

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._refresh_button = QPushButton("Rescan")
        self._refresh_button.setToolTip(f"Rescan {HMSVC_DIRNAME}/ for new or removed services")
        self._refresh_button.clicked.connect(self._rescan)

        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self._list.setStyleSheet(ITEM_LIST_STYLE)
        self._list.setSpacing(ITEM_LIST_SPACING)

        self._log_label = QLabel()
        self._log_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(LOG_LINES_SHOWN)

        top_row = QHBoxLayout()
        top_row.addWidget(self._status_label, 1)
        top_row.addWidget(self._refresh_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self._list, stretch=2)
        layout.addWidget(self._log_label)
        layout.addWidget(self._log_view, stretch=1)

        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._refresh_logs)
        self._log_timer.start(LOG_REFRESH_INTERVAL_MS)

        self.reload()

    def _manager(self):
        return current_context.get_hmsvc_manager()

    def reload(self) -> None:
        manager = self._manager()
        self._services = manager.list_services() if manager is not None else []
        self._populate_list()

    def bind_event_mediator(self, instance_id: str, mediator) -> None:
        self._subscription = EventSubscription(mediator, instance_id, names=[HMSVC_CHANGED_EVENT], parent=self)
        self._subscription.message_received.connect(self._on_mediated_event)

    def _on_mediated_event(self, name: str, payload: object, _sender_instance_id: str) -> None:
        if name == HMSVC_CHANGED_EVENT and isinstance(payload, dict):
            self._services = payload.get("services", [])
            self._populate_list()

    def _populate_list(self) -> None:
        self._list.clear()
        running = sum(1 for s in self._services if s["status"] == STATUS_RUNNING)
        if not self._services:
            self._status_label.setText(f"No services. Add one at {HMSVC_DIRNAME}/<name>/{SERVICE_ENTRY_FILENAME}.")
        else:
            self._status_label.setText(f"{len(self._services)} services, {running} running.")
        for service in self._services:
            item = QListWidgetItem()
            row = self._build_row(service)
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
        self._refresh_logs()

    def _build_row(self, service: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        color = STATUS_COLORS.get(service["status"], "#666")
        details = [f"<b>{service['name']}</b> <span style='color:{color}'>{service['status']}</span>"]
        if service["port"] is not None and service["status"] in (STATUS_RUNNING, STATUS_STARTING):
            details.append(f"port {service['port']}")
        if service["pid"] is not None:
            details.append(f"pid {service['pid']}")
        if service["exit_code"] is not None and service["pid"] is None:
            details.append(f"exit {service['exit_code']}")
        text = " &nbsp;·&nbsp; ".join(details)
        if service["url"]:
            text += f"<br>{service['url']}"
        if service["description"]:
            text += f"<br><i>{service['description']}</i>"
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(label, 1)

        active = service["status"] in (STATUS_RUNNING, STATUS_STARTING)
        name = service["name"]
        for text, handler, enabled in (
            ("Start", self._start, not active),
            ("Stop", self._stop, active),
            ("Restart", self._restart, True),
            ("Logs", self._select, True),
            ("Source", self._view_source, True),
        ):
            button = QPushButton(text)
            button.setFixedWidth(ROW_BUTTON_WIDTH)
            button.setEnabled(enabled)
            button.clicked.connect(lambda checked=False, n=name, h=handler: h(n))
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    # -- actions -------------------------------------------------------

    def _run_async(self, action: str, name: str) -> None:
        manager = self._manager()
        if manager is None:
            return
        self._selected = name

        def work() -> None:
            ok, message = getattr(manager, action)(name)
            if not ok:
                # Surfaces in the log pane; status changes themselves
                # arrive via the manager's own change event.
                manager.append_log(name, f"[desk] {message}")

        threading.Thread(target=work, daemon=True).start()

    def _start(self, name: str) -> None:
        self._run_async("start", name)

    def _stop(self, name: str) -> None:
        self._run_async("stop", name)

    def _restart(self, name: str) -> None:
        self._run_async("restart", name)

    def _select(self, name: str) -> None:
        self._selected = name
        self._log_view.clear()
        self._refresh_logs()

    def _rescan(self) -> None:
        manager = self._manager()
        if manager is not None:
            manager.refresh()

    def _view_source(self, name: str) -> None:
        manager = self._manager()
        opener = current_context.get_editor_or_scrap_opener()
        if manager is None or opener is None or manager.services_dir is None:
            return
        opener(manager.services_dir / name / SERVICE_ENTRY_FILENAME)

    def _refresh_logs(self) -> None:
        manager = self._manager()
        if manager is None or self._selected is None:
            self._log_label.setText("Select a service's Logs to see its output.")
            return
        lines = manager.get_logs(self._selected, LOG_LINES_SHOWN)
        self._log_label.setText(f"Logs: {self._selected}")
        text = "\n".join(lines)
        if text != self._log_view.toPlainText():
            self._log_view.setPlainText(text)
            scrollbar = self._log_view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())


def build() -> QWidget:
    return HmsvcManagerWidget()
