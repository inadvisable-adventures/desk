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
            self._widgets = {"claude": WidgetInfo("claude", Path("."), "python", "Claude", "w.py", [], (400, 300))}
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
    iid = win.start_expert_session("do the thing")
    check("start_expert_session places a claude widget seeded through an instructions file",
          iid == "claude-1" and win.placed[0][0] == "claude" and win.placed[0][1]["claude_extra_instructions"] == " read it"
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
    check("the Answered filter lists both answered questions", spin(lambda: w._list.count() == 2))
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
