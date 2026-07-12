from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from desk.widgets import WidgetInfo

WIDGET_ID_ROLE = Qt.ItemDataRole.UserRole

# (group label, collapsed by default) -- order here is also display order.
_GROUPS = (("Active", False), ("Deprecated", True))


class WidgetSpawnMenu(QWidget):
    """A small typeable-filter popup listing the widget catalog, shown on
    right-click over the Workspace Canvas (see WorkspaceView
    .contextMenuEvent). Qt has no built-in menu with a live-filterable
    query, so this is a dedicated popup widget rather than a QMenu — see
    design-docs/widget-ux.md.

    Entries are grouped into collapsible "Active"/"Deprecated" sections
    (TODO ed483e2) via a QTreeWidget with two persistent, non-selectable
    top-level group items — matches the Markdown (Extended) widget's own
    existing use of QTreeWidget for a similar grouped-list job, rather
    than introducing a new pattern. "Active" starts expanded,
    "Deprecated" starts collapsed; each group's expand state is only
    ever changed by the user (re-populating on every filter keystroke
    only touches each group's children, never recreates the group
    headers themselves, so a manually-toggled state survives typing)."""

    widget_chosen = pyqtSignal(str)

    def __init__(self, catalog: dict[str, WidgetInfo], parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._catalog = catalog

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Add widget…")
        self._filter.textChanged.connect(self._apply_filter)
        self._filter.installEventFilter(self)
        layout.addWidget(self._filter)

        self._list = QTreeWidget()
        self._list.setHeaderHidden(True)
        self._list.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self._list)

        self._group_items: dict[str, QTreeWidgetItem] = {}
        for label, collapsed_by_default in _GROUPS:
            group_item = QTreeWidgetItem([label])
            group_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            self._list.addTopLevelItem(group_item)
            group_item.setExpanded(not collapsed_by_default)
            self._group_items[label] = group_item

        self._populate(sorted(catalog.items(), key=lambda pair: pair[1].name))
        self._filter.setFocus()

    def _populate(self, entries: list[tuple[str, WidgetInfo]]) -> None:
        for group_item in self._group_items.values():
            group_item.takeChildren()

        for widget_id, info in entries:
            label = "Deprecated" if info.deprecated else "Active"
            item = QTreeWidgetItem([info.name])
            item.setData(0, WIDGET_ID_ROLE, widget_id)
            self._group_items[label].addChild(item)

        for group_item in self._group_items.values():
            group_item.setHidden(group_item.childCount() == 0)

        visible = self._visible_entries()
        if visible:
            self._list.setCurrentItem(visible[0])

    def _visible_entries(self) -> list[QTreeWidgetItem]:
        """Leaf (non-group) items reachable by keyboard nav right now --
        skips group headers themselves, and skips any entry sitting
        under a currently-collapsed or hidden (zero-match) group."""
        result = []
        for group_item in self._group_items.values():
            if group_item.isHidden() or not group_item.isExpanded():
                continue
            for i in range(group_item.childCount()):
                result.append(group_item.child(i))
        return result

    def _apply_filter(self, text: str) -> None:
        query = text.lower()
        matches = [
            (widget_id, info)
            for widget_id, info in self._catalog.items()
            if query in info.name.lower() or query in widget_id.lower()
        ]
        self._populate(sorted(matches, key=lambda pair: pair[1].name))

    def _on_item_activated(self, item: QTreeWidgetItem) -> None:
        widget_id = item.data(0, WIDGET_ID_ROLE)
        if widget_id is None:
            return  # a group header, not a real entry
        self._activate(widget_id)

    def _activate(self, widget_id: str) -> None:
        self.widget_chosen.emit(widget_id)
        self.close()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._filter and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            visible = self._visible_entries()
            if key == Qt.Key.Key_Down:
                self._move_current(visible, 1)
                return True
            if key == Qt.Key.Key_Up:
                self._move_current(visible, -1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                current = self._list.currentItem()
                if current is not None and current in visible:
                    self._activate(current.data(0, WIDGET_ID_ROLE))
                return True
            if key == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)

    def _move_current(self, visible: list[QTreeWidgetItem], delta: int) -> None:
        if not visible:
            return
        current = self._list.currentItem()
        index = visible.index(current) if current in visible else -1
        new_index = max(0, min(len(visible) - 1, index + delta))
        self._list.setCurrentItem(visible[new_index])
