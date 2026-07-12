from pathlib import Path

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class NewDeskDialog(QWidget):
    """A single dialog collecting every "New Desk" decision up front
    (TODO 4716585), instead of the previous name/directory/development
    -process-confirm/.desk_temp-confirm/.gitignore-confirm chain of up
    to five sequential modal popups. Same floating `Qt.WindowType.Tool`
    shape as `widgets/todo/widget.py`'s `_ItemDialog` (must not dismiss
    on click-away) -- see that class's docstring and LEARNINGS.md for
    why a Popup won't do. See plans/fix-new-desk-flow-crash.md."""

    created = pyqtSignal(str, str, bool, bool, bool)
    # name, directory, create_temp_ui, create_gitignore, copy_development_process

    def __init__(
        self,
        default_directory: Path,
        dev_process_filename: str | None,
        parent=None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(440, 260)
        self._directory = default_directory

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Name:"))
        self._name_field = QLineEdit()
        self._name_field.setPlaceholderText("New Desk name…")
        layout.addWidget(self._name_field)

        layout.addWidget(QLabel("Path:"))
        path_row = QHBoxLayout()
        self._path_field = QLineEdit(str(default_directory))
        self._path_field.setReadOnly(True)
        path_row.addWidget(self._path_field, stretch=1)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse)
        path_row.addWidget(browse_button)
        layout.addLayout(path_row)

        self._temp_ui_checkbox = QCheckBox("Create .desk_temp for tempui")
        self._temp_ui_checkbox.setChecked(True)
        layout.addWidget(self._temp_ui_checkbox)

        self._gitignore_checkbox = QCheckBox("Create/update .gitignore with Desk-specific patterns")
        self._gitignore_checkbox.setChecked(True)
        layout.addWidget(self._gitignore_checkbox)

        # Only offered if the current Desk actually has one to copy
        # from -- mirrors the old flow's own source.is_file() gate.
        self._dev_process_checkbox: QCheckBox | None = None
        if dev_process_filename is not None:
            self._dev_process_checkbox = QCheckBox(f"Copy {dev_process_filename} from the current Desk")
            layout.addWidget(self._dev_process_checkbox)

        layout.addStretch()

        button_row = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.close)
        button_row.addWidget(cancel_button)
        create_button = QPushButton("Create")
        create_button.clicked.connect(self._submit)
        button_row.addWidget(create_button)
        layout.addLayout(button_row)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Deferred for the same reason as _ItemDialog's showEvent (see
        # widgets/todo/widget.py): something else may still be settling
        # window-manager activation right after show().
        QTimer.singleShot(0, self._claim_focus)

    def _claim_focus(self) -> None:
        self.raise_()
        self.activateWindow()
        self._name_field.setFocus()

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "New Desk Directory", str(self._directory))
        if chosen:
            self._directory = Path(chosen)
            self._path_field.setText(str(self._directory))

    def _submit(self) -> None:
        name = self._name_field.text().strip()
        if not name:
            return
        self.created.emit(
            name,
            str(self._directory),
            self._temp_ui_checkbox.isChecked(),
            self._gitignore_checkbox.isChecked(),
            self._dev_process_checkbox.isChecked() if self._dev_process_checkbox is not None else False,
        )
        self.close()
