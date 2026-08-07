import contextlib
import io
import threading
import traceback
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from desk import jobs
from desk.shell import current_context
from desk.temp_ui import TEMP_UI_DIRNAME, JobDefinition, parse_job

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


class _Relay(QObject):
    """Owns the pyqtSignal a background python-Job-execution thread
    reports through -- same shape as widgets/git_diff/widget.py's own
    relay."""

    finished = pyqtSignal(bool, str, str, str)  # ok, stdout, stderr, traceback


def _run_python_job(script_text: str, relay: _Relay) -> None:
    """Module-level, not a method: runs on a background thread and must
    not touch any Qt widget directly -- only ever reports back via the
    relay's signal (TODO d7e66f6). A fresh module namespace per run;
    `desk`/anything else on this process's own sys.path is importable
    exactly the way any kind:"python" widget's own code already can --
    no sandboxing, matching the "View Code is the only review step"
    decision this project already made for Jobs generally."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(compile(script_text, "<job>", "exec"), {"__name__": "__job__"})
        relay.finished.emit(True, stdout.getvalue(), stderr.getvalue(), "")
    except Exception:
        relay.finished.emit(False, stdout.getvalue(), stderr.getvalue(), traceback.format_exc())


class JobRunnerWidget(QWidget):
    """Binds to a `Job` tempui file (TODO d7e66f6) -- shows its
    declared summary/kind, a "View Code" button (opens the script's own
    text in the Editor widget), and a "Start" button that runs it in
    the appropriate context: `python` in-process on a background
    thread, `html` as a real, capability-scoped `kind: "html"` widget
    instance (via `current_context.get_html_job_starter()`). See
    plans/lightweight-agent-job-mechanism.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tempui_path: Path | None = None
        self._definition: JobDefinition | None = None
        self._job_id: str | None = None
        self._status = NOT_STARTED
        self._detail = ""
        self._relay = _Relay()
        self._relay.finished.connect(self._on_python_job_finished)

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
        already uses -- Question/LightningRound's own established
        shape). `path`'s own filename (a uuid, TODO a02b001) doubles as
        this Job's id."""
        self._tempui_path = path
        self._job_id = path.name
        try:
            text = path.read_text()
        except OSError:
            text = ""
        self._definition = parse_job(text)
        self._refresh_summary_display()

    def _refresh_summary_display(self) -> None:
        if self._definition is None:
            self._summary_label.setText("(malformed Job file)")
            return
        summary = self._definition.summary or "(no summary given)"
        self._summary_label.setText(f"Job ({self._definition.kind}): {summary}")

    # -- persisted status (TODO d7e66f6) ------------------------------

    def get_widget_local_storage(self) -> dict:
        """The generic python-widget persisted-state hook (same
        pull-based mechanism desk.self.getLocalStorage/setLocalStorage
        generalizes for kind:"html" widgets) -- lets "has this Job
        already run" survive a Desk reload without writing back to the
        Job's own tempui file."""
        return {"status": self._status, "detail": self._detail}

    def set_widget_local_storage(self, data: dict) -> None:
        status = data.get("status", NOT_STARTED)
        if status not in (NOT_STARTED, DONE, ERRORED, EXECUTING):
            status = NOT_STARTED
        # A restored "executing" status means Desk closed mid-run --
        # there's no in-flight thread/placed widget to reconnect to,
        # so this is shown as interrupted rather than a permanently
        # "Executing..." widget with no way forward.
        if status == EXECUTING:
            status = INTERRUPTED
        self._status = status
        self._detail = data.get("detail", "")
        self._refresh_status_display()

    def has_unsaved_local_edits(self) -> bool:
        """Duck-typed hook (mirrors ScratchWidget's own, TODO 9ee505f)
        letting DeskWindow's tempui live-refresh know not to clobber an
        already-started Job's state -- True once Start has been
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
        if self._definition is None or self._job_id is None:
            return
        directory = current_context.get_current_desk_directory()
        if directory is None:
            return
        desk_temp_dir = directory / TEMP_UI_DIRNAME
        script_path = jobs.materialize_script_body(desk_temp_dir, self._job_id, self._definition)
        if script_path is None:
            return
        opener = current_context.get_editor_or_scrap_opener()
        if opener is not None:
            opener(script_path)

    # -- Start -----------------------------------------------------------

    def _on_start_clicked(self) -> None:
        if self._definition is None or self._job_id is None:
            return
        if self._status not in (NOT_STARTED, INTERRUPTED):
            return
        self._set_status(EXECUTING)
        if self._definition.kind == "python":
            self._start_python_job()
        else:
            self._start_html_job()

    def _start_python_job(self) -> None:
        desk_directory = current_context.get_current_desk_directory()
        if desk_directory is None or self._definition is None:
            self._set_status(ERRORED, "No current Desk directory known -- cannot materialize this job.")
            return
        desk_temp_dir = desk_directory / TEMP_UI_DIRNAME
        job_directory = jobs.materialize(desk_temp_dir, self._job_id, self._definition)
        if job_directory is None:
            self._set_status(ERRORED, "Failed to decode this Job's script content.")
            return
        script_text = (job_directory / jobs.PYTHON_JOB_ENTRY_FILENAME).read_text()
        thread = threading.Thread(target=_run_python_job, args=(script_text, self._relay), daemon=True)
        thread.start()

    def _on_python_job_finished(self, ok: bool, stdout: str, stderr: str, tb: str) -> None:
        if ok:
            detail = stdout
            self._set_status(DONE, detail)
        else:
            detail = tb if tb else (stderr or "The job raised an error.")
            self._set_status(ERRORED, detail)

    def _start_html_job(self) -> None:
        starter = current_context.get_html_job_starter()
        if starter is None or self._definition is None or self._job_id is None:
            self._set_status(ERRORED, "No html Job starter is available.")
            return
        starter(self._job_id, self._definition, self._on_html_job_status)

    def _on_html_job_status(self, status: str, detail: str) -> None:
        self._set_status(status, detail)


def build() -> QWidget:
    return JobRunnerWidget()
