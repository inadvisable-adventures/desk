"""State Manager (TODO 6330249): view and edit every registered
desk.state.* schema (widget-declared and top-level) and the data stored
under those keys -- deep insight into shared state, not a read-only
listing. See plans/state-schema-management-widget.md.

Kind: "python", not "html" -- matches every comparable Desk management
widget (todo, parking_lot, event_log, project_files), gets native Qt
table/tree/form controls, and sidesteps CLAUDE.md's TypeScript-strict/
<template> requirements entirely (those apply to code that runs in a
browser; this widget never does).
"""

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desk.schema_registry import SCHEMA_CHANGED_EVENT
from desk.shell import current_context
from desk.shell.event_broker import EventSubscription

KEY_ROLE = Qt.ItemDataRole.UserRole
TREE_HEADERS = ("Key", "Schema", "Source", "Status")


def _pretty(value: object) -> str:
    return json.dumps(value, indent=2)


def _status_text(entry: dict) -> str:
    if entry["type_expr"] is None:
        return "—"
    if entry["permanent"]:
        return "permanent"
    count = entry["placed_instance_count"]
    return f"{count} placed instance{'s' if count != 1 else ''}" if count else "dormant"


class _NewKeyDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New State Key")
        layout = QFormLayout(self)

        self.key_field = QLineEdit()
        layout.addRow("Key:", self.key_field)

        self.value_field = QPlainTextEdit("null")
        self.value_field.setFixedHeight(80)
        layout.addRow("Initial value (JSON):", self.value_field)

        self.type_expr_field = QLineEdit()
        self.type_expr_field.setPlaceholderText("optional -- e.g. string | number")
        layout.addRow("Schema type expression:", self.type_expr_field)

        self.location_field = QComboBox()
        self.location_field.addItem("Ephemeral (.desk_temp/schemas/)", "ephemeral")
        self.location_field.addItem("Git-tracked (./desk-schemas/)", "git_tracked")
        layout.addRow("Schema location:", self.location_field)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class StateManagerWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._instance_id: str | None = None
        self._selected_key: str | None = None
        self._overview: dict[str, dict] = {}

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(TREE_HEADERS)
        self._tree.setRootIsDecorated(False)
        self._tree.currentItemChanged.connect(self._on_selection_changed)

        new_key_button = QPushButton("New Key")
        new_key_button.clicked.connect(self._on_new_key_clicked)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        save_state_button = QPushButton("Save State...")
        save_state_button.clicked.connect(self._on_save_state_clicked)
        load_state_button = QPushButton("Load State...")
        load_state_button.clicked.connect(self._on_load_state_clicked)
        toolbar = QHBoxLayout()
        toolbar.addWidget(new_key_button)
        toolbar.addWidget(refresh_button)
        toolbar.addWidget(save_state_button)
        toolbar.addWidget(load_state_button)
        toolbar.addStretch(1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addLayout(toolbar)
        left_layout.addWidget(self._tree)

        self._detail_key_label = QLabel("Select a key")
        self._detail_key_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._schema_status_label = QLabel()
        self._schema_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._schema_type_field = QLineEdit()
        self._schema_location_field = QComboBox()
        self._schema_location_field.addItem("Ephemeral (.desk_temp/schemas/)", "ephemeral")
        self._schema_location_field.addItem("Git-tracked (./desk-schemas/)", "git_tracked")
        self._schema_save_button = QPushButton("Save Schema")
        self._schema_save_button.clicked.connect(self._on_save_schema_clicked)
        self._schema_delete_button = QPushButton("Delete Schema")
        self._schema_delete_button.clicked.connect(self._on_delete_schema_clicked)
        schema_buttons = QHBoxLayout()
        schema_buttons.addWidget(self._schema_save_button)
        schema_buttons.addWidget(self._schema_delete_button)
        schema_buttons.addStretch(1)

        self._value_field = QPlainTextEdit()
        self._edit_note_field = QLineEdit()
        self._edit_note_field.setPlaceholderText("optional note describing this edit")
        self._value_save_button = QPushButton("Save Value")
        self._value_save_button.clicked.connect(self._on_save_value_clicked)

        self._history_list = QListWidget()

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._status_label.setWordWrap(True)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self._detail_key_label)
        right_layout.addWidget(QLabel("Schema"))
        right_layout.addWidget(self._schema_status_label)
        right_layout.addWidget(self._schema_type_field)
        right_layout.addWidget(self._schema_location_field)
        right_layout.addLayout(schema_buttons)
        right_layout.addWidget(QLabel("Value (JSON)"))
        right_layout.addWidget(self._value_field, stretch=1)
        right_layout.addWidget(self._edit_note_field)
        right_layout.addWidget(self._value_save_button)
        right_layout.addWidget(QLabel("History (latest first)"))
        right_layout.addWidget(self._history_list, stretch=1)
        right_layout.addWidget(self._status_label)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.addWidget(splitter)

        self._show_detail_for(None)
        self.refresh()

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def refresh(self) -> None:
        provider = current_context.get_state_overview_provider()
        entries = provider() if provider is not None else []
        self._overview = {entry["key"]: entry for entry in entries}

        self._tree.blockSignals(True)
        self._tree.clear()
        for key in sorted(self._overview):
            entry = self._overview[key]
            item = QTreeWidgetItem(
                [
                    key,
                    entry["type_expr"] or "—",
                    entry["source"] or "—",
                    _status_text(entry),
                ]
            )
            item.setData(0, KEY_ROLE, key)
            self._tree.addTopLevelItem(item)
        self._tree.blockSignals(False)

        if self._selected_key is not None and self._selected_key in self._overview:
            self._show_detail_for(self._selected_key)
        else:
            self._selected_key = None
            self._show_detail_for(None)

    def _on_selection_changed(self, current: QTreeWidgetItem, _previous: QTreeWidgetItem) -> None:
        key = current.data(0, KEY_ROLE) if current is not None else None
        self._selected_key = key
        self._set_status("")
        self._show_detail_for(key)

    def _show_detail_for(self, key: str | None) -> None:
        """Re-renders the detail panel for `key` -- deliberately never
        touches the status label itself (callers that need a fresh
        selection to clear a stale message do so explicitly first, see
        _on_selection_changed): refresh() also calls this to
        repopulate after a save, and clearing the status here would
        immediately wipe out the very "Saved."/error message that save
        handler just set before calling refresh()."""
        if key is None or key not in self._overview:
            self._detail_key_label.setText("Select a key")
            for widget in (
                self._schema_type_field,
                self._schema_location_field,
                self._schema_save_button,
                self._schema_delete_button,
                self._value_field,
                self._edit_note_field,
                self._value_save_button,
            ):
                widget.setEnabled(False)
            self._schema_status_label.setText("")
            self._value_field.setPlainText("")
            self._history_list.clear()
            return

        entry = self._overview[key]
        self._detail_key_label.setText(key)

        editable_schema = entry["type_expr"] is None or entry["source_kind"] == "file"
        self._schema_type_field.setEnabled(editable_schema)
        self._schema_location_field.setEnabled(editable_schema)
        self._schema_save_button.setEnabled(editable_schema)
        self._schema_delete_button.setEnabled(entry["source_kind"] == "file")
        if entry["type_expr"] is None:
            self._schema_status_label.setText("No schema declared -- this key is non-validated.")
            self._schema_type_field.setText("")
        elif entry["source_kind"] == "file":
            self._schema_status_label.setText(f"Declared in {entry['source']} -- editable here.")
            self._schema_type_field.setText(entry["type_expr"])
        else:
            self._schema_status_label.setText(
                f"Declared by widget {entry['source']!r} -- edit its own manifest to change it."
            )
            self._schema_type_field.setText(entry["type_expr"])

        self._value_field.setEnabled(True)
        self._edit_note_field.setEnabled(True)
        self._value_save_button.setEnabled(True)
        self._value_field.setPlainText(_pretty(entry["value"]))
        self._edit_note_field.setText("")

        history_provider = current_context.get_state_history_provider()
        history = history_provider(key, 50) if history_provider is not None else []
        self._history_list.clear()
        for item in history:
            self._history_list.addItem(f"{_pretty(item['value'])}  (edit: {item['edit']!r})")

    def _on_save_value_clicked(self) -> None:
        if self._selected_key is None:
            return
        try:
            value = json.loads(self._value_field.toPlainText())
        except json.JSONDecodeError as e:
            self._set_status(f"Not valid JSON: {e}")
            return
        writer = current_context.get_state_writer()
        if writer is None or self._instance_id is None:
            self._set_status("Not ready yet -- try again in a moment.")
            return
        edit = self._edit_note_field.text() or None
        error = writer(self._selected_key, value, edit, self._instance_id, None)
        if error is not None:
            self._set_status(f"Save failed: {error}")
            return
        self._set_status("Saved.")
        self.refresh()

    def _on_save_schema_clicked(self) -> None:
        if self._selected_key is None:
            return
        type_expr = self._schema_type_field.text().strip()
        if not type_expr:
            self._set_status("Enter a type expression first.")
            return
        writer = current_context.get_schema_file_writer()
        if writer is None:
            self._set_status("Not ready yet -- try again in a moment.")
            return
        location = self._schema_location_field.currentData()
        error = writer(location, self._selected_key, type_expr)
        if error is not None:
            self._set_status(f"Schema save failed: {error}")
            return
        self._set_status("Schema saved.")
        self.refresh()

    def _on_delete_schema_clicked(self) -> None:
        if self._selected_key is None:
            return
        deleter = current_context.get_schema_file_deleter()
        if deleter is None:
            self._set_status("Not ready yet -- try again in a moment.")
            return
        error = deleter(self._selected_key)
        if error is not None:
            self._set_status(f"Schema delete failed: {error}")
            return
        self._set_status("Schema deleted.")
        self.refresh()

    def _on_new_key_clicked(self) -> None:
        dialog = _NewKeyDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        key = dialog.key_field.text().strip()
        if not key:
            QMessageBox.warning(self, "New State Key", "A key name is required.")
            return
        try:
            value = json.loads(dialog.value_field.toPlainText())
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "New State Key", f"Initial value is not valid JSON: {e}")
            return

        type_expr = dialog.type_expr_field.text().strip()
        if type_expr:
            writer = current_context.get_schema_file_writer()
            if writer is not None:
                error = writer(dialog.location_field.currentData(), key, type_expr)
                if error is not None:
                    QMessageBox.warning(self, "New State Key", f"Schema could not be saved: {error}")
                    return

        value_writer = current_context.get_state_writer()
        if value_writer is not None and self._instance_id is not None:
            error = value_writer(key, value, None, self._instance_id, None)
            if error is not None:
                QMessageBox.warning(self, "New State Key", f"Value could not be saved: {error}")
        self.refresh()

    def _on_save_state_clicked(self) -> None:
        exporter = current_context.get_state_exporter()
        if exporter is None:
            self._set_status("Not ready yet -- try again in a moment.")
            return
        filename, _filter = QFileDialog.getSaveFileName(self, "Save State", "state.json", "JSON (*.json)")
        if not filename:
            return
        error = exporter(Path(filename))
        self._set_status(f"Save failed: {error}" if error is not None else f"Saved to {filename}.")

    def _on_load_state_clicked(self) -> None:
        importer = current_context.get_state_importer()
        if importer is None:
            self._set_status("Not ready yet -- try again in a moment.")
            return
        filename, _filter = QFileDialog.getOpenFileName(self, "Load State", "", "JSON (*.json)")
        if not filename:
            return
        confirmed = QMessageBox.question(
            self,
            "Load State",
            f"Import {filename}? This can overwrite currently-live values.",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        error = importer(Path(filename))
        if error is not None:
            self._set_status(f"Load failed: {error}")
            return
        self._set_status(f"Loaded from {filename}.")
        self.refresh()

    def bind_event_mediator(self, instance_id, mediator) -> None:
        """TODO 6330249: opts into DeskWindow._bind_event_mediator's
        generic per-placed-python-widget hook to keep the overview live
        -- both a value write (desk.state.changed) and a schema
        registration/change (SCHEMA_CHANGED_EVENT) just trigger a full
        refresh() rather than a targeted per-key update, matching
        SchemaRegistry's own "cheap enough to just re-fetch" reasoning
        for its empty event payload."""
        self._instance_id = instance_id
        self._subscription = EventSubscription(
            mediator, instance_id, names=["desk.state.changed", SCHEMA_CHANGED_EVENT], parent=self
        )
        self._subscription.message_received.connect(lambda *_args: self.refresh())


def build() -> QWidget:
    return StateManagerWidget()
