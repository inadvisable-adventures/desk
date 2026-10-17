"""TODO 71d11da: the desk_raise_event MCP tool publishes agent-raised desk events through the
shared EventMediator, refuses reserved names and oversize payloads, and is documented."""
import asyncio
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk import event_mediator  # noqa: E402
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


def raise_event(args):
    return asyncio.run(mcp._raise_event.handler(args))


def text_of(result):
    return result["content"][0]["text"]


with tempfile.TemporaryDirectory() as d:
    mediator = event_mediator.EventMediator()
    mediator.set_log_directory(Path(d))
    current_context.set_event_mediator(mediator)
    mediator.subscribe("widget-a", "ask")
    mediator.subscribe("widget-b", "ask")
    mediator.subscribe("widget-c", "other")

    result = raise_event({"name": "ask", "payload": {"id": "q1", "n": [1, 2]}})
    check("success is not an error", not result["is_error"])
    check("result reports 2 subscribers", "2 widget instance(s)" in text_of(result))
    got = mediator.drain("widget-a")
    check("subscriber receives name, payload and sender 'agent'",
          len(got) == 1 and got[0].name == "ask" and got[0].payload == {"id": "q1", "n": [1, 2]}
          and got[0].sender_instance_id == mcp.AGENT_EVENT_SENDER_ID == "agent")
    check("second subscriber also receives it", len(mediator.drain("widget-b")) == 1)
    check("subscriber to a different name receives nothing", mediator.drain("widget-c") == [])

    result = raise_event({"name": "ask"})
    check("payload-free event delivers a None payload", mediator.drain("widget-a")[0].payload is None)
    result = raise_event({"name": "nobody-home"})
    check("zero subscribers is reported, not an error", not result["is_error"] and "0 widget instance(s)" in text_of(result))

    parsed = event_mediator.parse_log(mediator.log_path.read_text(encoding="utf-8"))
    check("every raise is in the event log with sender 'agent'",
          [e.name for e in parsed] == ["ask", "ask", "nobody-home"] and all(e.sender_instance_id == "agent" for e in parsed))

    before = len(parsed)
    for bad in ("desk.state.changed", "desk.anything", "recording", "stopped_recording", "", "   ", "x" * 201):
        r = raise_event({"name": bad})
        check(f"refused name {bad[:20]!r}", r["is_error"])
    check("name must be a string", raise_event({"name": 5})["is_error"])
    check("missing name refused", raise_event({})["is_error"])
    big = raise_event({"name": "ask", "payload": "x" * (mcp.MAX_EVENT_PAYLOAD_BYTES + 1)})
    check("oversize payload refused with a file hint", big["is_error"] and "file" in text_of(big))
    ok_edge = raise_event({"name": "ask", "payload": "x" * 1000})
    check("a 1000-byte payload is accepted", not ok_edge["is_error"])
    mediator.drain("widget-a")
    after = len(event_mediator.parse_log(mediator.log_path.read_text(encoding="utf-8")))
    check("refused calls published nothing", after == before + 1)

    current_context._event_mediator = None
    r = raise_event({"name": "ask"})
    check("no mediator -> not-ready error", r["is_error"] and "not reachable" in text_of(r))

check("tool is registered", mcp._raise_event in mcp._TOOLS)

doc = SPLIT_DOC_CONTENT[AGENT_EVENTS_DOC_FILENAME]
tag = next((t for t in CURRENT_TAGS if "agent-raised desk events" in t), None)
check("doc filename", AGENT_EVENTS_DOC_FILENAME == "tempui-agent-events.md")
check("tag has a changelog entry linking the doc", tag in _NEW_FEATURES and "tempui-agent-events.md" in _NEW_FEATURES[tag])
check("overview, custom-widgets and porting docs link it", all("tempui-agent-events.md" in x for x in (DOC_TEMPLATE, _CUSTOM_WIDGETS_DOC, _PORTING_DOC)))
check("doc names the tool and its real limits", "desk_raise_event" in doc and "64 KiB" in doc and str(mcp.MAX_EVENT_NAME_CHARS) in doc)
check("doc names the reserved names", "`desk.`" in doc and "stopped_recording" in doc)
check("doc states the 1 KB file guidance", "1 KB" in doc)

print("FAILURES:", failures)
sys.exit(1 if failures else 0)
