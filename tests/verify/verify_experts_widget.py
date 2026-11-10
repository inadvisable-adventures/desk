"""TODO d15791d: the Experts widget, the notifier and the window glue (real throwaway PostgreSQL cluster)."""
import importlib.util
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk import expert_registry as er  # noqa: E402
from desk import temp_ui  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.expert_notifier import ExpertNotifier  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.widgets import WidgetInfo, discover_widgets  # noqa: E402

passed = failed = 0
_KEEP = []


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def spin(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


spec = importlib.util.spec_from_file_location("experts_check", REPO_ROOT / "widgets" / "experts" / "widget.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# ---- the prompts (no database needed) ----
open_q = {"question_id": "q1", "expert_id": "user", "asker": "agent", "asked_at": "now", "question": "Which DB?", "status": "open"}
p = module.build_agent_prompt(open_q, {"name": "You"})
check("an open question's prompt asks the agent to answer through the tool, with the id",
      "desk_answer_expert_question" in p and 'question_id "q1"' in p and "Which DB?" in p)
done_q = dict(open_q, status="answered", answer="Postgres.", answered_by="you")
p = module.build_agent_prompt(done_q, {"name": "You"}, "if yes, update section 3")
check("an answered question's prompt carries the answer and the asker's note",
      "Postgres." in p and "if yes, update section 3" in p and "Act on the answer" in p)
check("without a note it says so", "(none" in module.build_agent_prompt(done_q, None, ""))

# ---- no PostgreSQL: the widget says so instead of failing ----
_real_find = er.find_pg_bin
er.find_pg_bin = lambda: None
er.set_registry(er.ExpertRegistry(Path("/nonexistent/pgdata")))
try:
    w0 = module.build()
    check("without PostgreSQL the widget shows the install hint", spin(lambda: "PostgreSQL was not found" in w0._status_label.text()))
    check("and offers nothing to act on", not w0._answer_button.isEnabled() and not w0._agent_button.isEnabled())
finally:
    er.find_pg_bin = _real_find
    er.set_registry(None)

if er.find_pg_bin() is None:
    print("SKIP: no PostgreSQL installation found; the live checks were not run")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)

root = Path(tempfile.mkdtemp(prefix="pgw", dir="/tmp"))  # short: unix socket paths are length-limited
reg = er.ExpertRegistry(root / "pgdata")
er.set_registry(reg)
previous_window = current_context.get_main_window()
try:
    # ---- notifier ----
    notifier = ExpertNotifier(lambda: reg)
    seen = []
    notifier.announced.connect(seen.append)
    fresh = er.ExpertRegistry(root / "never-created")
    check("with no cluster the notifier does nothing and creates nothing",
          ExpertNotifier(lambda: fresh).poll_once() == [] and not fresh.cluster_exists())
    reg.ensure()
    reg.register_expert("bot", "Bot", "", "agent", "t")
    a = reg.ask("bot", "answered one?", "agent", "note")
    reg.answer(a["question_id"], "yes", "bot")
    u = reg.ask("user", "for the human", "agent")
    found = notifier.poll_once()
    check("it finds the new answer and the new question for the user",
          sorted(i["kind"] for i in found) == ["answer", "question"] and len(seen) == 1)
    check("each is stamped, so the next poll is empty", notifier.poll_once() == [] and len(seen) == 1)

    # ---- two Desks sharing the registry (TODO 488cf49) ----
    ca = ExpertNotifier(lambda: reg, origin_provider=lambda: "/desk/a")
    cb = ExpertNotifier(lambda: reg, origin_provider=lambda: "/desk/b")
    ca.poll_once(); cb.poll_once()  # both check in
    q1 = reg.ask("bot", "asked in A", "agent", origin="/desk/a")
    reg.answer(q1["question_id"], "ok", "bot")
    got_b = cb.poll_once()
    got_a = ca.poll_once()
    check("only the asking Desk announces the answer",
          got_b == [] and [i["question"]["question_id"] for i in got_a] == [q1["question_id"]])
    check("and the other Desk never repeats it", cb.poll_once() == [] and ca.poll_once() == [])

    # ---- the desk expert's fallback (TODO 86a837e) ----
    fb = []
    ca.fallback_needed.connect(fb.append)
    dq = reg.ask("desk", "what is X?", "agent", origin="/desk/a")
    ca.poll_once()
    check("a fresh question to desk is not taken over yet", fb == [])
    reg._exec(f"UPDATE expert_questions SET asked_at = now() - interval '30 seconds' WHERE question_id = '{dq['question_id']}';")
    cb.poll_once()
    check("another Desk does not take it over", fb == [])
    ca.poll_once()
    check("after the wait the asking Desk is told to answer it",
          len(fb) == 1 and [q["question_id"] for q in fb[0]] == [dq["question_id"]]
          and reg.get_question(dq["question_id"])["accepted_by"] == "desk-fallback")
    ca.poll_once()
    check("and only once", len(fb) == 1)

    class _FallbackWin:
        def __init__(self, fail):
            self.fail, self.started = fail, []

        def start_registry_desk_expert(self, question):
            if self.fail:
                raise ValueError("no widget")
            self.started.append(question["question_id"])

    from desk.shell.window import DeskWindow as _DW
    _FallbackWin._on_expert_fallbacks = _DW.__dict__["_on_expert_fallbacks"]
    ok_win = _FallbackWin(False)
    ok_win._on_expert_fallbacks(fb[0])
    check("the window starts a session for each", ok_win.started == [dq["question_id"]])
    _FallbackWin(True)._on_expert_fallbacks(fb[0])
    check("if it cannot, the question goes back to open", reg.get_question(dq["question_id"])["status"] == "open")
    body = _DW.__dict__["_build_desk_expert_instructions"](type("S", (), {})(), "what is X?", question_id=dq["question_id"])
    check("the session is told to record its answer against that question",
          dq["question_id"] in body and "desk_answer_expert_question" in body and "desk-fallback" in body and "what is X?" in body)

    # reports (TODO a63e115): a new report for desk/user is announced by the reporting Desk; outcomes by the reporter's
    nr = reg.report("desk", "News", "something", "", "agent", origin="/desk/a")
    got_b = [i for i in cb.poll_once() if "report" in i]
    got_a = [i for i in ca.poll_once() if "report" in i]
    check("a new report is announced once, by the reporting Desk",
          got_b == [] and [(i["kind"], i["report"]["report_id"]) for i in got_a] == [("report", nr["report_id"])])
    reg.review_report(nr["report_id"], "rejected", "no", "someone")
    out_b = [i for i in cb.poll_once() if "report" in i]
    out_a = [i for i in ca.poll_once() if "report" in i]
    check("the outcome is announced once, to the reporter's Desk",
          out_b == [] and [(i["kind"], i["report"]["status"]) for i in out_a] == [("report_outcome", "rejected")])
    check("nothing repeats", [i for i in ca.poll_once() + cb.poll_once() if "report" in i] == [])
    reg.register_expert("listener", "Listener", "", "agent", "t", listens_for="things")
    lr = reg.report("listener", "Not for the human", "f", origin="/desk/a")
    check("a report to another expert does not banner the user", [i for i in ca.poll_once() if "report" in i] == [])
    reg.review_report(lr["report_id"], "accepted")
    check("accepting (not final) gives the reporter no banner yet", [i for i in ca.poll_once() if "report" in i] == [])
    reg.integrate_report(lr["report_id"], "in docs")
    check("integrating does", [i["kind"] for i in ca.poll_once() if "report" in i] == ["report_outcome"])
    reg.withdraw(dq["question_id"])  # keep the widget checks below about their own questions

    # ---- the window glue (real methods on a stand-in) ----
    class _View:
        def __init__(self):
            self.notes = []

        def notify_temp_ui(self, path, text, on_clicked):
            self.notes.append((str(path), text, on_clicked))

        def mapToScene(self, p):
            from PyQt6.QtCore import QPointF
            return QPointF(100.0, 100.0)

        def viewport(self):
            return type("VP", (), {"rect": lambda s: type("R", (), {"center": lambda s: None})()})()

    class _Win:
        def __init__(self):
            self.view = _View()
            self._widgets = {"claude_desk": WidgetInfo("claude_desk", Path("."), "python", "Claude (Desk)", "w.py", [], (400, 300))}
            self.placed = []
            self.written = []
            self._docked = {}

        def _write_claude_instructions_file(self, body, prefix):
            self.written.append((prefix, body))
            return " read it"

        def _place_widget(self, widget_id, info, pos, size, **kw):
            self.placed.append((widget_id, kw))
            return type("F", (), {"instance_id": "claude-1"})()

        def _reveal_experts_widget(self):
            pass

    for name in ("start_expert_session", "_on_expert_announcements"):
        setattr(_Win, name, DeskWindow.__dict__[name])
    win = _Win()
    win._on_expert_announcements(found)
    texts = sorted(n[1] for n in win.view.notes)
    check("one banner per finding, naming the expert / the question",
          len(win.view.notes) == 2 and texts[0].startswith("Answer from bot: answered one?")
          and texts[1].startswith("New question for you: for the human"))
    check("banner keys are distinct per question and kind", len({n[0] for n in win.view.notes}) == 2)
    win._on_expert_announcements([
        {"kind": "report", "report": {"report_id": "r1", "expert_id": "desk", "title": "Zoom drops focus"}},
        {"kind": "report_outcome", "report": {"report_id": "r2", "expert_id": "x", "title": "T", "status": "integrated"}},
    ])
    texts2 = [n[1] for n in win.view.notes[2:]]
    check("report and outcome banners", texts2 == ["New finding for desk: Zoom drops focus", "Your report was integrated: T"]
          and len({n[0] for n in win.view.notes}) == 4)
    iid = win.start_expert_session("do the thing")
    check("start_expert_session places a claude_desk widget seeded through an instructions file",
          iid == "claude-1" and win.placed[0][0] == "claude_desk" and win.placed[0][1]["claude_extra_instructions"] == " read it"
          and win.written == [("expert-handoff", "do the thing")])
    win._widgets.clear()
    try:
        win.start_expert_session("x")
        raised = False
    except ValueError:
        raised = True
    check("without a claude widget it raises a clear error", raised)

    # ---- the widget ----
    class _MainWin:
        def __init__(self):
            self.sessions = []

        def start_expert_session(self, text):
            self.sessions.append(text)
            return "claude-2"

    main = _MainWin()
    current_context.set_main_window(main)
    mediator = EventMediator()
    _KEEP.append(mediator)
    w = module.build()
    w.bind_event_mediator("experts-1", mediator)
    check("opens with the waiting question for the user (Open filter)", spin(lambda: w._list.count() == 1))
    check("it shows the expert's name and the question", "[You] for the human" in w._list.item(0).text())
    w._list.setCurrentRow(0)
    check("selecting shows the question and enables answering", "for the human" in w._detail.toPlainText() and w._answer_button.isEnabled())
    check("the asker's note is never shown in the widget", "note" not in w._detail.toPlainText().lower().replace("notification", ""))

    # send an open question to an agent
    w._agent_button.click()
    check("Send to agent starts a session with the answer-me prompt", len(main.sessions) == 1 and "desk_answer_expert_question" in main.sessions[0])
    check("it claims the question for the session", reg.get_question(u["question_id"])["status"] == "accepted")
    spin(lambda: "accepted" in w._list.item(0).text() if w._list.count() else False)

    # answer through the widget
    w._list.setCurrentRow(0)
    w._answer_box.setPlainText("Use Postgres.")
    w._answer_button.click()
    check("Answer records the text as 'you'", reg.get_question(u["question_id"])["answer"] == "Use Postgres." and reg.get_question(u["question_id"])["answered_by"] == "you")
    check("an answer written here is not announced again", notifier.poll_once() == [])
    check("the answered question leaves the Open list", spin(lambda: w._list.count() == 0) and w._status_label.text() == module.EMPTY_STATUS)
    w._answer_button.click()
    check("answering with nothing selected is harmless", w._status_label.text() == module.EMPTY_STATUS)

    # the Answered filter and hand-off of an answered question (this one carries a private note)
    w._filter.setCurrentIndex(1)
    check("the Answered filter lists all three answered questions", spin(lambda: w._list.count() == 3))
    row = [i for i in range(w._list.count()) if "answered one?" in w._list.item(i).text()][0]
    w._list.setCurrentRow(row)
    check("an answered question shows its answer", "--- Answer (bot) ---" in w._detail.toPlainText() and not w._answer_button.isEnabled())
    check("its button reads 'Send answer to agent'", w._agent_button.text() == "Send answer to agent")
    w._agent_button.click()
    check("the handoff prompt has the answer and the asker's private note",
          len(main.sessions) == 2 and "yes" in main.sessions[1] and "note" in main.sessions[1] and "Act on the answer" in main.sessions[1])
    check("the handoff is stamped", reg.get_question(a["question_id"])["handed_off_at"] is not None)

    # live refresh from the event
    reg.ask("user", "another one", "agent")
    w._filter.setCurrentIndex(0)
    spin(lambda: w._list.count() == 1)
    mediator.publish(er.EXPERTS_CHANGED_EVENT, {"kind": "question", "id": "x"}, "desk")
    reg.ask("user", "yet another", "agent")
    w._subscription._poll()
    check("a desk.experts.changed event reloads the list", spin(lambda: w._list.count() == 2))

    # ---- reports (TODO a63e115) ----
    rep = reg.report("desk", "Zoom drops focus", "after zoom the editor loses focus", "saw it twice", "agent", "/desk/a")
    w._filter.setCurrentIndex(3)
    check("the Reports to review mode lists the report",
          spin(lambda: w._list.count() == 1 and "Zoom drops focus" in w._list.item(0).text() and w._kind == "reports"))
    w._list.setCurrentRow(0)
    detail = w._detail.toPlainText()
    check("the detail shows the finding and evidence", "after zoom the editor loses focus" in detail and "saw it twice" in detail)
    check("review buttons replace Answer", not w._answer_button.isVisibleTo(w) and w._review_buttons["rejected"].isVisibleTo(w)
          and all(b.isEnabled() for b in w._review_buttons.values()))
    w._review("rejected")
    check("rejecting without a note shows the registry's error", "note" in w._status_label.text().lower()
          and reg.get_report(rep["report_id"])["status"] == "new")
    w._answer_box.setPlainText("cannot reproduce")
    w._review("rejected")
    got = reg.get_report(rep["report_id"])
    check("rejecting with a note records it as you", got["status"] == "rejected" and got["review_note"] == "cannot reproduce" and got["reviewed_by"] == "you")
    check("it leaves the to-review list", spin(lambda: w._list.count() == 0))
    rep2 = reg.report("desk", "Second", "another thing", "", "agent", "/desk/a")
    w.refresh()
    spin(lambda: w._list.count() == 1)
    w._list.setCurrentRow(0)
    w._review("accepted")
    check("accepting needs no note", reg.get_report(rep2["report_id"])["status"] == "accepted")
    w._filter.setCurrentIndex(3)
    spin(lambda: w._list.count() == 1)
    w._list.setCurrentRow(0)
    before = len(main.sessions)
    w._agent_button.click()
    prompt = main.sessions[-1] if len(main.sessions) > before else ""
    check("Send to agent starts a session told to verify and record against the report",
          len(main.sessions) == before + 1 and rep2["report_id"] in prompt and "desk_integrate_expert_report" in prompt
          and "desk_review_expert_report" in prompt and "lead, not a fact" in prompt)
    w._filter.setCurrentIndex(0)
    spin(lambda: w._kind == "questions")
    check("switching back to questions restores the Answer button", w._answer_button.isVisibleTo(w) and not w._review_buttons["accepted"].isVisibleTo(w))
finally:
    current_context.set_main_window(previous_window) if previous_window is not None else current_context.set_main_window(None)
    er.set_registry(None)
    reg.stop()
    shutil.rmtree(root, ignore_errors=True)

# ---- manifest, registration, docs ----
info = discover_widgets(REPO_ROOT / "widgets").get("experts")
check("discovered as a python widget named Experts", info is not None and info.kind == "python" and info.name == "Experts")
tag = "Experts widget + answer notifications #804805"
check("changelog tag current, with an entry", tag in temp_ui.CURRENT_TAGS and tag in temp_ui._NEW_FEATURES)
check("the experts doc describes the widget and the notification", all(t in temp_ui.SPLIT_DOC_CONTENT["tempui-experts.md"] for t in ("Experts` widget", "Send to agent", "notification")))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
