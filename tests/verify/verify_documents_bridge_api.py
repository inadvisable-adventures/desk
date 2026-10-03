"""Verifies TODO `8e4711e`'s Bridge API routes (desk.documents.open/read/
close) through the real server, plus the JS client surface and the
current_context hook for python widgets."""

import base64
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

from desk.server.bridge_client import BRIDGE_CLIENT_TEMPLATE  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402
from desk_services.documents import get_service  # noqa: E402

passed = 0
failed = 0
BINARY = bytes(range(256)) * 8


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


class _FakeDesk:
    def __init__(self, directory):
        self.directory = directory


class _FakeGuiWindow:
    def __init__(self, desk_directory, capabilities):
        self.current_desk = _FakeDesk(desk_directory)
        self._capabilities = capabilities

    def get_widget_info(self, widget_id):
        return WidgetInfo(id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html", capabilities=self._capabilities, default_size=None, content_hash="abc")


def _request(url, token, widget_id, method="GET", body=None):
    headers = {"X-Desk-Token": token, "X-Desk-Widget-Id": widget_id, "X-Desk-Instance-Id": "inst-1"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def _run_with_pumped_event_loop(fn, timeout=15):
    outcome = {}

    def run():
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            outcome["error"] = e
        finally:
            outcome["done"] = True

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.time() + timeout
    while not outcome.get("done") and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    thread.join(timeout=1)
    assert outcome.get("done"), "background requests never finished"
    if "error" in outcome:
        raise outcome["error"]


def test_bridge_round_trip():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "project"
        desk_dir.mkdir()
        (desk_dir / "data.bin").write_bytes(BINARY)
        service = get_service()
        service.configure(lambda: desk_dir, lambda: desk_dir / ".desk_temp" / "documents_cache")
        handle = start_server(widgets_dir=widgets_dir)
        try:
            handle.gui_bridge.attach(_FakeGuiWindow(desk_dir, ["documents"]))
            base = f"http://{handle.host}:{handle.port}"
            results = {}

            def run():
                post = lambda path, body: _request(f"{base}/api/bridge/documents/{path}", handle.token, "W", method="POST", body=body)
                status, opened = post("open", {"path": "data.bin"})
                results["open"] = (status, opened)
                h = opened["handle"]
                results["read1"] = post("read", {"handle": h, "offset": 0, "length": 100})
                results["read_end"] = post("read", {"handle": h, "offset": 2000, "length": 500})
                results["read_default"] = post("read", {"handle": h})
                results["bad_handle"] = post("read", {"handle": "nope", "offset": 0, "length": 1})
                results["missing"] = post("open", {"path": "missing.bin"})
                results["close"] = post("close", {"handle": h})
                results["read_closed"] = post("read", {"handle": h, "offset": 0, "length": 1})
                results["close_again"] = post("close", {"handle": h})

            _run_with_pumped_event_loop(run)
            check("open returns a handle for a relative path resolved against the Desk", results["open"][0] == 200 and len(results["open"][1]["handle"]) > 0)
            status, body = results["read1"]
            check("read returns base64 raw bytes for the range", status == 200 and base64.b64decode(body["data"]) == BINARY[:100] and body["eof"] is False)
            status, body = results["read_end"]
            check("a range reaching the end reports eof", base64.b64decode(body["data"]) == BINARY[2000:] and body["eof"] is True)
            check("offset/length default sensibly (whole small file)", base64.b64decode(results["read_default"][1]["data"]) == BINARY and results["read_default"][1]["eof"] is True)
            check("an unknown handle is a 400 with a clear message", results["bad_handle"][0] == 400 and "Unknown" in results["bad_handle"][1]["detail"])
            check("opening a missing file is a 400", results["missing"][0] == 400)
            check("close reports it closed the handle, and a second close reports false", results["close"][1] == {"closed": True} and results["close_again"][1] == {"closed": False})
            check("a closed handle can't be read", results["read_closed"][0] == 400)
        finally:
            handle.stop()


def test_capability_is_required():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        (Path(d) / "x.bin").write_bytes(b"abc")
        handle = start_server(widgets_dir=widgets_dir)
        try:
            handle.gui_bridge.attach(_FakeGuiWindow(Path(d), ["fs"]))
            base = f"http://{handle.host}:{handle.port}"
            out = {}

            def run():
                out["r"] = _request(f"{base}/api/bridge/documents/open", handle.token, "W", method="POST", body={"path": str(Path(d) / "x.bin")})

            _run_with_pumped_event_loop(run)
            check("a widget without the `documents` capability is refused", out["r"][0] == 403)
        finally:
            handle.stop()


def test_client_js_and_python_hook():
    js = BRIDGE_CLIENT_TEMPLATE
    check("the JS client exposes desk.documents.open/read/close", all(s in js for s in ("documents: {", "/api/bridge/documents/open", "/api/bridge/documents/read", "/api/bridge/documents/close")))
    check("python widgets get the same service via current_context", current_context.get_documents_service() is get_service())


test_bridge_round_trip()
test_capability_is_required()
test_client_js_and_python_hook()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
