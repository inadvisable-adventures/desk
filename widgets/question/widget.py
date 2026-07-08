from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from desk.shell import current_context
from desk.temp_ui import TempUiDocument, append_answer, parse_temp_ui


class QuestionWidget(QWidget):
    """Renders a TempUI question/options file (TODO a02b001) and appends
    the chosen answer back to it. Starts empty until set_source_file is
    called -- build() takes no arguments (the fixed contract every
    widget kind relies on), so whoever places this widget configures it
    afterward, the same shape as ScratchWidget.set_label. See
    plans/temporary-ui.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._path: Path | None = None

        layout = QVBoxLayout(self)
        self._question_label = QLabel()
        self._question_label.setWordWrap(True)
        self._question_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self._question_label)

        self._option_buttons: list[QPushButton] = []
        self._buttons_layout = QVBoxLayout()
        layout.addLayout(self._buttons_layout)
        layout.addStretch()

        self._show_placeholder("No question loaded yet.")

    def set_source_file(self, path: Path) -> None:
        self._path = path
        self._reload()

    def _reload(self) -> None:
        if self._path is None or not self._path.is_file():
            self._show_placeholder("This question no longer exists.")
            return
        self._render(parse_temp_ui(self._path.read_text()))

    def _clear_buttons(self) -> None:
        for button in self._option_buttons:
            self._buttons_layout.removeWidget(button)
            button.deleteLater()
        self._option_buttons = []

    def _show_placeholder(self, text: str) -> None:
        self._clear_buttons()
        self._question_label.setText(text)

    def _render(self, doc: TempUiDocument) -> None:
        self._clear_buttons()
        self._question_label.setText(doc.question or "(no question text)")
        answered = doc.answer is not None
        for option in doc.options:
            label = f"✓ {option}" if answered and option == doc.answer else option
            button = QPushButton(label)
            button.setEnabled(not answered)
            if not answered:
                button.clicked.connect(lambda _checked=False, opt=option: self._choose(opt))
            self._buttons_layout.addWidget(button)
            self._option_buttons.append(button)

    def _choose(self, option: str) -> None:
        if self._path is None:
            return
        text = append_answer(self._path, option)
        recorder = current_context.get_temp_ui_write_recorder()
        if recorder is not None:
            recorder(self._path, text)
        self._reload()


def build() -> QWidget:
    return QuestionWidget()
