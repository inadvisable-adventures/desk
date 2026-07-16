"""Side by Side (TODO d28885f) -- a container widget with two fixed
"slots", each optionally holding one kind:"python" child widget
instance, laid out in a QSplitter with a Swap button (exchanges which
splitter position each slot occupies, without touching either slot's
own identity) and an orientation toggle. Inter-widget communication
uses the existing mediated event system (desk.event_mediator) -- this
container doesn't invent a new protocol, it just ensures both slots are
properly bound to the shared bus with stable, persisted instance ids,
the same as any other placed widget. See
plans/side-by-side-widget-container.md."""

import logging
import uuid
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from desk.shell import current_context
from desk.shell.python_widget import PythonWidgetHost

logger = logging.getLogger(__name__)


class _Slot:
    """Plain data holder for one of the container's two fixed slots --
    never reassigned by Swap (see SideBySideWidget._order); a slot's own
    instance_id is minted once and reused verbatim across rebuilds/
    reloads, so any mediator subscriptions or widget-local storage a
    child keeps under it stay valid."""

    def __init__(self) -> None:
        self.widget_id: str | None = None
        self.instance_id: str | None = None
        self.host: PythonWidgetHost | None = None
        self.local_storage: dict = {}


def _catalog_entries() -> list[dict]:
    provider = current_context.get_widget_catalog_provider()
    return provider() if provider is not None else []


def _catalog_entry(widget_id: str) -> dict | None:
    for entry in _catalog_entries():
        if entry["id"] == widget_id:
            return entry
    return None


class SideBySideWidget(QWidget):
    """See the module docstring and plans/side-by-side-widget-container.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mediator = current_context.get_event_mediator()
        self._broker = current_context.get_hot_reload_broker()
        self._slots = [_Slot(), _Slot()]
        self._order = [0, 1]
        self._orientation = Qt.Orientation.Horizontal

        self._placeholders = [self._build_placeholder(i) for i in (0, 1)]

        self._splitter = QSplitter(self._orientation)
        self._splitter.addWidget(self._placeholders[0])
        self._splitter.addWidget(self._placeholders[1])

        swap_button = QPushButton("Swap")
        swap_button.clicked.connect(self._swap)
        orientation_button = QPushButton("Orientation")
        orientation_button.clicked.connect(self._toggle_orientation)

        toolbar = QHBoxLayout()
        toolbar.addWidget(swap_button)
        toolbar.addWidget(orientation_button)
        toolbar.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._splitter, stretch=1)

        if self._broker is not None:
            self._broker.widget_changed.connect(self._on_widget_changed)

        # Captured as plain values (not `self`) -- connecting an
        # object's own `destroyed` signal to one of its own bound
        # methods silently never fires (LEARNINGS.md); mirrors the
        # `watcher = self._watcher; self.destroyed.connect(lambda:
        # watcher.stop())` idiom used throughout this codebase.
        mediator = self._mediator
        slots = self._slots

        def _teardown() -> None:
            if mediator is None:
                return
            for slot in slots:
                if slot.instance_id is not None:
                    mediator.unsubscribe_all(slot.instance_id)

        self.destroyed.connect(_teardown)

    # --- placeholder / picker UI ---------------------------------------

    def _build_placeholder(self, slot_index: int) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel(f"Slot {slot_index + 1} — choose a widget")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        combo = QComboBox()
        for entry in _catalog_entries():
            combo.addItem(entry["name"], entry["id"])
        choose_button = QPushButton("Choose")
        choose_button.clicked.connect(lambda: self._choose_widget(slot_index, combo.currentData()))
        layout.addWidget(label)
        layout.addWidget(combo)
        layout.addWidget(choose_button)
        layout.addStretch()
        return widget

    def _choose_widget(self, slot_index: int, widget_id: str | None) -> None:
        if not widget_id:
            return
        slot = self._slots[slot_index]
        if slot.instance_id is not None and self._mediator is not None:
            self._mediator.unsubscribe_all(slot.instance_id)
        slot.widget_id = widget_id
        slot.instance_id = uuid.uuid4().hex[:8]
        slot.local_storage = {}
        self._build_slot_content(slot_index)

    # --- building slot content ------------------------------------------

    def _build_slot_content(self, slot_index: int) -> None:
        slot = self._slots[slot_index]
        entry = _catalog_entry(slot.widget_id) if slot.widget_id else None
        if entry is None or self._broker is None:
            return
        old_host = slot.host
        host = PythonWidgetHost(slot.widget_id, Path(entry["path"]), entry["entry"], self._broker)
        slot.host = host
        self._bind_slot_content(slot)
        self._refresh_splitter_widgets()
        if old_host is not None:
            old_host.deleteLater()

    def _bind_slot_content(self, slot: "_Slot") -> None:
        content = slot.host.current if slot.host is not None else None
        if content is None:
            return
        if slot.instance_id is not None and self._mediator is not None and hasattr(content, "bind_event_mediator"):
            content.bind_event_mediator(slot.instance_id, self._mediator)
        if slot.local_storage and hasattr(content, "set_widget_local_storage"):
            try:
                content.set_widget_local_storage(slot.local_storage)
            except Exception:
                logger.error(
                    "Failed to restore local storage for slot with widget %s", slot.widget_id, exc_info=True
                )

    def _on_widget_changed(self, changed_widget_id: str) -> None:
        """A slot's own PythonWidgetHost already rebuilt its content in
        response to this same broker signal (that's the host's job) --
        this just re-runs this container's own separate bookkeeping
        (mediator binding, local storage restore) against the freshly
        -built `.current`, otherwise only ever done right after a host
        is first constructed."""
        for slot in self._slots:
            if slot.widget_id == changed_widget_id and slot.host is not None:
                self._bind_slot_content(slot)

    # --- swap / orientation -----------------------------------------------

    def _widget_for_slot(self, slot_index: int) -> QWidget:
        slot = self._slots[slot_index]
        return slot.host if slot.host is not None else self._placeholders[slot_index]

    def _refresh_splitter_widgets(self) -> None:
        for position, slot_index in enumerate(self._order):
            widget = self._widget_for_slot(slot_index)
            if self._splitter.widget(position) is not widget:
                self._splitter.insertWidget(position, widget)

    def _swap(self) -> None:
        self._order = [self._order[1], self._order[0]]
        self._refresh_splitter_widgets()

    def _toggle_orientation(self) -> None:
        self._orientation = (
            Qt.Orientation.Vertical if self._orientation == Qt.Orientation.Horizontal else Qt.Orientation.Horizontal
        )
        self._splitter.setOrientation(self._orientation)

    # --- widget-local storage (TODO fb76057) -------------------------------

    def get_widget_local_storage(self) -> dict:
        """Recurses into each occupied slot's own content
        get_widget_local_storage() (if it has one) since the child
        never gets its own top-level WidgetFrame/WidgetState -- without
        this, a slot's child (e.g. an Editor's open file) would forget
        its own state every Desk reload."""
        slots_data = []
        for slot in self._slots:
            local_storage = slot.local_storage
            content = slot.host.current if slot.host is not None else None
            if content is not None and hasattr(content, "get_widget_local_storage"):
                try:
                    local_storage = content.get_widget_local_storage()
                except Exception:
                    logger.error(
                        "Failed to capture local storage for slot with widget %s", slot.widget_id, exc_info=True
                    )
            slots_data.append(
                {"widget_id": slot.widget_id, "instance_id": slot.instance_id, "local_storage": local_storage}
            )
        return {
            "orientation": "horizontal" if self._orientation == Qt.Orientation.Horizontal else "vertical",
            "order": list(self._order),
            "slots": slots_data,
        }

    def set_widget_local_storage(self, data: dict) -> None:
        orientation = data.get("orientation", "horizontal")
        self._orientation = Qt.Orientation.Horizontal if orientation == "horizontal" else Qt.Orientation.Vertical
        self._splitter.setOrientation(self._orientation)
        order = data.get("order")
        if isinstance(order, list) and sorted(order) == [0, 1]:
            self._order = list(order)
        for slot_index, slot_data in enumerate(data.get("slots", [])[:2]):
            slot = self._slots[slot_index]
            slot.widget_id = slot_data.get("widget_id")
            slot.instance_id = slot_data.get("instance_id")
            slot.local_storage = slot_data.get("local_storage", {})
            if slot.widget_id:
                self._build_slot_content(slot_index)
        self._refresh_splitter_widgets()


def build() -> QWidget:
    return SideBySideWidget()
