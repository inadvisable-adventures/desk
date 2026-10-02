# TODO 20ca851: ClaudeSession's persistent reader, turn serialization,
# structured session_event model and mismatch detection. A fake client
# stands in for sdk.ClaudeSDKClient (no subprocess/network); its
# receive_messages() is fed from a queue the test controls, mimicking
# the SDK's one shared, unlabeled stream.
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

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


def text_msg(t):
    return sdk.AssistantMessage(content=[sdk.TextBlock(text=t)], model="m")


def result_msg(r="ok"):
    return sdk.ResultMessage(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
        num_turns=1, session_id="s", total_cost_usd=0.0, usage={}, result=r,
    )


class _FakeClient:
    """query() records the prompt and (if `auto_reply`) feeds a reply +
    result onto the shared stream; tests can also push() messages at any
    time, e.g. while no turn is outstanding."""

    def __init__(self, auto_reply=True):
        self.stream = asyncio.Queue()
        self.queried = []
        self.auto_reply = auto_reply
        self.outstanding = 0
        self.max_outstanding = 0

    async def query(self, text):
        self.queried.append(text)
        self.outstanding += 1
        self.max_outstanding = max(self.max_outstanding, self.outstanding)
        if self.auto_reply:
            await asyncio.sleep(0.01)
            self.push(text_msg(f"reply to {text}"))
            self.push(result_msg())
            self.outstanding -= 1

    def push(self, message):
        self.stream.put_nowait(message)

    async def receive_messages(self):
        while True:
            item = await self.stream.get()
            if isinstance(item, Exception):
                raise item
            yield item


def make_session(client):
    session = ClaudeSession()
    session._client = client
    events, legacy = [], {"text": [], "done": [], "error": []}
    session.session_event.connect(events.append)
    session.assistant_text.connect(lambda t: legacy["text"].append(t))
    session.turn_complete.connect(lambda d: legacy["done"].append(d))
    session.session_error.connect(lambda m: legacy["error"].append(m))
    return session, events, legacy


def test_concurrent_turns_are_serialized_and_pair_in_order():
    async def run():
        client = _FakeClient()
        session, events, legacy = make_session(client)
        await asyncio.gather(
            session._query_and_stream("one"), session._query_and_stream("two"), session._query_and_stream("three")
        )
        return client, events, legacy

    client, events, legacy = asyncio.run(run())
    check("never more than one query outstanding", client.max_outstanding == 1)
    check("queries sent in submission order", client.queried == ["one", "two", "three"])
    texts = [(e["turn_id"], e["data"]["text"]) for e in events if e["kind"] == "assistant_text"]
    check("each reply is filed under its own turn", texts == [(1, "reply to one"), (2, "reply to two"), (3, "reply to three")])
    check("legacy turn_complete fired once per turn", len(legacy["done"]) == 3)


def test_event_seq_and_turn_ids_are_monotonic():
    async def run():
        session, events, _ = make_session(_FakeClient())
        await session._query_and_stream("a")
        await session._query_and_stream("b")
        return events

    events = asyncio.run(run())
    seqs = [e["seq"] for e in events]
    check("seq strictly increasing", seqs == sorted(set(seqs)) and seqs[0] == 1)
    check("every event has a timestamp and kind", all(e["ts"] > 0 and e["kind"] for e in events))
    check("kinds cover start/text/complete", {"turn_started", "assistant_text", "turn_complete"} <= {e["kind"] for e in events})


def test_unsolicited_output_while_idle_does_not_leak_into_next_turn():
    # The stale-result scenario: a ScheduleWakeup-style continuation
    # arrives with no turn outstanding. It must be tagged unsolicited,
    # and the NEXT real prompt must still get its own reply.
    async def run():
        client = _FakeClient()
        session, events, legacy = make_session(client)
        session._ensure_reader()
        client.push(text_msg("wakeup output"))
        client.push(result_msg("wakeup"))
        await asyncio.sleep(0.05)
        await session._query_and_stream("real")
        return events, legacy

    events, legacy = asyncio.run(run())
    wake = [e for e in events if e["kind"] == "assistant_text" and e["data"]["text"] == "wakeup output"]
    real = [e for e in events if e["kind"] == "assistant_text" and e["data"]["text"] == "reply to real"]
    check("wakeup output tagged unsolicited", len(wake) == 1 and wake[0]["solicited"] is False)
    check("unsolicited turn start announced", any(e["kind"] == "unsolicited_turn_started" for e in events))
    check("real reply is solicited and under a different turn", len(real) == 1 and real[0]["solicited"] and real[0]["turn_id"] != wake[0]["turn_id"])
    check("legacy turn_complete fired only for the real turn", len(legacy["done"]) == 1)
    check("no spurious errors", legacy["error"] == [])


def test_stray_result_is_a_protocol_violation():
    async def run():
        client = _FakeClient()
        session, events, legacy = make_session(client)
        session._ensure_reader()
        client.push(result_msg("stray"))
        await asyncio.sleep(0.05)
        return events, legacy

    events, legacy = asyncio.run(run())
    check("protocol_violation event emitted", any(e["kind"] == "protocol_violation" for e in events))
    check("session_error surfaced loudly", len(legacy["error"]) == 1)
    check("stray result not rendered as a completed turn", legacy["done"] == [])


def test_stream_failure_fails_the_pending_turn_without_hanging():
    async def run():
        client = _FakeClient(auto_reply=False)
        session, events, legacy = make_session(client)
        task = asyncio.ensure_future(session._query_and_stream("x"))
        await asyncio.sleep(0.02)
        client.push(RuntimeError("boom"))
        await asyncio.wait_for(task, timeout=2)
        return events, legacy

    events, legacy = asyncio.run(run())
    check("session_error surfaced", legacy["error"] == ["boom"])
    check("error event carries the turn id", any(e["kind"] == "session_error" and e["turn_id"] == 1 for e in events))


test_concurrent_turns_are_serialized_and_pair_in_order()
test_event_seq_and_turn_ids_are_monotonic()
test_unsolicited_output_while_idle_does_not_leak_into_next_turn()
test_stray_result_is_a_protocol_violation()
test_stream_failure_fails_the_pending_turn_without_hanging()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
