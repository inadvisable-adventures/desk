from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desk.shell import current_context

DEFAULT_ROWS = 12
DEFAULT_COLUMNS = 6
CELL_ALIGNMENT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
TSV_FILTER = "TSV (*.tsv *.tab *.txt);;All files (*)"


class SheetWidget(QWidget):
    """A basic spreadsheet backed by QTableWidget: resizable rows/columns,
    word-wrapped/clipped cells, all entries left-aligned and vertically
    centered, serialized to/from TSV. The Open/Save dialogs seed from the
    current Desk directory (desk.shell.current_context); the open file is
    not persisted across a reload (same as the editor/markdown widgets --
    the widget contract has no per-instance state payload yet, see
    PARKINGLOT.md). See plans/sheet-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_path: Path | None = None
        self._last_dir = current_context.get_current_desk_directory() or Path.home()
        self._dirty = False

        self._table = QTableWidget(DEFAULT_ROWS, DEFAULT_COLUMNS)
        self._table.setWordWrap(True)
        # Cells the user creates by typing into an empty cell are cloned
        # from this prototype, so they inherit the alignment without any
        # per-edit handling (confirmed clone() preserves textAlignment).
        prototype = QTableWidgetItem()
        prototype.setTextAlignment(CELL_ALIGNMENT)
        self._table.setItemPrototype(prototype)
        for header in (self._table.horizontalHeader(), self._table.verticalHeader()):
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._fill_empty_items()
        self._table.itemChanged.connect(self._on_item_changed)

        self._label = QLabel()
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        toolbar = QHBoxLayout()
        for text, slot in (
            ("Open", self._open_file),
            ("Save", self._save_file),
            ("Save As", self._save_file_as),
            ("Add Row", self._add_row),
            ("Add Column", self._add_column),
            ("Delete Row", self._delete_row),
            ("Delete Column", self._delete_column),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            toolbar.addWidget(button)
        toolbar.addStretch()
        toolbar.addWidget(self._label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._table, stretch=1)

        self._update_label()

    def _new_item(self, text: str = "") -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(CELL_ALIGNMENT)
        return item

    def _fill_empty_items(self) -> None:
        """Ensures every cell holds a real, correctly-aligned item (rather
        than a lazily-created one) so an unedited grid still round-trips
        and looks consistent."""
        for row in range(self._table.rowCount()):
            for column in range(self._table.columnCount()):
                if self._table.item(row, column) is None:
                    self._table.setItem(row, column, self._new_item())

    # --- editing -----------------------------------------------------

    def _on_item_changed(self, _item: QTableWidgetItem) -> None:
        self._mark_dirty()

    def _add_row(self) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        for column in range(self._table.columnCount()):
            self._table.setItem(row, column, self._new_item())
        self._mark_dirty()

    def _add_column(self) -> None:
        column = self._table.columnCount()
        self._table.insertColumn(column)
        for row in range(self._table.rowCount()):
            self._table.setItem(row, column, self._new_item())
        self._mark_dirty()

    def _delete_row(self) -> None:
        row = self._table.currentRow()
        if row >= 0 and self._table.rowCount() > 1:
            self._table.removeRow(row)
            self._mark_dirty()

    def _delete_column(self) -> None:
        column = self._table.currentColumn()
        if column >= 0 and self._table.columnCount() > 1:
            self._table.removeColumn(column)
            self._mark_dirty()

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self._update_label()

    def _update_label(self) -> None:
        name = self._current_path.name if self._current_path else "(untitled)"
        self._label.setText(name + (" •" if self._dirty else ""))

    # --- TSV I/O -----------------------------------------------------

    def to_tsv(self) -> str:
        lines = []
        for row in range(self._table.rowCount()):
            cells = []
            for column in range(self._table.columnCount()):
                item = self._table.item(row, column)
                cells.append(item.text() if item is not None else "")
            lines.append("\t".join(cells))
        return "\n".join(lines) + "\n"

    def load_tsv(self, text: str) -> None:
        rows = [line.split("\t") for line in text.splitlines()] or [[""]]
        columns = max(len(row) for row in rows)
        # Block itemChanged while rebuilding so bulk population doesn't
        # flip the dirty flag -- a freshly-loaded file isn't "unsaved".
        self._table.blockSignals(True)
        self._table.clear()
        self._table.setRowCount(len(rows))
        self._table.setColumnCount(columns)
        for r, row in enumerate(rows):
            for c in range(columns):
                self._table.setItem(r, c, self._new_item(row[c] if c < len(row) else ""))
        self._table.blockSignals(False)

    def _load_file(self, path: Path) -> None:
        self.load_tsv(path.read_text())
        self._current_path = path
        self._last_dir = path.parent
        self._dirty = False
        self._update_label()

    def _open_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open TSV File", str(self._last_dir), TSV_FILTER
        )
        if filename:
            self._load_file(Path(filename))

    def _save_file(self) -> bool:
        if self._current_path is None:
            return self._save_file_as()
        self._current_path.write_text(self.to_tsv())
        self._dirty = False
        self._update_label()
        return True

    def _save_file_as(self) -> bool:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save TSV File", str(self._last_dir), TSV_FILTER
        )
        if not filename:
            return False
        self._current_path = Path(filename)
        self._last_dir = self._current_path.parent
        return self._save_file()


def build() -> QWidget:
    return SheetWidget()
