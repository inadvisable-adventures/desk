import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# TODO 78bfa41: QWebEngineWidgets must be imported before a
# QApplication is constructed -- desk.shell.window pulls in
# ChromiumWidget (and therefore QWebEngineView) transitively, so this
# import has to happen before the QApplication below even though this
# script never places a real ChromiumWidget itself.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

app = QApplication(sys.argv)

from desk.server.bridge_client import BRIDGE_CLIENT_TEMPLATE  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.shell.widget_frame import WidgetFrame  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import CUSTOM_WIDGETS_DOC_FILENAME, SPLIT_DOC_CONTENT, TEMPUI_DOC_VERSION  # noqa: E402

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


# ---------- _TitleBar / WidgetFrame label composition ----------


def test_titlebar_subtitle_composition():
    content = QWidget()
    frame = WidgetFrame("My Widget", content)
    check("bare title with no subtitle", frame._titlebar._label.text() == "My Widget")

    frame.set_subtitle("some-document.md")
    check("title + subtitle composes with an em dash", frame._titlebar._label.text() == "My Widget — some-document.md")

    frame.set_external(True)
    check(
        "title + subtitle + [EXTERNAL] compose in order",
        frame._titlebar._label.text() == "My Widget — some-document.md [EXTERNAL]",
    )

    frame.set_external(False)
    check(
        "clearing external leaves title + subtitle",
        frame._titlebar._label.text() == "My Widget — some-document.md",
    )

    frame.set_subtitle(None)
    check("None clears the subtitle back to the bare title", frame._titlebar._label.text() == "My Widget")

    frame.set_subtitle("another-document.md")
    frame.set_subtitle("")
    check("empty string also clears the subtitle", frame._titlebar._label.text() == "My Widget")


# ---------- DeskWindow.set_widget_subtitle ----------


class _FakeWindow:
    def __init__(self, frames):
        self._frames = frames

    def find_frame_by_instance_id(self, instance_id):
        for frame in self._frames:
            if frame.instance_id == instance_id:
                return frame
        return None


_FakeWindow.set_widget_subtitle = DeskWindow.set_widget_subtitle


def test_set_widget_subtitle_resolves_the_right_frame():
    frame_a = WidgetFrame("A", QWidget(), instance_id="inst-a")
    frame_b = WidgetFrame("B", QWidget(), instance_id="inst-b")
    win = _FakeWindow([frame_a, frame_b])

    win.set_widget_subtitle("inst-b", "hello")
    check("the targeted frame's titlebar updates", frame_b._titlebar._label.text() == "B — hello")
    check("an unrelated frame is left untouched", frame_a._titlebar._label.text() == "A")


def test_set_widget_subtitle_unknown_instance_is_a_silent_noop():
    win = _FakeWindow([])
    try:
        win.set_widget_subtitle("does-not-exist", "hello")
        check("unknown instance id does not raise", True)
    except Exception as e:  # noqa: BLE001
        check(f"unknown instance id does not raise (raised {e!r})", False)


# ---------- Bridge client template ----------


def test_bridge_client_declares_self_setSubtitle():
    check('bridge client declares self.setSubtitle', '"/api/bridge/self/setSubtitle"' in BRIDGE_CLIENT_TEMPLATE)
    check("setSubtitle sends text under a text key", "setSubtitle: (text)" in BRIDGE_CLIENT_TEMPLATE)


# ---------- Doc content ----------


def test_doc_content():
    check("TEMPUI_DOC_VERSION bumped to at least 30", TEMPUI_DOC_VERSION >= 30)
    doc = SPLIT_DOC_CONTENT[CUSTOM_WIDGETS_DOC_FILENAME]
    check("doc documents desk.self.setSubtitle", "desk.self.setSubtitle(text)" in doc)
    new_features_doc = SPLIT_DOC_CONTENT["tempui-new-features.md"]
    check("new-features doc has a Version 30 entry mentioning setSubtitle", "## Version 30" in new_features_doc and "setSubtitle" in new_features_doc)


# ---------- Real HTTP round trip through a real server ----------


def _request(url, token, instance_id, method="POST", body=None):
    headers = {"X-Desk-Token": token, "X-Desk-Instance-Id": instance_id}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_set_subtitle_bridge_route_end_to_end():
    """No X-Desk-Widget-Id header sent at all -- setSubtitle, like
    getLocalStorage/setLocalStorage, is gated only by
    require_instance_id, needing no capability declaration."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            frame = WidgetFrame("Doc Viewer", QWidget(), instance_id="http-inst-1")
            win = _FakeWindow([frame])
            handle.gui_bridge.attach(win)
            base = f"http://{handle.host}:{handle.port}"
            outcome = {}

            def run_request():
                try:
                    status, body = _request(
                        f"{base}/api/bridge/self/setSubtitle", handle.token, "http-inst-1",
                        body={"text": "report.pdf"},
                    )
                    outcome["status"] = status
                    outcome["body"] = body
                except Exception as e:  # noqa: BLE001
                    outcome["error"] = e
                finally:
                    outcome["done"] = True

            thread = threading.Thread(target=run_request, daemon=True)
            thread.start()
            deadline = time.time() + 10
            while not outcome.get("done") and time.time() < deadline:
                app.processEvents()
                time.sleep(0.01)
            thread.join(timeout=1)
            check("background request finished", outcome.get("done", False))
            if "error" in outcome:
                raise outcome["error"]
            check("setSubtitle route returns 200", outcome.get("status") == 200)
            check("setSubtitle route returns ok:true", outcome.get("body") == {"ok": True})
            check(
                "the real titlebar label was updated via the full HTTP round trip",
                frame._titlebar._label.text() == "Doc Viewer — report.pdf",
            )
        finally:
            handle.stop()


test_titlebar_subtitle_composition()
test_set_widget_subtitle_resolves_the_right_frame()
test_set_widget_subtitle_unknown_instance_is_a_silent_noop()
test_bridge_client_declares_self_setSubtitle()
test_doc_content()
test_set_subtitle_bridge_route_end_to_end()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
