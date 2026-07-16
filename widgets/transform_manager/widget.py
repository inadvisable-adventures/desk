from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
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
from desk.temp_ui import TEMP_UI_DIRNAME
from desk.transforms import PROJECT_TRANSFORMS_DIRNAME, TEMP_TRANSFORMS_DIRNAME, TransformInfo
from desk_services.transforms import TransformError, get_service

COLUMN_HEADERS = ("Name", "Input Type", "Output Type", "Language", "Config?", "Identity?", "Location", "")
PROMOTE_COLUMN = len(COLUMN_HEADERS) - 1


class TransformManagerWidget(QWidget):
    """Lists every discovered transform (TODO `b5e15cf`) -- see
    design-docs/transforms.md. Modeled on EventLogWidget's plain
    QTableWidget shape (there's no existing "list/introspect other
    widgets or definitions" widget precedent to mirror instead). No
    file-watching: transforms aren't edited anywhere near as often as
    TODO.md -- this is a manager/introspection widget, not a
    live-edited document -- so a Refresh button re-runs discovery on
    demand instead."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._table = QTableWidget(0, len(COLUMN_HEADERS))
        self._table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)

        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.clicked.connect(self.refresh)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._refresh_button)
        toolbar.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._status_label)
        layout.addLayout(toolbar)
        layout.addWidget(self._table, stretch=1)

        # A freshly-placed widget shouldn't sit blank until the user
        # thinks to click Refresh -- same "don't leave it empty at
        # first" convention widgets/git_status/widget.py's own initial
        # _poll(initial=True) already established.
        self.refresh()

    def _resolve_directories(self) -> tuple[Path, Path] | tuple[None, None]:
        directory = current_context.get_current_desk_directory()
        if directory is None:
            return None, None
        return directory / TEMP_UI_DIRNAME / TEMP_TRANSFORMS_DIRNAME, directory / PROJECT_TRANSFORMS_DIRNAME

    def refresh(self) -> None:
        desk_temp_dir, project_dir = self._resolve_directories()
        if desk_temp_dir is None:
            self._status_label.setText("No Desk directory available yet.")
            self._table.setRowCount(0)
            return
        transforms, errors = get_service().discover(desk_temp_dir, project_dir)
        plural = "" if len(transforms) == 1 else "s"
        self._status_label.setText(f"{len(transforms)} transform{plural} discovered.")
        self._populate(transforms, errors, desk_temp_dir, project_dir)

    def _populate(self, transforms: dict, errors: dict, desk_temp_dir: Path, project_dir: Path) -> None:
        rows = sorted(transforms.values(), key=lambda info: info.name)
        error_rows = sorted(errors.items())
        self._table.setRowCount(len(rows) + len(error_rows))
        for row, info in enumerate(rows):
            self._set_row(row, info, desk_temp_dir, project_dir)
        for offset, (name, message) in enumerate(error_rows):
            self._set_error_row(len(rows) + offset, name, message)

    def _set_row(self, row: int, info: TransformInfo, desk_temp_dir: Path, project_dir: Path) -> None:
        values = (
            info.name,
            info.input_type,
            info.output_type,
            info.kind,
            "Yes" if info.has_config else "No",
            "Yes" if info.has_identity else "No",
            "Local (.desk_temp)" if info.location == "desk_temp" else "Project",
        )
        for column, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, column, item)
        if info.location == "desk_temp":
            button = QPushButton("Promote")
            button.clicked.connect(lambda _checked=False, i=info: self._promote(i, desk_temp_dir, project_dir))
            self._table.setCellWidget(row, PROMOTE_COLUMN, button)
        else:
            # setRowCount() doesn't clear an existing row's cell widget
            # when the row count is unchanged across a refresh -- without
            # this, a row that used to be .desk_temp-located (and had a
            # Promote button) keeps showing a stale one after being
            # promoted, even though it's now project-located.
            self._table.removeCellWidget(row, PROMOTE_COLUMN)

    def _set_error_row(self, row: int, directory_name: str, message: str) -> None:
        item = QTableWidgetItem(f"[!] {directory_name}: {message}")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row, 0, item)
        self._table.setSpan(row, 0, 1, len(COLUMN_HEADERS))

    def _promote(self, info: TransformInfo, desk_temp_dir: Path, project_dir: Path) -> None:
        opener = current_context.get_popup_opener()
        if opener is None:
            return
        result = opener(
            "Promote Transform",
            f"Promote '{info.name}' to desk_transforms/? This moves its source into the "
            "project, to be committed to version control going forward.",
            ["Promote", "Cancel"],
            "Cancel",
        )
        if result != "Promote":
            return
        try:
            get_service().promote(info.id, desk_temp_dir, project_dir)
        except TransformError as e:
            opener("Promote Failed", str(e), ["OK"], "OK")
            return
        self.refresh()


def build() -> QWidget:
    return TransformManagerWidget()
