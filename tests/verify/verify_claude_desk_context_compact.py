"""Verifies TODO `db1cd65`: context-usage polling, the context label, and
the confirmed Compact now button. Fake client only (the live behavior was
established by a one-off probe -- see plans/claude-desk-context-usage-and-compact.md)."""

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

import claude_agent_sdk as sdk  # noqa: E402

from desk.claude_session import ClaudeSession  # noqa: E402

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


def _module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ctx_check", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _module()
USAGE = {"totalTokens": 5000, "maxTokens": 200000, "percentage": 2.5, "autoCompactThreshold": 167000, "isAutoCompactEnabled": True, "model": "m", "extra": 1}


def result():
    return sdk.ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s", total_cost_usd=0.0, usage={}, result="")


class _Client:
    def __init__(self, usage=USAGE, fail=False):
        self.stream = asyncio.Queue()
        self.usage = usage
        self.fail = fail
        self.polls = 0
        self.order = []

    async def query(self, text):
        self.order.append(("query", text))
        self.stream.put_nowait(result())

    async def get_context_usage(self):
        self.polls += 1
        self.order.append(("poll", None))
        if self.fail:
            raise RuntimeError("no control channel")
        return self.usage

    async def receive_messages(self):
        while True:
            yield await self.stream.get()


def run_turns(client, count=1):
    session = ClaudeSession()
    session._client = client
    readings, events, errors, done = [], [], [], []
    session.context_usage.connect(readings.append)
    session.session_event.connect(events.append)
    session.session_error.connect(errors.append)
    session.turn_complete.connect(done.append)

    async def go():
        for i in range(count):
            await session._query_and_stream(f"q{i}")

    asyncio.run(go())
    return readings, events, errors, done


def test_poll_after_each_turn():
    client = _Client()
    readings, events, errors, done = run_turns(client, 2)
    check("one reading per turn", client.polls == 2 and len(readings) == 2)
    check("only the documented keys are forwarded", set(readings[0]) == {"totalTokens", "maxTokens", "percentage", "autoCompactThreshold", "isAutoCompactEnabled", "model"})
    check("a context_usage session_event is emitted with the turn id", [e["turn_id"] for e in events if e["kind"] == "context_usage"] == [1, 2])
    check("the poll happens after the turn's result, before the next query", client.order == [("query", "q0"), ("poll", None), ("query", "q1"), ("poll", None)])
    check("turn_complete still fires normally", len(done) == 2 and errors == [])


def test_poll_failure_never_breaks_the_turn():
    readings, events, errors, done = run_turns(_Client(fail=True))
    check("no reading, no error, turn completed", readings == [] and errors == [] and len(done) == 1)

    class _NoMethod(_Client):
        get_context_usage = None

    readings, _e, errors, done = run_turns(_NoMethod())
    check("a client without the method is tolerated too", readings == [] and errors == [] and len(done) == 1)


# -- widget --------------------------------------------------------------------------


class _FakeSession:
    def __init__(self):
        self.sent = []

    def send_prompt(self, t):
        self.sent.append(t)

    def stop(self):
        pass


def make_widget():
    widget = module.build()
    widget._session = _FakeSession()
    return widget


def usage(total, threshold=167000, enabled=True):
    return {"totalTokens": total, "maxTokens": 200000, "percentage": total / 2000, "autoCompactThreshold": threshold, "isAutoCompactEnabled": enabled}


def test_context_label_thresholds():
    widget = make_widget()
    check("hidden before any reading", widget._context_label.isHidden())
    widget._on_context_usage(usage(20000))
    check("shows the percentage", not widget._context_label.isHidden() and widget._context_label.text() == "Context 10%")
    check("plain below the warning fraction", widget._context_label.styleSheet() == "")
    check("tooltip has exact tokens and the threshold", "20,000" in widget._context_label.toolTip() and "167,000" in widget._context_label.toolTip())
    widget._on_context_usage(usage(int(167000 * 0.9)))
    check("amber near the threshold", "e8a33d" in widget._context_label.styleSheet())
    widget._on_context_usage(usage(170000))
    check("red at or past it", "da3232" in widget._context_label.styleSheet())
    widget._on_context_usage(usage(20000, enabled=False))
    check("tooltip says auto-compact is off when it is", "auto-compact off" in widget._context_label.toolTip())
    widget._on_context_usage({"totalTokens": 100, "maxTokens": 1000})
    check("missing threshold/percentage degrade gracefully", widget._context_label.text() == "Context 10%" and widget._context_label.styleSheet() == "")


def test_compact_confirm_flow():
    widget = make_widget()
    session = widget._session
    check("confirm row hidden at first", widget._compact_label.isHidden())
    widget._compact_button.click()
    check("clicking shows the confirmation, sends nothing", not widget._compact_label.isHidden() and session.sent == [])
    widget._compact_cancel_button.click()
    check("Cancel hides it, still nothing sent", widget._compact_label.isHidden() and session.sent == [])
    widget._compact_button.click()
    widget._compact_confirm_button.click()
    check("Compact sends the literal /compact", session.sent == ["/compact"])
    check("the history shows what was sent", any(e.meta.kind == "user" and e.text == "/compact" for e in widget._history.entries()))
    check("the row is dismissed and the widget is busy", widget._compact_label.isHidden() and widget._busy)


def test_compact_disabled_while_busy():
    widget = make_widget()
    widget._compact_button.click()
    check("sanity: row open", not widget._compact_label.isHidden())
    widget._set_busy(True)
    check("going busy disables the button and closes an open confirmation", not widget._compact_button.isEnabled() and widget._compact_label.isHidden())
    widget._set_busy(False)
    check("idle re-enables it", widget._compact_button.isEnabled())
    widget._set_busy(True)
    widget._on_compact_clicked()
    widget._confirm_compact()
    check("even a stray confirm while busy sends nothing", widget._session.sent == [])


test_poll_after_each_turn()
test_poll_failure_never_breaks_the_turn()
test_context_label_thresholds()
test_compact_confirm_flow()
test_compact_disabled_while_busy()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
