from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

WIDGET_ID_ROLE = Qt.ItemDataRole.UserRole


class WidgetSpawnMenu(QWidget):
    """A small typeable-filter popup listing the widget catalog, shown on
    right-click over the Workspace Canvas (see WorkspaceView
    .contextMenuEvent). Qt has no built-in menu with a live-filterable
    query, so this is a dedicated popup widget rather than a QMenu — see
    design-docs/widget-ux.md."""

    widget_chosen = pyqtSignal(str)

    def __init__(self, catalog: dict[str, str], parent=None) -> None:
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

        self._list = QListWidget()
        self._list.itemActivated.connect(self._activate_item)
        layout.addWidget(self._list)

        self._populate(sorted(catalog.items(), key=lambda pair: pair[1]))
        self._filter.setFocus()

    def _populate(self, entries: list[tuple[str, str]]) -> None:
        self._list.clear()
        for widget_id, name in entries:
            item = QListWidgetItem(name)
            item.setData(WIDGET_ID_ROLE, widget_id)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _apply_filter(self, text: str) -> None:
        query = text.lower()
        matches = [
            (widget_id, name)
            for widget_id, name in self._catalog.items()
            if query in name.lower() or query in widget_id.lower()
        ]
        self._populate(sorted(matches, key=lambda pair: pair[1]))

    def _activate_item(self, item: QListWidgetItem) -> None:
        self.widget_chosen.emit(item.data(WIDGET_ID_ROLE))
        self.close()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._filter and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self._list.setCurrentRow(min(self._list.count() - 1, self._list.currentRow() + 1))
                return True
            if key == Qt.Key.Key_Up:
                self._list.setCurrentRow(max(0, self._list.currentRow() - 1))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self._list.currentItem()
                if item is not None:
                    self._activate_item(item)
                return True
            if key == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)
