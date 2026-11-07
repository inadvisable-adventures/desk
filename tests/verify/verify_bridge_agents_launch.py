"""TODO 507b8d5: desk.agents.launch (capability `launch_agent`)."""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401  (must precede QApplication)
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.server.bridge_client import BRIDGE_CLIENT_TEMPLATE  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.window import CLAUDE_DESK_WIDGET_ID, DeskWindow  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


class FakeWindow:
    def __init__(self, capabilities):
        self._caps = list(capabilities)
        self.calls = []

    def get_widget_info(self, widget_id):
        return WidgetInfo(id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
                          capabilities=self._caps, default_size=None)

    def launch_agent(self, instructions, source_instance_id, pos):
        self.calls.append((instructions, source_instance_id, pos))
        if instructions == "boom":
            raise ValueError("The Claude (Desk) widget isn't available in this Desk.")
        return "new-instance"


def post(url, token, widget_id, instance_id, body):
    headers = {"X-Desk-Token": token, "X-Desk-Widget-Id": widget_id, "X-Desk-Instance-Id": instance_id,
               "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def pumped(fn, timeout=10):
    out = {}

    def run():
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            out["error"] = e
        finally:
            out["done"] = True

    threading.Thread(target=run, daemon=True).start()
    end = time.time() + timeout
    while not out.get("done") and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    assert out.get("done"), "request never finished"
    if "error" in out:
        raise out["error"]


def serve(caps):
    d = tempfile.TemporaryDirectory()
    wd = Path(d.name) / "widgets"
    wd.mkdir()
    handle = start_server(widgets_dir=wd)
    fake = FakeWindow(caps)
    handle.gui_bridge.attach(fake)
    return d, handle, fake


def call(handle, body, widget_id="w"):
    res = {}
    url = f"http://{handle.host}:{handle.port}/api/bridge/agents/launch"
    pumped(lambda: res.update(zip(("status", "body"), post(
        url, handle.issue_credential(widget_id, "inst-9"), widget_id, "inst-9", body))))
    return res["status"], res["body"]


# --- the route ---
d, handle, fake = serve(["launch_agent"])
try:
    status, body = call(handle, {"instructions": "discuss Q and A"})
    check("200 with the new instance id", status == 200 and body == {"instance_id": "new-instance"})
    check("instructions + caller instance id reach DeskWindow.launch_agent, no pos",
          fake.calls == [("discuss Q and A", "inst-9", None)])
    status, body = call(handle, {"instructions": "x", "x": 10.5, "y": 20})
    check("x/y forwarded as pos", fake.calls[-1][2] == (10.5, 20.0))
    status, body = call(handle, {"instructions": "x", "x": 10})
    check("only one coordinate -> default placement", fake.calls[-1][2] is None)
    n = len(fake.calls)
    status, body = call(handle, {"instructions": "   "})
    check("blank instructions -> 400, window not called", status == 400 and len(fake.calls) == n)
    status, body = call(handle, {})
    check("missing instructions -> 422", status == 422)
    status, body = call(handle, {"instructions": "boom"})
    check("window ValueError -> 400 with its message", status == 400 and "isn't available" in body["detail"])
finally:
    handle.stop()
    d.cleanup()

d, handle, fake = serve(["widgets"])
try:
    status, body = call(handle, {"instructions": "hi"})
    check("without launch_agent capability -> 403", status == 403 and "launch_agent" in body["detail"] and not fake.calls)
finally:
    handle.stop()
    d.cleanup()

# --- the client ---
check("client exposes desk.agents.launch", "agents: {" in BRIDGE_CLIENT_TEMPLATE
      and "/api/bridge/agents/launch" in BRIDGE_CLIENT_TEMPLATE)

# --- the real DeskWindow.launch_agent, unbound against a stub ---
with tempfile.TemporaryDirectory() as td:
    placed = {}
    frame_proxy = SimpleNamespace(sceneBoundingRect=lambda: SimpleNamespace(right=lambda: 300.0, top=lambda: 40.0))
    stub = SimpleNamespace(
        _widgets={CLAUDE_DESK_WIDGET_ID: SimpleNamespace(default_size=(500, 400))},
        find_frame_by_instance_id=lambda i: SimpleNamespace(graphicsProxyWidget=lambda: frame_proxy) if i == "src" else None,
        view=SimpleNamespace(
            mapToScene=lambda p: SimpleNamespace(x=lambda: 1.0, y=lambda: 2.0),
            viewport=lambda: SimpleNamespace(rect=lambda: SimpleNamespace(center=lambda: None)),
        ),
    )
    stub._write_claude_instructions_file = lambda body, prefix: DeskWindow._write_claude_instructions_file(stub, body, prefix)

    def fake_place(widget_id, widget, pos, size, **kw):
        placed.update(widget_id=widget_id, pos=pos, size=size, **kw)
        return SimpleNamespace(instance_id="abc")

    stub._place_widget = fake_place
    previous = current_context.get_current_desk_directory()
    current_context.set_current_desk_directory(Path(td))
    try:
        iid = DeskWindow.launch_agent(stub, "Q: why?\nA: because", "src", None)
        extra = placed["claude_extra_instructions"]
        written = next(Path(td, ".desk_temp").glob("launch-instructions-*.md"))
        check("returns the placed instance id", iid == "abc" and placed["widget_id"] == CLAUDE_DESK_WIDGET_ID)
        check("placed right of the calling frame", placed["pos"] == (324.0, 40.0))
        check("instructions written verbatim to a launch-instructions file",
              written.read_text() == "Q: why?\nA: because" and str(written) in extra)
        DeskWindow.launch_agent(stub, "z", "gone", None)
        check("unknown caller frame -> viewport center", placed["pos"] == (1.0, 2.0))
        DeskWindow.launch_agent(stub, "z", "src", (5.0, 6.0))
        check("explicit pos wins", placed["pos"] == (5.0, 6.0))
        stub._widgets = {}
        try:
            DeskWindow.launch_agent(stub, "z", None, None)
            check("missing claude_desk widget raises ValueError", False)
        except ValueError:
            check("missing claude_desk widget raises ValueError", True)
    finally:
        if previous is not None:
            current_context.set_current_desk_directory(previous)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
