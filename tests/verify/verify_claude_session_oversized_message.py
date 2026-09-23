# TODO f35466a: the Claude (Desk) widget's underlying ClaudeSession must
# stay usable after an oversized tool-result/message during a turn,
# instead of the "widget got glitchy" symptom reported. No live Claude
# API access here (see disabled_verify_scoped_claude_session.py's own
# precedent for why that kind of coverage is split out and disabled) --
# this reproduces the confirmed real cause (claude_agent_sdk's
# subprocess transport caps a single NDJSON line at max_buffer_size,
# raising CLIJSONDecodeError when exceeded) directly at the exact
# boundary Desk's own code owns: a fake sdk.ClaudeSDKClient substituted
# for ClaudeSession._client, no subprocess or network involved.
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import claude_agent_sdk as sdk  # noqa: E402

from desk.claude_session import ClaudeSession, _MAX_BUFFER_SIZE  # noqa: E402

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


class _FakeClient:
    """Stands in for a real sdk.ClaudeSDKClient: query() just records
    what was sent, receive_response() yields whatever this test wants,
    including raising partway through -- exactly what
    ClaudeSession._query_and_stream actually consumes, with no
    subprocess/transport underneath it."""

    def __init__(self, messages, error=None):
        self._messages = messages
        self._error = error
        self.queried = []

    async def query(self, text):
        self.queried.append(text)

    async def receive_response(self):
        for message in self._messages:
            yield message
        if self._error is not None:
            raise self._error


def _oversized_message_error():
    # The exact exception claude_agent_sdk's own
    # _internal/transport/subprocess_cli.py's guard() raises, word for word.
    return sdk.CLIJSONDecodeError(
        "JSON message exceeded maximum buffer size of 1048576 bytes",
        ValueError("Buffer size 1234567 exceeds limit 1048576"),
    )


def _connect_events(session):
    events = []
    session.assistant_text.connect(lambda t: events.append(("text", t)))
    session.session_error.connect(lambda m: events.append(("error", m)))
    session.turn_complete.connect(lambda d: events.append(("done", d)))
    return events


def test_max_buffer_size_is_raised_well_above_the_sdk_default():
    check("the new limit is well above the SDK's own 1MB default", _MAX_BUFFER_SIZE > 5_000_000)


def test_max_buffer_size_is_actually_passed_to_claude_agent_options():
    captured = {}
    real_options_cls = sdk.ClaudeAgentOptions

    def _capturing_options(**kwargs):
        captured.update(kwargs)
        return real_options_cls(**kwargs)

    session = ClaudeSession()

    class _StubClient:
        def __init__(self, options):
            captured["client_options"] = options

        async def connect(self):
            pass

    with patch("desk.claude_session.sdk.ClaudeAgentOptions", side_effect=_capturing_options):
        with patch("desk.claude_session.sdk.ClaudeSDKClient", _StubClient):
            asyncio.run(
                session._connect_and_maybe_prompt(
                    "session-1", False, None, "default", None, ""
                )
            )

    check("max_buffer_size was passed to ClaudeAgentOptions", captured.get("max_buffer_size") == _MAX_BUFFER_SIZE)
    check(
        "the real ClaudeAgentOptions object built from it carries the same value",
        captured["client_options"].max_buffer_size == _MAX_BUFFER_SIZE,
    )


def test_oversized_message_mid_turn_delivers_what_arrived_first():
    session = ClaudeSession()
    events = _connect_events(session)
    session._client = _FakeClient(
        [sdk.AssistantMessage(content=[sdk.TextBlock(text="partial reply")], model="m")],
        error=_oversized_message_error(),
    )

    asyncio.run(session._query_and_stream("hi"))

    check("the message that arrived before the failure is still delivered, not lost", ("text", "partial reply") in events)


def test_oversized_message_surfaces_a_bounded_legible_session_error():
    session = ClaudeSession()
    events = _connect_events(session)
    session._client = _FakeClient([], error=_oversized_message_error())

    asyncio.run(session._query_and_stream("hi"))

    errors = [message for kind, message in events if kind == "error"]
    check("session_error fired exactly once", len(errors) == 1)
    check("the message names the actual cause", "buffer size" in errors[0].lower())
    check(
        # CLIJSONDecodeError.__str__ truncates to the first 100 chars of
        # whatever it's given -- confirming the oversized payload itself
        # is never what ends up dumped into the widget's own history.
        "the message is short/bounded, not the oversized payload itself",
        len(errors[0]) < 200,
    )


def test_no_hang_on_the_failing_turn():
    # asyncio.run() completing at all (rather than this script itself
    # hanging) is the actual proof here -- a real, if coarse, check
    # against the SDK-level failure looking like a hang instead of a
    # clean exception.
    session = ClaudeSession()
    _connect_events(session)
    session._client = _FakeClient([], error=_oversized_message_error())
    asyncio.run(asyncio.wait_for(session._query_and_stream("hi"), timeout=5))
    check("the failing turn's coroutine completed, did not hang", True)


def test_session_remains_usable_for_a_subsequent_turn():
    # TODO f35466a point 3: "the session left usable" -- not just that
    # session_error fired, but that a fresh call still works normally
    # afterward, against a client standing in for a healthy connection.
    session = ClaudeSession()
    events = _connect_events(session)
    session._client = _FakeClient([], error=_oversized_message_error())
    asyncio.run(session._query_and_stream("hi"))
    check("sanity: the first turn did fail", any(kind == "error" for kind, _ in events))

    events.clear()
    session._client = _FakeClient(
        [
            sdk.ResultMessage(
                subtype="success",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id="s",
                total_cost_usd=0.0,
                usage={},
                result="ok",
            )
        ]
    )
    asyncio.run(session._query_and_stream("hi again"))
    check(
        "a subsequent turn against a working client completes normally, the session isn't left broken",
        any(kind == "done" for kind, _ in events),
    )


test_max_buffer_size_is_raised_well_above_the_sdk_default()
test_max_buffer_size_is_actually_passed_to_claude_agent_options()
test_oversized_message_mid_turn_delivers_what_arrived_first()
test_oversized_message_surfaces_a_bounded_legible_session_error()
test_no_hang_on_the_failing_turn()
test_session_remains_usable_for_a_subsequent_turn()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
