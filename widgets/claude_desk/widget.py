import time


from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.claude_flow_view import FlowView
from desk.claude_history_view import HistoryEntry, HistoryView
from desk.claude_staleness import StalenessTracker
from desk.claude_session import TERMINAL_TASK_STATUSES, ClaudeSession
from desk.connectivity_probe import ConnectivityProbe
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
    "round), not unconditionally. Reading these documents is "
    "orientation only: it is not itself a task, and it does not mean "
    "you should start working (for example by picking up a TODO.md "
    "item or calling desk_get_next_todo_item) unless the message from "
    "the user separately asks for it. You also have direct MCP tools "
    "(mcp__desk__...) for interacting with Desk's own live shell -- "
    "desk_reveal_widget, desk_screenshot_widget, desk_screenshot_desk, "
    "desk_list_widget_instances, desk_save, desk_list_todo_items, and "
    "desk_get_next_todo_item. These are a faster, lower-ceremony "
    "alternative to the Job/DeskProc tempui file-drop mechanism for "
    "exactly these actions -- prefer them over dropping a DeskProc "
    "file when one of them already covers what you need. In "
    "particular, when the user has asked you to work on TODO items, "
    "check desk_get_next_todo_item before assuming an earlier read of "
    "TODO.md is still current -- another session may have "
    "reprioritized or completed items since."
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

# TODO eb50b84: the data-flow panel's fixed height, same reasoning as
# TASKS_PANEL_HEIGHT above (symmetric frame resize on toggle).
FLOW_PANEL_HEIGHT = 170

# TODO 8df6797: fixed, not sizeHint-driven, matching TASKS_PANEL_HEIGHT's
# own precedent above -- ~3 lines at the default font size. Keeps the
# prompt box multi-line without letting an arbitrarily long prompt push
# the history area off the bottom of the widget; _PromptInput still
# scrolls vertically past this height, so nothing is ever lost, only
# the visible height is capped.
PROMPT_INPUT_HEIGHT = 60

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
    return f" This project also has its own {DEVELOPMENT_PROCESS_FILENAME} at {path} -- please read that too, as orientation only: reading it is not itself a task, and it does not mean you should start working on a TODO item unless the message from the user separately asks for it."


# TODO db2402c: ResultMessage.terminal_reason values meaning the turn was
# cancelled via interrupt (per claude_agent_sdk.types.ResultMessage's docs).
INTERRUPTED_TERMINAL_REASONS = ("aborted_streaming", "aborted_tools")


def _usage_counts(usage: dict) -> tuple[int, int]:
    """(context/input tokens, output tokens) from an SDK usage dict --
    cache reads/creations count toward the input side since they are
    part of the context the model was given."""
    input_tokens = (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0)
    )
    return input_tokens, int(usage.get("output_tokens") or 0)


def _format_token_count(count: int) -> str:
    return f"{count / 1000:.1f}k" if count >= 1000 else str(count)


def _format_token_counts(input_tokens: int, output_tokens: int) -> str:
    return f"↑{_format_token_count(input_tokens)} ↓{_format_token_count(output_tokens)} tokens"


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
        # TODO dffb428: connected before the legacy per-kind signals --
        # ClaudeSession emits session_event first for every message, so
        # (queued connections preserve order) _on_session_event has
        # recorded the message's turn/provenance by the time the
        # matching legacy handler below renders it.
        self._session.session_event.connect(self._on_session_event)
        self._session.assistant_text.connect(self._on_assistant_text)
        self._session.tool_use.connect(self._on_tool_use)
        self._session.tool_result.connect(self._on_tool_result)
        self._session.permission_request.connect(self._on_permission_request)
        self._session.question_request.connect(self._on_question_request)
        self._session.turn_complete.connect(self._on_turn_complete)
        self._session.session_error.connect(self._on_session_error)
        self._session.task_event.connect(self._on_task_event)
        self._session.token_usage.connect(self._on_token_usage)
        self._session.rate_limit.connect(self._on_rate_limit)
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
        # TODO 6ab9e85: queued AskUserQuestion calls, shown one at a
        # time in _question_panel (see _show_next_question).
        self._pending_questions: list[tuple[str, dict]] = []
        # Per question of the one currently shown: its option buttons
        # and free-text box, in order.
        self._question_controls: list[tuple[str, bool, list[QPushButton], QLineEdit]] = []

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

        # TODO c1eb687: shown only while the CLI reports a non-"allowed"
        # rate-limit status.
        self._rate_limit_label = QLabel()
        self._rate_limit_label.setVisible(False)
        self._rate_limit_status = "allowed"

        # TODO 5ce8447: silence detection while something is outstanding
        # (see desk.claude_staleness / plans/claude-desk-staleness-and-probe.md).
        # A separate amber label rather than a suffix on _status_label,
        # which many other paths rewrite.
        self._stale_label = QLabel()
        self._stale_label.setStyleSheet("color: #e8a33d; font-weight: 600;")
        self._stale_label.setVisible(False)
        self._staleness = StalenessTracker()
        self._network_ok: bool | None = None
        self._probe = ConnectivityProbe(parent=self)
        self._probe.result.connect(self._on_probe_result)
        self._staleness_timer = QTimer(self)
        self._staleness_timer.setInterval(1000)
        self._staleness_timer.timeout.connect(self._tick_staleness)
        self._staleness_timer.start()

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

        # TODO eb50b84: live data-flow view of the session's events,
        # expanding from the bottom exactly like the tasks panel.
        self._flow_toggle_button = QPushButton("Flow ▸")
        self._flow_toggle_button.setCheckable(True)
        self._flow_toggle_button.setToolTip("Show a live diagram of messages flowing through this widget")
        self._flow_toggle_button.toggled.connect(self._on_flow_toggled)
        self._flow_view = FlowView()
        self._flow_view.setFixedHeight(FLOW_PANEL_HEIGHT)
        self._flow_view.setVisible(False)

        # TODO dffb428: structured history -- one framed, individually
        # collapsible entry per item, each carrying turn/time/source
        # metadata (see desk.claude_history_view). Replaces the single
        # QPlainTextEdit text stream and its extra-selection overlays
        # (TODOs 78d6207 user coloring, ed5c62f tool folds, a4c3dec hover
        # reload), all of which are now per-entry features.
        self._history = HistoryView()
        self._history.on_reload = self._on_reload_requested
        # Provenance from ClaudeSession.session_event (TODO 20ca851):
        # the latest event (consumed by the legacy handler that follows
        # it), the turn currently in flight, user entries still waiting
        # for their turn id, and whether the next stream entry begins an
        # unsolicited (CLI-initiated) turn.
        self._current_event: dict | None = None
        self._active_turn_id: int | None = None
        self._unassigned_user_entries: list[HistoryEntry] = []
        self._next_entry_starts_turn = False

        self._prompt_input = _PromptInput()
        self._prompt_input.setPlaceholderText("Message Claude...")
        self._prompt_input.setFixedHeight(PROMPT_INPUT_HEIGHT)
        self._prompt_input.send_requested.connect(self._on_send_clicked)
        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self._on_send_clicked)
        # TODO db2402c: shown only while a turn is in flight.
        self._interrupt_button = QPushButton("Interrupt")
        self._interrupt_button.clicked.connect(self._on_interrupt_clicked)
        self._interrupt_button.setVisible(False)
        # TODO db2402c: per-turn token tally behind the "Working..." text
        # -- input is the latest message's context size (each API call
        # re-sends the whole context, so summing would overcount), output
        # accumulates across the turn's messages.
        self._turn_input_tokens = 0
        self._turn_output_tokens = 0
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

        self._question_panel = QWidget()
        self._question_layout = QVBoxLayout(self._question_panel)
        self._question_layout.setContentsMargins(0, 0, 0, 0)
        self._question_panel.setVisible(False)

        top_row = QHBoxLayout()
        top_row.addWidget(self._status_label, stretch=1)
        top_row.addWidget(self._queue_label)
        top_row.addWidget(self._rate_limit_label)
        top_row.addWidget(self._stale_label)
        top_row.addWidget(self._model_combo)
        top_row.addWidget(self._permission_mode_combo)
        top_row.addWidget(self._tasks_toggle_button)
        top_row.addWidget(self._flow_toggle_button)

        prompt_row = QHBoxLayout()
        prompt_row.addWidget(self._mic_button)
        prompt_row.setAlignment(self._mic_button, Qt.AlignmentFlag.AlignBottom)
        prompt_row.addWidget(self._prompt_input, stretch=1)
        send_column = QVBoxLayout()
        send_column.setContentsMargins(0, 0, 0, 0)
        send_column.addStretch(1)
        send_column.addWidget(self._interrupt_button)
        send_column.addWidget(self._send_button)
        prompt_row.addLayout(send_column)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self._history, stretch=1)
        layout.addLayout(self._permission_row)
        layout.addWidget(self._question_panel)
        layout.addLayout(prompt_row)
        # TODO f4a7872: expands from the bottom of the widget on toggle
        # (see _on_tasks_toggled) -- last in the layout, below the
        # prompt row.
        layout.addWidget(self._tasks_list)
        layout.addWidget(self._flow_view)

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
            self._add_user_entry(initial_prompt, initial_prompt)
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

    def _on_flow_toggled(self, checked: bool) -> None:
        self._flow_view.setVisible(checked)
        self._flow_toggle_button.setText("Flow ▾" if checked else "Flow ▸")
        adjuster = current_context.get_widget_height_adjuster()
        if adjuster is not None and self._session_id is not None:
            adjuster(self._session_id, FLOW_PANEL_HEIGHT if checked else -FLOW_PANEL_HEIGHT)

    # -- structured history (TODO dffb428) ----------------------------

    def _on_session_event(self, event: dict) -> None:
        kind = event["kind"]
        self._current_event = event
        self._flow_view.feed(event)
        self._staleness.feed(event, time.monotonic())
        if kind == "turn_started":
            self._active_turn_id = event["turn_id"]
            self._turn_input_tokens = 0
            self._turn_output_tokens = 0
            self._interrupt_button.setEnabled(True)
            if self._unassigned_user_entries:
                self._unassigned_user_entries.pop(0).set_turn(event["turn_id"])
        elif kind == "unsolicited_turn_started":
            self._next_entry_starts_turn = True
        elif kind == "turn_complete" and event["solicited"]:
            self._active_turn_id = None

    def _add_entry(self, kind: str, text: str, *, from_stream: bool = False, reload_text: str | None = None) -> HistoryEntry:
        """Appends one history entry. `from_stream` entries (assistant
        text, tool calls/results, session errors) take their turn id and
        source from the session_event that immediately preceded the
        legacy signal being handled; everything else is attributed to
        the turn currently in flight (if any)."""
        event = self._current_event if from_stream else None
        turn_start = False
        source = ""
        if event is not None:
            turn_id = event["turn_id"]
            if not event["solicited"]:
                source = "unsolicited"
            if self._next_entry_starts_turn:
                turn_start = True
                self._next_entry_starts_turn = False
        else:
            turn_id = self._active_turn_id
        return self._history.add_entry(
            kind, text, turn_id=turn_id, source=source, turn_start=turn_start, reload_text=reload_text
        )

    def _add_user_entry(self, text: str, reload_text: str) -> None:
        # A user prompt opens a turn; its id arrives later with the
        # turn_started event (see _on_session_event).
        entry = self._history.add_entry("user", text, turn_start=True, reload_text=reload_text)
        self._unassigned_user_entries.append(entry)

    def _on_reload_requested(self, reload_text: str) -> None:
        # setPlainText, not appending/sending (TODO fe7d8f2's own
        # dictated-text precedent) -- the user reviews/edits before
        # anything goes to Claude; reload is "start over from this
        # earlier prompt", not "add to what's already there".
        self._prompt_input.setPlainText(reload_text)
        self._prompt_input.moveCursor(QTextCursor.MoveOperation.End)
        self._prompt_input.setFocus()

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
        self._interrupt_button.setVisible(busy)
        if busy:
            self._status_label.setText("Working...")

    def _set_permission_row_visible(self, visible: bool) -> None:
        for widget in self._permission_widgets:
            widget.setVisible(visible)

    def _update_queue_label(self) -> None:
        self._flow_view.set_queue_depth(len(self._message_queue))
        if not self._message_queue:
            self._queue_label.setVisible(False)
            return
        self._queue_label.setText(f"Queued: {len(self._message_queue)}")
        self._queue_label.setToolTip("\n".join(self._message_queue))
        self._queue_label.setVisible(True)

    def _send_now(self, text: str) -> None:
        self._add_user_entry(text, text)
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
            self._add_entry("queued", text, reload_text=text)
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
        self._add_entry("assistant", text, from_stream=True)

    def _on_tool_use(self, tool_use_id: str, name: str, tool_input: dict) -> None:
        # Long payloads collapse by default inside the entry itself
        # (see desk.claude_history_view.collapse_preview).
        self._add_entry("tool", f"{name}({_format_tool_input(tool_input)})", from_stream=True)

    def _on_tool_result(self, tool_use_id: str, content: object, is_error: bool) -> None:
        self._add_entry("tool_error" if is_error else "tool_result", str(content), from_stream=True)

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
        self._add_entry("permission", f"{'allowed' if allow else 'denied'} {tool_name}")
        self._show_next_permission()

    def _on_turn_complete(self, summary: dict) -> None:
        # TODO db2402c: terminal_reason tells an interrupted turn from a
        # normal/errored one.
        if summary.get("terminal_reason") in INTERRUPTED_TERMINAL_REASONS:
            idle_status = "Interrupted."
        else:
            idle_status = "Error." if summary.get("is_error") else "Idle."
        api_status = summary.get("api_error_status")
        if summary.get("is_error") and api_status:
            # TODO c1eb687: say *why* instead of a bare "Error."
            idle_status = f"Error (HTTP {api_status})."
            self._add_entry("error", f"API error (HTTP {api_status}): {summary.get('result') or 'no detail'}")
        usage = summary.get("usage") or {}
        if usage:
            self._status_label.setToolTip(f"Last turn: {_format_token_counts(*_usage_counts(usage))}")
        self._finish_busy_period(idle_status)

    def _tick_staleness(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        level = self._staleness.level(now)
        if level == 2:
            if not self._probe.is_running():
                self._probe.start()
        else:
            self._probe.stop()
            self._network_ok = None
        note = self._staleness.describe(now, self._network_ok)
        self._stale_label.setText(note)
        self._stale_label.setVisible(bool(note))
        self._flow_view.set_stale(self._staleness.silent_seconds(now) if level else None)

    def _on_probe_result(self, ok: bool) -> None:
        # Ignore a result that lands after the stall already resolved.
        if self._probe.is_running():
            self._network_ok = ok
            self._tick_staleness()

    def _on_rate_limit(self, info: dict) -> None:
        status = info.get("status", "allowed")
        resets_at = info.get("resets_at")
        reset_text = f" -- resets {time.strftime('%H:%M', time.localtime(resets_at))}" if resets_at else ""
        if status == "allowed":
            self._rate_limit_label.setVisible(False)
        else:
            text = ("Rate limited" if status == "rejected" else "Rate limit warning") + reset_text
            self._rate_limit_label.setText(text)
            color = "#da3232" if status == "rejected" else "#e8a33d"
            self._rate_limit_label.setStyleSheet(f"color: {color}; font-weight: 600;")
            self._rate_limit_label.setToolTip(
                f"{info.get('rate_limit_type') or 'rate limit'}"
                + (f", {info['utilization'] * 100:.0f}% used" if info.get("utilization") is not None else "")
            )
            self._rate_limit_label.setVisible(True)
        if status != self._rate_limit_status:
            self._rate_limit_status = status
            if status != "allowed":
                self._add_entry("notice", f"[rate limit] {self._rate_limit_label.text()}")

    def _on_interrupt_clicked(self) -> None:
        self._interrupt_button.setEnabled(False)
        self._status_label.setText("Interrupting...")
        self._session.interrupt()

    def _on_token_usage(self, usage: dict) -> None:
        input_tokens, output_tokens = _usage_counts(usage)
        self._turn_input_tokens = input_tokens
        self._turn_output_tokens += output_tokens
        if self._busy and self._interrupt_button.isEnabled():
            self._status_label.setText(
                f"Working... ({_format_token_counts(self._turn_input_tokens, self._turn_output_tokens)})"
            )

    def _on_session_error(self, message: str) -> None:
        # Deliberately does not drain the queue (TODO e1f6391): a
        # session error may mean the session itself is in a bad state,
        # and firing the next queued message right after risks
        # compounding the confusion. Anything still queued stays
        # visible via _queue_label, frozen until the user does
        # something themselves -- no auto-retry for this first pass.
        self._set_busy(False)
        self._status_label.setText(f"Error: {message}")
        self._add_entry("error", message, from_stream=True)

    # -- AskUserQuestion (TODO 6ab9e85) ------------------------------

    def _on_question_request(self, request_id: str, tool_input: dict) -> None:
        self._pending_questions.append((request_id, tool_input))
        if not self._question_panel.isVisible():
            self._show_next_question()

    def _show_next_question(self) -> None:
        while self._question_layout.count():
            item = self._question_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._question_controls = []
        if not self._pending_questions:
            self._question_panel.setVisible(False)
            return
        _request_id, tool_input = self._pending_questions[0]
        for question in tool_input.get("questions", []):
            text = str(question.get("question", ""))
            multi = bool(question.get("multiSelect"))
            header = QLabel(text)
            header.setWordWrap(True)
            self._question_layout.addWidget(header)
            buttons: list[QPushButton] = []
            row = QHBoxLayout()
            for option in question.get("options", []):
                button = QPushButton(str(option.get("label", "")))
                button.setCheckable(True)
                if option.get("description"):
                    button.setToolTip(str(option["description"]))
                button.toggled.connect(
                    lambda checked, b=button, group=buttons, m=multi: self._on_option_toggled(b, group, m, checked)
                )
                buttons.append(button)
                row.addWidget(button)
            row.addStretch(1)
            row_widget = QWidget()
            row_widget.setLayout(row)
            self._question_layout.addWidget(row_widget)
            other = QLineEdit()
            other.setPlaceholderText("Other (free text)...")
            other.textChanged.connect(lambda _text: self._update_question_submit())
            self._question_layout.addWidget(other)
            self._question_controls.append((text, multi, buttons, other))
        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        self._question_submit = QPushButton("Submit")
        self._question_submit.clicked.connect(self._submit_question)
        skip = QPushButton("Skip")
        skip.clicked.connect(self._skip_question)
        buttons_row.addWidget(self._question_submit)
        buttons_row.addWidget(skip)
        buttons_widget = QWidget()
        buttons_widget.setLayout(buttons_row)
        self._question_layout.addWidget(buttons_widget)
        self._update_question_submit()
        self._question_panel.setVisible(True)

    def _on_option_toggled(self, button: QPushButton, group: list[QPushButton], multi: bool, checked: bool) -> None:
        if checked and not multi:
            for other in group:
                if other is not button and other.isChecked():
                    other.blockSignals(True)
                    other.setChecked(False)
                    other.blockSignals(False)
        self._update_question_submit()

    def _collect_answers(self) -> dict[str, str] | None:
        """question text -> answer string (multi-select labels joined
        with ", "; free text verbatim -- replacing the single-select
        choice, appended for multi-select), or None if any question
        has no answer yet."""
        answers: dict[str, str] = {}
        for text, multi, buttons, other in self._question_controls:
            parts = [b.text() for b in buttons if b.isChecked()]
            free = other.text().strip()
            if free:
                parts = parts + [free] if multi else [free]
            if not parts:
                return None
            answers[text] = ", ".join(parts)
        return answers

    def _update_question_submit(self) -> None:
        if self._question_controls:
            self._question_submit.setEnabled(self._collect_answers() is not None)

    def _submit_question(self) -> None:
        answers = self._collect_answers()
        if answers is None or not self._pending_questions:
            return
        request_id, _tool_input = self._pending_questions.pop(0)
        self._session.respond_to_question(request_id, answers)
        self._add_entry("question", "answered: " + "; ".join(f"{q} -> {a}" for q, a in answers.items()))
        self._show_next_question()

    def _skip_question(self) -> None:
        if not self._pending_questions:
            return
        request_id, _tool_input = self._pending_questions.pop(0)
        self._session.respond_to_question(request_id, None)
        self._add_entry("question", "skipped")
        self._show_next_question()


def build() -> QWidget:
    return ClaudeDeskWidget()
