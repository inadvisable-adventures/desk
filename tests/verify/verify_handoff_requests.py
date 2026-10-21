"""TODO e814eaf: RecordStore (filesystem + in-memory), handoff lifecycle, and the MCP tools."""
import asyncio
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk import handoff_requests as hr  # noqa: E402
from desk.record_store import (  # noqa: E402
    FilesystemRecordStore,
    InMemoryRecordStore,
    RecordConflict,
    RecordNotFound,
)
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


def raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def lifecycle(label, store):
    rec = hr.create_request(store, "Fix the thing: now", "Change X", why="because", requested_by="a")
    check(f"{label}: created as new", rec.status == "new" and rec.fields["requested_by"] == "a")
    check(f"{label}: get round-trips", store.get(rec.id).title == "Fix the thing: now" and "Change X" in store.get(rec.id).body)
    check(f"{label}: list by status", [r.id for r in store.list("new")] == [rec.id] and store.list("complete") == [])
    check(f"{label}: keyword filter", len(store.list(keyword="CHANGE x")) == 1 and store.list(keyword="zzz") == [])
    check(f"{label}: cannot complete before claiming", raises(RecordConflict, lambda: hr.complete_request(store, rec.id, "done")))
    claimed = hr.claim_request(store, rec.id, "agent-1")
    check(f"{label}: claimed", claimed.status == "in-progress" and claimed.fields["claimed_by"] == "agent-1")
    check(f"{label}: second claim conflicts", raises(RecordConflict, lambda: hr.claim_request(store, rec.id, "agent-2")))
    check(f"{label}: unknown id", raises(RecordNotFound, lambda: hr.claim_request(store, "nope")))
    check(f"{label}: bad outcome rejected", raises(ValueError, lambda: hr.complete_request(store, rec.id, "great")))
    done = hr.complete_request(store, rec.id, "partial", "half of it was wrong")
    check(f"{label}: completed with outcome", done.status == "complete" and done.fields["outcome"] == "partial")
    check(f"{label}: outcome persisted", store.get(rec.id).fields["outcome_note"] == "half of it was wrong")
    check(f"{label}: bad status rejected", raises(ValueError, lambda: store.list("bogus") or store.create("t", {}, "", "bogus")))


with tempfile.TemporaryDirectory() as d:
    root = Path(d) / "reqs"
    lifecycle("filesystem", hr.filesystem_store(root))
    check("filesystem: file sits in complete/", len(list((root / "complete").glob("*.md"))) == 1 and not list((root / "new").glob("*.md")))
lifecycle("in-memory", InMemoryRecordStore(hr.STATUSES))

# hand-written file in the older prose convention still reads
with tempfile.TemporaryDirectory() as d:
    store = hr.filesystem_store(Path(d))
    (Path(d) / "new").mkdir()
    (Path(d) / "new" / "old-request.md").write_text("# Old style\n\nStatus: new\n")
    rec = store.get("old-request")
    check("legacy no-frontmatter file decodes", rec is not None and rec.title == "Old style" and rec.status == "new")
    check("get refuses path tricks", store.get("../x") is None)
    claimed = hr.claim_request(store, "old-request")
    check("legacy file claimable, body kept", claimed.status == "in-progress" and "Status: new" in claimed.body)

# concurrent claim: exactly one winner
with tempfile.TemporaryDirectory() as d:
    store = hr.filesystem_store(Path(d))
    rec = hr.create_request(store, "race", "x")
    results = []

    def attempt(n):
        try:
            hr.claim_request(store, rec.id, f"c{n}")
            results.append("won")
        except RecordConflict:
            results.append("lost")

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    check("exactly one concurrent claimant wins", results.count("won") == 1 and results.count("lost") == 7)

# MCP tools
def call(tool_obj, args):
    result = asyncio.run(tool_obj.handler(args))
    return result["content"][0]["text"], bool(result.get("is_error"))


with tempfile.TemporaryDirectory() as d:
    project = Path(d) / "proj"
    project.mkdir()
    current_context.set_current_desk_directory(project)
    text, err = call(srv._create_handoff_request, {"title": "T", "what": "W", "directory": "../sibling/reqs"})
    created = json.loads(text)
    check("create tool reaches a sibling via ..", not err and (Path(d) / "sibling/reqs/new" / f"{created['id']}.md").is_file())
    text, err = call(srv._create_handoff_request, {"title": "T", "what": "W", "directory": str(Path(d) / "abs")})
    check("absolute directory refused", err and "relative" in text)
    text, err = call(srv._create_handoff_request, {"title": "", "what": "W"})
    check("empty title refused", err)
    args = {"directory": "../sibling/reqs"}
    text, err = call(srv._list_handoff_requests, {**args, "status": "new"})
    check("list tool", not err and [r["id"] for r in json.loads(text)] == [created["id"]])
    text, err = call(srv._list_handoff_requests, {**args, "status": "bogus"})
    check("list bad status errors", err)
    text, err = call(srv._claim_handoff_request, {**args, "id": created["id"], "claimed_by": "me"})
    check("claim tool", not err and json.loads(text)["status"] == "in-progress")
    text, err = call(srv._claim_handoff_request, {**args, "id": created["id"]})
    check("second claim is a tool error", err and "RecordConflict" in text)
    text, err = call(srv._complete_handoff_request, {**args, "id": created["id"], "outcome": "done", "note": "ok"})
    check("complete tool", not err and json.loads(text)["fields"]["outcome"] == "done")

    # store-agnostic: swap the factory for the in-memory store
    memory = InMemoryRecordStore(hr.STATUSES)
    saved = srv._handoff_store_factory
    srv._handoff_store_factory = lambda path: memory
    try:
        text, err = call(srv._create_handoff_request, {"title": "M", "what": "W"})
        rid = json.loads(text)["id"]
        call(srv._claim_handoff_request, {"id": rid})
        text, err = call(srv._complete_handoff_request, {"id": rid, "outcome": "declined"})
        check("tools run unchanged over a non-filesystem store", not err and memory.get(rid).status == "complete" and not list(project.iterdir()))
    finally:
        srv._handoff_store_factory = saved
    current_context.set_current_desk_directory(None)
    text, err = call(srv._list_handoff_requests, {})
    check("no current directory -> error", err)

check("tools registered", all(t in srv._TOOLS for t in (srv._create_handoff_request, srv._list_handoff_requests, srv._claim_handoff_request, srv._complete_handoff_request)))
check("tempui tag minted", "handoff request MCP tools #070658" in CURRENT_TAGS)
check("dedicated doc registered", "tempui-handoff-requests.md" in SPLIT_DOC_CONTENT)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
