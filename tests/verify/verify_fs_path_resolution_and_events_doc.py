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
    def __init__(self, desk_directory):
        self.current_desk = _FakeDesk(desk_directory)

    def get_widget_info(self, widget_id):
        return WidgetInfo(
            id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
            capabilities=["fs"], default_size=None, content_hash="abc123def456",
        )


def _request(url, token, widget_id, method="GET", body=None):
    headers = {"X-Desk-Token": token, "X-Desk-Widget-Id": widget_id}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8')}") from e


def _run_with_pumped_event_loop(fn, timeout=10):
    """See verify_html_widget_local_storage.py's own comment: GuiBridge
    .call needs the GUI thread's Qt event loop actually spinning to
    dispatch its queued signal, so real HTTP requests against a
    GUI-bridge-crossing route have to run on a background thread while
    this thread pumps app.processEvents() concurrently."""
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


def test_fs_relative_path_resolves_against_desk_directory():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            handle.gui_bridge.attach(_FakeGuiWindow(desk_dir))
            base = f"http://{handle.host}:{handle.port}"

            def run_requests():
                write_result = _request(
                    f"{base}/api/bridge/fs/writeFile", handle.token, "SomeWidget",
                    method="POST", body={"path": "hello.txt", "contents": "hi"},
                )
                assert write_result == {"ok": True}, write_result
                on_disk = desk_dir / "hello.txt"
                assert on_disk.is_file(), "relative writeFile did not land under the Desk's own directory"
                assert on_disk.read_text() == "hi"

                read_result = _request(
                    f"{base}/api/bridge/fs/readFile?path=hello.txt", handle.token, "SomeWidget"
                )
                assert read_result == {"contents": "hi"}, read_result

            _run_with_pumped_event_loop(run_requests)
            check("relative fs.writeFile lands under the current Desk's directory", True)
            check("relative fs.readFile reads back from the current Desk's directory", True)
        finally:
            handle.stop()


def test_fs_absolute_path_used_as_is():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        elsewhere = Path(d) / "elsewhere.txt"
        handle = start_server(widgets_dir=widgets_dir)
        try:
            handle.gui_bridge.attach(_FakeGuiWindow(desk_dir))
            base = f"http://{handle.host}:{handle.port}"

            def run_requests():
                write_result = _request(
                    f"{base}/api/bridge/fs/writeFile", handle.token, "SomeWidget",
                    method="POST", body={"path": str(elsewhere), "contents": "abs"},
                )
                assert write_result == {"ok": True}, write_result

            _run_with_pumped_event_loop(run_requests)
            check("absolute fs.writeFile path is used as-is", elsewhere.read_text() == "abs")
        finally:
            handle.stop()


def test_get_manifest_includes_directory():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            handle.gui_bridge.attach(_FakeGuiWindow(desk_dir))
            base = f"http://{handle.host}:{handle.port}"
            result = {}

            def run_requests():
                result["manifest"] = _request(f"{base}/api/bridge/self/getManifest", handle.token, "SomeWidget")

            _run_with_pumped_event_loop(run_requests)
            check("getManifest includes directory", result["manifest"]["directory"] == str(desk_dir))
            check("getManifest still includes content_hash", result["manifest"]["content_hash"] == "abc123def456")
        finally:
            handle.stop()


def test_doc_content():
    check("TEMPUI_DOC_VERSION bumped to at least 13", TEMPUI_DOC_VERSION >= 13)
    doc = SPLIT_DOC_CONTENT[CUSTOM_WIDGETS_DOC_FILENAME]
    check("getManifest bullet mentions directory field", "`directory`" in doc)
    check("events callout appears before fs bullet", doc.index("reach for `desk.events.*`\nfirst") < doc.index("desk.fs.readFile"))
    check("fs bullet documents relative-path resolution", "resolves against the current Desk's own directory" in doc)


test_fs_relative_path_resolves_against_desk_directory()
test_fs_absolute_path_used_as_is()
test_get_manifest_includes_directory()
test_doc_content()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
