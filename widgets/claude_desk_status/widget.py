from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.claude_session import CLAUDE_DESK_STATUS_EVENT
from desk.shell import current_context
from desk.shell.event_broker import EventSubscription

CLAUDE_DESK_WIDGET_ID = "claude_desk"
POLL_INTERVAL_MS = 1000
NO_INSTANCES_STATUS = "No Claude (Desk) widgets are open."
NO_STATUS_TEXT = "no status yet"
ATTENTION_STYLE = "color: #e8a33d; font-weight: 600;"


def describe_status(status: dict | None) -> tuple[str, bool]:
    """(row text, needs attention). A status of None means that instance
    hasn't published yet -- see plans/claude-desk-status-events-and-widget.md
    (push only, deliberately no request/reply to learn current state)."""
    if status is None:
        return NO_STATUS_TEXT, False
    if status.get("waiting_on_user"):
        detail = status.get("detail")
        return (f"Waiting on you: {detail}" if detail else "Waiting on you"), True
    return ("Working" if status.get("busy") else "Idle"), False


class _InstanceRow(QWidget):
    """One claude_desk instance: "{display name} -- {status}" plus a 👁
    button firing zoom_requested(instance_id), the same action as a placed
    widget's titlebar eye button (see widgets/event_subscribers/widget.py)."""

    zoom_requested = pyqtSignal(str)

    def __init__(self, instance_id: str, display_name: str, text: str, attention: bool, parent=None) -> None:
        super().__init__(parent)
        label = QLabel(f"{display_name} — {text}")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        label.setWordWrap(True)
        if attention:
            label.setStyleSheet(ATTENTION_STYLE)
        elif text == NO_STATUS_TEXT:
            label.setStyleSheet("color: gray;")

        zoom_button = QPushButton("\U0001f441")  # 👁
        zoom_button.setFixedWidth(28)
        zoom_button.setToolTip("Zoom/pan to this widget")
        zoom_button.clicked.connect(lambda: self.zoom_requested.emit(instance_id))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(label, stretch=1)
        layout.addWidget(zoom_button)
        self.label = label


class ClaudeDeskStatusWidget(QWidget):
    """Lists every live Claude (Desk) instance with its latest published
    status. Membership is polled (no push exists for widget placement/
    removal); status arrives by subscription to CLAUDE_DESK_STATUS_EVENT.
    See plans/claude-desk-status-events-and-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._statuses: dict[str, dict] = {}
        self._subscription: EventSubscription | None = None

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._list = QListWidget()

        layout = QVBoxLayout(self)
        layout.addWidget(self._status_label)
        layout.addWidget(self._list, stretch=1)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh(initial=True)

    def bind_event_mediator(self, instance_id: str, mediator) -> None:
        self._subscription = EventSubscription(mediator, instance_id, names=[CLAUDE_DESK_STATUS_EVENT], parent=self)
        self._subscription.message_received.connect(self._on_mediated_event)

    def _on_mediated_event(self, name: str, payload: object, sender_instance_id: str) -> None:
        if name == CLAUDE_DESK_STATUS_EVENT and isinstance(payload, dict):
            self._statuses[sender_instance_id] = payload
            self._refresh(initial=True)

    def _instance_ids(self) -> list[str]:
        window = current_context.get_main_window()
        if window is None:
            return []
        widgets = window.get_state_dict().get("widgets", [])
        return [w["instance_id"] for w in widgets if w.get("widget_id") == CLAUDE_DESK_WIDGET_ID]

    def _refresh(self, initial: bool = False) -> None:
        if not initial and not self.isVisible():
            return
        instance_ids = self._instance_ids()
        # Forget instances that are gone.
        self._statuses = {iid: status for iid, status in self._statuses.items() if iid in instance_ids}

        resolver = current_context.get_widget_display_name_resolver()
        rows = []
        for instance_id in instance_ids:
            text, attention = describe_status(self._statuses.get(instance_id))
            name = resolver(instance_id) if resolver is not None else instance_id
            rows.append((not attention, name, instance_id, text, attention))
        rows.sort(key=lambda row: (row[0], row[1]))

        self._list.clear()
        if not rows:
            self._status_label.setText(NO_INSTANCES_STATUS)
            return
        for _key, name, instance_id, text, attention in rows:
            row = _InstanceRow(instance_id, name, text, attention)
            row.zoom_requested.connect(self._on_zoom_requested)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
        waiting = sum(1 for row in rows if row[4])
        self._status_label.setText(f"{len(rows)} instance(s), {waiting} waiting on you.")

    def _on_zoom_requested(self, instance_id: str) -> None:
        zoomer = current_context.get_widget_zoomer()
        if zoomer is not None:
            zoomer(instance_id)


def build() -> QWidget:
    return ClaudeDeskStatusWidget()
