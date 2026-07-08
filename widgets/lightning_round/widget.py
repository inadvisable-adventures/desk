from pathlib import Path

from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from desk.shell import current_context
from desk.temp_ui import (
    LightningRoundDocument,
    parse_lightning_round,
    record_lightning_round_answer,
)


class LightningRoundWidget(QWidget):
    """Renders a TempUI LightningRound file (TODO 11aeb43): a shared set
    of single-character-keyed options, applied one at a time to a list
    of items, answerable by clicking a button or pressing the
    corresponding key. Starts empty until set_source_file is called --
    same build()-takes-no-arguments contract as QuestionWidget. See
    plans/lightning-round-tempui.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._path: Path | None = None
        self._current_item_index: int | None = None
        self._option_chars: list[str] = []
        # A plain QWidget defaults to NoFocus, so it would never receive
        # keyPressEvent at all without this -- needed so the keyboard
        # shortcuts (not just button clicks) actually work.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        self._prompt_label = QLabel()
        self._prompt_label.setWordWrap(True)
        self._prompt_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._prompt_label.installEventFilter(self)
        layout.addWidget(self._prompt_label)

        self._item_label = QLabel()
        self._item_label.setWordWrap(True)
        self._item_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._item_label.installEventFilter(self)
        layout.addWidget(self._item_label)

        self._option_buttons: list[QPushButton] = []
        self._buttons_layout = QVBoxLayout()
        layout.addLayout(self._buttons_layout)
        layout.addStretch()

        self._show_placeholder("No lightning round loaded yet.")

    def set_source_file(self, path: Path) -> None:
        self._path = path
        self._reload()

    def _reload(self) -> None:
        if self._path is None or not self._path.is_file():
            self._show_placeholder("This lightning round no longer exists.")
            return
        self._render(parse_lightning_round(self._path.read_text()))

    def _clear_buttons(self) -> None:
        for button in self._option_buttons:
            self._buttons_layout.removeWidget(button)
            button.deleteLater()
        self._option_buttons = []

    def _show_placeholder(self, text: str) -> None:
        self._clear_buttons()
        self._prompt_label.setText("")
        self._item_label.setText(text)
        self._current_item_index = None
        self._option_chars = []

    def _render(self, doc: LightningRoundDocument) -> None:
        self._clear_buttons()
        self._prompt_label.setText(doc.prompt or doc.name or "(no prompt)")
        self._option_chars = doc.options

        next_index = next((i for i, item in enumerate(doc.items) if item.answer is None), None)
        if next_index is None:
            self._item_label.setText("All items answered!" if doc.items else "No items yet.")
            self._current_item_index = None
            return

        self._current_item_index = next_index
        self._item_label.setText(doc.items[next_index].description)
        for character in doc.options:
            button = QPushButton(f"Press {character}")
            button.clicked.connect(lambda _checked=False, c=character: self._choose(c))
            self._buttons_layout.addWidget(button)
            self._option_buttons.append(button)

    def _choose(self, character: str) -> None:
        if self._path is None or self._current_item_index is None:
            return
        text = record_lightning_round_answer(self._path, self._current_item_index, character)
        recorder = current_context.get_temp_ui_write_recorder()
        if recorder is not None:
            recorder(self._path, text)
        self._reload()

    def keyPressEvent(self, event) -> None:
        text = event.text()
        if text:
            for character in self._option_chars:
                if text.lower() == character.lower():
                    self._choose(character)
                    return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event) -> bool:
        # QLabel defaults to NoFocus, so a click landing on the prompt/
        # item label (the most prominent, natural place to click) is
        # never considered for click-to-focus by Qt at all -- it doesn't
        # climb to this widget's own StrongFocus policy the way an
        # ignored key press would. Piggyback a focus grab on the same
        # click instead, without consuming it (the label keeps its normal
        # -- currently inert, NoTextInteraction -- behavior).
        if event.type() == QEvent.Type.MouseButtonPress and obj in (
            self._prompt_label,
            self._item_label,
        ):
            # Deferred: QGraphicsProxyWidget resolves scene focus for this
            # same press *after* event filters run (it walks to the
            # specific embedded child under the cursor, which is
            # NoFocus here, and clears scene focus accordingly) --
            # calling setFocus() synchronously here is clobbered by that
            # later step. Scheduling it for the next event-loop iteration
            # lets our grab win instead. Confirmed directly: a synchronous
            # call here is silently undone; this deferral holds.
            QTimer.singleShot(0, lambda: self.setFocus(Qt.FocusReason.MouseFocusReason))
        return super().eventFilter(obj, event)


def build() -> QWidget:
    return LightningRoundWidget()
