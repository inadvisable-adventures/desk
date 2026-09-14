from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desk.claude_session import TERMINAL_TASK_STATUSES, ClaudeSession
from desk.shell import current_context
from desk.speech import TranscriptionResult
from desk.temp_ui import DOC_FILENAME, TEMP_UI_DIRNAME
from desk.voice_capture import MicRecorder

# Duplicated from widgets/claude/widget.py rather than imported --
# widget directories can't import each other (see
# plans/claude-widget-agent-sdk-integration.md). Kept in sync by hand;
# the two widgets' session-management code isn't unified, which is an
# accepted cost of not disturbing the existing widget. This copy has
# now deliberately diverged from widgets/claude/widget.py's own (TODO
# a762501): the MCP paragraph below only applies to a session started
# through this widget (ClaudeSession wires the in-process desk MCP
# server into every session's own ClaudeAgentOptions.mcp_servers) --
# the original PTY-based widget spawns a real `claude` CLI subprocess
# directly, with no equivalent wiring, so its own prompt copy should
# NOT claim this capability exists.
CLAUDE_WIDGET_PROMPT = (
    "You are running inside of Desk. Please read this document to "
    "understand the implications of that: {doc_path} -- it links to "
    "further tempui-*.md files (in that same directory) with more "
    "detail on specific capabilities; only open one of those if you "
    "actually need that particular capability (e.g. only read "
    "tempui-lightning-round.md if you are about to run a lightning "
    "round), not unconditionally. You also have direct MCP tools "
    "(mcp__desk__...) for interacting with Desk's own live shell -- "
    "desk_reveal_widget, desk_screenshot_widget, desk_screenshot_desk, "
    "desk_list_widget_instances, desk_save, desk_list_todo_items, and "
    "desk_get_next_todo_item. These are a faster, lower-ceremony "
    "alternative to the Job/DeskProc tempui file-drop mechanism for "
    "exactly these actions -- prefer them over dropping a DeskProc "
    "file when one of them already covers what you need. In "
    "particular, check desk_get_next_todo_item before assuming an "
    "earlier read of TODO.md is still current -- another session may "
    "have reprioritized or completed items since."
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

# TODO e9eddba: the six real claude_agent_sdk.types.PermissionMode
# values, with human-readable labels -- same (label, value) tuple-list
# shape MODEL_CHOICES above already uses. "Default" (index 0) stays
# the initial selection: a deliberate deviation from the plan's
# suggested "auto" parity default with the existing widget's own
# --permission-mode auto (TODO 2dca4c8), made after a real, empirical
# finding during verification: can_use_tool is consulted reliably
# under "default" (confirmed across many real sessions, including a
# bootstrap-prompt-then-Write sequence matching this widget's own real
# usage), but under "auto" it fires inconsistently for the exact same
# kind of request -- "auto" appears to use a looser, non-deterministic
# heuristic that sometimes skips the gate entirely (matches its
# apparent purpose: fewer prompts, at the cost of consistency). Since
# this widget's entire point is a real, meaningful approval UI (unlike
# the original PTY-based widget, which has none), defaulting to a mode
# where that UI reliably triggers matters more here than matching the
# other widget's own default -- a user who wants fewer prompts can
# still pick "Auto" (or "Accept Edits"/"Bypass Permissions") themselves
# from the dropdown.
PERMISSION_MODE_CHOICES = [
    ("Default", "default"),
    ("Accept Edits", "acceptEdits"),
    ("Plan", "plan"),
    ("Bypass Permissions", "bypassPermissions"),
    ("Don't Ask", "dontAsk"),
    ("Auto", "auto"),
]
DEFAULT_PERMISSION_MODE_INDEX = 0  # "Default"

# TODO f4a7872: fixed, not sizeHint-driven -- keeps the panel's own
# expand/collapse frame-resize delta (see _on_tasks_toggled) exactly
# symmetric regardless of how many background tasks have accumulated;
# the panel's own QListWidget scrolls internally past this height.
TASKS_PANEL_HEIGHT = 140

# TODO 8df6797: fixed, not sizeHint-driven, matching TASKS_PANEL_HEIGHT's
# own precedent above -- ~3 lines at the default font size. Keeps the
# prompt box multi-line without letting an arbitrarily long prompt push
# the history area off the bottom of the widget; _PromptInput still
# scrolls vertically past this height, so nothing is ever lost, only
# the visible height is capped.
PROMPT_INPUT_HEIGHT = 60

# TODO 78d6207: this app's established accent blue -- see
# widgets/editor/widget.py's own CARET_COLOR, which names this exact
# hex as such -- reused here rather than inventing a new color to
# visually set user-authored history lines apart from everything else.
USER_MESSAGE_COLOR = QColor("#3daee9")


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


class _PromptInput(QPlainTextEdit):
    """A word-wrapping, multi-line stand-in for the QLineEdit this
    widget's prompt box used to be (TODO 8df6797) -- QPlainTextEdit has
    no QLineEdit-only `returnPressed` signal, so this recreates the
    same "Enter submits" affordance itself: a bare Return/Enter (no
    Shift) emits `send_requested` instead of inserting a newline;
    Shift+Enter (or any other key) falls through to the normal
    QPlainTextEdit behavior, which inserts one."""

    send_requested = pyqtSignal()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.send_requested.emit()
            return
        super().keyPressEvent(event)


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
        self._session.task_event.connect(self._on_task_event)
        # TODO 551014c: shows this session's id in the titlebar once the
        # SDK client actually connects -- not done directly inside
        # start_session, since that runs synchronously inside
        # DeskWindow._load_desk_widgets on a Desk restore, *before*
        # DeskWindow.__init__ reaches its own current_context hook
        # -wiring block (including the widget-subtitle-setter hook this
        # needs). `connected` is instead emitted later, asynchronously,
        # from the session's own background thread -- Qt only delivers
        # a cross-thread signal once this (GUI) thread's event loop
        # actually runs, which is strictly after DeskWindow.__init__'s
        # synchronous call stack (hook-wiring included) has returned --
        # so connecting to it here works correctly for both a fresh
        # launch and a restore, with no change needed to that wiring
        # order at all.
        self._session.connected.connect(self._on_session_connected)
        # Set at the top of start_session -- doubles as this widget's
        # own placed instance_id (DeskWindow._place_widget's own
        # comment explains why), so no separate instance-id plumbing is
        # needed for either the subtitle (above) or the background
        # -tasks panel's own height-adjuster call below.
        self._session_id: str | None = None
        # QObject.destroyed fires right before this widget's own C++
        # object is torn down, regardless of whether that happens via
        # close()/deleteLater()/parent deletion -- canvas.py's
        # remove_widget uses deleteLater(), which does not otherwise
        # call closeEvent(). Without this, the session's background
        # thread/event loop and its live claude subprocess connection
        # would leak for as long as the app keeps running.
        self.destroyed.connect(lambda: self._session.stop())

        self._pending_permissions: list[tuple[str, str, dict]] = []

        # TODO e1f6391: a message submitted while a turn is in flight
        # queues instead of the prompt box simply going dead -- see
        # _set_busy/_on_send_clicked/_finish_busy_period.
        self._busy = False
        self._message_queue: list[str] = []

        # TODO fe7d8f2: mic capture + transcription itself is shared
        # with widgets/voice_input/widget.py via desk.voice_capture
        # (widget directories can't import each other) -- this widget
        # only owns the button/status presentation on top of it.
        self._mic_recorder = MicRecorder(self)
        self._mic_recorder.recording_started.connect(self._on_mic_recording_started)
        self._mic_recorder.recording_stopped.connect(self._on_mic_recording_stopped)
        self._mic_recorder.transcription_finished.connect(self._on_mic_transcription_finished)
        self._mic_recorder.error.connect(self._on_mic_error)

        self._status_label = QLabel("Idle.")

        self._queue_label = QLabel()
        self._queue_label.setVisible(False)

        self._model_combo = QComboBox()
        for label, _value in MODEL_CHOICES:
            self._model_combo.addItem(label)
        self._model_combo.setCurrentIndex(DEFAULT_MODEL_INDEX)

        self._permission_mode_combo = QComboBox()
        for label, _value in PERMISSION_MODE_CHOICES:
            self._permission_mode_combo.addItem(label)
        self._permission_mode_combo.setCurrentIndex(DEFAULT_PERMISSION_MODE_INDEX)
        self._permission_mode_combo.currentIndexChanged.connect(self._on_permission_mode_changed)

        # TODO f4a7872: task_id -> {"description", "status", "summary",
        # "last_tool_name"} (only whichever keys have actually been
        # reported so far -- see _on_task_event), insertion-ordered.
        self._background_tasks: dict[str, dict] = {}
        self._tasks_toggle_button = QPushButton()
        self._tasks_toggle_button.setCheckable(True)
        self._tasks_toggle_button.toggled.connect(self._on_tasks_toggled)
        self._tasks_list = QListWidget()
        self._tasks_list.setFixedHeight(TASKS_PANEL_HEIGHT)
        self._tasks_list.setVisible(False)
        self._update_tasks_toggle_label()

        self._history = QPlainTextEdit()
        self._history.setReadOnly(True)
        # TODO 78d6207: accumulated across the whole session and
        # re-applied wholesale on every user line (see _append_history)
        # -- QPlainTextEdit.setExtraSelections() always replaces its
        # entire argument, so earlier highlights must be tracked here
        # rather than appended to Qt's own list.
        self._history_user_selections: list[QTextEdit.ExtraSelection] = []

        self._prompt_input = _PromptInput()
        self._prompt_input.setPlaceholderText("Message Claude...")
        self._prompt_input.setFixedHeight(PROMPT_INPUT_HEIGHT)
        self._prompt_input.send_requested.connect(self._on_send_clicked)
        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self._on_send_clicked)
        self._mic_button = QPushButton("●")
        self._mic_button.setToolTip("Record")
        self._mic_button.clicked.connect(self._on_mic_clicked)

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
        top_row.addWidget(self._queue_label)
        top_row.addWidget(self._model_combo)
        top_row.addWidget(self._permission_mode_combo)
        top_row.addWidget(self._tasks_toggle_button)

        prompt_row = QHBoxLayout()
        prompt_row.addWidget(self._mic_button)
        prompt_row.setAlignment(self._mic_button, Qt.AlignmentFlag.AlignBottom)
        prompt_row.addWidget(self._prompt_input, stretch=1)
        prompt_row.addWidget(self._send_button)
        prompt_row.setAlignment(self._send_button, Qt.AlignmentFlag.AlignBottom)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self._history, stretch=1)
        layout.addLayout(self._permission_row)
        layout.addLayout(prompt_row)
        # TODO f4a7872: expands from the bottom of the widget on toggle
        # (see _on_tasks_toggled) -- last in the layout, below the
        # prompt row.
        layout.addWidget(self._tasks_list)

        self._set_busy(False)

    def start_session(self, session_id: str, resume: bool, extra_instructions: str = "") -> None:
        self._session_id = session_id
        model = MODEL_CHOICES[self._model_combo.currentIndex()][1]
        permission_mode = PERMISSION_MODE_CHOICES[self._permission_mode_combo.currentIndex()][1]
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
            self._append_history(f"> {initial_prompt}", is_user=True)
        else:
            # Resuming with nothing queued to send: connect() alone
            # never fires turn_complete/session_error (there's no
            # turn) -- without this, _busy would stay True forever, so
            # anything typed during "Connecting..." would queue and
            # then never get drained. _finish_busy_period (TODO
            # e1f6391) is the same drain-the-queue-or-go-idle logic
            # _on_turn_complete uses below. Not wired for the
            # fresh-launch case above: there, connected fires *before*
            # the bootstrap turn actually completes, and this would
            # fire prematurely while that first turn is still in
            # flight.
            self._session.connected.connect(lambda: self._finish_busy_period("Idle."))
        self._session.start(session_id, resume, model, permission_mode, cwd, initial_prompt)

    def _on_permission_mode_changed(self, index: int) -> None:
        """Changes permission mode live, mid-session (TODO e9eddba) --
        a no-op via ClaudeSession.set_permission_mode's own guard if no
        session has started yet (e.g. the combo box's initial
        setCurrentIndex above, before __init__ finishes, or a
        not-yet-connected widget)."""
        self._session.set_permission_mode(PERMISSION_MODE_CHOICES[index][1])

    def _on_session_connected(self) -> None:
        """TODO 551014c: shows this session's id in the titlebar (see
        __init__'s own comment on why this is wired to `connected`
        rather than done directly inside start_session). Truncated to
        8 hex characters, matching this codebase's existing instance-id
        display convention elsewhere (DeskWindow
        ._display_name_for_instance)."""
        setter = current_context.get_widget_subtitle_setter()
        if setter is not None and self._session_id is not None:
            setter(self._session_id, self._session_id[:8])

    # -- persisted model/permission-mode selection (TODO 1ceb701) -----

    @staticmethod
    def _index_for_value(choices: list[tuple[str, str | None]], value: object, default_index: int) -> int:
        for index, (_label, choice_value) in enumerate(choices):
            if choice_value == value:
                return index
        return default_index

    def get_widget_local_storage(self) -> dict:
        """The generic python-widget persisted-state hook (TODO
        fb76057) -- lets a Desk reboot restore a resumed session's
        previously-selected model/permission-mode instead of resetting
        to this widget's hardcoded defaults. Stores the real SDK
        value, not the combo index, so it stays meaningful even if
        MODEL_CHOICES/PERMISSION_MODE_CHOICES later gain/lose/reorder
        entries."""
        return {
            "model": MODEL_CHOICES[self._model_combo.currentIndex()][1],
            "permission_mode": PERMISSION_MODE_CHOICES[self._permission_mode_combo.currentIndex()][1],
        }

    # A sentinel, not None: MODEL_CHOICES' own "Default" entry's value
    # IS None (see MODEL_CHOICES above), so an explicitly-saved "model":
    # None (the user really had "Default" selected) must be told apart
    # from the key being entirely absent (data saved before this
    # feature existed, or an empty {} from a widget instance that
    # predates it) -- data.get(key, _NOT_SAVED) below, not data.get(key).
    _NOT_SAVED = object()

    def set_widget_local_storage(self, data: dict) -> None:
        """Falls back to this widget's own existing hardcoded default
        index for a value no longer present in the choices list (e.g. a
        retired model), or for data saved before this feature existed
        (an empty/missing-key dict) -- never raises on unexpected
        input, since a Desk restore must not fail a widget's placement
        over a stale preference."""
        model = data.get("model", self._NOT_SAVED)
        self._model_combo.setCurrentIndex(
            DEFAULT_MODEL_INDEX if model is self._NOT_SAVED
            else self._index_for_value(MODEL_CHOICES, model, DEFAULT_MODEL_INDEX)
        )
        permission_mode = data.get("permission_mode", self._NOT_SAVED)
        self._permission_mode_combo.setCurrentIndex(
            DEFAULT_PERMISSION_MODE_INDEX if permission_mode is self._NOT_SAVED
            else self._index_for_value(PERMISSION_MODE_CHOICES, permission_mode, DEFAULT_PERMISSION_MODE_INDEX)
        )

    # -- background-tasks panel (TODO f4a7872) ------------------------

    def _on_task_event(self, task_id: str, patch: dict) -> None:
        task = self._background_tasks.setdefault(task_id, {})
        for key, value in patch.items():
            if value is not None:
                task[key] = value
        self._refresh_tasks_list()

    def _refresh_tasks_list(self) -> None:
        self._tasks_list.clear()
        for task_id, task in self._background_tasks.items():
            status = task.get("status", "pending")
            description = task.get("description") or task_id
            text = f"[{status}] {description}"
            summary = task.get("summary")
            if summary:
                text += f" — {summary}"
            self._tasks_list.addItem(text)
        self._update_tasks_toggle_label()

    def _update_tasks_toggle_label(self) -> None:
        running = sum(
            1 for task in self._background_tasks.values() if task.get("status") not in TERMINAL_TASK_STATUSES
        )
        base = f"Background Tasks ({running} running)" if running else "Background Tasks"
        arrow = "▾" if self._tasks_toggle_button.isChecked() else "▸"
        self._tasks_toggle_button.setText(f"{base} {arrow}")

    def _on_tasks_toggled(self, checked: bool) -> None:
        """Expands/collapses the panel and grows/shrinks this widget's
        own placed frame to fit it (TODO f4a7872), rather than
        squeezing the existing history/prompt area -- a no-op on the
        resize (the panel still shows/hides normally) if this widget
        instance's own id isn't known yet or the height-adjuster hook
        isn't registered, matching every other current_context hook's
        own "unset is a safe no-op" convention."""
        self._tasks_list.setVisible(checked)
        self._update_tasks_toggle_label()
        adjuster = current_context.get_widget_height_adjuster()
        if adjuster is not None and self._session_id is not None:
            adjuster(self._session_id, TASKS_PANEL_HEIGHT if checked else -TASKS_PANEL_HEIGHT)

    def _append_history(self, text: str, *, is_user: bool = False) -> None:
        self._history.appendPlainText(text)
        if not is_user:
            return
        # setExtraSelections() (TODO 78d6207) is a pure render overlay
        # -- never part of the document, never in toPlainText(), never
        # in what gets copied -- so this adds visual differentiation
        # with zero risk to today's plain-text selection/copy output.
        # end/start computed from `text`'s own length, not block
        # counting: correct whether or not appendPlainText needed to
        # insert a leading block separator (not part of `text`, so
        # irrelevant to this arithmetic) and whether `text` itself
        # contains embedded newlines (each becomes a block boundary
        # that still consumes exactly one character position, same as
        # a literal "\n" here) -- covers a multi-line prompt correctly,
        # not just a single line.
        end = self._history.document().characterCount() - 1
        start = end - len(text)
        cursor = QTextCursor(self._history.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        fmt = QTextCharFormat()
        fmt.setForeground(USER_MESSAGE_COLOR)
        fmt.setFontWeight(QFont.Weight.DemiBold)
        selection.format = fmt
        self._history_user_selections.append(selection)
        self._history.setExtraSelections(self._history_user_selections)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        # _prompt_input/_send_button deliberately stay enabled while
        # busy (TODO e1f6391) -- self._busy, not Qt's own isEnabled(),
        # is what _on_send_clicked checks to decide send-now vs. queue.
        # _mic_button still goes dark while busy -- dictating a *new*
        # message while a turn is in flight is unchanged, out of scope
        # here.
        self._mic_button.setEnabled(not busy)
        self._send_button.setText("Queue" if busy else "Send")
        if busy:
            self._status_label.setText("Working...")

    def _set_permission_row_visible(self, visible: bool) -> None:
        for widget in self._permission_widgets:
            widget.setVisible(visible)

    def _update_queue_label(self) -> None:
        if not self._message_queue:
            self._queue_label.setVisible(False)
            return
        self._queue_label.setText(f"Queued: {len(self._message_queue)}")
        self._queue_label.setToolTip("\n".join(self._message_queue))
        self._queue_label.setVisible(True)

    def _send_now(self, text: str) -> None:
        self._append_history(f"> {text}", is_user=True)
        self._set_busy(True)
        self._session.send_prompt(text)

    def _finish_busy_period(self, idle_status: str) -> None:
        """Shared by _on_turn_complete and start_session's
        resume-with-nothing-to-send path (TODO e1f6391): drains the
        next queued message instead of going idle, if there is one."""
        self._set_busy(False)
        if self._message_queue:
            self._send_now(self._message_queue.pop(0))
            self._update_queue_label()
        else:
            self._status_label.setText(idle_status)

    def _on_send_clicked(self) -> None:
        text = self._prompt_input.toPlainText().strip()
        if not text:
            return
        self._prompt_input.clear()
        if self._busy:
            self._message_queue.append(text)
            self._append_history(f"[queued] {text}", is_user=True)
            self._update_queue_label()
        else:
            self._send_now(text)

    def _on_mic_clicked(self) -> None:
        if self._mic_recorder.is_recording():
            self._mic_recorder.stop()
        else:
            self._mic_recorder.start()

    def _on_mic_recording_started(self) -> None:
        self._mic_button.setText("■")
        self._mic_button.setToolTip("Stop")
        self._prompt_input.setEnabled(False)
        self._send_button.setEnabled(False)
        self._status_label.setText("Recording...")

    def _on_mic_recording_stopped(self) -> None:
        self._mic_button.setText("●")
        self._mic_button.setToolTip("Record")
        self._mic_button.setEnabled(False)
        self._status_label.setText("Transcribing...")

    def _on_mic_error(self, message: str) -> None:
        # Covers both "couldn't start" (mic_button never left its
        # Record state) and "stopped but nothing came out of it"
        # (recording_stopped already disabled mic_button, so it also
        # needs re-enabling here) -- distinguishing which happened
        # isn't necessary since both leave every control back at its
        # normal idle-and-enabled state.
        self._mic_button.setEnabled(True)
        self._prompt_input.setEnabled(True)
        self._send_button.setEnabled(True)
        self._status_label.setText(f"Error: {message}")

    def _on_mic_transcription_finished(self, result: TranscriptionResult | None, error: str | None) -> None:
        self._mic_button.setEnabled(True)
        self._prompt_input.setEnabled(True)
        self._send_button.setEnabled(True)
        if error is not None:
            self._status_label.setText(f"Error: {error}")
            return
        # Set, not sent: the user reviews/edits a dictated prompt the
        # same way they would review anything they typed -- nothing
        # goes to Claude until they hit Send/Enter themselves.
        self._prompt_input.setPlainText(result.text)
        self._status_label.setText("Idle.")

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
        self._finish_busy_period("Error." if summary.get("is_error") else "Idle.")

    def _on_session_error(self, message: str) -> None:
        # Deliberately does not drain the queue (TODO e1f6391): a
        # session error may mean the session itself is in a bad state,
        # and firing the next queued message right after risks
        # compounding the confusion. Anything still queued stays
        # visible via _queue_label, frozen until the user does
        # something themselves -- no auto-retry for this first pass.
        self._set_busy(False)
        self._status_label.setText(f"Error: {message}")
        self._append_history(f"[error] {message}")


def build() -> QWidget:
    return ClaudeDeskWidget()
