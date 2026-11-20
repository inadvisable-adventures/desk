"""TODO b9689cd: RecorderService driving a fake DeskRecorder over a real Unix socket."""
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from desk import recorder_protocol as proto  # noqa: E402
from desk import transcript_pool as pool  # noqa: E402
from desk.recorder_service import RecorderError, RecorderService, TRANSCRIPT_LOG_NAME  # noqa: E402
from desk.widget_logs import WidgetLogStore  # noqa: E402
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


def wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


with tempfile.TemporaryDirectory() as tmp:
    desk_dir = Path(tmp)
    logs = WidgetLogStore()
    fake = FakeRecorder()
    service = RecorderService(launcher=fake.launch, app_locator=lambda: Path("/fake/DeskRecorder.app"))
    service.configure(lambda: desk_dir, logs)

    check("not connected before first use", not service.status()["connected"])
    try:
        RecorderService(app_locator=lambda: None).ensure_running()
        check("missing app raises", False)
    except RecorderError as e:
        check("missing app raises a helpful error", "scripts/build_desk_recorder_app.sh" in str(e))
    try:
        RecorderService().stop("bogus")
        check("unknown feature raises", False)
    except RecorderError:
        check("unknown feature raises", True)

    changes = []
    service.add_listener(lambda: changes.append(1))
    result = service.start("transcribe", wait=3)
    check("start transcribe starts the app and reaches running", result["state"] == "running")
    check("app is connected", service.status()["connected"])
    check("listener was notified", len(changes) > 0)
    session = result["session"]
    check("a session id was assigned", bool(session) and pool.valid_session_id(session))
    check("fake wrote a segment into the real pool dir", wait_for(lambda: pool.read_collapsed(service.pool_dir(), session)))
    check("pool segment text is readable", pool.read_collapsed(service.pool_dir(), session)[0].text == "hello desk")
    check("final was mirrored into the widget log", wait_for(lambda: [e.text for e in logs.query(TRANSCRIPT_LOG_NAME)] == ["hello desk"]))
    check("the mirrored entry uses the segment start time", logs.query(TRANSCRIPT_LOG_NAME)[0].t == 1000)
    check("the transcribe command carried the pool dir", fake.received[0].fields == (session, str(service.pool_dir())))

    s = service.start("screen", target="window:Desk%20x", wait=3)
    check("screen starts while transcribe keeps running", s["state"] == "running" and service.feature_status("transcribe")["state"] == "running")
    check("camera was untouched", service.feature_status("camera")["state"] == "idle")
    check("screen got a path under .desk_temp/recordings", ".desk_temp/recordings/screen-" in s["path"] and s["path"].endswith(".mp4"))
    check("screen command carried the target and path", fake.received[-1].name == "start-screen" and fake.received[-1].fields[0] == "window:Desk%20x")
    check("starting a running feature is a no-op", service.start("screen")["state"] == "running" and len([m for m in fake.received if m.name == "start-screen"]) == 1)

    st = service.stop("screen")
    check("stop reports stopping or idle", st["state"] in ("stopping", "idle"))
    check("screen returns to idle with its file path", wait_for(lambda: service.feature_status("screen")["state"] == "idle" and service.feature_status("screen")["path"] == "/some/file.mp4"))
    check("transcribe was unaffected by stopping screen", service.feature_status("transcribe")["state"] == "running")
    service.stop("transcribe")
    check("transcribe stops independently", wait_for(lambda: service.feature_status("transcribe")["state"] == "idle"))
    check("stopping an idle feature is harmless", service.stop("camera")["state"] == "idle")

    sources = service.request_sources()
    check("sources are returned", sources == {"window": ["Desk - project"], "camera": ["FaceTime HD Camera"]})

    st = service.status()
    check("status shows a fresh heartbeat", st["heartbeat_age_seconds"] is not None and not st["stale"])
    check("status lists all three features", set(st["features"]) == {"transcribe", "screen", "camera"})

    # --- died app ---
    service.start("camera", wait=3)
    fake.die()
    check("app death is noticed", wait_for(lambda: not service.status()["connected"]))
    check("a running feature becomes disconnected", service.feature_status("camera")["state"] == "disconnected")
    check("an idle feature stays idle", service.feature_status("screen")["state"] == "idle")
    try:
        service._send("status")
        check("sending to a dead app raises", False)
    except RecorderError:
        check("sending to a dead app raises", True)

    # --- restart after death, and per-feature failures ---
    fake2 = FakeRecorder(deny={"screen"}, fail={"camera"})
    service._launcher = fake2.launch
    r = service.start("screen", wait=3)
    check("a denied permission reports denied", r["state"] == "denied" and "denied" in r["detail"])
    check("the app was restarted after dying", service.status()["connected"])
    c = service.start("camera", wait=3)
    check("a failing feature reports error with its reason", c["state"] == "error" and c["detail"] == "no such device")
    t = service.start("transcribe", wait=3)
    check("the other feature still runs after a denial and an error", t["state"] == "running")
    check("a denied feature can be retried", service.start("screen", wait=3)["state"] == "denied" and len([m for m in fake2.received if m.name == "start-screen"]) == 2)

    # --- stale heartbeat ---
    fake3 = FakeRecorder(heartbeat=False)
    s3 = RecorderService(launcher=fake3.launch, app_locator=lambda: Path("/fake"))
    s3.configure(lambda: desk_dir, None)
    s3.ensure_running()
    check("a non-beating app is not stale right away", not s3.status()["stale"])
    s3._last_heartbeat = time.monotonic() - 60
    check("a long-silent app is reported stale", s3.status()["stale"])
    s3.shutdown()
    check("shutdown sends quit", wait_for(lambda: any(m.name == "quit" for m in fake3.received)))
    fake2.die()
    service.shutdown()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
