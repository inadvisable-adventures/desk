import contextlib
import io
import threading
import traceback
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from desk import desk_proc
from desk.shell import current_context
from desk.temp_ui import TEMP_UI_DIRNAME, DeskProcDefinition, parse_desk_proc

NOT_STARTED = "not_started"
EXECUTING = "executing"
DONE = "done"
ERRORED = "errored"
INTERRUPTED = "interrupted"

_STATUS_LABELS = {
    NOT_STARTED: "Not started.",
    EXECUTING: "Executing…",
    DONE: "Done.",
    ERRORED: "Error:",
    INTERRUPTED: "Interrupted (Desk closed mid-run) -- you can start it again.",
}


class DeskProcApi:
    """The curated, documented object injected into a Desk Proc
    script's exec namespace as `deskproc` (TODO 97bd090) -- the *safe*
    front door for acting on Desk's own live shell from the script's
    own background thread (nothing stops a script from also `import`
    -ing internals directly and bypassing this, same trust level a Job
    already has -- this doesn't add a capability boundary, just a
    documented, ergonomic one). Every method that touches Qt state
    routes through current_context.get_gui_thread_caller() -- reading
    current_context.get_main_window() itself is a plain attribute read
    (safe from any thread); only *calling* one of its methods needs the
    GUI-thread hop, which the lambda passed to `_call` provides."""

    def _call(self, fn):
        caller = current_context.get_gui_thread_caller()
        if caller is None:
            raise RuntimeError("deskproc: no GUI thread caller registered -- Desk isn't ready yet")
        return caller(fn)

    def reveal_widget(self, instance_id: str) -> bool:
        window = current_context.get_main_window()
        if window is None:
            return False
        return self._call(lambda: window.zoom_to_widget_by_instance_id(instance_id))

    def screenshot_widget(self, instance_id: str, path: str, max_width: int | None = None) -> bool:
        window = current_context.get_main_window()
        if window is None:
            return False
        return self._call(lambda: window.screenshot_widget_instance(instance_id, path, max_width))

    def screenshot_desk(self, path: str, max_width: int | None = None) -> bool:
        window = current_context.get_main_window()
        if window is None:
            return False
        return self._call(lambda: window.screenshot_desk(path, max_width))

    def list_widget_instances(self) -> list:
        window = current_context.get_main_window()
        if window is None:
            return []
        state = self._call(lambda: window.get_state_dict())
        return state.get("widgets", [])


class _Relay(QObject):
    """Owns the pyqtSignal a background Desk-Proc-execution thread
    reports through -- same shape as widgets/job_runner/widget.py's own
    relay (which itself mirrors widgets/git_diff/widget.py's)."""

    finished = pyqtSignal(bool, str, str, str)  # ok, stdout, stderr, traceback


def _run_desk_proc(script_text: str, relay: _Relay) -> None:
    """Module-level, not a method: runs on a background thread and must
    not touch any Qt widget directly except through the `deskproc`
    global's own current_context.get_gui_thread_caller()-marshaled
    calls -- only ever reports its own completion back via the relay's
    signal (TODO 97bd090). A fresh module namespace per run; `desk`/
    anything else on this process's own sys.path is importable exactly
    the way a Job's own python-kind execution already allows -- no
    sandboxing, matching the "View Code is the only review step"
    decision this project already made for Jobs generally. `deskproc`
    is the one addition a Job's own exec namespace doesn't have."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(
                compile(script_text, "<desk_proc>", "exec"),
                {"__name__": "__desk_proc__", "deskproc": DeskProcApi()},
            )
        relay.finished.emit(True, stdout.getvalue(), stderr.getvalue(), "")
    except Exception:
        relay.finished.emit(False, stdout.getvalue(), stderr.getvalue(), traceback.format_exc())


class DeskProcRunnerWidget(QWidget):
    """Binds to a `DeskProc` tempui file (TODO 97bd090) -- shows its
    declared summary, a "View Code" button (opens the script's own text
    in the Editor widget), and a "Start" button that runs it in
    -process on a background thread, the same shape
    `widgets/job_runner/widget.py` already establishes for a Job's own
    `python`-kind execution, plus a curated `deskproc` global for safe
    GUI-thread interaction. See plans/desk-proc-mechanism.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tempui_path: Path | None = None
        self._definition: DeskProcDefinition | None = None
        self._proc_id: str | None = None
        self._status = NOT_STARTED
        self._detail = ""
        self._relay = _Relay()
        self._relay.finished.connect(self._on_desk_proc_finished)

        self._summary_label = QLabel("Loading…")
        self._summary_label.setWordWrap(True)
        self._summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._view_code_button = QPushButton("View Code")
        self._view_code_button.clicked.connect(self._on_view_code_clicked)
        self._start_button = QPushButton("Start")
        self._start_button.clicked.connect(self._on_start_clicked)

        button_row = QHBoxLayout()
        button_row.addWidget(self._view_code_button)
        button_row.addWidget(self._start_button)
        button_row.addStretch()

        self._status_label = QLabel(_STATUS_LABELS[NOT_STARTED])
        self._status_label.setWordWrap(True)
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._detail_view = QPlainTextEdit()
        self._detail_view.setReadOnly(True)
        self._detail_view.setFont(QFont("Menlo"))
        self._detail_view.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._summary_label)
        layout.addLayout(button_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._detail_view, stretch=1)

        self._refresh_status_display()

    # -- tempui binding ----------------------------------------------

    def set_source_file(self, path: Path) -> None:
        """Called by DeskWindow._bind_temp_ui_content (the generic
        "no special kind, just re-parse your own source" fallback
        branch every tempui-bound widget without a dedicated branch
        already uses -- Question/LightningRound/Job's own established
        shape). `path`'s own filename (a uuid) doubles as this Desk
        Proc's id."""
        self._tempui_path = path
        self._proc_id = path.name
        try:
            text = path.read_text()
        except OSError:
            text = ""
        self._definition = parse_desk_proc(text)
        self._refresh_summary_display()

    def _refresh_summary_display(self) -> None:
        if self._definition is None:
            self._summary_label.setText("(malformed Desk Proc file)")
            return
        summary = self._definition.summary or "(no summary given)"
        self._summary_label.setText(f"Desk Proc: {summary}")

    # -- persisted status (mirrors widgets/job_runner/widget.py) ------

    def get_widget_local_storage(self) -> dict:
        """The generic python-widget persisted-state hook -- lets "has
        this Desk Proc already run" survive a Desk reload without
        writing back to the Desk Proc's own tempui file."""
        return {"status": self._status, "detail": self._detail}

    def set_widget_local_storage(self, data: dict) -> None:
        status = data.get("status", NOT_STARTED)
        if status not in (NOT_STARTED, DONE, ERRORED, EXECUTING):
            status = NOT_STARTED
        # A restored "executing" status means Desk closed mid-run --
        # there's no in-flight thread to reconnect to, so this is shown
        # as interrupted rather than a permanently "Executing..." widget
        # with no way forward.
        if status == EXECUTING:
            status = INTERRUPTED
        self._status = status
        self._detail = data.get("detail", "")
        self._refresh_status_display()

    def has_unsaved_local_edits(self) -> bool:
        """Duck-typed hook (mirrors JobRunnerWidget/ScratchWidget's own)
        letting DeskWindow's tempui live-refresh know not to clobber an
        already-started Desk Proc's state -- True once Start has been
        clicked at all (anything other than "not started")."""
        return self._status not in (NOT_STARTED, INTERRUPTED)

    def _refresh_status_display(self) -> None:
        label = _STATUS_LABELS.get(self._status, self._status)
        self._status_label.setText(label)
        if self._detail:
            self._detail_view.setPlainText(self._detail)
            self._detail_view.show()
        else:
            self._detail_view.hide()
        self._start_button.setEnabled(self._status in (NOT_STARTED, INTERRUPTED))

    def _set_status(self, status: str, detail: str = "") -> None:
        self._status = status
        self._detail = detail
        self._refresh_status_display()

    # -- View Code -----------------------------------------------------

    def _on_view_code_clicked(self) -> None:
        if self._definition is None or self._proc_id is None:
            return
        directory = current_context.get_current_desk_directory()
        if directory is None:
            return
        desk_temp_dir = directory / TEMP_UI_DIRNAME
        script_path = desk_proc.materialize_script_body(desk_temp_dir, self._proc_id, self._definition)
        if script_path is None:
            return
        opener = current_context.get_editor_or_scrap_opener()
        if opener is not None:
            opener(script_path)

    # -- Start -----------------------------------------------------------

    def _on_start_clicked(self) -> None:
        if self._definition is None or self._proc_id is None:
            return
        if self._status not in (NOT_STARTED, INTERRUPTED):
            return
        self._set_status(EXECUTING)
        desk_directory = current_context.get_current_desk_directory()
        if desk_directory is None:
            self._set_status(ERRORED, "No current Desk directory known -- cannot materialize this Desk Proc.")
            return
        desk_temp_dir = desk_directory / TEMP_UI_DIRNAME
        proc_directory = desk_proc.materialize(desk_temp_dir, self._proc_id, self._definition)
        if proc_directory is None:
            self._set_status(ERRORED, "Failed to decode this Desk Proc's script content.")
            return
        script_text = (proc_directory / desk_proc.PYTHON_DESK_PROC_ENTRY_FILENAME).read_text()
        thread = threading.Thread(target=_run_desk_proc, args=(script_text, self._relay), daemon=True)
        thread.start()

    def _on_desk_proc_finished(self, ok: bool, stdout: str, stderr: str, tb: str) -> None:
        if ok:
            self._set_status(DONE, stdout)
        else:
            detail = tb if tb else (stderr or "The Desk Proc raised an error.")
            self._set_status(ERRORED, detail)


def build() -> QWidget:
    return DeskProcRunnerWidget()
