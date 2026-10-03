"""Verifies TODO `c1eb687`: RateLimitEvent and api_error_status surfaced
in ClaudeSession, the widget and the flow view. No live API."""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import claude_agent_sdk as sdk  # noqa: E402

from desk.claude_flow_view import FlowView  # noqa: E402
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

    spec = importlib.util.spec_from_file_location("rl_check", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _module()


def rate_event(status="allowed_warning", resets_at=None, utilization=0.9):
    info = sdk.RateLimitInfo(status=status, resets_at=resets_at, rate_limit_type="five_hour", utilization=utilization)
    return sdk.RateLimitEvent(rate_limit_info=info, uuid="u", session_id="s")


def result(**kw):
    base = dict(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s", total_cost_usd=0.0, usage={}, result="ok")
    base.update(kw)
    return sdk.ResultMessage(**base)


class _FakeSession:
    def send_prompt(self, t):
        pass

    def stop(self):
        pass


def test_session_dispatches_rate_limit_without_opening_a_turn():
    session = ClaudeSession()
    events, limits = [], []
    session.session_event.connect(events.append)
    session.rate_limit.connect(limits.append)
    session._dispatch(rate_event(resets_at=1_700_000_000))
    check("signal carries the flattened info", limits[0]["status"] == "allowed_warning" and limits[0]["resets_at"] == 1_700_000_000 and limits[0]["rate_limit_type"] == "five_hour")
    check("a rate_limit session_event is emitted", [e["kind"] for e in events] == ["rate_limit"])
    check("it did NOT open an unsolicited turn", session._unsolicited_turn_id is None and all(e["kind"] != "unsolicited_turn_started" for e in events))
    errors = []
    session.session_error.connect(errors.append)
    session._dispatch(result())
    check("a result after an idle rate-limit event is still a protocol violation (no phantom turn)", len(errors) == 1)


def test_rate_limit_during_a_turn_is_tagged_with_it():
    import asyncio

    session = ClaudeSession()
    events = []
    session.session_event.connect(events.append)

    async def run():
        session._pending_turn = (4, asyncio.get_running_loop().create_future())
        session._dispatch(rate_event())

    asyncio.run(run())
    check("tagged with the in-flight turn, solicited", events[0]["turn_id"] == 4 and events[0]["solicited"] is True)


def test_turn_complete_carries_api_error_status():
    session = ClaudeSession()
    done = []
    session.turn_complete.connect(done.append)
    session._handle_message(result(is_error=True, api_error_status=429), 1, True)
    check("api_error_status forwarded", done[0]["api_error_status"] == 429)


def test_widget_label_and_notice():
    widget = module.build()
    widget._session = _FakeSession()
    check("label hidden initially", widget._rate_limit_label.isHidden())
    resets = int(time.time()) + 3600
    widget._on_rate_limit({"status": "allowed_warning", "resets_at": resets, "rate_limit_type": "five_hour", "utilization": 0.9})
    hhmm = time.strftime("%H:%M", time.localtime(resets))
    check("warning label shown with the reset time", not widget._rate_limit_label.isHidden() and widget._rate_limit_label.text() == f"Rate limit warning -- resets {hhmm}")
    check("tooltip has window and utilization", "five_hour" in widget._rate_limit_label.toolTip() and "90%" in widget._rate_limit_label.toolTip())
    check("a history notice was added once", sum("Rate limit warning" in e.text for e in widget._history.entries()) == 1)
    widget._on_rate_limit({"status": "allowed_warning", "resets_at": resets})
    check("a repeated same-status event adds no second notice", sum("Rate limit warning" in e.text for e in widget._history.entries()) == 1)
    widget._on_rate_limit({"status": "rejected", "resets_at": resets})
    check("rejected reads as Rate limited", widget._rate_limit_label.text().startswith("Rate limited"))
    widget._on_rate_limit({"status": "allowed"})
    check("allowed hides the label again", widget._rate_limit_label.isHidden())


def test_api_error_status_in_widget():
    widget = module.build()
    widget._session = _FakeSession()
    widget._set_busy(True)
    widget._on_turn_complete({"is_error": True, "api_error_status": 529, "result": "overloaded"})
    check("status names the HTTP status", widget._status_label.text() == "Error (HTTP 529).")
    check("an error entry carries the detail", any("HTTP 529" in e.text and "overloaded" in e.text for e in widget._history.entries()))


def test_flow_view_annotates_the_cli_node():
    view = FlowView()
    ev = lambda status: {"seq": 1, "ts": 1.0, "turn_id": None, "solicited": False, "kind": "rate_limit", "data": {"status": status}}
    view.feed(ev("allowed_warning"))
    check("warning annotates throttled", "throttled" in view._annotation("cli"))
    check("no marker spawned for a rate-limit event", view.markers() == [])
    view.feed(ev("rejected"))
    check("rejected annotates RATE LIMITED", "RATE LIMITED" in view._annotation("cli"))
    view.feed(ev("allowed"))
    check("allowed clears it", view._annotation("cli") == "0 bg tasks")
    view.resize(520, 170)
    view.feed(ev("rejected"))
    check("painting with a rate-limited CLI node works", view.grab().width() == 520)


test_session_dispatches_rate_limit_without_opening_a_turn()
test_rate_limit_during_a_turn_is_tagged_with_it()
test_turn_complete_carries_api_error_status()
test_widget_label_and_notice()
test_api_error_status_in_widget()
test_flow_view_annotates_the_cli_node()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
