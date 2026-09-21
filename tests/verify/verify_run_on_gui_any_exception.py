"""TODO b89cf17: run_on_gui/run_on_gui_async turn *any* GUI-thread
exception into an error response carrying its type and message."""
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

from desk.server.runner import start_server  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402

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


class _Boom(Exception):
    pass


class _FakeGuiWindow:
    @property
    def current_desk(self):
        raise _Boom("widget crashed")

    def get_widget_info(self, widget_id):
        return WidgetInfo(
            id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
            capabilities=["fs", "transforms"], default_size=None, content_hash="abc123def456",
        )

    def run_transform(self, *args, **kwargs):
        raise _Boom("async starter crashed")


def _post(url, token, body):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"X-Desk-Token": token, "X-Desk-Widget-Id": "W", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _pumped(fn, timeout=10):
    out = {}

    def run():
        try:
            out["result"] = fn()
        finally:
            out["done"] = True

    threading.Thread(target=run, daemon=True).start()
    deadline = time.time() + timeout
    while not out.get("done") and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert out.get("done"), "request never finished"
    return out["result"]


with tempfile.TemporaryDirectory() as d:
    handle = start_server(widgets_dir=Path(d))
    try:
        handle.gui_bridge.attach(_FakeGuiWindow())
        base = f"http://{handle.host}:{handle.port}"
        status, body = _pumped(lambda: _post(
            f"{base}/api/bridge/fs/writeFile", handle.token, {"path": "x.txt", "contents": "hi"}))
        check("sync: arbitrary exception -> 500", status == 500)
        check("sync: body carries type and message", "_Boom: widget crashed" in body)
        status, body = _pumped(lambda: _post(
            f"{base}/api/bridge/transforms/run", handle.token,
            {"transform_id": "t", "input": "", "config": {}}))
        check("async: arbitrary exception -> 500", status == 500)
        check("async: body carries type and message", "_Boom: async starter crashed" in body)
    finally:
        handle.stop()

print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
