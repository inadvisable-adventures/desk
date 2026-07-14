"""Qt-friendly wrapper around `desk.event_mediator.EventMediator` for a
`kind: "python"` widget (TODO 6f9c51b) -- the shared mediator is
queue/blocking-based, which a GUI-thread Qt widget can't call directly
without freezing the UI. `EventSubscription` wraps this the same way
`desk.hotreload.HotReloadBroker`/`desk.file_watch.SingleFileWatcher`
already wrap a non-Qt-native source into Qt signals, except delivery here
never needs to *block* anything (unlike `desk.shell.bridge.GuiBridge`,
which exists because its caller genuinely needs to wait for a GUI-thread
result) -- so a lightweight repeating `QTimer` polling the mediator's
non-blocking `drain()` is enough; no background thread or cross-thread
signal marshalling needed.

A widget opts in by defining `bind_event_mediator(self, instance_id,
mediator)`, duck-typed and called generically for every placed python
widget by `desk.shell.window.DeskWindow._bind_event_mediator` -- see that
method and `_bind_claude_widget` for the established shape this follows.
"""

from collections.abc import Iterable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from desk.event_mediator import EventMediator

DEFAULT_POLL_INTERVAL_MS = 150


class EventSubscription(QObject):
    """Subscribes `instance_id` to `names` on construction, then polls
    `mediator.drain(instance_id)` every `poll_interval_ms` and re-emits
    each arrived message as `message_received`. Call `publish`/
    `subscribe`/`unsubscribe` to send/adjust subscriptions."""

    message_received = pyqtSignal(str, object, str)  # name, payload, sender_instance_id

    def __init__(
        self,
        mediator: EventMediator,
        instance_id: str,
        names: Iterable[str] = (),
        parent: QObject | None = None,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ) -> None:
        super().__init__(parent)
        self._mediator = mediator
        self._instance_id = instance_id
        for name in names:
            mediator.subscribe(instance_id, name)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(poll_interval_ms)
        # Deliberately a plain closure over `mediator`/`instance_id` (no
        # reference to `self`), not a bound method -- connecting an
        # object's own `destroyed` signal to one of its own bound methods
        # never actually fires (see LEARNINGS.md's TerminalWidget entry,
        # the same trap, same fix shape).
        self.destroyed.connect(lambda: mediator.unsubscribe_all(instance_id))

    def publish(self, name: str, payload: object = None) -> None:
        self._mediator.publish(name, payload, self._instance_id)

    def subscribe(self, name: str) -> None:
        self._mediator.subscribe(self._instance_id, name)

    def unsubscribe(self, name: str) -> None:
        self._mediator.unsubscribe(self._instance_id, name)

    def _poll(self) -> None:
        for event in self._mediator.drain(self._instance_id):
            self.message_received.emit(event.name, event.payload, event.sender_instance_id)

    def stop(self) -> None:
        self._timer.stop()
        self._mediator.unsubscribe_all(self._instance_id)
