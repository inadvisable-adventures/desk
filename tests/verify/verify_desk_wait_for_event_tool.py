"""TODO 30069f6: the desk_wait_for_event MCP tool waits for a desk event through the shared
EventMediator, times out / ends / cancels cleanly without leaking a subscription or thread, is
guarded against main-conversation use, and is documented."""
import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk import event_mediator  # noqa: E402
from desk.claude_session import ClaudeSession  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell import desk_mcp_server as mcp  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    AGENT_EVENTS_DOC_FILENAME, CURRENT_TAGS, DOC_TEMPLATE, SPLIT_DOC_CONTENT, _CUSTOM_WIDGETS_DOC, _NEW_FEATURES,
    _PORTING_DOC,
)

failures = 0


def check(name, ok):
    global failures
    print(("PASS" if ok else "FAIL") + ":", name)
    failures += 0 if ok else 1


def body(result):
    return json.loads(result["content"][0]["text"])


def listeners(mediator):
    return [i for i in mediator.list_subscriptions() if i.startswith(mcp.EVENT_LISTENER_ID_PREFIX)]


def publish_later(mediator, delay, name, payload, sender="widget-x"):
    threading.Timer(delay, lambda: mediator.publish(name, payload, sender)).start()


mediator = event_mediator.EventMediator()
current_context.set_event_mediator(mediator)


async def scenarios():
    # event arrives while waiting
    publish_later(mediator, 0.3, "ans", {"id": "q1", "yes": True})
    t0 = time.monotonic()
    got = body(await mcp._wait_for_event.handler({"name": "ans"}))
    check("event returned with status, name, payload, sender, timestamp",
          got["status"] == "event" and got["name"] == "ans" and got["payload"] == {"id": "q1", "yes": True}
          and got["sender"] == "widget-x" and got["timestamp"])
    check("returned promptly after the publish", time.monotonic() - t0 < 2.0)
    check("subscription removed after an event", listeners(mediator) == [])

    publish_later(mediator, 0.2, "nudge", None)
    check("payload-free event gives a null payload", body(await mcp._wait_for_event.handler({"name": "nudge"}))["payload"] is None)

    # only the awaited name wakes it
    publish_later(mediator, 0.1, "other", 1)
    publish_later(mediator, 0.4, "ans", 2)
    check("other names are ignored", body(await mcp._wait_for_event.handler({"name": "ans"}))["payload"] == 2)

    # round trip with the raise tool
    waiter = asyncio.ensure_future(mcp._wait_for_event.handler({"name": "q"}))
    for _ in range(50):
        if listeners(mediator):
            break
        await asyncio.sleep(0.05)
    check("a waiting call shows up as a subscriber", len(listeners(mediator)) == 1)
    raised = await mcp._raise_event.handler({"name": "q", "payload": "hi"})
    check("raise reports the listener as a subscriber", "1 widget instance(s)" in raised["content"][0]["text"])
    got = body(await asyncio.wait_for(waiter, 5))
    check("agent-raised event is received (round trip)", got["payload"] == "hi" and got["sender"] == "agent")

    # timeout
    t0 = time.monotonic()
    got = body(await mcp._wait_for_event.handler({"name": "never", "timeout_seconds": 0.5}))
    check("timeout status", got["status"] == "timeout" and 0.4 < time.monotonic() - t0 < 2.5)
    check("subscription removed after a timeout", listeners(mediator) == [])

    # Desk switch (clear_all) ends the wait
    waiter = asyncio.ensure_future(mcp._wait_for_event.handler({"name": "x"}))
    await asyncio.sleep(0.3)
    mediator.clear_all()
    t0 = time.monotonic()
    got = body(await asyncio.wait_for(waiter, 5))
    check("clear_all gives status ended promptly", got["status"] == "ended" and time.monotonic() - t0 < 3)

    # cancellation frees the subscription and the slot
    waiter = asyncio.ensure_future(mcp._wait_for_event.handler({"name": "x"}))
    await asyncio.sleep(0.3)
    check("cancel target is subscribed", len(listeners(mediator)) == 1)
    waiter.cancel()
    try:
        await waiter
    except asyncio.CancelledError:
        pass
    check("subscription removed after cancel", listeners(mediator) == [])
    check("listener slot released after cancel", mcp._active_listeners == 0)

    # argument validation
    for bad in ({}, {"name": ""}, {"name": 3}, {"name": "x", "timeout_seconds": 0}, {"name": "x", "timeout_seconds": -1},
                {"name": "x", "timeout_seconds": "5"}, {"name": "x", "timeout_seconds": True}):
        r = await mcp._wait_for_event.handler(bad)
        check(f"bad args refused: {bad}", r["is_error"])
    check("bad args left no subscription", listeners(mediator) == [])

    # concurrency cap
    waiters = [asyncio.ensure_future(mcp._wait_for_event.handler({"name": f"cap{i}"})) for i in range(mcp.MAX_CONCURRENT_EVENT_LISTENERS)]
    await asyncio.sleep(0.5)
    r = await mcp._wait_for_event.handler({"name": "overflow"})
    check("call beyond the cap is refused", r["is_error"] and "limit" in r["content"][0]["text"])
    check("refused call did not subscribe", len(listeners(mediator)) == mcp.MAX_CONCURRENT_EVENT_LISTENERS)
    for w in waiters:
        w.cancel()
    await asyncio.gather(*waiters, return_exceptions=True)
    check("all cap waiters cleaned up", listeners(mediator) == [] and mcp._active_listeners == 0)
    await asyncio.sleep(1.5)  # let the pool threads notice and exit their slice
    publish_later(mediator, 0.1, "after", 1)
    check("pool still serves a new wait after saturation",
          body(await asyncio.wait_for(mcp._wait_for_event.handler({"name": "after"}), 5))["payload"] == 1)

    current_context._event_mediator = None
    r = await mcp._wait_for_event.handler({"name": "x"})
    check("no mediator -> not-ready error", r["is_error"] and "not reachable" in r["content"][0]["text"])


asyncio.run(scenarios())

check("tool registered", mcp._wait_for_event in mcp._TOOLS)

# guard
denied = mcp.wait_for_event_hook({"tool_name": "mcp__desk__desk_wait_for_event"})
check("main-conversation call is denied with a reason",
      denied["hookSpecificOutput"]["permissionDecision"] == "deny"
      and "background sub-agent" in denied["hookSpecificOutput"]["permissionDecisionReason"])
check("sub-agent call is allowed", mcp.wait_for_event_hook({"agent_id": "a1", "tool_name": "x"}) == {})
fake = SimpleNamespace(_check_path_scope=object(), _require_subagent_for_wait=object())
hooks = ClaudeSession._pre_tool_use_hooks(fake, False)["PreToolUse"]
check("non-scoped session registers the guard for exactly the wait tool",
      len(hooks) == 1 and hooks[0].matcher == f"mcp__{mcp.DESK_MCP_SERVER_NAME}__{mcp.WAIT_FOR_EVENT_TOOL_NAME}"
      == "mcp__desk__desk_wait_for_event" and hooks[0].hooks == [fake._require_subagent_for_wait])
scoped = ClaudeSession._pre_tool_use_hooks(fake, True)["PreToolUse"]
check("scoped session keeps only the path-scope check", len(scoped) == 1 and scoped[0].matcher is None and scoped[0].hooks == [fake._check_path_scope])
guard = asyncio.run(ClaudeSession._require_subagent_for_wait(fake, {}, None, None))
check("the session hook delegates to the decision function", guard["hookSpecificOutput"]["permissionDecision"] == "deny")

# docs
doc = SPLIT_DOC_CONTENT[AGENT_EVENTS_DOC_FILENAME]
tag = next((t for t in CURRENT_TAGS if "agent waits for a desk event" in t), None)
check("tag has a changelog entry linking the doc", tag in _NEW_FEATURES and "tempui-agent-events.md" in _NEW_FEATURES[tag])
check("overview, custom-widgets and porting docs name the tool", all("desk_wait_for_event" in x for x in (DOC_TEMPLATE, _CUSTOM_WIDGETS_DOC, _PORTING_DOC)))
check("doc names the tool, statuses and the background rule",
      all(k in doc for k in ("desk_wait_for_event", '"event"', '"timeout"', '"ended"', "background sub-agent", "run_in_background")))
check("doc is honest about foreground sub-agents and the between-calls gap",
      "foreground" in doc and "between two calls" in doc)
check("doc states the real concurrency cap", f"At most {mcp.MAX_CONCURRENT_EVENT_LISTENERS} waits" in doc)

print("FAILURES:", failures)
sys.exit(1 if failures else 0)
