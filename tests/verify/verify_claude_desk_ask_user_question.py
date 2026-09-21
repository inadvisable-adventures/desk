"""Verifies TODO `6ab9e85`: real question UI for AskUserQuestion in the
Claude (Desk) widget, and the session's routing of that tool. See
`plans/claude-desk-ask-user-question.md`. No real network calls: the
session-level check drives `_can_use_tool` on a real asyncio loop, the
widget-level ones call the widget's slots directly with a recording
stand-in for the session's respond_to_question."""

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def _load_widget_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "claude_desk_ask_question_check", REPO_ROOT / "widgets" / "claude_desk" / "widget.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load_widget_module()

Q1 = {
    "question": "Which color?",
    "header": "Color",
    "multiSelect": False,
    "options": [{"label": "Red", "description": "r"}, {"label": "Blue", "description": "b"}],
}
Q2 = {
    "question": "Which toppings?",
    "header": "Top",
    "multiSelect": True,
    "options": [{"label": "Cheese", "description": "c"}, {"label": "Ham", "description": "h"}],
}


# -- session ---------------------------------------------------------


def test_session_routing():
    from desk.claude_session import ClaudeSession

    async def run(tool_name, respond):
        session = ClaudeSession()
        session._loop = asyncio.get_running_loop()
        emitted = []
        session.question_request.connect(lambda rid, inp: emitted.append(("q", rid, inp)))
        session.permission_request.connect(lambda rid, name, inp: emitted.append(("p", rid, name)))
        task = asyncio.ensure_future(session._can_use_tool(tool_name, {"questions": [Q1]}, None))
        for _ in range(5):
            await asyncio.sleep(0)
            app.processEvents()
        rid = emitted[0][1]
        future = session._pending_permissions[rid]
        future.set_result(respond)
        return emitted, await task

    emitted, result = asyncio.run(run("AskUserQuestion", {"Which color?": "Red"}))
    check("question call emits question_request only", [e[0] for e in emitted] == ["q"])
    check("answers land in updated_input", result.updated_input["answers"] == {"Which color?": "Red"})
    check("original questions preserved", result.updated_input["questions"] == [Q1])
    emitted, result = asyncio.run(run("AskUserQuestion", None))
    check("skip denies", result.behavior == "deny")
    emitted, result = asyncio.run(run("Write", (True, "")))
    check("other tools still use permission_request", [e[0] for e in emitted] == ["p"])


# -- widget ----------------------------------------------------------


def _widget():
    widget = module.build()
    calls = []
    widget._session.respond_to_question = lambda rid, answers: calls.append((rid, answers))
    return widget, calls


def test_single_select():
    widget, calls = _widget()
    widget._on_question_request("r1", {"questions": [Q1]})
    check("panel shown", widget._question_panel.isVisibleTo(widget))
    check("submit disabled until answered", not widget._question_submit.isEnabled())
    _t, _m, buttons, _other = widget._question_controls[0]
    buttons[0].setChecked(True)
    buttons[1].setChecked(True)
    check("single-select is exclusive", not buttons[0].isChecked() and buttons[1].isChecked())
    widget._question_submit.click()
    check("answer delivered", calls == [("r1", {"Which color?": "Blue"})])
    check("panel hidden afterward", not widget._question_panel.isVisibleTo(widget))


def test_multi_and_free_text():
    widget, calls = _widget()
    widget._on_question_request("r2", {"questions": [Q1, Q2]})
    _t, _m, b1, other1 = widget._question_controls[0]
    _t, _m, b2, other2 = widget._question_controls[1]
    other1.setText("Green")
    check("submit still disabled with question 2 unanswered", not widget._question_submit.isEnabled())
    b2[0].setChecked(True)
    b2[1].setChecked(True)
    widget._question_submit.click()
    check(
        "free text verbatim; multi comma-joined",
        calls == [("r2", {"Which color?": "Green", "Which toppings?": "Cheese, Ham"})],
    )


def test_skip_and_queue():
    widget, calls = _widget()
    widget._on_question_request("a", {"questions": [Q1]})
    widget._on_question_request("b", {"questions": [Q2]})
    check("second question waits", len(widget._pending_questions) == 2)
    widget._skip_question()
    check("skip sends None", calls == [("a", None)])
    check("next question shown", widget._question_controls[0][0] == "Which toppings?")
    widget._skip_question()
    check("queue drained", calls[-1] == ("b", None) and not widget._question_panel.isVisibleTo(widget))


test_session_routing()
test_single_select()
test_multi_and_free_text()
test_skip_and_queue()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
