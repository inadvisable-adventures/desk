from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from desk.claude_history_view import KINDS, HistoryView
from desk.claude_session import CLAUDE_DESK_TASK_LOG_EVENT
from desk.shell.event_broker import EventSubscription

UNSEEDED_TEXT = "No log available -- this widget is opened from a Claude (Desk) background task."


class ClaudeDeskTaskLogWidget(QWidget):
    """Read-only log of one Claude (Desk) background task: a HistoryView
    seeded once with the task's accumulated entries (by
    DeskWindow.open_background_task_log -> seed()), then kept live by the
    task-log event, filtered to this task and its source instance. See
    plans/claude-desk-task-panel-and-log-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._source_instance_id: str | None = None
        self._task_id: str | None = None
        self._subscription: EventSubscription | None = None

        self._title = QLabel(UNSEEDED_TEXT)
        self._title.setWordWrap(True)
        self._title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._history = HistoryView()

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self._history, stretch=1)

    def bind_event_mediator(self, instance_id: str, mediator) -> None:
        self._subscription = EventSubscription(mediator, instance_id, names=[CLAUDE_DESK_TASK_LOG_EVENT], parent=self)
        self._subscription.message_received.connect(self._on_mediated_event)

    def seed(self, source_instance_id: str, task_id: str, title: str, entries: list[dict]) -> None:
        self._source_instance_id = source_instance_id
        self._task_id = task_id
        self._title.setText(title)
        for entry in entries:
            self._add(entry)

    def _on_mediated_event(self, name: str, payload: object, sender_instance_id: str) -> None:
        if name != CLAUDE_DESK_TASK_LOG_EVENT or not isinstance(payload, dict):
            return
        if sender_instance_id != self._source_instance_id or payload.get("task_id") != self._task_id:
            return
        entry = payload.get("entry")
        if isinstance(entry, dict):
            self._add(entry)

    def _add(self, entry: dict) -> None:
        kind = entry.get("kind", "notice")
        self._history.add_entry(
            kind if kind in KINDS else "notice",
            str(entry.get("text", "")),
            ts=entry.get("ts"),
            turn_id=entry.get("turn_id"),
        )


def build() -> QWidget:
    return ClaudeDeskTaskLogWidget()
