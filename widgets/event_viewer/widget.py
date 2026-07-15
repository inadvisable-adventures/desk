import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFormLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from desk.event_mediator import MediatedEvent

PLACEHOLDER_TEXT = "No event selected -- open this from the Event Log widget by double-clicking a row."
_NO_VALUE = "—"


def _format_payload(payload: object) -> str:
    """Pretty-printed (multi-line, indented) JSON, the opposite of
    widgets/event_log/widget.py's own _format_payload, which
    deliberately compacts to one line for its table row -- this widget
    exists specifically to show the full, readable form. `None` (no
    payload at all) is an empty string, matching that function's own
    `None` handling."""
    return "" if payload is None else json.dumps(payload, indent=2)


class EventViewerWidget(QWidget):
    """Shows one mediated event's (desk.event_mediator.MediatedEvent,
    TODO 6f9c51b) full detail -- timestamp, event name, sender instance
    id, and its payload pretty-printed in full -- rather than the Event
    Log widget's own truncated single-line table summary. Opened by
    double-clicking a row in the Event Log widget (TODO 0d2ebc1), via
    set_event -- duck-typed the same way set_file is on the Editor/
    Markdown widgets, so the opener doesn't need to import this class
    directly. Placed standalone (e.g. from the spawn menu) with no event
    set yet, shows a placeholder instead. Deliberately has no
    persistence: this is a point-in-time detail view of one already
    -logged event, not something whose content should survive a reload
    the way an editor's open file does."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._timestamp_label = QLabel(_NO_VALUE)
        self._name_label = QLabel(_NO_VALUE)
        self._sender_label = QLabel(_NO_VALUE)
        for label in (self._timestamp_label, self._name_label, self._sender_label):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form = QFormLayout()
        form.addRow("Timestamp:", self._timestamp_label)
        form.addRow("Event:", self._name_label)
        form.addRow("Sender:", self._sender_label)

        self._payload_view = QPlainTextEdit()
        self._payload_view.setReadOnly(True)
        self._payload_view.setPlainText(PLACEHOLDER_TEXT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(form)
        layout.addWidget(QLabel("Payload:"))
        layout.addWidget(self._payload_view, stretch=1)

    def set_event(self, event: MediatedEvent) -> None:
        self._timestamp_label.setText(event.timestamp)
        self._name_label.setText(event.name)
        self._sender_label.setText(event.sender_instance_id)
        self._payload_view.setPlainText(_format_payload(event.payload))


def build() -> QWidget:
    return EventViewerWidget()
