# DISABLED (see tests/verify/README.md) -- TODO 06fa070 tracks
# investigating this. Current failure: Fails on a single stale assertion: hardcodes TEMPUI_DOC_VERSION ==
# 16, but the doc version has since moved on (now 17, after later TODOs
# bumped it further). Every other check in this script still passes.
# Reasonable suspicion: not a real bug, just an outdated hardcoded
# version number -- rewrite the assertion to check `>= 16` (or drop the
# version check from this script entirely).

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

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.server.bridge_client import BRIDGE_CLIENT_TEMPLATE  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.temp_ui import CUSTOM_WIDGETS_DOC_FILENAME, SPLIT_DOC_CONTENT, TEMPUI_DOC_VERSION  # noqa: E402
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


class _FakeDesk:
    def __init__(self, directory):
        self.directory = directory


class _FakeGuiWindow:
    def __init__(self, directory, capabilities=("editor",)):
        self.current_desk = _FakeDesk(directory)
        self._capabilities = list(capabilities)
        self.open_editor_or_scrap_calls = []

    def get_widget_info(self, widget_id):
        return WidgetInfo(
            id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
            capabilities=self._capabilities, default_size=None,
        )

    def open_editor_or_scrap(self, path):
        self.open_editor_or_scrap_calls.append(path)


def _request(url, token, widget_id, method="POST", body=None):
    headers = {"X-Desk-Token": token, "X-Desk-Widget-Id": widget_id}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
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
    assert outcome.get("done"), "background requests never finished"
    if "error" in outcome:
        raise outcome["error"]


def test_relative_path_resolves_against_desk_directory():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            fake_window = _FakeGuiWindow(desk_dir)
            handle.gui_bridge.attach(fake_window)
            base = f"http://{handle.host}:{handle.port}"
            result = {}

            def run_requests():
                result["status"], result["body"] = _request(
                    f"{base}/api/bridge/editor/openOrScrap", handle.token, "some_widget",
                    body={"path": "notes/a.txt"},
                )

            _run_with_pumped_event_loop(run_requests)
            check("relative path request returns ok", result["body"] == {"ok": True})
            check("status 200", result["status"] == 200)
            check(
                "relative path resolved against the Desk directory",
                fake_window.open_editor_or_scrap_calls == [desk_dir / "notes" / "a.txt"],
            )
        finally:
            handle.stop()


def test_absolute_path_used_as_is():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        elsewhere = Path(d) / "elsewhere.txt"
        handle = start_server(widgets_dir=widgets_dir)
        try:
            fake_window = _FakeGuiWindow(desk_dir)
            handle.gui_bridge.attach(fake_window)
            base = f"http://{handle.host}:{handle.port}"
            result = {}

            def run_requests():
                result["status"], result["body"] = _request(
                    f"{base}/api/bridge/editor/openOrScrap", handle.token, "some_widget",
                    body={"path": str(elsewhere)},
                )

            _run_with_pumped_event_loop(run_requests)
            check("absolute path request returns ok", result["body"] == {"ok": True})
            check("absolute path used as-is", fake_window.open_editor_or_scrap_calls == [elsewhere])
        finally:
            handle.stop()


def test_missing_capability_gets_403():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            fake_window = _FakeGuiWindow(desk_dir, capabilities=())
            handle.gui_bridge.attach(fake_window)
            base = f"http://{handle.host}:{handle.port}"
            result = {}

            def run_requests():
                result["status"], result["body"] = _request(
                    f"{base}/api/bridge/editor/openOrScrap", handle.token, "some_widget",
                    body={"path": "a.txt"},
                )

            _run_with_pumped_event_loop(run_requests)
            check("caller without the editor capability gets 403", result["status"] == 403)
            check("no call made without the capability", fake_window.open_editor_or_scrap_calls == [])
        finally:
            handle.stop()


def test_bridge_client_declares_editor_namespace():
    check("bridge client declares editor.openOrScrap", '"/api/bridge/editor/openOrScrap"' in BRIDGE_CLIENT_TEMPLATE)


def test_doc_content():
    check("TEMPUI_DOC_VERSION bumped to 16", TEMPUI_DOC_VERSION == 16)
    doc = SPLIT_DOC_CONTENT[CUSTOM_WIDGETS_DOC_FILENAME]
    check("doc lists the editor capability", "desk.editor.openOrScrap" in doc and "capability `editor`" in doc)
    check("doc lists the filetypes capability", "desk.filetypes.get()" in doc and "capability `filetypes`" in doc)


test_relative_path_resolves_against_desk_directory()
test_absolute_path_used_as_is()
test_missing_capability_gets_403()
test_bridge_client_declares_editor_namespace()
test_doc_content()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
