"""TODO b9689cd: desk.recorder / desk.transcripts Bridge routes (capabilities `recorder`, `transcripts`)."""
import json
import os
import shutil
import subprocess
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
sys.path.insert(0, str(REPO_ROOT / "tests" / "verify"))

from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401  (must precede QApplication)
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk import transcript_pool as pool  # noqa: E402
from desk.server.bridge_client import render_bridge_client  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402
from _recorder_fake import FakeRecorder  # noqa: E402

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

    def get_widget_info(self, widget_id):
        return WidgetInfo(id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
                          capabilities=self._caps, default_size=None)


def request(handle, method, path, body=None, widget_id="w"):
    headers = {"X-Desk-Token": handle.issue_credential(widget_id, "inst-1"), "X-Desk-Widget-Id": widget_id,
               "X-Desk-Instance-Id": "inst-1", "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://{handle.host}:{handle.port}{path}", data=data, headers=headers, method=method)
    out = {}

    def run():
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                out["r"] = (r.status, json.loads(r.read().decode()))
        except urllib.error.HTTPError as e:
            out["r"] = (e.code, json.loads(e.read().decode()))

    t = threading.Thread(target=run, daemon=True)
    t.start()
    end = time.time() + 30
    while "r" not in out and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    return out["r"]


tmp = tempfile.mkdtemp()
wd = Path(tmp) / "widgets"
wd.mkdir()
desk_dir = Path(tmp) / "desk"
desk_dir.mkdir()
handle = start_server(widgets_dir=wd)
fake_window = FakeWindow(["recorder", "transcripts"])
handle.gui_bridge.attach(fake_window)
fake = FakeRecorder()
svc = handle.recorder_service
svc._launcher = fake.launch
svc._app_locator = lambda: Path("/fake/DeskRecorder.app")
svc.configure(lambda: desk_dir, handle.widget_logs)
try:
    status, body = request(handle, "GET", "/api/bridge/recorder/status")
    check("status works before the app runs", status == 200 and body["connected"] is False and set(body["features"]) == {"transcribe", "screen", "camera", "audio"})

    status, body = request(handle, "POST", "/api/bridge/recorder/start", {"feature": "transcribe", "wait": 5})
    check("start transcribe -> running", status == 200 and body["state"] == "running")
    session = body["session"]
    status, body = request(handle, "POST", "/api/bridge/recorder/start", {"feature": "screen", "target": "screen", "wait": 5})
    check("start screen alongside", status == 200 and body["state"] == "running")
    status, body = request(handle, "GET", "/api/bridge/recorder/status")
    check("status shows both running, camera idle", body["features"]["transcribe"]["state"] == "running"
          and body["features"]["screen"]["state"] == "running" and body["features"]["camera"]["state"] == "idle")
    status, body = request(handle, "POST", "/api/bridge/recorder/start", {"feature": "bogus"})
    check("unknown feature -> 400", status == 400 and "Unknown feature" in body["detail"])
    status, body = request(handle, "POST", "/api/bridge/recorder/stop", {"feature": "screen"})
    check("stop screen", status == 200)
    status, body = request(handle, "GET", "/api/bridge/recorder/sources")
    check("sources", status == 200 and body["sources"]["camera"] == ["FaceTime HD Camera"])

    # transcripts
    end = time.time() + 5
    while time.time() < end and not pool.read_collapsed(pool.pool_dir(desk_dir), session):
        time.sleep(0.05)
    status, body = request(handle, "GET", "/api/bridge/transcripts/list")
    check("transcripts/list shows the session", status == 200 and [s["session"] for s in body["sessions"]] == [session])
    status, body = request(handle, "GET", f"/api/bridge/transcripts/read?session={session}")
    check("transcripts/read returns raw records and an offset", status == 200 and body["segments"][0]["text"] == "hello desk" and body["next_offset"] > 0)
    off = body["next_offset"]
    pool.append_segment(pool.pool_dir(desk_dir), pool.Segment(session, 1, 3000, 3500, "next", False))
    pool.append_segment(pool.pool_dir(desk_dir), pool.Segment(session, 1, 3000, 3600, "next one", True))
    status, body = request(handle, "GET", f"/api/bridge/transcripts/read?session={session}&offset={off}")
    check("tailing from the offset returns only new records", [s["text"] for s in body["segments"]] == ["next", "next one"])
    status, body = request(handle, "GET", f"/api/bridge/transcripts/read?session={session}&collapsed=true")
    check("collapsed read returns the latest per seq", [s["text"] for s in body["segments"]] == ["hello desk", "next one"])
    status, body = request(handle, "GET", "/api/bridge/transcripts/read?session=../x")
    check("traversal session id -> 400", status == 400)
    status, body = request(handle, "GET", "/api/bridge/transcripts/read?session=rec-0-none")
    check("unknown session -> empty, not an error", status == 200 and body["segments"] == [])

    # capability separation
    fake_window._caps = ["transcripts"]
    status, body = request(handle, "GET", "/api/bridge/recorder/status")
    check("recorder routes need the recorder capability", status == 403 and "recorder" in body["detail"])
    status, body = request(handle, "GET", "/api/bridge/transcripts/list")
    check("transcripts-only widget can read", status == 200)
    fake_window._caps = ["recorder"]
    status, body = request(handle, "GET", "/api/bridge/transcripts/list")
    check("transcripts routes need the transcripts capability", status == 403 and "transcripts" in body["detail"])
    status, body = request(handle, "POST", "/api/bridge/recorder/stop", {"feature": "transcribe"})
    check("recorder-only widget can control", status == 200)

    # no app installed -> a clean 400
    fake.die()
    svc._app_locator = lambda: None
    time.sleep(0.3)
    status, body = request(handle, "POST", "/api/bridge/recorder/start", {"feature": "camera"})
    check("app not installed -> 400 with the build hint", status == 400 and "build_desk_recorder_app.sh" in body["detail"])
finally:
    handle.stop()
    shutil.rmtree(tmp, ignore_errors=True)

# --- the client ---
js = render_bridge_client("w", "inst", "tok")
check("client exposes desk.recorder", "recorder: {" in js and "/api/bridge/recorder/start" in js and "/api/bridge/recorder/sources" in js)
check("client exposes desk.transcripts", "transcripts: {" in js and "/api/bridge/transcripts/read" in js)
node = shutil.which("node")
if node:
    script = f"const window = {{}}; const document = {{}}; {js}\n" + (
        "const d = window.desk || globalThis.desk;"
        "console.log(typeof d.recorder.start, typeof d.recorder.stop, typeof d.recorder.status, typeof d.recorder.sources,"
        " typeof d.transcripts.list, typeof d.transcripts.read);"
    )
    r = subprocess.run([node, "-e", script], capture_output=True, text=True)
    check("the rendered client is valid JS with the new functions", "function function function function function function" in r.stdout or r.returncode == 0 and "function" in r.stdout)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
