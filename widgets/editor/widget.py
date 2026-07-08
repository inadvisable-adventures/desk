from collections.abc import Callable
from pathlib import Path

from PyQt6.Qsci import (
    QsciLexerBash,
    QsciLexerCPP,
    QsciLexerHTML,
    QsciLexerJavaScript,
    QsciLexerJSON,
    QsciLexerMarkdown,
    QsciLexerPython,
    QsciLexerYAML,
    QsciScintilla,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFontDatabase, QKeySequence, QShortcut
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from desk.shell import current_context

EXTENSION_LEXERS = {
    ".py": QsciLexerPython,
    ".json": QsciLexerJSON,
    ".js": QsciLexerJavaScript,
    ".ts": QsciLexerJavaScript,
    ".html": QsciLexerHTML,
    ".htm": QsciLexerHTML,
    ".md": QsciLexerMarkdown,
    ".sh": QsciLexerBash,
    ".bash": QsciLexerBash,
    ".yaml": QsciLexerYAML,
    ".yml": QsciLexerYAML,
    ".c": QsciLexerCPP,
    ".h": QsciLexerCPP,
    ".cpp": QsciLexerCPP,
    ".hpp": QsciLexerCPP,
}

# Returns "save" | "discard" | "cancel".
ConfirmUnsaved = Callable[[], str]


class EditorWidget(QWidget):
    """A native Qt/QScintilla text/code editor: open, edit, and save a file
    from disk, with syntax highlighting chosen by file extension. See
    plans/code-editor-widget.md. The "Open" dialog's initial directory
    defaults to the current Desk's associated directory (via
    desk.shell.current_context, resolved once at construction -- same
    shape as the TODO widget's own use of it) when one is known, falling
    back to the user's home directory otherwise. See
    plans/editor-open-default-desk-directory.md."""

    def __init__(self, parent=None, confirm_unsaved: ConfirmUnsaved | None = None) -> None:
        super().__init__(parent)
        self._confirm_unsaved = confirm_unsaved
        self._current_path: Path | None = None
        self._last_dir = current_context.get_current_desk_directory() or Path.home()

        self.editor = QsciScintilla()
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.editor.setFont(font)
        self.editor.setUtf8(True)
        self.editor.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.editor.setMarginWidth(0, "0000")
        self.editor.setCaretLineVisible(True)
        self.editor.setCaretLineBackgroundColor(QColor("#2a2d2f"))
        self.editor.modificationChanged.connect(lambda _modified: self._update_label())

        self._label = QLabel()
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._update_label()

        open_button = QPushButton("Open")
        save_button = QPushButton("Save")
        save_as_button = QPushButton("Save As")
        open_button.clicked.connect(self._open_file)
        save_button.clicked.connect(lambda: self._save_file())
        save_as_button.clicked.connect(lambda: self._save_file_as())

        toolbar = QHBoxLayout()
        toolbar.addWidget(open_button)
        toolbar.addWidget(save_button)
        toolbar.addWidget(save_as_button)
        toolbar.addStretch()
        toolbar.addWidget(self._label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self.editor, stretch=1)

        QShortcut(QKeySequence.StandardKey.Open, self, activated=self._open_file)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=lambda: self._save_file())
        QShortcut(QKeySequence.StandardKey.SaveAs, self, activated=lambda: self._save_file_as())

    def _apply_lexer(self, path: Path) -> None:
        lexer_cls = EXTENSION_LEXERS.get(path.suffix.lower())
        if lexer_cls is None:
            self.editor.setLexer(None)
            return
        lexer = lexer_cls(self.editor)
        lexer.setFont(self.editor.font())
        self.editor.setLexer(lexer)

    def _update_label(self) -> None:
        name = self._current_path.name if self._current_path else "(untitled)"
        marker = " •" if self.editor.isModified() else ""
        self._label.setText(name + marker)

    def _load_file(self, path: Path) -> None:
        self.editor.setText(path.read_text())
        self.editor.setModified(False)
        self._current_path = path
        self._last_dir = path.parent
        self._apply_lexer(path)
        self._update_label()

    def _save_file(self) -> bool:
        if self._current_path is None:
            return self._save_file_as()
        self._current_path.write_text(self.editor.text())
        self.editor.setModified(False)
        self._update_label()
        return True

    def _save_file_as(self) -> bool:
        filename, _ = QFileDialog.getSaveFileName(self, "Save As", str(self._last_dir))
        if not filename:
            return False
        self._current_path = Path(filename)
        self._last_dir = self._current_path.parent
        self._current_path.write_text(self.editor.text())
        self.editor.setModified(False)
        self._apply_lexer(self._current_path)
        self._update_label()
        return True

    def _open_file(self) -> None:
        if not self._handle_unsaved_changes():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Open File", str(self._last_dir))
        if filename:
            self._load_file(Path(filename))

    def _handle_unsaved_changes(self) -> bool:
        """Returns True if it's OK to proceed (no unsaved changes, changes
        were saved, or the user chose to discard them); False if the
        caller should abandon whatever it was about to do."""
        if not self.editor.isModified():
            return True

        if self._confirm_unsaved is not None:
            action = self._confirm_unsaved()
        else:
            box = QMessageBox(self)
            box.setWindowTitle("Unsaved Changes")
            name = self._current_path.name if self._current_path else "this file"
            box.setText(f"Save changes to {name}?")
            box.setStandardButtons(
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel
            )
            result = box.exec()
            if result == QMessageBox.StandardButton.Save:
                action = "save"
            elif result == QMessageBox.StandardButton.Discard:
                action = "discard"
            else:
                action = "cancel"

        if action == "save":
            return self._save_file()
        return action == "discard"


def build() -> QWidget:
    return EditorWidget()
