"""TODO 540e886: feedback-item store layout and MCP tools."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk import feedback_items as fi  # noqa: E402
from desk.record_store import InMemoryRecordStore  # noqa: E402
from desk.shell import current_context, desk_mcp_server as srv  # noqa: E402
from desk.temp_ui import CURRENT_TAGS, SPLIT_DOC_CONTENT  # noqa: E402

passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def call(tool_obj, args):
    result = asyncio.run(tool_obj.handler(args))
    return result["content"][0]["text"], bool(result.get("is_error"))


with tempfile.TemporaryDirectory() as d:
    project = Path(d) / "desk"
    fb = Path(d) / "FEEDBACK"
    project.mkdir()
    (fb / "implemented").mkdir(parents=True)
    (fb / "parkinglot").mkdir()
    (fb / "FEEDBACK-DESK-old-open-thing-2026-10-01-0900.md").write_text("# Feedback: old open thing\n\nwidgets flicker\n")
    (fb / "implemented" / "FEEDBACK-DESK-done-thing-2026-09-01-0900.md").write_text("# Done thing\n\ntext\n")
    (fb / "parkinglot" / "FEEDBACK-DESK-later-2026-09-02-0900.md").write_text("# Feedback: later\n")
    current_context.set_current_desk_directory(project)

    text, err = call(srv._list_feedback, {})
    items = json.loads(text)
    by_status = {i["status"]: i for i in items}
    check("lists all three, statuses from placement", not err and set(by_status) == {"open", "implemented", "parkinglot"})
    check("title strips 'Feedback: ' prefix / reads plain heading", by_status["open"]["title"] == "old open thing" and by_status["implemented"]["title"] == "Done thing")
    check("list omits bodies", all("body" not in i for i in items))
    check("status filter", [i["status"] for i in json.loads(call(srv._list_feedback, {"status": "implemented"})[0])] == ["implemented"])
    check("keyword searches body", len(json.loads(call(srv._list_feedback, {"keyword": "FLICKER"})[0])) == 1)
    check("bad status errors", call(srv._list_feedback, {"status": "x"})[1])

    text, err = call(srv._create_feedback, {"title": "Cross agent: handoff?", "body": "It hurts."})
    created = json.loads(text)
    path = fb / f"{created['id']}.md"
    check("created at top level with convention filename", not err and path.is_file() and created["id"].startswith("FEEDBACK-DESK-cross-agent-handoff-"))
    check("file shape matches existing files", path.read_text().startswith("# Feedback: Cross agent: handoff?\n\nIt hurts."))
    check("new item is open", created["status"] == "open")
    text, err = call(srv._get_feedback, {"id": created["id"]})
    check("get returns full text", not err and "It hurts." in json.loads(text)["body"])
    check("get missing -> error", call(srv._get_feedback, {"id": "nope"})[1])
    check("get refuses path tricks", call(srv._get_feedback, {"id": "../desk/x"})[1])
    check("empty body refused", call(srv._create_feedback, {"title": "t", "body": " "})[1])
    check("absolute directory refused", call(srv._list_feedback, {"directory": str(fb)})[1])
    check("no triage tools exposed", not any("feedback" in t.name and any(v in t.name for v in ("move", "update", "delete", "triage")) for t in srv._TOOLS))

    memory = InMemoryRecordStore(fi.STATUSES)
    saved = srv._feedback_store_factory
    srv._feedback_store_factory = lambda path: memory
    try:
        rid = json.loads(call(srv._create_feedback, {"title": "M", "body": "b"})[0])["id"]
        check("tools run unchanged over a non-filesystem store", memory.get(rid) is not None and len(json.loads(call(srv._list_feedback, {})[0])) == 1)
    finally:
        srv._feedback_store_factory = saved
    current_context.set_current_desk_directory(None)

check("tools registered", all(t in srv._TOOLS for t in (srv._create_feedback, srv._list_feedback, srv._get_feedback)))
check("tempui tag minted", "feedback item MCP tools #156881" in CURRENT_TAGS)
check("dedicated doc registered", "tempui-feedback-items.md" in SPLIT_DOC_CONTENT)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
