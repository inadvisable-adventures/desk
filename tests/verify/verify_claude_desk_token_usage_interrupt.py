"""Verifies TODO `db2402c`: the Claude (Desk) widget's live token-usage
indicator and Interrupt button. Fake client / fake session only -- no
live API."""

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

    spec = importlib.util.spec_from_file_location("tok_check", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _module()


class _FakeSession:
    def __init__(self):
        self.interrupts = 0

    def send_prompt(self, text):
        pass

    def stop(self):
        pass

    def interrupt(self):
        self.interrupts += 1


def ev(kind, turn_id=1, solicited=True):
    return {"seq": 1, "ts": 1.0, "turn_id": turn_id, "solicited": solicited, "kind": kind, "data": {}}


def result(**kw):
    base = dict(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s", total_cost_usd=0.0, usage={}, result="ok")
    base.update(kw)
    return sdk.ResultMessage(**base)


# -- ClaudeSession ----------------------------------------------------------


def test_session_forwards_usage_for_top_level_messages_only():
    session = ClaudeSession()
    usages, events = [], []
    session.token_usage.connect(usages.append)
    session.session_event.connect(events.append)
    session._handle_message(sdk.AssistantMessage(content=[], model="m", usage={"input_tokens": 5, "output_tokens": 2}), 1, True)
    session._handle_message(sdk.AssistantMessage(content=[], model="m", usage={"input_tokens": 9}, parent_tool_use_id="toolu_x"), 1, True)
    session._handle_message(sdk.AssistantMessage(content=[], model="m"), 1, True)
    check("only the top-level message with usage is forwarded", usages == [{"input_tokens": 5, "output_tokens": 2}])
    check("a matching token_usage session_event is emitted", [e["kind"] for e in events] == ["token_usage"])


def test_turn_complete_carries_final_tally_and_terminal_reason():
    session = ClaudeSession()
    done = []
    session.turn_complete.connect(done.append)
    session._handle_message(result(usage={"output_tokens": 7}, terminal_reason="aborted_streaming"), 1, True)
    check("usage forwarded", done[0]["usage"] == {"output_tokens": 7})
    check("terminal_reason forwarded", done[0]["terminal_reason"] == "aborted_streaming")
    check("model_usage key present", "model_usage" in done[0])


def test_interrupt_calls_the_client_on_the_session_loop():
    class _Client:
        def __init__(self):
            self.interrupted = 0

        async def interrupt(self):
            self.interrupted += 1

    async def run():
        session = ClaudeSession()
        session._client = _Client()
        await session._interrupt()
        return session._client.interrupted

    check("_interrupt awaits client.interrupt()", asyncio.run(run()) == 1)
    session = ClaudeSession()
    session.interrupt()
    check("interrupt() before start is a safe no-op", True)

    class _Boom:
        async def interrupt(self):
            raise RuntimeError("nope")

    errors = []
    session = ClaudeSession()
    session._client = _Boom()
    session.session_error.connect(errors.append)
    asyncio.run(session._interrupt())
    check("a failing interrupt surfaces as session_error", errors == ["nope"])


# -- widget -------------------------------------------------------------------


def test_status_shows_live_token_counts_while_busy():
    widget = module.build()
    widget._session = _FakeSession()
    widget._set_busy(True)
    widget._on_session_event(ev("turn_started"))
    widget._on_token_usage({"input_tokens": 1000, "cache_read_input_tokens": 200, "output_tokens": 340})
    check("status shows input (incl. cache) and output", widget._status_label.text() == "Working... (↑1.2k ↓340 tokens)")
    widget._on_token_usage({"input_tokens": 1500, "output_tokens": 60})
    check("input is the latest context size, output accumulates", widget._status_label.text() == "Working... (↑1.5k ↓400 tokens)")
    widget._on_session_event(ev("turn_started", 2))
    check("counters reset on a new turn", (widget._turn_input_tokens, widget._turn_output_tokens) == (0, 0))


def test_interrupt_button_visibility_and_action():
    widget = module.build()
    session = _FakeSession()
    widget._session = session
    check("hidden while idle", widget._interrupt_button.isHidden())
    widget._set_busy(True)
    check("shown while busy", not widget._interrupt_button.isHidden())
    widget._interrupt_button.click()
    check("clicking calls session.interrupt()", session.interrupts == 1)
    check("status says Interrupting and the button disables (no double-fire)", widget._status_label.text() == "Interrupting..." and not widget._interrupt_button.isEnabled())
    widget._on_token_usage({"output_tokens": 5})
    check("late usage doesn't overwrite the Interrupting status", widget._status_label.text() == "Interrupting...")
    widget._on_turn_complete({"is_error": False, "terminal_reason": "aborted_streaming", "usage": {"input_tokens": 10, "output_tokens": 3}})
    check("interrupted turn reads Interrupted.", widget._status_label.text() == "Interrupted.")
    check("button hidden again once idle", widget._interrupt_button.isHidden())
    check("final tally lands in the status tooltip", "↑10 ↓3" in widget._status_label.toolTip())
    widget._set_busy(True)
    widget._on_session_event(ev("turn_started", 5))
    check("a new turn re-enables the button", widget._interrupt_button.isEnabled())


def test_normal_and_error_turns_unchanged():
    widget = module.build()
    widget._session = _FakeSession()
    widget._set_busy(True)
    widget._on_turn_complete({"is_error": False, "terminal_reason": "completed"})
    check("normal turn -> Idle.", widget._status_label.text() == "Idle.")
    widget._set_busy(True)
    widget._on_turn_complete({"is_error": True})
    check("errored turn -> Error.", widget._status_label.text() == "Error.")


test_session_forwards_usage_for_top_level_messages_only()
test_turn_complete_carries_final_tally_and_terminal_reason()
test_interrupt_calls_the_client_on_the_session_loop()
test_status_shows_live_token_counts_while_busy()
test_interrupt_button_visibility_and_action()
test_normal_and_error_turns_unchanged()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
