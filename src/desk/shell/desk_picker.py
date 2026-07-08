from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QWidget

BROWSE_LABEL = "…  Open another Desk…"
NEW_DESK_LABEL = "＋  New Desk…"
RENAME_LABEL = "✎  Rename current Desk…"

PATH_ROLE = Qt.ItemDataRole.UserRole
# Distinguishes the non-navigation action rows (browse/new/rename) from
# the MRU desk rows (which carry a Path in PATH_ROLE and have no action).
ACTION_ROLE = Qt.ItemDataRole.UserRole + 1

# A muted foreground for the action rows, so the popup reads as "recent
# desks, then actions" rather than one flat list.
_ACTION_ROW_COLOR = QColor("#9aa0a6")

# Matches the app's existing accent color (see widgets/todo/widget.py's
# FILTER_BUTTON_STYLE) so hover feedback here reads as the same "this is
# interactive" language used elsewhere, not a one-off.
_ACCENT = "61, 174, 233"

NAME_STYLE = (
    "background-color: rgba(40, 42, 46, 128); color: #e8e8e8; font-weight: 600;"
    " padding: 4px 8px; border-radius: 6px;"
)
NAME_HOVER_STYLE = (
    f"background-color: rgba({_ACCENT}, 160); color: #ffffff; font-weight: 600;"
    " padding: 4px 8px; border-radius: 6px; text-decoration: underline;"
)
DIRECTORY_STYLE = (
    "background-color: rgba(40, 42, 46, 90); color: #b8bcc2;"
    " padding: 4px 8px; border-radius: 6px;"
)
DIRECTORY_HOVER_STYLE = (
    f"background-color: rgba({_ACCENT}, 130); color: #ffffff;"
    " padding: 4px 8px; border-radius: 6px; text-decoration: underline;"
)
SEPARATOR_STYLE = "color: #888;"


class _ClickableLabel(QLabel):
    """A non-selectable `QLabel` (per `CLAUDE.md`'s "labels shouldn't be
    user-selectable" convention) that looks and behaves like a small
    button: a distinct hover style and a `clicked` signal. A plain
    `QWidget` child of `WorkspaceView.viewport()` (not a scene item), so
    its own mouse events already reflect real screen coordinates -- none
    of design-docs/widget-ux.md's Zoom-Correct-Dragging concerns (which
    are specifically about widgets embedded via `QGraphicsProxyWidget`)
    apply here."""

    clicked = pyqtSignal()

    def __init__(self, base_style: str, hover_style: str, parent=None) -> None:
        super().__init__(parent)
        self._base_style = base_style
        self._hover_style = hover_style
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(base_style)

    def enterEvent(self, event) -> None:
        self.setStyleSheet(self._hover_style)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setStyleSheet(self._base_style)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class _DeskListPopup(QWidget):
    """A stable, fully-visible-immediately list of MRU desks plus a
    trailing "browse" entry -- shown on a name-label click, replacing the
    old `QComboBox` (which needed a hover to reveal, then a further click
    to open its own native popup, and could be lost by moving the mouse
    off it before finishing). Uses the same `Qt.WindowType.Popup` pattern
    as `WidgetSpawnMenu` (click-away/Escape dismissal), just without a
    filter box -- MRU lists are short."""

    desk_chosen = pyqtSignal(Path)
    browse_requested = pyqtSignal()
    new_desk_requested = pyqtSignal()
    rename_requested = pyqtSignal()

    def __init__(self, entries: list[Path], current: Path, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._list = QListWidget()
        self._list.itemClicked.connect(self._activate_item)
        self._list.itemActivated.connect(self._activate_item)
        layout.addWidget(self._list)

        for path in entries:
            item = QListWidgetItem(path.stem)
            item.setData(PATH_ROLE, path)
            self._list.addItem(item)
            if path == current:
                self._list.setCurrentItem(item)

        for label, action in (
            (NEW_DESK_LABEL, "new"),
            (RENAME_LABEL, "rename"),
            (BROWSE_LABEL, "browse"),
        ):
            item = QListWidgetItem(label)
            item.setData(ACTION_ROLE, action)
            item.setForeground(_ACTION_ROW_COLOR)
            self._list.addItem(item)

    def _activate_item(self, item: QListWidgetItem) -> None:
        # Close *before* emitting, and never touch `self` afterward: a
        # downstream slot (desk_chosen ultimately reaches DeskWindow
        # .switch_desk, which can show a real confirmation dialog via
        # _provision_temp_ui) may show a modal dialog before returning.
        # That modal stealing active-window status auto-closes this
        # still-open Qt.WindowType.Popup, and WA_DeleteOnClose's
        # deleteLater() gets processed by the modal's own nested event
        # loop while this method is still on the call stack -- so a
        # `self.close()` called *after* the emit crashes with
        # "wrapped C/C++ object ... has been deleted". Confirmed
        # directly. See plans/fix-desk-list-popup-deleted-mid-callback.md.
        path = item.data(PATH_ROLE)
        action = item.data(ACTION_ROLE)
        self.close()
        if action == "new":
            self.new_desk_requested.emit()
        elif action == "rename":
            self.rename_requested.emit()
        elif action == "browse":
            self.browse_requested.emit()
        elif path is not None:
            self.desk_chosen.emit(path)


class DeskPicker(QWidget):
    """Top-left HUD picker (mirrors ZoomControl's screen-space placement
    pattern, opposite corner): always shows the current desk's name and
    associated directory as two distinct, independently clickable label
    chips (see `_ClickableLabel`) -- clicking the name opens a stable
    popup of recently-used desks (see `_DeskListPopup`); clicking the
    directory opens the directory picker directly. A "dumb" UI
    component — confirmation and the actual desk switch/directory change
    are DeskWindow's job, not this widget's. See design-docs/widget-ux.md."""

    desk_chosen = pyqtSignal(Path)
    browse_requested = pyqtSignal()
    new_desk_requested = pyqtSignal()
    rename_requested = pyqtSignal()
    directory_change_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._mru_entries: list[Path] = []
        self._current_path: Path | None = None

        self._name_label = _ClickableLabel(NAME_STYLE, NAME_HOVER_STYLE)
        self._name_label.clicked.connect(self._on_name_clicked)

        self._separator = QLabel("—")
        self._separator.setStyleSheet(SEPARATOR_STYLE)
        self._separator.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._directory_label = _ClickableLabel(DIRECTORY_STYLE, DIRECTORY_HOVER_STYLE)
        self._directory_label.clicked.connect(self.directory_change_requested)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._name_label)
        layout.addWidget(self._separator)
        layout.addWidget(self._directory_label)

    def _on_name_clicked(self) -> None:
        popup = _DeskListPopup(self._mru_entries, self._current_path, self)
        popup.desk_chosen.connect(self.desk_chosen)
        popup.browse_requested.connect(self.browse_requested)
        popup.new_desk_requested.connect(self.new_desk_requested)
        popup.rename_requested.connect(self.rename_requested)
        popup.move(self.mapToGlobal(self._name_label.geometry().bottomLeft()))
        popup.show()

    def set_current(self, name: str, directory: Path) -> None:
        self._name_label.setText(name)
        self._directory_label.setText(str(directory))
        # Without this, the picker's outer bounds stay whatever they were
        # computed as at construction time (when both labels were still
        # empty), clipping their real text -- see plans/fix-desk-picker
        # -label.md.
        self.adjustSize()

    def set_mru(self, entries: list[Path], current: Path) -> None:
        # The popup must always be able to select the actually-open desk,
        # regardless of whether the persisted MRU list has caught up yet
        # -- on a desk's first open, nothing has called add_to_mru() for
        # it, so without this it's simply absent from `entries`. See
        # plans/fix-desk-picker-label.md.
        if current not in entries:
            entries = [current, *entries]
        self._mru_entries = entries
        self._current_path = current
        self.adjustSize()
