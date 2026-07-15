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

from desk.shell import current_context

POLL_INTERVAL_MS = 1000
NOT_CONNECTED_STATUS = "Not yet connected to the event channel."
EMPTY_STATUS = "No widgets are currently registered."


class _SubscriberRow(QWidget):
    """One registered instance: a label ("{display name} — {event
    names}") plus a 👁 button firing zoom_requested(instance_id) -- the
    same visual affordance and action as a placed widget's own titlebar
    eye button (TODO 33d3e8d), reached here via
    current_context.get_widget_zoomer() rather than the WidgetFrame
    chrome directly, since this is ordinary widget content, not shell
    chrome."""

    zoom_requested = pyqtSignal(str)

    def __init__(self, instance_id: str, display_name: str, names: set[str], parent=None) -> None:
        super().__init__(parent)
        self._instance_id = instance_id

        label = QLabel(f"{display_name} — {', '.join(sorted(names))}")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        label.setWordWrap(True)

        zoom_button = QPushButton("\U0001f441")  # 👁
        zoom_button.setFixedWidth(28)
        zoom_button.setToolTip("Zoom/pan to this widget")
        zoom_button.clicked.connect(lambda: self.zoom_requested.emit(self._instance_id))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(label, stretch=1)
        layout.addWidget(zoom_button)


class EventSubscribersWidget(QWidget):
    """Lists every widget instance currently subscribed to at least one
    name on Desk's event mediator channel (TODO 6f9c51b), refreshed on a
    timer since the mediator has no signal-based "subscriptions changed"
    notification to react to instead. See
    plans/event-subscribers-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

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

        # initial=True: mirrors widgets/git_status/widget.py's own
        # reasoning -- a freshly-constructed widget isn't visible yet,
        # so the isVisible() gate below (skipping *later* polls for a
        # widget nobody's looking at) must not also suppress this very
        # first refresh, which would otherwise leave the widget blank
        # until the first timer tick.
        self._refresh(initial=True)

    def _refresh(self, initial: bool = False) -> None:
        if not initial and not self.isVisible():
            return

        mediator = current_context.get_event_mediator()
        if mediator is None:
            self._status_label.setText(NOT_CONNECTED_STATUS)
            self._list.clear()
            return

        resolver = current_context.get_widget_display_name_resolver()
        subscriptions = {
            instance_id: names for instance_id, names in mediator.list_subscriptions().items() if names
        }

        self._list.clear()
        if not subscriptions:
            self._status_label.setText(EMPTY_STATUS)
            return

        rows = [
            (resolver(instance_id) if resolver is not None else instance_id, instance_id, names)
            for instance_id, names in subscriptions.items()
        ]
        rows.sort(key=lambda row: row[0])
        for display_name, instance_id, names in rows:
            row = _SubscriberRow(instance_id, display_name, names)
            row.zoom_requested.connect(self._on_zoom_requested)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)

        self._status_label.setText(f"{len(subscriptions)} widget(s) registered.")

    def _on_zoom_requested(self, instance_id: str) -> None:
        zoomer = current_context.get_widget_zoomer()
        if zoomer is not None:
            zoomer(instance_id)


def build() -> QWidget:
    return EventSubscribersWidget()
