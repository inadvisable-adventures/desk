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
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.server.bridge_client import BRIDGE_CLIENT_TEMPLATE  # noqa: E402
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


class _FakeGuiWindow:
    """Simulates DeskWindow.run_transform -- with a deliberately delayed
    (QTimer, not immediate) resolution, the same shape a real
    TypeScript/JavaScript transform's background-thread completion
    actually has, to prove the route's run_on_gui_async plumbing
    genuinely waits for a later callback rather than only working by
    accident for an immediately-resolving one."""

    def __init__(self, capabilities=("transforms",)) -> None:
        self._capabilities = list(capabilities)
        self.run_transform_calls = []

    def get_widget_info(self, widget_id):
        return WidgetInfo(
            id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
            capabilities=self._capabilities, default_size=None,
        )

    def run_transform(self, transform_id, input_data, config, on_result):
        self.run_transform_calls.append((transform_id, input_data, config))
        if transform_id == "does_not_exist":
            QTimer.singleShot(50, lambda: on_result(None, "Unknown transform"))
            return
        QTimer.singleShot(50, lambda: on_result(input_data.upper(), None))


def _request(url, token, widget_id, body):
    headers = {"X-Desk-Token": token, "X-Desk-Widget-Id": widget_id, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _run_with_pumped_event_loop(fn, timeout=10):
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
    assert outcome.get("done"), "background request never finished"
    if "error" in outcome:
        raise outcome["error"]


def test_run_resolves_via_a_delayed_callback():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            fake_window = _FakeGuiWindow()
            handle.gui_bridge.attach(fake_window)
            base = f"http://{handle.host}:{handle.port}"
            result = {}

            def run_requests():
                result["status"], result["body"] = _request(
                    f"{base}/api/bridge/transforms/run", handle.token, "some_widget",
                    body={"transform_id": "my_transform", "input": "hello", "config": None},
                )

            _run_with_pumped_event_loop(run_requests)
            check("status 200", result["status"] == 200)
            check("delayed on_result's output reaches the HTTP response", result["body"] == {"output": "HELLO", "error": None})
            check(
                "DeskWindow.run_transform was called with the request's own fields",
                fake_window.run_transform_calls == [("my_transform", "hello", None)],
            )
        finally:
            handle.stop()


def test_run_error_surfaces_in_the_response_not_as_an_http_error():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            fake_window = _FakeGuiWindow()
            handle.gui_bridge.attach(fake_window)
            base = f"http://{handle.host}:{handle.port}"
            result = {}

            def run_requests():
                result["status"], result["body"] = _request(
                    f"{base}/api/bridge/transforms/run", handle.token, "some_widget",
                    body={"transform_id": "does_not_exist", "input": "x", "config": None},
                )

            _run_with_pumped_event_loop(run_requests)
            check("status still 200 (the failure is in the body, not an HTTP error)", result["status"] == 200)
            check("the error message reaches the HTTP response", result["body"] == {"output": None, "error": "Unknown transform"})
        finally:
            handle.stop()


def test_missing_capability_gets_403():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            fake_window = _FakeGuiWindow(capabilities=())
            handle.gui_bridge.attach(fake_window)
            base = f"http://{handle.host}:{handle.port}"
            result = {}

            def run_requests():
                result["status"], result["body"] = _request(
                    f"{base}/api/bridge/transforms/run", handle.token, "some_widget",
                    body={"transform_id": "my_transform", "input": "x", "config": None},
                )

            _run_with_pumped_event_loop(run_requests)
            check("caller without the transforms capability gets 403", result["status"] == 403)
            check("no call made without the capability", fake_window.run_transform_calls == [])
        finally:
            handle.stop()


def test_bridge_client_declares_transforms_namespace():
    check(
        "bridge client declares transforms.run",
        '"/api/bridge/transforms/run"' in BRIDGE_CLIENT_TEMPLATE and "transforms:" in BRIDGE_CLIENT_TEMPLATE,
    )


test_run_resolves_via_a_delayed_callback()
test_run_error_surfaces_in_the_response_not_as_an_http_error()
test_missing_capability_gets_403()
test_bridge_client_declares_transforms_namespace()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
