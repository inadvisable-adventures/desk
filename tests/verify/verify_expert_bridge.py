"""TODO b2e031d: the Bridge `experts` capability -- an hmsvc registers as an expert, polls, accepts and answers.
Real Local Web Server + a real throwaway PostgreSQL cluster; the service identity is exercised through the
real `desk.hmsvc_client.DeskClient`."""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk import expert_registry as er  # noqa: E402
from desk import temp_ui  # noqa: E402
from desk.hmsvc_client import DeskClient, DeskError  # noqa: E402
from desk.server.runner import running_server  # noqa: E402

passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


if er.find_pg_bin() is None:
    print("SKIP: no PostgreSQL installation found")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0)


def in_thread(fn):
    box = {}

    def run():
        try:
            box["value"] = fn()
        except Exception as e:  # noqa: BLE001
            box["error"] = e

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 40
    while thread.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    if "error" in box:
        raise box["error"]
    return box.get("value")


def denied(fn):
    try:
        in_thread(fn)
    except DeskError as e:
        return str(e)[:3]
    return "allowed"


root = Path(tempfile.mkdtemp(prefix="pgb", dir="/tmp"))  # short: unix socket paths are length-limited
reg = er.ExpertRegistry(root / "pgdata")
er.set_registry(reg)
try:
    with tempfile.TemporaryDirectory() as tmp, running_server() as handle:
        project = Path(tmp)
        for name, caps in (("oracle", ["experts"]), ("nocap", ["state"]), ("other", ["experts"])):
            d = project / "desk_hmsvc" / name
            d.mkdir(parents=True)
            (d / "service.py").write_text("async def app(scope, receive, send):\n    pass\n")
            (d / "service.json").write_text(json.dumps({"capabilities": caps}))
        handle.hmsvc_manager.set_directory(project)

        def client(name):
            return DeskClient(url=f"http://{handle.host}:{handle.port}", token=handle.credentials.issue_service(name), name=name)

        oracle, other, nocap = client("oracle"), client("other"), client("nocap")

        e = in_thread(lambda: oracle.experts_register("oracle", "The oracle", "knows things"))
        check("a service registers itself as an expert of kind hmsvc", e["kind"] == "hmsvc" and e["registered_by"] == "hmsvc:oracle")
        check("the registry has it", any(x["expert_id"] == "oracle" for x in reg.list_experts()))
        check("a service lacking the capability gets 403", denied(lambda: nocap.experts_register("x", "x")) == "403")
        check("another service cannot overwrite it", denied(lambda: other.experts_register("oracle", "Mine")) == "400")
        check("the built-in user expert cannot be claimed", denied(lambda: oracle.experts_register("user", "x")) == "400")

        q = reg.ask("oracle", "What is the answer?", "agent", "private note to self")
        pending = in_thread(lambda: oracle.experts_pending("oracle"))
        check("pending lists the open question without the note", [x["question_id"] for x in pending] == [q["question_id"]]
              and "note_to_self" not in json.dumps(pending))
        check("a service cannot read another's experts", denied(lambda: other.experts_pending("oracle")) == "403")
        check("unknown expert is a 400", denied(lambda: oracle.experts_pending("ghost")) == "400")

        acc = in_thread(lambda: oracle.experts_accept(q["question_id"]))
        check("accept claims it for the service", acc["status"] == "accepted" and acc["accepted_by"] == "hmsvc:oracle")
        check("it no longer shows as pending", in_thread(lambda: oracle.experts_pending("oracle")) == [])
        check("another service cannot answer it", denied(lambda: other.experts_answer(q["question_id"], "no")) == "403")
        ans = in_thread(lambda: oracle.experts_answer(q["question_id"], "42"))
        check("answer is recorded as the service's", ans["status"] == "answered" and ans["answer"] == "42" and ans["answered_by"] == "hmsvc:oracle")
        check("answering twice is a 400", denied(lambda: oracle.experts_answer(q["question_id"], "again")) == "400")
        check("the asker sees it and still has the note", reg.get_question(q["question_id"], True)["note_to_self"] == "private note to self")

        # an html widget instance (no `experts` capability) is turned away
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            f"http://{handle.host}:{handle.port}/api/bridge/experts/pending?expert_id=oracle",
            headers={"X-Desk-Token": handle.credentials.issue("filetype_registry_editor", "inst-1"), "X-Desk-Widget-Id": "filetype_registry_editor", "X-Desk-Instance-Id": "inst-1"},
        )
        try:
            in_thread(lambda: urllib.request.urlopen(req, timeout=10))
            code = "allowed"
        except urllib.error.HTTPError as err:
            code = err.code
        check("an html widget without the capability gets 403", code == 403)
finally:
    er.set_registry(None)
    reg.stop()
    shutil.rmtree(root, ignore_errors=True)

tag = "hmsvc experts capability: answer questions #598971"
check("changelog tag current, with an entry", tag in temp_ui.CURRENT_TAGS and tag in temp_ui._NEW_FEATURES)
doc = temp_ui.SPLIT_DOC_CONTENT["tempui-experts.md"]
check("the experts doc names the client calls", all(n in doc for n in ("experts_register", "experts_pending", "experts_accept", "experts_answer")))
check("the hmsvc doc lists the experts capability", "`experts`" in temp_ui.SPLIT_DOC_CONTENT["tempui-hmsvc.md"])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
