from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.claude_session import ClaudeSession
from desk.shell import current_context
from desk.temp_ui import DOC_FILENAME, TEMP_UI_DIRNAME

# Duplicated from widgets/claude/widget.py rather than imported --
# widget directories can't import each other (see
# plans/claude-widget-agent-sdk-integration.md). Kept in sync by hand;
# the two widgets' session-management code isn't unified, which is an
# accepted cost of not disturbing the existing widget.
CLAUDE_WIDGET_PROMPT = (
    "You are running inside of Desk. Please read this document to "
    "understand the implications of that: {doc_path} -- it links to "
    "further tempui-*.md files (in that same directory) with more "
    "detail on specific capabilities; only open one of those if you "
    "actually need that particular capability (e.g. only read "
    "tempui-lightning-round.md if you are about to run a lightning "
    "round), not unconditionally."
)

DEVELOPMENT_PROCESS_FILENAME = "development-process.md"

MODEL_CHOICES = [
    ("Default", None),
    ("Sonnet", "claude-sonnet-5"),
    ("Opus", "claude-opus-5"),
    ("Haiku", "claude-haiku-4-5-20251001"),
]
DEFAULT_MODEL_INDEX = 1  # "Sonnet" -- see plan step 5: an explicit model
# choice from the start, unlike the original widget which passes none.

# Deliberately NOT "auto" -- a deviation from the plan's suggested
# parity default with the existing widget's --permission-mode auto
# (TODO 2dca4c8), made after a real, empirical finding during
# verification: can_use_tool is consulted reliably under "default"
# (confirmed across many real sessions, including a bootstrap-prompt
# -then-Write sequence matching this widget's own real usage), but
# under "auto" it fires inconsistently for the exact same kind of
# request -- "auto" appears to use a looser, non-deterministic
# heuristic that sometimes skips the gate entirely (matches its
# apparent purpose: fewer prompts, at the cost of consistency). Since
# this widget's entire point is a real, meaningful approval UI (unlike
# the original PTY-based widget, which has none), defaulting to a mode
# where that UI reliably triggers matters more here than matching the
# other widget's own default.
PERMISSION_MODE = "default"


def _doc_path() -> str:
    directory = current_context.get_current_desk_directory()
    if directory is not None:
        return str(directory / TEMP_UI_DIRNAME / DOC_FILENAME)
    return f"{TEMP_UI_DIRNAME}/{DOC_FILENAME}"


def _development_process_instruction() -> str:
    directory = current_context.get_current_desk_directory()
    if directory is None:
        return ""
    path = directory / DEVELOPMENT_PROCESS_FILENAME
    if not path.is_file():
        return ""
    return f" This project also has its own {DEVELOPMENT_PROCESS_FILENAME} at {path} -- please read that too."


def _format_tool_input(tool_input: dict) -> str:
    return ", ".join(f"{key}={value!r}" for key, value in tool_input.items())


class ClaudeDeskWidget(QWidget):
    """Status UI + prompt input + scrollable history, backed by
    desk.claude_session.ClaudeSession (the Python Claude Agent SDK)
    instead of the PTY/pyte mechanism widgets/claude/widget.py uses.
    See plans/claude-widget-agent-sdk-integration.md. Exposes the same
    start_session(session_id, resume, extra_instructions) shape as the
    existing widget, so DeskWindow's binding code stays symmetric
    between the two (DeskWindow._bind_claude_desk_widget)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._session = ClaudeSession()
        self._session.assistant_text.connect(self._on_assistant_text)
        self._session.tool_use.connect(self._on_tool_use)
        self._session.tool_result.connect(self._on_tool_result)
        self._session.permission_request.connect(self._on_permission_request)
        self._session.turn_complete.connect(self._on_turn_complete)
        self._session.session_error.connect(self._on_session_error)
        # QObject.destroyed fires right before this widget's own C++
        # object is torn down, regardless of whether that happens via
        # close()/deleteLater()/parent deletion -- canvas.py's
        # remove_widget uses deleteLater(), which does not otherwise
        # call closeEvent(). Without this, the session's background
        # thread/event loop and its live claude subprocess connection
        # would leak for as long as the app keeps running.
        self.destroyed.connect(lambda: self._session.stop())

        self._pending_permissions: list[tuple[str, str, dict]] = []

        self._status_label = QLabel("Idle.")

        self._model_combo = QComboBox()
        for label, _value in MODEL_CHOICES:
            self._model_combo.addItem(label)
        self._model_combo.setCurrentIndex(DEFAULT_MODEL_INDEX)

        self._history = QPlainTextEdit()
        self._history.setReadOnly(True)

        self._prompt_input = QLineEdit()
        self._prompt_input.setPlaceholderText("Message Claude...")
        self._prompt_input.returnPressed.connect(self._on_send_clicked)
        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self._on_send_clicked)

        self._permission_label = QLabel()
        self._permission_label.setWordWrap(True)
        self._allow_button = QPushButton("Allow")
        self._allow_button.clicked.connect(lambda: self._resolve_current_permission(True))
        self._deny_button = QPushButton("Deny")
        self._deny_button.clicked.connect(lambda: self._resolve_current_permission(False))
        self._permission_row = QHBoxLayout()
        self._permission_row.addWidget(self._permission_label, stretch=1)
        self._permission_row.addWidget(self._allow_button)
        self._permission_row.addWidget(self._deny_button)
        self._permission_widgets = [self._permission_label, self._allow_button, self._deny_button]
        self._set_permission_row_visible(False)

        top_row = QHBoxLayout()
        top_row.addWidget(self._status_label, stretch=1)
        top_row.addWidget(self._model_combo)

        prompt_row = QHBoxLayout()
        prompt_row.addWidget(self._prompt_input, stretch=1)
        prompt_row.addWidget(self._send_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self._history, stretch=1)
        layout.addLayout(self._permission_row)
        layout.addLayout(prompt_row)

        self._set_busy(False)

    def start_session(self, session_id: str, resume: bool, extra_instructions: str = "") -> None:
        model = MODEL_CHOICES[self._model_combo.currentIndex()][1]
        cwd = current_context.get_current_desk_directory()
        if resume:
            initial_prompt = ""
        else:
            initial_prompt = (
                CLAUDE_WIDGET_PROMPT.format(doc_path=_doc_path())
                + _development_process_instruction()
                + extra_instructions
            )
        self._status_label.setText("Connecting...")
        self._set_busy(True)
        if initial_prompt:
            self._append_history(f"> {initial_prompt}")
        else:
            # Resuming with nothing queued to send: connect() alone
            # never fires turn_complete/session_error (there's no turn),
            # so without this the prompt box would stay disabled
            # forever. Not wired for the fresh-launch case above: there,
            # connected fires *before* the bootstrap turn actually
            # completes, and re-enabling input that early would let a
            # user send a second message while the first is still in
            # flight.
            self._session.connected.connect(lambda: self._set_busy(False))
        self._session.start(session_id, resume, model, PERMISSION_MODE, cwd, initial_prompt)

    def _append_history(self, text: str) -> None:
        self._history.appendPlainText(text)

    def _set_busy(self, busy: bool) -> None:
        self._prompt_input.setEnabled(not busy)
        self._send_button.setEnabled(not busy)
        if busy:
            self._status_label.setText("Working...")

    def _set_permission_row_visible(self, visible: bool) -> None:
        for widget in self._permission_widgets:
            widget.setVisible(visible)

    def _on_send_clicked(self) -> None:
        text = self._prompt_input.text().strip()
        if not text:
            return
        self._append_history(f"> {text}")
        self._prompt_input.clear()
        self._set_busy(True)
        self._session.send_prompt(text)

    def _on_assistant_text(self, text: str) -> None:
        self._append_history(text)

    def _on_tool_use(self, tool_use_id: str, name: str, tool_input: dict) -> None:
        self._append_history(f"[tool] {name}({_format_tool_input(tool_input)})")

    def _on_tool_result(self, tool_use_id: str, content: object, is_error: bool) -> None:
        marker = "tool error" if is_error else "tool result"
        self._append_history(f"[{marker}] {content}")

    def _on_permission_request(self, request_id: str, tool_name: str, tool_input: dict) -> None:
        self._pending_permissions.append((request_id, tool_name, tool_input))
        self._show_next_permission()

    def _show_next_permission(self) -> None:
        if not self._pending_permissions:
            self._set_permission_row_visible(False)
            return
        _request_id, tool_name, tool_input = self._pending_permissions[0]
        self._permission_label.setText(f"Allow {tool_name}({_format_tool_input(tool_input)})?")
        self._set_permission_row_visible(True)

    def _resolve_current_permission(self, allow: bool) -> None:
        if not self._pending_permissions:
            return
        request_id, tool_name, _tool_input = self._pending_permissions.pop(0)
        self._session.respond_to_permission(request_id, allow, "" if allow else "Denied by user.")
        self._append_history(f"[permission] {'allowed' if allow else 'denied'} {tool_name}")
        self._show_next_permission()

    def _on_turn_complete(self, summary: dict) -> None:
        self._set_busy(False)
        self._status_label.setText("Error." if summary.get("is_error") else "Idle.")

    def _on_session_error(self, message: str) -> None:
        self._set_busy(False)
        self._status_label.setText(f"Error: {message}")
        self._append_history(f"[error] {message}")


def build() -> QWidget:
    return ClaudeDeskWidget()
