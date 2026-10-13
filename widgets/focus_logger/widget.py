"""Focus Logger widget (TODO 00ea6b3; plans/focus-logger-widget.md;
investigations/text-focus-stability.md).

The one piece of UI for `desk.focus_logger.FocusLogger` (TODO `b4d99a1`,
off by default, owned by `DeskWindow`, reached via
`current_context.get_focus_logger()`): a Start/Stop button, a live view
of new `desk-focus` log entries (polled from the same `WidgetLogStore`
the `desk_query_widget_log` MCP tool reads -- the store has no change
signal, by design), and an automatic on/off bracket around the user's
own dictation via the `recording`/`stopped_recording` desk events, so
entries line up with a timecoded transcript.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from desk.focus_logger import FOCUS_LOG_NAME, FocusLogger
from desk.shell import current_context
from desk.shell.event_broker import EventSubscription
from desk.widget_logs import RECORDING_EVENT, STOPPED_RECORDING_EVENT, format_time_iso, now_ms

POLL_INTERVAL_MS = 500
NO_LOGGER_TEXT = "Focus logging isn't available in this Desk."
ON_STYLE = "color: #3fae5a; font-weight: 600;"


def _stop_if_started_here(logger: FocusLogger, state: dict) -> None:
    """`destroyed` closure target -- a module-level function touching
    neither `self` nor any Qt child of this widget, since connecting an
    object's own `destroyed` signal to one of its own bound methods
    never actually fires (LEARNINGS.md). `logger`/`state` are plain
    values captured at connect time, not `self`; `state` is a dict
    shared with (and mutated by) the live widget instance, so it still
    reflects the truth right up to teardown."""
    if state["started_by_button"] and logger.is_enabled():
        logger.disable()


class FocusLoggerWidget(QWidget):
    """`_auto_started` is true only while a `recording` event -- not the
    button -- is the reason this instance's own `enable()` call turned
    the logger on; see plans/focus-logger-widget.md's "Key design
    decisions" for why a manually-started session must survive the
    matching `stopped_recording` and vice versa."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._logger: FocusLogger | None = current_context.get_focus_logger()
        self._store = current_context.get_widget_log_store()
        self._subscription: EventSubscription | None = None
        self._auto_started = False
        # Plain dict, not an attribute read by the destroyed-closure through
        # self -- see _stop_if_started_here.
        self._state = {"started_by_button": False}
        self._last_seen_ms: int | None = None

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._toggle_button = QPushButton()
        self._toggle_button.clicked.connect(self._on_toggle_clicked)

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)

        top = QHBoxLayout()
        top.addWidget(self._status_label, stretch=1)
        top.addWidget(self._toggle_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self._view, stretch=1)

        if self._logger is None:
            self._status_label.setText(NO_LOGGER_TEXT)
            self._toggle_button.setEnabled(False)
            return

        # "Live" starts from now -- never backfill whatever the log already
        # held (e.g. an earlier DESK_FOCUS_LOG=1 session) into a freshly
        # placed widget's view.
        self._last_seen_ms = now_ms()
        self._refresh_status()
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

        logger, state = self._logger, self._state
        self.destroyed.connect(lambda: _stop_if_started_here(logger, state))

    # --- event mediator ----------------------------------------------------

    def bind_event_mediator(self, instance_id: str, mediator) -> None:
        self._subscription = EventSubscription(
            mediator, instance_id, names=[RECORDING_EVENT, STOPPED_RECORDING_EVENT], parent=self
        )
        self._subscription.message_received.connect(self._on_mediated_event)

    def _on_mediated_event(self, name: str, payload: object, sender_instance_id: str) -> None:
        if self._logger is None or not isinstance(payload, dict):
            return
        recording_id = payload.get("recording_id")
        if name == RECORDING_EVENT:
            was_enabled = self._logger.is_enabled()
            self._logger.enable(tag=recording_id)
            self._auto_started = not was_enabled
        elif name == STOPPED_RECORDING_EVENT:
            if self._auto_started:
                self._logger.disable()
                self._state["started_by_button"] = False
            else:
                self._logger.set_tag(None)  # a manual session outlives the recording
            self._auto_started = False
        self._refresh_status()

    # --- button / live view -------------------------------------------------

    def _on_toggle_clicked(self) -> None:
        if self._logger is None:
            return
        if self._logger.is_enabled():
            self._logger.disable()
            self._state["started_by_button"] = False
            self._auto_started = False
        else:
            self._logger.enable()
            self._state["started_by_button"] = True
        self._refresh_status()

    def _poll(self) -> None:
        self._refresh_status()
        if self._store is None:
            return
        start_ms = (self._last_seen_ms + 1) if self._last_seen_ms is not None else 0
        entries = self._store.query(FOCUS_LOG_NAME, start_ms=start_ms, limit=200)
        for entry in entries:
            self._view.appendPlainText(f"{format_time_iso(entry.t)}  {entry.text}")
            self._last_seen_ms = entry.t
        if entries:
            scrollbar = self._view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _refresh_status(self) -> None:
        if self._logger is None:
            return
        on = self._logger.is_enabled()
        tag = self._logger.tag
        text = "Logging ON" if on else "Logging off"
        if on and tag:
            text += f" (rec={tag})"
        self._status_label.setText(text)
        self._status_label.setStyleSheet(ON_STYLE if on else "")
        self._toggle_button.setText("Stop" if on else "Start")


def build() -> QWidget:
    return FocusLoggerWidget()
