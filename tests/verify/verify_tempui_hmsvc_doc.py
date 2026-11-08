"""TODO 879bfb4: tempui-hmsvc.md documents what hmsvc authoring needs (see plans/tempui-hmsvc-doc.md)."""
import re
import sys

sys.path.insert(0, "src")

from desk.temp_ui import (  # noqa: E402
    CURRENT_TAGS, HMSVC_DOC_FILENAME, SPLIT_DOC_CONTENT, _CUSTOM_WIDGETS_DOC, _NEW_FEATURES, _PORTING_DOC,
)
import desk.hmsvc as hmsvc  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


doc = SPLIT_DOC_CONTENT[HMSVC_DOC_FILENAME]
tag = next(t for t in CURRENT_TAGS if "dedicated hmsvc doc" in t)
check("registered in SPLIT_DOC_CONTENT", HMSVC_DOC_FILENAME == "tempui-hmsvc.md")
check("changelog entry exists for its tag", tag in _NEW_FEATURES and "tempui-hmsvc.md" in _NEW_FEATURES[tag])
for key in ("description", "autostart", "external", "capabilities", "venv", "python"):
    check(f"documents service.json key {key!r}", f"- `{key}`" in doc)
check("documents module-level `app`", "module-level ASGI" in doc and "uvicorn" in doc)
check("documents Rescan and the live watcher", "Rescan" in doc and "watches `desk_hmsvc/` live" in doc and "New\nmicroservice available" in doc)
check("documents management-only networking", "management only" in doc and "fetch()" in doc)
check("documents CORS + preflight", "CORS is mandatory" in doc and "OPTIONS" in doc)
check("log cap in doc matches code", f"{hmsvc.LOG_LINE_LIMIT} lines" in doc)
check("startup timeout in doc matches code", f"{int(hmsvc.STARTUP_TIMEOUT_SECONDS)} seconds" in doc)
check("default capabilities in doc match code", '["state", "events"]' in doc and hmsvc.DEFAULT_CAPABILITIES == ("state", "events"))
check("documents every list() field", all(f in doc for f in ("lan_url", "started_at", "exit_code", "autostart")))
check("custom-widgets doc and porting doc link to it", "tempui-hmsvc.md" in _CUSTOM_WIDGETS_DOC and "tempui-hmsvc.md" in _PORTING_DOC)

# the worked example is runnable
match = re.search(r"`desk_hmsvc/hello/service.py`.*?```python\n(.*?)```", doc, re.S)
check("worked example present", match is not None)
ns = {}
exec(match.group(1), ns)
import asyncio  # noqa: E402

sent = []


async def run(method):
    async def send(m):
        sent.append(m)

    async def receive():
        return {}

    await ns["app"]({"type": "http", "method": method, "path": "/x"}, receive, send)


asyncio.run(run("GET"))
check("example answers GET 200 with CORS", sent[0]["status"] == 200 and (b"access-control-allow-origin", b"*") in sent[0]["headers"])
sent.clear()
asyncio.run(run("OPTIONS"))
check("example answers preflight 204", sent[0]["status"] == 204)

from desk.temp_ui import DOC_TEMPLATE  # noqa: E402

nav_tag = next(t for t in CURRENT_TAGS if "check new-features doc" in t)
check("TODO 601dae5: overview has the thin-doc navigation rule", "too thinly to act on" in DOC_TEMPLATE and "FEEDBACK file" in DOC_TEMPLATE)
check("TODO 601dae5: changelog entry for the rule", nav_tag in _NEW_FEATURES)
dev = open("development-process.md").read()
check("TODO 601dae5: process doc has the dedicated-doc policy", "Give agent-visible features a real doc" in dev and "SPLIT_DOC_CONTENT" in dev)

# TODO 650713d: the doc's JS examples run against the REAL route's response shapes
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import urllib.request  # noqa: E402
from pathlib import Path  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication  # noqa: E402

qt_app = QApplication.instance() or QApplication(sys.argv)
from desk.server.runner import start_server  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402


class _Window:
    def get_widget_info(self, widget_id):
        return WidgetInfo(id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
                          capabilities=["hmsvc"], default_size=None)


def _get(url, token):
    req = urllib.request.Request(url, headers={"X-Desk-Token": token, "X-Desk-Widget-Id": "w", "X-Desk-Instance-Id": "i"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


with tempfile.TemporaryDirectory() as wd:
    handle = start_server(widgets_dir=Path(wd))
    try:
        handle.gui_bridge.attach(_Window())
        token = handle.issue_credential("w", "i")
        base = f"http://{handle.host}:{handle.port}/api/bridge/hmsvc"
        got = {}

        def fetch_all():
            got["list"] = _get(base + "/list", token)
            got["logs"] = _get(base + "/logs?name=nope", token)

        t = threading.Thread(target=fetch_all, daemon=True)
        t.start()
        end = time.time() + 10
        while t.is_alive() and time.time() < end:
            qt_app.processEvents()
            time.sleep(0.01)
        check("real list route resolves to an object with `services`", isinstance(got.get("list"), dict) and isinstance(got["list"].get("services"), list))
        check("real logs route resolves to an object with `lines`", isinstance(got.get("logs"), dict) and isinstance(got["logs"].get("lines"), list))
    finally:
        handle.stop()

check("doc states list() resolves to {services}", "`{ services: [...] }`" in doc and "not a bare array" in doc)
check("doc states logs() -> {lines} and start/stop/restart -> {ok, message}", "`{ lines: [...] }`" in doc and "`{ ok, message }`" in doc)
check("doc points URL-only widgets at desk.state before the hmsvc walkthrough",
      doc.index("Only need a service's URL?") < doc.index("calls `await desk.hmsvc.list()`"))
blocks = re.findall(r"```js\n(.*?)```", doc, re.S)
check("doc has the JS examples", any("desk.hmsvc.list()" in b for b in blocks) and any("desk.state.get" in b for b in blocks))
if shutil.which("node") and "list" in got:
    stub = (
        "const desk = {hmsvc: {list: async () => (%s)}, events: {subscribe: async () => ({})}, state: {get: async () => ({value: {status: 'running', url: 'http://x/'}})}};\n"
        "const fetch = async () => ({json: async () => ({})});\n" % json.dumps(got["list"])
    )
    for block in blocks:
        if "desk.hmsvc.list()" in block or "desk.state.get(\"desk.hmsvc.hello\")" in block:
            r = subprocess.run(["node", "-e", f"(async () => {{ {stub} {block} }})().catch(e => {{ console.error(e.message); process.exit(1); }})"],
                               capture_output=True, text=True)
            check(f"doc JS example runs against real response shapes: {block.strip().splitlines()[0][:50]}", r.returncode == 0)
            if r.returncode:
                print(r.stderr)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
