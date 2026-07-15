import json

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.shell.event_broker import EventSubscription

NAME_PLACEHOLDER = "event.name"
PAYLOAD_PLACEHOLDER = '{"key": "value"}  or plain text  (optional)'


def _parse_payload(text: str) -> tuple[object, bool]:
    """Empty -> (None, True). Valid JSON -> (parsed value, True). Invalid
    JSON -> (the raw text as a string payload, False) -- a tester typing
    unquoted plain text (`ping`, not `"ping"`) is a common, reasonable
    expectation for a quick manual test; the bool tells the caller which
    branch was taken, for the status label."""
    text = text.strip()
    if not text:
        return None, True
    try:
        return json.loads(text), True
    except ValueError:
        return text, False


class EventPosterWidget(QWidget):
    """A general-purpose tool for manually publishing a named message on
    Desk's event mediator channel (TODO 6f9c51b) -- a hand-operated
    companion to the read-only Event Log widget (widgets/event_log/),
    useful for testing/demoing another widget's subscription handling
    without scripting a real publisher. See plans/event-poster-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._subscription: EventSubscription | None = None

        self._name_field = QLineEdit()
        self._name_field.setPlaceholderText(NAME_PLACEHOLDER)
        self._name_field.returnPressed.connect(self._publish)

        self._payload_field = QPlainTextEdit()
        self._payload_field.setPlaceholderText(PAYLOAD_PLACEHOLDER)
        self._payload_field.installEventFilter(self)

        form = QFormLayout()
        form.addRow("Name:", self._name_field)
        form.addRow("Payload:", self._payload_field)

        self._publish_button = QPushButton("Publish")
        self._publish_button.clicked.connect(self._publish)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self._publish_button)

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(form, stretch=1)
        layout.addLayout(button_row)
        layout.addWidget(self._status_label)

        self._refresh_enabled_state()

    # --- event mediator binding -----------------------------------

    def bind_event_mediator(self, instance_id: str, mediator) -> None:
        """Duck-typed hook (TODO 6f9c51b) -- see
        desk.shell.window.DeskWindow._bind_event_mediator. No names are
        subscribed: this widget only ever sends, never receives; the
        subscription object is used purely to get a correctly
        -identified `.publish(name, payload)` call (the real sender
        instance id, which current_context.get_event_mediator() alone
        can't provide)."""
        self._subscription = EventSubscription(mediator, instance_id, parent=self)
        self._refresh_enabled_state()

    def _refresh_enabled_state(self) -> None:
        bound = self._subscription is not None
        self._publish_button.setEnabled(bound)
        if not bound:
            self._status_label.setText("Not yet connected to the event channel.")

    # --- publish -----------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if obj is self._payload_field and event.type() == QEvent.Type.KeyPress:
            # Multiline field: plain Return/Enter inserts a newline like
            # any normal multiline editing -- only Ctrl+Return/Ctrl+Enter
            # publishes (same convention as widgets/todo/widget.py's
            # item editor, TODO 8db7891).
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self._publish()
                    return True
                return False
        return super().eventFilter(obj, event)

    def _publish(self) -> None:
        if self._subscription is None:
            self._status_label.setText("Not yet connected to the event channel.")
            return
        name = self._name_field.text().strip()
        if not name:
            self._status_label.setText("Enter an event name first.")
            return
        payload, was_json = _parse_payload(self._payload_field.toPlainText())
        self._subscription.publish(name, payload)
        if payload is None:
            kind = "no payload"
        elif was_json:
            kind = "JSON payload"
        else:
            kind = "text payload"
        self._status_label.setText(f'Published "{name}" ({kind}).')


def build() -> QWidget:
    return EventPosterWidget()
