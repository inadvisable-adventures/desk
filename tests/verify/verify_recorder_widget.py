"""TODO b9689cd: the Recorder widget (widgets/recorder/) against a fake DeskRecorder."""
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "verify"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QComboBox, QLabel  # noqa: E402

app = QApplication(sys.argv)

from _recorder_fake import FakeRecorder  # noqa: E402
from desk import transcript_pool as pool  # noqa: E402
from desk.recorder_service import RecorderService  # noqa: E402
from desk.shell import current_context  # noqa: E402

spec = importlib.util.spec_from_file_location("recorder_widget", REPO_ROOT / "widgets/recorder/widget.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def pump_until(cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


# --- no service at all ---
current_context.set_recorder_service(None)
w = module.build()
check("without a service the widget says so and disables its buttons",
      "not available" in w._banner.text() and not any(b.isEnabled() for b in w._buttons.values()))
w.close()

with tempfile.TemporaryDirectory() as tmp:
    desk_dir = Path(tmp)
    fake = FakeRecorder(deny={"screen"}, fail={"camera"})
    # not installed first
    service = RecorderService(launcher=fake.launch, app_locator=lambda: None)
    service.configure(lambda: desk_dir, None)
    current_context.set_recorder_service(service)
    w = module.build()
    w.refresh()
    check("not installed: the banner explains how to build it", "build_desk_recorder_app.sh" in w._banner.text())
    w.close()

    service = RecorderService(launcher=fake.launch, app_locator=lambda: Path("/fake/DeskRecorder.app"))
    service.configure(lambda: desk_dir, None)
    current_context.set_recorder_service(service)
    w = module.build()
    w.show()
    check("four feature rows with start buttons", set(w._buttons) == {"transcribe", "screen", "camera", "audio"} and all(b.text() == "Start" for b in w._buttons.values()))
    check("all states start as off", all(l.text() == "off" for l in w._state_labels.values()))
    check("no raw QComboBox is used", not w.findChildren(QComboBox))
    labels = w.findChildren(QLabel)
    check("labels are not user-selectable", all(not (l.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse) for l in labels))
    check("the transcript view is read-only", w._transcript.isReadOnly())

    # transcription on
    w._buttons["transcribe"].click()
    check("transcription turns on", pump_until(lambda: w._state_labels["transcribe"].text() == "recording" and w._buttons["transcribe"].text() == "Stop"))
    check("it shows the transcript from the pool", pump_until(lambda: "hello desk" in w._transcript.toPlainText()))
    check("transcript lines carry a time", w._transcript.toPlainText().startswith("["))
    # a provisional then final update, replaced in place
    session = service.feature_status("transcribe")["session"]
    p = pool.pool_dir(desk_dir)
    pool.append_segment(p, pool.Segment(session, 1, 5000, 5400, "partial wor", False))
    check("a provisional segment is marked with ~", pump_until(lambda: "~ partial wor" in w._transcript.toPlainText()))
    pool.append_segment(p, pool.Segment(session, 1, 5000, 5900, "partial words done", True))
    check("the final replaces it, no duplicate", pump_until(lambda: "partial words done" in w._transcript.toPlainText())
          and "partial wor\n" not in w._transcript.toPlainText() and "~" not in w._transcript.toPlainText())

    # the denied and failing features report themselves without affecting transcription
    w._buttons["screen"].click()
    check("a denied screen shows its state and the reason", pump_until(lambda: w._state_labels["screen"].text() == "permission denied" and "denied" in w._detail.text()))
    w._buttons["camera"].click()
    check("a failing camera shows its error", pump_until(lambda: w._state_labels["camera"].text() == "error" and "no such device" in w._detail.text()))
    check("transcription kept running", w._state_labels["transcribe"].text() == "recording")
    check("a denied feature's button offers Start again", w._buttons["screen"].text() == "Start")

    # sources fill the combos with quoted tokens
    w._refresh_sources()
    check("windows and cameras fill the pickers", pump_until(lambda: w._target_combo.count() == 2 and w._camera_combo.count() == 2))
    check("a window choice is a quoted token", w._target_combo.itemData(1) == "window:Desk%20-%20project")
    check("a camera choice is a quoted token", w._camera_combo.itemData(1) == "FaceTime%20HD%20Camera")
    w._target_combo.setCurrentIndex(1)
    w._buttons["screen"].click()
    check("the chosen window is what the recorder is told to capture",
          pump_until(lambda: any(m.name == "start-screen" and m.fields[0] == "window:Desk%20-%20project" for m in fake.received)))

    # stopping
    w._buttons["transcribe"].click()
    check("transcription stops from the button", pump_until(lambda: w._state_labels["transcribe"].text() == "off"))

    # app dies
    fake.die()
    check("a lost recorder is shown", pump_until(lambda: not service.status()["connected"]))
    w.refresh()
    check("the banner no longer claims it is running", "is running" not in w._banner.text())
    w.close()
    service.shutdown()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
