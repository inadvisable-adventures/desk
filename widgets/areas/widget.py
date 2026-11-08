from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.desks import AREAS_CHANGED_EVENT
from desk.shell import current_context
from desk.shell.event_broker import EventSubscription

EMPTY_STATUS = "No areas yet. Add one."
NOT_CONNECTED_STATUS = "Not yet connected to Desk."
UNTITLED = "(untitled area)"
_AREA_ID_ROLE = Qt.ItemDataRole.UserRole


class AreasWidget(QWidget):
    """Lists the desk's areas (TODO 747806b), live from `desk.areas.changed`.
    Click a row to view that area; Add / Rename / Delete act on the selected
    row. See plans/areas-list-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._areas: list[dict] = []
        self._subscription: EventSubscription | None = None
        self._pending_edit: str | None = None  # an area_id whose title to start editing once it shows up

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemChanged.connect(self._on_item_changed)

        self._add_button = QPushButton("Add")
        self._add_button.clicked.connect(self._add)
        self._rename_button = QPushButton("Rename")
        self._rename_button.clicked.connect(self._rename)
        self._delete_button = QPushButton("Delete")
        self._delete_button.clicked.connect(self._delete)
        buttons = QHBoxLayout()
        buttons.addWidget(self._add_button)
        buttons.addWidget(self._rename_button)
        buttons.addWidget(self._delete_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._status_label)
        layout.addWidget(self._list, stretch=1)
        layout.addLayout(buttons)

        window = current_context.get_main_window()
        self._set_areas(window.list_areas() if window is not None else [], connected=window is not None)

    def bind_event_mediator(self, instance_id: str, mediator) -> None:
        self._subscription = EventSubscription(mediator, instance_id, names=[AREAS_CHANGED_EVENT], parent=self)
        self._subscription.message_received.connect(self._on_mediated_event)

    def _on_mediated_event(self, name: str, payload: object, _sender: str) -> None:
        if name == AREAS_CHANGED_EVENT and isinstance(payload, dict):
            self._set_areas(payload.get("areas", []))

    def _set_areas(self, areas: list[dict], connected: bool = True) -> None:
        selected = self._selected_area_id()
        self._areas = list(areas)
        self._list.blockSignals(True)
        self._list.clear()
        for area in self._areas:
            item = QListWidgetItem(area.get("title") or UNTITLED)
            item.setData(_AREA_ID_ROLE, area["area_id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(f"{area.get('width', 0):.0f} x {area.get('height', 0):.0f} at ({area.get('x', 0):.0f}, {area.get('y', 0):.0f})")
            self._list.addItem(item)
            if area["area_id"] == selected:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        has_rows = bool(self._areas)
        self._rename_button.setEnabled(has_rows)
        self._delete_button.setEnabled(has_rows)
        self._add_button.setEnabled(connected)
        if not connected:
            self._status_label.setText(NOT_CONNECTED_STATUS)
        elif not has_rows:
            self._status_label.setText(EMPTY_STATUS)
        else:
            self._status_label.setText(f"{len(self._areas)} area(s). Click one to view it.")
        if self._pending_edit is not None:
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item.data(_AREA_ID_ROLE) == self._pending_edit:
                    self._pending_edit = None
                    self._list.setCurrentItem(item)
                    self._list.editItem(item)
                    break

    def _selected_area_id(self) -> str | None:
        item = self._list.currentItem()
        return item.data(_AREA_ID_ROLE) if item is not None else None

    def _window(self):
        return current_context.get_main_window()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        window = self._window()
        if window is not None:
            window.view_area(item.data(_AREA_ID_ROLE))

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """An in-place title edit finished."""
        window = self._window()
        if window is None:
            return
        area_id = item.data(_AREA_ID_ROLE)
        title = item.text().strip()
        current = next((a for a in self._areas if a["area_id"] == area_id), None)
        if current is None or title == (current.get("title") or UNTITLED):
            return
        if not title:
            self._set_areas(window.list_areas())  # an empty title is not a rename: put the old one back
            return
        window.update_area(area_id, title=title)

    def _add(self) -> None:
        window = self._window()
        if window is None:
            return
        try:
            area = window.create_area(title=f"Area {len(self._areas) + 1}")
        except ValueError:
            return
        self._pending_edit = area["area_id"]
        self._set_areas(window.list_areas())  # in case the event has not arrived yet

    def _rename(self) -> None:
        item = self._list.currentItem()
        if item is not None:
            self._list.editItem(item)

    def _delete(self) -> None:
        area_id = self._selected_area_id()
        window = self._window()
        if area_id is None or window is None or not self._confirm_delete():
            return
        window.delete_area(area_id)

    def _confirm_delete(self) -> bool:
        """Split out so headless verification can monkeypatch just this one
        method -- mirrors widgets/recently_removed's _confirm_clear."""
        opener = current_context.get_popup_opener()
        if opener is None:
            return False
        return (
            opener(
                "Delete Area",
                "Delete this area? Widgets inside it are not affected.",
                ["Yes", "No"],
                "No",
            )
            == "Yes"
        )


def build() -> QWidget:
    return AreasWidget()
