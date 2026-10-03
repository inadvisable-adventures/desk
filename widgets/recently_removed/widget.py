import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.recently_removed import RECENTLY_REMOVED_CHANGED_EVENT
from desk.shell import current_context
from desk.shell.event_broker import EventSubscription

EMPTY_STATUS = "Nothing has been removed recently."
NOT_CONNECTED_STATUS = "Not yet connected to Desk."


def relative_time(removed_at: float, now: float | None = None) -> str:
    seconds = max(0, int((time.time() if now is None else now) - removed_at))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


class _Row(QWidget):
    """One tombstone: "{label} ({kind}) -- {relative time}" and Revive."""

    revive_requested = pyqtSignal(str)

    def __init__(self, entry: dict, parent=None) -> None:
        super().__init__(parent)
        self.entry = entry
        label = QLabel(f"{entry.get('label', '')} ({entry.get('kind', '')}) — {relative_time(entry.get('removed_at', 0))}")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        label.setWordWrap(True)
        self.label = label
        self.revive_button = QPushButton("Revive")
        self.revive_button.clicked.connect(lambda: self.revive_requested.emit(entry["instance_id"]))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(label, stretch=1)
        layout.addWidget(self.revive_button)


class RecentlyRemovedWidget(QWidget):
    """Lists recently removed widget instances with a Revive button each
    (TODO 454d718). Loaded once from the main window, then replaced from
    each change event. See plans/recently-removed-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries: list[dict] = []
        self._subscription: EventSubscription | None = None

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._clear_button = QPushButton("Clear all")
        self._clear_button.clicked.connect(self._clear)
        self._list = QListWidget()

        top = QHBoxLayout()
        top.addWidget(self._status_label, stretch=1)
        top.addWidget(self._clear_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._list, stretch=1)

        window = current_context.get_main_window()
        self._set_entries(window.get_recently_removed() if window is not None else [], connected=window is not None)

    def bind_event_mediator(self, instance_id: str, mediator) -> None:
        self._subscription = EventSubscription(mediator, instance_id, names=[RECENTLY_REMOVED_CHANGED_EVENT], parent=self)
        self._subscription.message_received.connect(self._on_mediated_event)

    def _on_mediated_event(self, name: str, payload: object, _sender: str) -> None:
        if name == RECENTLY_REMOVED_CHANGED_EVENT and isinstance(payload, dict):
            self._set_entries(payload.get("entries", []))

    def _set_entries(self, entries: list[dict], connected: bool = True) -> None:
        self._entries = list(entries)
        self._list.clear()
        for entry in self._entries:
            row = _Row(entry)
            row.revive_requested.connect(self._revive)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
        self._clear_button.setEnabled(bool(self._entries))
        if not connected:
            self._status_label.setText(NOT_CONNECTED_STATUS)
        elif not self._entries:
            self._status_label.setText(EMPTY_STATUS)
        else:
            self._status_label.setText(f"{len(self._entries)} recently removed.")

    def _revive(self, instance_id: str) -> None:
        window = current_context.get_main_window()
        if window is not None:
            window.revive_removed_widget(instance_id)

    def _clear(self) -> None:
        if not self._confirm_clear():
            return
        window = current_context.get_main_window()
        if window is not None:
            window.clear_recently_removed()

    def _confirm_clear(self) -> bool:
        """Split out so headless verification can monkeypatch just this one
        method -- mirrors widgets/event_log/widget.py's _confirm_clear (the
        desk-internal popups service, not a QMessageBox)."""
        opener = current_context.get_popup_opener()
        if opener is None:
            return False
        return (
            opener(
                "Clear Recently Removed",
                "Forget every recently removed widget? Their saved state can't be revived afterwards.",
                ["Yes", "No"],
                "No",
            )
            == "Yes"
        )


def build() -> QWidget:
    return RecentlyRemovedWidget()
