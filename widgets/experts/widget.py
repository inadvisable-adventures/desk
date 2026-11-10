import threading

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk import expert_registry
from desk.expert_registry import EXPERTS_CHANGED_EVENT, ExpertRegistryError
from desk.shell import current_context
from desk.shell.event_broker import EventSubscription
from desk.shell.qt_controls.painted_combo import PaintedComboBox

NOT_CONNECTED_STATUS = "Not yet connected to Desk."
EMPTY_STATUS = "Nothing here."
# (label, what it lists, statuses). Questions are put to experts; reports are findings agents sent to listening ones.
FILTERS = (
    ("Open", "questions", ("open", "accepted")),
    ("Answered", "questions", ("answered",)),
    ("All", "questions", None),
    ("Reports to review", "reports", ("new", "accepted")),
    ("Reports: all", "reports", None),
)
_QID_ROLE = Qt.ItemDataRole.UserRole


def build_agent_prompt(question: dict, expert: dict | None, note: str = "") -> str:
    """What a new Claude session is told. An unanswered question asks the agent to answer it through
    desk_answer_expert_question (it never sees the asker's note); an answered one hands over the question, the
    answer and the asker's private note so the agent can act on it."""
    expert_name = (expert or {}).get("name") or question["expert_id"]
    header = (
        f"Question id: {question['question_id']}\n"
        f"Put to the expert: {expert_name} ({question['expert_id']})\n"
        f"Asked by: {question.get('asker') or '(unknown)'} at {question.get('asked_at') or '?'}\n\n"
        f"Question:\n{question['question']}\n"
    )
    if question["status"] == "answered":
        return (
            "An expert has answered a question that was asked earlier (the session that asked it is probably gone). "
            "Act on the answer.\n\n"
            + header
            + f"\nAnswer (from {question.get('answered_by') or 'the expert'}):\n{question.get('answer') or ''}\n"
            + "\nNote the asker left for whoever acts on the answer:\n"
            + (note.strip() or "(none -- summarise the answer for the user and ask what they would like done)")
            + "\n\nDo this work here, in this session; do not start another expert session."
        )
    return (
        "A question was put to an expert and is still unanswered. Answer it as well as you can, reading whatever "
        "you need from the project.\n\n"
        + header
        + f"\nWhen you have an answer, record it by calling the desk MCP tool desk_answer_expert_question with "
        f"question_id \"{question['question_id']}\" and answered_by \"claude session\" (optionally call "
        "desk_accept_expert_question first). If you cannot answer it, say why to the user instead of guessing."
    )


def build_report_agent_prompt(report: dict, expert: dict | None) -> str:
    """What a new Claude session is told about a reported finding: verify it, fold it in where it belongs, and
    record the outcome with the report tools (the reporter reads that)."""
    expert_name = (expert or {}).get("name") or report["expert_id"]
    listens = (expert or {}).get("listens_for") or ""
    return (
        "An agent reported a finding to an expert. You are acting for that expert: evaluate the report and, if it "
        "holds, fold it in.\n\n"
        f"Report id: {report['report_id']}\n"
        f"Reported to: {expert_name} ({report['expert_id']})"
        + (f", who listens for: {listens}" if listens else "")
        + f"\nReported by: {report.get('reporter') or '(unknown)'} at {report.get('reported_at') or '?'}\n\n"
        f"Title: {report['title']}\n\nFinding:\n{report['finding']}\n\n"
        f"Evidence given:\n{report.get('evidence') or '(none)'}\n\n"
        "A report is a lead, not a fact. First check it yourself, reading whatever you need from the project or "
        "running what the evidence says it ran. Then record the outcome with the desk MCP tools:\n"
        f"- if it is wrong, unsupported or out of scope: desk_review_expert_report with report_id \"{report['report_id']}\", "
        "decision \"rejected\" and a note saying why;\n"
        f"- if it is already known: decision \"duplicate\" and a note saying where;\n"
        "- if it holds: put it where it belongs (a doc, a TODO, a FEEDBACK file, the code), then call "
        f"desk_integrate_expert_report with report_id \"{report['report_id']}\" and an integration_note saying exactly "
        "where, and use \"claude session\" as integrated_by / reviewed_by.\n"
        "Tell the user what you decided."
    )


class _Loader(QObject):
    """Runs the registry reads on a worker thread (the first one may provision Postgres) and delivers the
    result on the GUI thread."""

    done = pyqtSignal(int, object, object)  # generation, (experts, questions) or None, error text or None

    def load(self, generation: int, kind: str, statuses) -> None:
        def work() -> None:
            try:
                registry = expert_registry.get_registry()
                items = registry.list_reports(None, statuses) if kind == "reports" else registry.list_questions(None, statuses)
                result = (registry.list_experts(), items)
                self.done.emit(generation, result, None)
            except ExpertRegistryError as e:
                self.done.emit(generation, None, str(e))

        threading.Thread(target=work, name="experts-load", daemon=True).start()


class ExpertsWidget(QWidget):
    """Open questions put to the registry's experts, with an answer box and "Send to agent"
    (TODO d15791d). See plans/expert-registry.md."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._subscription: EventSubscription | None = None
        self._questions: list[dict] = []
        self._kind = "questions"  # what the list shows: "questions" or "reports"
        self._experts: dict[str, dict] = {}
        self._generation = 0
        self._loader = _Loader(self)
        self._loader.done.connect(self._on_loaded)

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._status_label.setWordWrap(True)
        self._filter = PaintedComboBox()
        for label, kind, statuses in FILTERS:
            self._filter.addItem(label, (kind, statuses))
        self._filter.currentIndexChanged.connect(lambda _i: self.refresh())
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.clicked.connect(self.refresh)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(lambda *_: self._show_selected())
        self._detail = QPlainTextEdit()
        self._detail.setReadOnly(True)
        self._answer_box = QPlainTextEdit()
        self._answer_box.setPlaceholderText("Your answer")
        self._answer_box.setFixedHeight(90)
        self._answer_button = QPushButton("Answer")
        self._answer_button.clicked.connect(self._answer)
        self._agent_button = QPushButton("Send to agent")
        self._agent_button.clicked.connect(self._send_to_agent)
        self._review_buttons = {}
        for decision, label in (("accepted", "Accept"), ("rejected", "Reject"), ("duplicate", "Duplicate")):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, d=decision: self._review(d))
            self._review_buttons[decision] = button

        top = QHBoxLayout()
        top.addWidget(self._filter, stretch=1)
        top.addWidget(self._refresh_button)
        buttons = QHBoxLayout()
        buttons.addWidget(self._answer_button)
        for button in self._review_buttons.values():
            buttons.addWidget(button)
        buttons.addWidget(self._agent_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._status_label)
        layout.addWidget(self._list, stretch=2)
        layout.addWidget(self._detail, stretch=2)
        layout.addWidget(self._answer_box)
        layout.addLayout(buttons)

        self._show_selected()
        self.refresh()

    def bind_event_mediator(self, instance_id: str, mediator) -> None:
        self._subscription = EventSubscription(mediator, instance_id, names=[EXPERTS_CHANGED_EVENT], parent=self)
        self._subscription.message_received.connect(self._on_mediated_event)

    def _on_mediated_event(self, name: str, payload: object, _sender: str) -> None:
        if name == EXPERTS_CHANGED_EVENT:
            self.refresh()

    # -- loading ----------------------------------------------------------

    def refresh(self) -> None:
        self._generation += 1
        self._status_label.setText("Loading…")
        kind, statuses = self._filter.currentData()
        self._loader.load(self._generation, kind, statuses)

    def _on_loaded(self, generation: int, result, error) -> None:
        if generation != self._generation:
            return  # a newer refresh is on its way
        if error is not None:
            self._set_questions([], {})
            self._status_label.setText(error)
            return
        experts, questions = result
        self._kind = self._filter.currentData()[0]
        self._set_questions(questions, {e["expert_id"]: e for e in experts})

    def _set_questions(self, questions: list[dict], experts: dict[str, dict]) -> None:
        selected = self._selected_id()
        self._questions, self._experts = list(questions), experts
        self._list.blockSignals(True)
        self._list.clear()
        for q in self._questions:
            name = (experts.get(q["expert_id"]) or {}).get("name") or q["expert_id"]
            if self._kind == "reports":
                first = q["title"].strip()
            else:
                first = (q["question"].strip().splitlines() or [""])[0]
            item = QListWidgetItem(f"[{name}] {first[:80]} ({q['status']})")
            item.setData(_QID_ROLE, self._id_of(q))
            self._list.addItem(item)
            if self._id_of(q) == selected:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        noun = "report(s)" if self._kind == "reports" else "question(s)"
        self._status_label.setText(f"{len(self._questions)} {noun}." if self._questions else EMPTY_STATUS)
        self._show_selected()

    # -- selection ----------------------------------------------------------

    def _selected_id(self) -> str | None:
        item = self._list.currentItem()
        return item.data(_QID_ROLE) if item is not None else None

    def _id_of(self, item: dict) -> str:
        return item["report_id"] if self._kind == "reports" else item["question_id"]

    def _selected(self) -> dict | None:
        qid = self._selected_id()
        return next((q for q in self._questions if self._id_of(q) == qid), None)

    def _show_selected(self) -> None:
        q = self._selected()
        reports = self._kind == "reports"
        self._answer_button.setVisible(not reports)
        for button in self._review_buttons.values():
            button.setVisible(reports)
        self._answer_box.setPlaceholderText(
            "Note (needed to reject or mark a duplicate)" if reports else "Your answer"
        )
        if q is None:
            self._detail.setPlainText("")
            self._answer_button.setEnabled(False)
            self._agent_button.setEnabled(False)
            self._answer_box.setEnabled(False)
            for button in self._review_buttons.values():
                button.setEnabled(False)
            return
        if reports:
            self._show_report(q)
            return
        expert = self._experts.get(q["expert_id"]) or {}
        lines = [
            f"To: {expert.get('name') or q['expert_id']} ({q['expert_id']})",
            f"From: {q.get('asker') or '(unknown)'}    Asked: {q.get('asked_at') or '?'}",
            f"Status: {q['status']}" + (f" by {q['accepted_by']}" if q.get("accepted_by") and q["status"] == "accepted" else ""),
            "",
            q["question"],
        ]
        if q["status"] == "answered":
            lines += ["", f"--- Answer ({q.get('answered_by') or 'unknown'}) ---", q.get("answer") or ""]
        self._detail.setPlainText("\n".join(lines))
        waiting = q["status"] in ("open", "accepted")
        self._answer_box.setEnabled(waiting)
        self._answer_button.setEnabled(waiting)
        self._agent_button.setEnabled(q["status"] in ("open", "accepted", "answered"))
        self._agent_button.setText("Send to agent" if waiting else "Send answer to agent")

    def _show_report(self, r: dict) -> None:
        expert = self._experts.get(r["expert_id"]) or {}
        lines = [
            f"To: {expert.get('name') or r['expert_id']} ({r['expert_id']})",
            f"From: {r.get('reporter') or '(unknown)'}    Reported: {r.get('reported_at') or '?'}",
            f"Status: {r['status']}",
            "",
            r["title"],
            "",
            r["finding"],
        ]
        if r.get("evidence"):
            lines += ["", "--- Evidence ---", r["evidence"]]
        if r.get("review_note"):
            lines += ["", f"--- Review ({r.get('reviewed_by') or 'unknown'}) ---", r["review_note"]]
        if r.get("integration_note"):
            lines += ["", f"--- Integrated ({r.get('integrated_by') or 'unknown'}) ---", r["integration_note"]]
        self._detail.setPlainText("\n".join(lines))
        pending = r["status"] in ("new", "accepted")
        self._answer_box.setEnabled(pending)
        for button in self._review_buttons.values():
            button.setEnabled(pending)
        self._agent_button.setEnabled(pending)
        self._agent_button.setText("Send to agent")

    # -- actions ------------------------------------------------------------

    def _review(self, decision: str) -> None:
        r = self._selected()
        if r is None or self._kind != "reports":
            return
        note = self._answer_box.toPlainText().strip()
        try:
            expert_registry.get_registry().review_report(r["report_id"], decision, note, "you")
        except ExpertRegistryError as e:
            self._status_label.setText(str(e))
            return
        self._answer_box.clear()
        self.refresh()

    def _answer(self) -> None:
        q = self._selected()
        text = self._answer_box.toPlainText().strip()
        if q is None or not text:
            self._status_label.setText("Type an answer first." if q is not None else EMPTY_STATUS)
            return
        try:
            registry = expert_registry.get_registry()
            registry.answer(q["question_id"], text, "you")
            registry.mark_announced(q["question_id"], "answer")  # you wrote it: no banner needed
        except ExpertRegistryError as e:
            self._status_label.setText(str(e))
            return
        self._answer_box.clear()
        self.refresh()

    def _send_to_agent(self) -> None:
        q = self._selected()
        window = current_context.get_main_window()
        if q is None:
            return
        if window is None:
            self._status_label.setText(NOT_CONNECTED_STATUS)
            return
        if self._kind == "reports":
            try:
                window.start_expert_session(build_report_agent_prompt(q, self._experts.get(q["expert_id"])))
            except ValueError as e:
                self._status_label.setText(str(e))
                return
            self._status_label.setText("Started an agent session.")
            return
        try:
            registry = expert_registry.get_registry()
            if q["status"] == "answered":
                full = registry.get_question(q["question_id"], include_note=True) or q
                prompt = build_agent_prompt(full, self._experts.get(q["expert_id"]), full.get("note_to_self", ""))
            else:
                prompt = build_agent_prompt(q, self._experts.get(q["expert_id"]))
            window.start_expert_session(prompt)
            if q["status"] == "answered":
                registry.mark_handed_off(q["question_id"])
            elif q["status"] == "open":
                registry.accept(q["question_id"], "claude session")
        except (ExpertRegistryError, ValueError) as e:
            self._status_label.setText(str(e))
            return
        self._status_label.setText("Started an agent session.")
        self.refresh()


def build() -> QWidget:
    return ExpertsWidget()
