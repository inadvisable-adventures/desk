"""TODO 1f74c27 (Track A): the Bridge `log` capability (append/list routes,
capability gate, JS client helper) and the MCP query/list tools."""
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.server.bridge_client import BRIDGE_CLIENT_TEMPLATE, render_bridge_client  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.desk_mcp_server import _list_widget_logs, _query_widget_log  # noqa: E402
from desk.widget_logs import WidgetLogStore, format_time_iso  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402

failures = 0


def check(name, ok):
    global failures
    print(("PASS" if ok else "FAIL") + ":", name)
    failures += 0 if ok else 1


class _FakeWindow:
    def __init__(self, capabilities):
        self._capabilities = list(capabilities)

    def get_widget_info(self, widget_id):
        return WidgetInfo(
            id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
            capabilities=self._capabilities, default_size=None,
        )


def _request(method, url, token, body=None):
    headers = {"X-Desk-Token": token, "X-Desk-Widget-Id": "w", "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def pumped(fn, timeout=15):
    """The capability check hops to the GUI thread (run_on_gui), so the
    Qt loop must keep spinning while the HTTP calls run elsewhere."""
    outcome = {}

    def run():
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            outcome["error"] = e
        finally:
            outcome["done"] = True

    threading.Thread(target=run, daemon=True).start()
    deadline = time.time() + timeout
    while not outcome.get("done") and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert outcome.get("done"), "requests never finished"
    if "error" in outcome:
        raise outcome["error"]


def text_of(result):
    return result["content"][0]["text"]


def requests_phase(handle, base):
    token = handle.issue_credential("w", "inst-1")
    handle.gui_bridge.attach(_FakeWindow(["log"]))
    status, body = _request("POST", f"{base}/api/bridge/log/append", token,
                            {"name": "demo-abc", "entries": [{"s": "one", "t": 1000}, {"s": "two"}]})
    check("append 200 stored 2", status == 200 and body == {"ok": True, "stored": 2})
    status, body = _request("GET", f"{base}/api/bridge/log/list", token)
    summary = {log["name"]: log for log in body["logs"]}
    check("list shows the log", status == 200 and summary["demo-abc"]["count"] == 2 and summary["demo-abc"]["first_t"] == 1000)
    status, _ = _request("POST", f"{base}/api/bridge/log/append", token, {"name": "", "entries": [{"s": "x"}]})
    check("empty name 400", status == 400)
    status, _ = _request("POST", f"{base}/api/bridge/log/append", token, {"name": "x", "entries": [{"t": 1}]})
    check("malformed entry 422", status == 422)
    check("handle.widget_logs is the store the route wrote to", handle.widget_logs.query("demo-abc", limit=1)[0].text == "one")

    handle.gui_bridge.attach(_FakeWindow([]))
    status, _ = _request("POST", f"{base}/api/bridge/log/append", token, {"name": "n", "entries": [{"s": "x"}]})
    check("no log capability -> 403", status == 403)
    check("nothing stored without capability", all(log.name != "n" for log in handle.widget_logs.list_logs()))


with tempfile.TemporaryDirectory() as d:
    widgets_dir = Path(d) / "widgets"
    widgets_dir.mkdir()
    handle = start_server(widgets_dir=widgets_dir)
    try:
        pumped(lambda: requests_phase(handle, f"http://{handle.host}:{handle.port}"))
    finally:
        handle.stop()

check("JS client declares log.append/line", "log: {" in BRIDGE_CLIENT_TEMPLATE and "line: (name, s)" in BRIDGE_CLIENT_TEMPLATE)
check("JS log send is keepalive and returns no promise", "keepalive: true" in BRIDGE_CLIENT_TEMPLATE and "append: (name, entries) => sendLog" in BRIDGE_CLIENT_TEMPLATE)
rendered = render_bridge_client("w", "i", "t")
check("JS client template still renders", "sendLog" in rendered)
import shutil, subprocess  # noqa: E402
node = shutil.which("node")
if node:
    js_path = Path(tempfile.mkdtemp()) / "client.js"
    js_path.write_text(rendered)
    check("rendered JS client parses (node --check)", subprocess.run([node, "--check", str(js_path)]).returncode == 0)
else:
    print("SKIP: node not available for JS syntax check")

# --- MCP tools ---------------------------------------------------------
store = WidgetLogStore()
store.append("a-1", [(1_700_000_000_000 + i * 1000, f"msg{i}") for i in range(5)])
current_context.set_widget_log_store(store)
run = asyncio.run
listed = json.loads(text_of(run(_list_widget_logs.handler({}))))
check("list tool", listed[0]["name"] == "a-1" and listed[0]["count"] == 5)
base_t = 1_700_000_000_000
out = text_of(run(_query_widget_log.handler({"log_name": "a-1"}))).split("\n")
check("query all, oldest first, time<TAB>text", len(out) == 5 and out[0] == f"{format_time_iso(base_t)}\tmsg0")
out = text_of(run(_query_widget_log.handler({"log_name": "a-1", "start": base_t + 1000, "end": base_t + 3000}))).split("\n")
check("inclusive epoch-ms range", [l.split("\t")[1] for l in out] == ["msg1", "msg2", "msg3"])
iso = format_time_iso(base_t + 2000)
out = text_of(run(_query_widget_log.handler({"log_name": "a-1", "start": iso, "end": iso}))).split("\n")
check("ISO bounds", [l.split("\t")[1] for l in out] == ["msg2"])
out = text_of(run(_query_widget_log.handler({"log_name": "a-1", "limit": 2}))).split("\n")
check("limit truncates with a note", len(out) == 3 and out[0].endswith("msg0") and "more entries" in out[2])
out = text_of(run(_query_widget_log.handler({"log_name": "a-1", "limit": 2, "order": "desc"}))).split("\n")
check("desc gives newest first", out[0].endswith("msg4") and out[1].endswith("msg3"))
check("exact-limit has no truncation note", "more entries" not in text_of(run(_query_widget_log.handler({"log_name": "a-1", "limit": 5}))))
r = run(_query_widget_log.handler({"log_name": "nope"}))
check("unknown log is an error", r.get("is_error") is True)
r = run(_query_widget_log.handler({"log_name": "a-1", "start": "garbage"}))
check("bad time is an error", r.get("is_error") is True)
check("empty range message", text_of(run(_query_widget_log.handler({"log_name": "a-1", "end": 5}))) == "(no entries in range)")
r = run(_query_widget_log.handler({"log_name": "a-1", "limit": 0}))
check("bad limit is an error", r.get("is_error") is True)

sys.exit(1 if failures else 0)
