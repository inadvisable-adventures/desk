from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.shell import current_context

OVERLAY_STYLE = "background-color: rgba(61, 174, 233, 60);"
OVERLAY_HINT_STYLE = "color: white; background-color: rgba(0, 0, 0, 160); padding: 6px; border-radius: 3px;"
OVERLAY_HINT_TEXT = "Click a UI element to identify it (Esc to cancel)"


class _PickOverlay(QWidget):
    """A full-screen (covering the app's own window, not the OS
    desktop -- "internal," matching the Feedback widget's own
    screenshot scope) translucent overlay: one left click resolves an
    identifying path for whatever's underneath via
    `current_context.get_widget_path_resolver()` and emits it; Escape
    cancels. See plans/feedback-widget.md."""

    picked = pyqtSignal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet(OVERLAY_STYLE)
        self.setGeometry(parent.rect())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        hint = QLabel(OVERLAY_HINT_TEXT, self)
        hint.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        hint.setStyleSheet(OVERLAY_HINT_STYLE)
        hint.move(12, 12)
        hint.adjustSize()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            resolver = current_context.get_widget_path_resolver()
            path = resolver(event.globalPosition().toPoint()) if resolver is not None else None
            self.picked.emit(path or "")
        self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.picked.emit("")
            self.close()
        else:
            super().keyPressEvent(event)


class FeedbackWidget(QWidget):
    """Free-form feedback text, with a Screenshot button (grabs the
    app's own window, TODO f2aede6 -- "internal," not OS-level screen
    capture) and a Pick UI Element button (shows `_PickOverlay`;
    resolves whatever's clicked into a short identifying path). Both
    insert into the text at the current caret position. Save Feedback
    writes `DESK-feedback-<timestamp>.md` plus any screenshot PNGs,
    all sharing one base name decided once (by the first screenshot,
    or Save Feedback itself if none were taken) rather than a
    placeholder rewritten later. See plans/feedback-widget.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._screenshots: list = []
        self._base_name: str | None = None

        self._body = QPlainTextEdit()
        self._body.setPlaceholderText("Describe your feedback…")

        screenshot_button = QPushButton("Screenshot")
        screenshot_button.clicked.connect(self._take_screenshot)
        pick_button = QPushButton("Pick UI Element")
        pick_button.clicked.connect(self._start_picking)
        self._save_button = QPushButton("Save Feedback")
        self._save_button.clicked.connect(self._save_feedback)

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        toolbar = QHBoxLayout()
        toolbar.addWidget(screenshot_button)
        toolbar.addWidget(pick_button)
        toolbar.addStretch()
        toolbar.addWidget(self._save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(self._body, stretch=1)
        layout.addWidget(self._status_label)

    def _insert_text(self, text: str) -> None:
        cursor = self._body.textCursor()
        cursor.insertText(text)
        self._body.setTextCursor(cursor)
        self._body.setFocus()

    def _ensure_base_name(self) -> str:
        if self._base_name is None:
            timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            self._base_name = f"DESK-feedback-{timestamp}"
        return self._base_name

    def _take_screenshot(self) -> None:
        window = current_context.get_main_window()
        if window is None:
            return
        pixmap = window.grab()
        self._screenshots.append(pixmap)
        index = len(self._screenshots)
        image_name = f"{self._ensure_base_name()}-screenshot-{index}.png"
        self._insert_text(f"\n![screenshot {index}]({image_name})\n")

    def _start_picking(self) -> None:
        window = current_context.get_main_window()
        if window is None:
            return
        overlay = _PickOverlay(window)
        overlay.picked.connect(self._on_ui_path_picked)
        overlay.show()
        overlay.raise_()
        overlay.setFocus()

    def _on_ui_path_picked(self, path: str) -> None:
        if path:
            self._insert_text(path)

    def _save_feedback(self) -> None:
        directory = current_context.get_current_desk_directory() or Path.cwd()
        base_name = self._ensure_base_name()
        md_path = directory / f"{base_name}.md"
        # Re-checked immediately before writing (TODO 4716585's
        # established pattern): an exceedingly unlikely timestamp
        # collision just means this quietly doesn't overwrite, rather
        # than clobbering something.
        if md_path.exists():
            self._status_label.setText(f"{md_path} already exists -- not saved.")
            return
        for index, pixmap in enumerate(self._screenshots, start=1):
            pixmap.save(str(directory / f"{base_name}-screenshot-{index}.png"), "PNG")
        md_path.write_text(self._body.toPlainText())
        self._status_label.setText(f"Saved {md_path}")
        self._screenshots = []
        self._base_name = None
        self._body.clear()


def build() -> QWidget:
    return FeedbackWidget()
