from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from desk.custom_widgets import SourceBuildError
from desk.shell import current_context
from desk.widget_components import CatalogEntry, catalog_signature, list_catalog, vendor_component

POLL_INTERVAL_MS = 2000
SCOPE_TITLES = {
    "project": "Project library (mutable)",
    "desk": "Desk-wide library (static)",
}


class ComponentsWidget(QWidget):
    """The catalog of shared web components (TODO 5ee7493): what a
    real-source widget can list in its widget.json `"components"` (TODO
    d34f8ed). Two libraries -- this project's own mutable
    `desk_widgets/_shared/components/` and Desk's static `shared-components/`
    -- as a grouped list; selecting one shows its README summary, files and
    which of this project's widgets use it. Buttons open its README/source
    in an editor, copy the `"components"` entry to paste, and (desk-wide
    only) copy it into the project library so a deployed build needs nothing
    from the opening Desk (TODO b04682e). Rescans on a short poll, so a
    component edited or added while this is open shows up."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries: list[CatalogEntry] = []
        self._signature: tuple | None = None

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._refresh_button = QPushButton("Rescan")
        self._refresh_button.clicked.connect(self.reload)

        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self._list.currentItemChanged.connect(self._on_selection_changed)

        self._details = QTextBrowser()
        self._details.setOpenLinks(False)

        self._readme_button = QPushButton("Open README")
        self._readme_button.clicked.connect(lambda: self._open("readme"))
        self._source_button = QPushButton("Open source")
        self._source_button.clicked.connect(lambda: self._open("ts"))
        self._copy_button = QPushButton("Copy entry")
        self._copy_button.setToolTip('Copies the widget.json "components" entry for this component')
        self._copy_button.clicked.connect(self._copy_entry)
        self._vendor_button = QPushButton("Copy to project library")
        self._vendor_button.setToolTip(
            "Copies this desk-wide component into desk_widgets/_shared/components/ so the project carries it"
        )
        self._vendor_button.clicked.connect(self._vendor)

        buttons = QHBoxLayout()
        for button in (self._readme_button, self._source_button, self._copy_button, self._vendor_button):
            buttons.addWidget(button)
        buttons.addStretch(1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._details, 1)
        right_layout.addLayout(buttons)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._list)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        top = QHBoxLayout()
        top.addWidget(self._status_label, 1)
        top.addWidget(self._refresh_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(POLL_INTERVAL_MS)

        self.reload()

    # ---- data ----------------------------------------------------------

    def _project_dir(self) -> Path | None:
        return current_context.get_current_desk_directory()

    def _poll(self) -> None:
        directory = self._project_dir()
        if directory is not None and catalog_signature(directory) != self._signature:
            self.reload()

    def reload(self) -> None:
        directory = self._project_dir()
        previous = self._selected_key()
        self._entries = list_catalog(directory) if directory is not None else []
        self._signature = catalog_signature(directory) if directory is not None else None
        self._populate(previous)

    def _populate(self, select: tuple[str, str] | None) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        target = None
        for scope in ("project", "desk"):
            entries = [e for e in self._entries if e.scope == scope]
            header = QListWidgetItem(f"{SCOPE_TITLES[scope]} -- {len(entries)}")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            self._list.addItem(header)
            for entry in entries:
                suffix = "  (copied to project)" if entry.vendored else ""
                item = QListWidgetItem(f"  {entry.name}{suffix}")
                item.setData(Qt.ItemDataRole.UserRole, (entry.scope, entry.name))
                self._list.addItem(item)
                if (entry.scope, entry.name) == select:
                    target = item
        self._list.blockSignals(False)
        if target is None:
            target = next(
                (self._list.item(i) for i in range(self._list.count()) if self._list.item(i).data(Qt.ItemDataRole.UserRole)),
                None,
            )
        if target is not None:
            self._list.setCurrentItem(target)
        self._on_selection_changed(target, None)
        used = sum(1 for e in self._entries if e.used_by)
        self._status_label.setText(
            f"{len(self._entries)} components, {used} in use." if self._entries else "No components found."
        )

    def _selected_key(self) -> tuple[str, str] | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _selected(self) -> CatalogEntry | None:
        key = self._selected_key()
        return next((e for e in self._entries if (e.scope, e.name) == key), None)

    # ---- details -------------------------------------------------------

    def _on_selection_changed(self, _current, _previous) -> None:
        entry = self._selected()
        for button in (self._readme_button, self._source_button, self._copy_button, self._vendor_button):
            button.setEnabled(entry is not None)
        if entry is None:
            self._details.setMarkdown("Select a component.")
            return
        self._readme_button.setEnabled(entry.readme is not None)
        self._vendor_button.setEnabled(entry.scope == "desk" and not entry.vendored)
        used = "\n".join(f"- `{path}`" for path in entry.used_by) or "- (no widget in this project uses it)"
        lines = [
            f"## {entry.name}",
            f"*{SCOPE_TITLES[entry.scope]}*" + (" -- a project copy exists and wins for bare names" if entry.vendored else ""),
            "",
            entry.summary or "(no README)",
            "",
            f'Use: `"components": ["{entry.name}"]` in a widget.json'
            + (f' (or `"project:{entry.name}"`)' if entry.scope == "project" else ""),
            "",
            "**Template:** " + ("yes (injected into the page)" if entry.has_template else "none"),
            "",
            "**Files**",
            *[f"- `{f}`" for f in entry.files],
            "",
            "**Used by**",
            used,
        ]
        self._details.setMarkdown("\n".join(lines))

    # ---- actions -------------------------------------------------------

    def _open(self, which: str) -> None:
        entry = self._selected()
        opener = current_context.get_editor_or_scrap_opener()
        if entry is None or opener is None:
            return
        path = entry.readme if which == "readme" else entry.ts_path
        if path is not None:
            opener(path)

    def _copy_entry(self) -> None:
        entry = self._selected()
        if entry is not None:
            QGuiApplication.clipboard().setText(f'"{entry.name}"')
            self._status_label.setText(f'Copied "{entry.name}" -- paste it into a widget.json "components" list.')

    def _vendor(self) -> None:
        entry = self._selected()
        directory = self._project_dir()
        if entry is None or directory is None:
            return
        try:
            _destination, outcome = vendor_component(directory, entry.name)
        except SourceBuildError as e:
            self._status_label.setText(str(e))
            return
        self.reload()  # first: it rewrites the status line
        self._status_label.setText(f"{entry.name}: {outcome}. Pin it in a widget with project:{entry.name}.")


def build() -> QWidget:
    return ComponentsWidget()
