import logging
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
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase, QKeySequence, QShortcut
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from desk.file_watch import SingleFileWatcher
from desk.persisted_path import resolve_persisted_path
from desk.shell import current_context

logger = logging.getLogger(__name__)

# This app's own established dark palette (matches desk.terminal_widget's
# DEFAULT_FOREGROUND/DEFAULT_BACKGROUND) -- committed to explicitly here
# (TODO cbbb661) rather than left to Qt's palette-derived default, which
# is what made the caret (hardcoded black by QScintilla) invisible
# against a dark background in the first place.
EDITOR_FOREGROUND = "#e8e8e8"
EDITOR_BACKGROUND = "#1e1e1e"
CARET_COLOR = "#3daee9"  # this app's established accent blue
LINE_NUMBER_COLOR = "#7a7f85"  # a muted, dimmer shade of EDITOR_FOREGROUND
MARGIN_DIVIDER_COLOR = "#3a3d41"  # matches WidgetFrame's own titlebar chrome
MARGIN_DIVIDER_WIDTH = 2

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
    plans/editor-open-default-desk-directory.md.

    Watches its open file for external changes (via
    desk.file_watch.SingleFileWatcher, TODO cee6f74) -- e.g. the TODO
    widget writing the same TODO.md this widget also has open. If there
    are no unsaved local edits, an external change reloads silently,
    same as the Markdown widget. If there ARE unsaved local edits, the
    buffer is never clobbered -- the change is just flagged in the
    title label until the next save or reload.

    Also emits `external_path_changed` (TODO a053e3a) when the open
    file's location relative to the current Desk directory changes --
    a distinct concept from the file-content-changed detection above,
    despite the similar name (one is "this file lives outside the Desk
    directory," the other is "this file's content changed on disk")."""

    external_path_changed = pyqtSignal(bool)

    def __init__(self, parent=None, confirm_unsaved: ConfirmUnsaved | None = None) -> None:
        super().__init__(parent)
        self._confirm_unsaved = confirm_unsaved
        self._current_path: Path | None = None
        self._last_dir = current_context.get_current_desk_directory() or Path.home()
        self._external_change_pending = False

        self.editor = QsciScintilla()
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.editor.setFont(font)
        self.editor.setUtf8(True)

        # Base text/background colors (TODO cbbb661) -- scoped
        # deliberately to just the base style and the margins below, not
        # any individual lexer's own token colors (_apply_lexer);
        # making syntax highlighting itself dark-theme-aware is a
        # separate, materially bigger task nobody asked for here.
        self.editor.setColor(QColor(EDITOR_FOREGROUND))
        self.editor.setPaper(QColor(EDITOR_BACKGROUND))
        self.editor.setCaretForegroundColor(QColor(CARET_COLOR))

        # Line-number margin (TODO 17a2720): matches the editor's own
        # background instead of Scintilla's independent white default,
        # numbers in a dimmer shade of the main text color.
        self.editor.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.editor.setMarginWidth(0, "0000")
        self.editor.setMarginsBackgroundColor(QColor(EDITOR_BACKGROUND))
        self.editor.setMarginsForegroundColor(QColor(LINE_NUMBER_COLOR))
        # A second, narrow solid-color margin as a divider line between
        # the numbers and the text -- Scintilla's own documented
        # mechanism for this, not an approximation.
        self.editor.setMarginType(1, QsciScintilla.MarginType.SymbolMarginColor)
        self.editor.setMarginWidth(1, MARGIN_DIVIDER_WIDTH)
        self.editor.setMarginBackgroundColor(1, QColor(MARGIN_DIVIDER_COLOR))

        # Wrap too-long lines (TODO 1d6777f). Scintilla's own default
        # wrapped-line numbering already shows the line number once, on
        # the first visual sub-line of a wrapped logical line -- "keep
        # the line number aligned with the top line" -- with no further
        # configuration needed.
        self.editor.setWrapMode(QsciScintilla.WrapMode.WrapWord)

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

        self._watcher = SingleFileWatcher(self)
        self._watcher.changed.connect(self._on_external_change)
        # Captured (not self._watcher) so this destroyed-triggered
        # closure never touches self -- same pattern as the Markdown/
        # Markdown (Extended)/Image Viewer/TODO widgets' own teardown.
        watcher = self._watcher
        self.destroyed.connect(lambda: watcher.stop())

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
        conflict = " (changed on disk)" if self._external_change_pending else ""
        self._label.setText(name + marker + conflict)

    def _load_file(self, path: Path) -> None:
        # Read before touching any widget state (TODO 810a5d6): on
        # failure, the buffer/current-path/watcher are left exactly as
        # they were -- showing a friendly message *in the buffer itself*
        # (like the read-only Markdown widget does) would risk the user
        # then hitting Save and overwriting a real file with that
        # message text, since this widget, unlike Markdown, is editable.
        try:
            text = path.read_text()
        except OSError as error:
            logger.error("Failed to read %s", path, exc_info=True)
            QMessageBox.warning(self, "Open File", f"Could not read {path.name}: {error}")
            return
        self.editor.setText(text)
        self.editor.setModified(False)
        self._current_path = path
        self._last_dir = path.parent
        self._external_change_pending = False
        self._apply_lexer(path)
        self._update_label()
        self._watcher.watch(path)
        self.refresh_external_path_status()

    def refresh_external_path_status(self) -> None:
        """Re-emits `external_path_changed` for the currently open file
        (TODO a053e3a) -- called here after every load, once more after
        `_save_file_as` (which sets `_current_path` directly, bypassing
        `_load_file`), and once more by DeskWindow right after wiring
        the signal, since the file may already have been loaded before
        that connection existed.

        Wrapped defensively (TODO 810a5d6): this is a purely cosmetic
        titlebar feature reached from a Qt-signal-invoked slot chain
        (Project Files' doubleClicked -> _open_index -> set_file ->
        here) where an uncaught exception is fatal to the whole process
        in this PyQt6 setup, not just to this feature -- see
        plans/isolate-hot-reload-crash.md and LEARNINGS.md."""
        try:
            is_external = self._current_path is not None and current_context.path_is_external(
                self._current_path
            )
        except Exception:
            logger.error("Failed to compute external-path status for %s", self._current_path, exc_info=True)
            return
        self.external_path_changed.emit(is_external)

    def _on_external_change(self) -> None:
        if self._current_path is None:
            return
        if not self.editor.isModified():
            # Nothing of the user's to lose -- reload silently, same as
            # the Markdown widget's unconditional reload.
            self._load_file(self._current_path)
            return
        # Don't clobber unsaved local edits: just flag the conflict.
        # Resolved in the user's favor by the next Save (which
        # overwrites the on-disk change) or the next full reload.
        self._external_change_pending = True
        self._update_label()

    def set_file(self, path: Path) -> None:
        """Public so other widgets (e.g. Project Files, TODO
        b927389) can open a file here programmatically -- matching
        MarkdownWidget/MarkdownExWidget's own set_file. Unlike the
        Open-button flow this doesn't confirm unsaved changes first:
        callers always get a freshly-placed instance with nothing to
        lose."""
        self._load_file(path)

    def _save_file(self) -> bool:
        if self._current_path is None:
            return self._save_file_as()
        text = self.editor.text()
        self._current_path.write_text(text)
        self._watcher.record_own_write(text)
        self.editor.setModified(False)
        self._external_change_pending = False
        self._update_label()
        return True

    def _save_file_as(self) -> bool:
        filename, _ = QFileDialog.getSaveFileName(self, "Save As", str(self._last_dir))
        if not filename:
            return False
        self._current_path = Path(filename)
        self._last_dir = self._current_path.parent
        text = self.editor.text()
        self._current_path.write_text(text)
        self._watcher.watch(self._current_path)
        self._watcher.record_own_write(text)
        self.editor.setModified(False)
        self._external_change_pending = False
        self._apply_lexer(self._current_path)
        self._update_label()
        self.refresh_external_path_status()
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

    # -- widget-local storage (TODO fb76057/02eda20) ---------------------

    def get_widget_local_storage(self) -> dict:
        return {"path": str(self._current_path)} if self._current_path else {}

    def set_widget_local_storage(self, data: dict) -> None:
        path = resolve_persisted_path(data.get("path"))
        if path is not None:
            self.set_file(path)


def build() -> QWidget:
    return EditorWidget()
