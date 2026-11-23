"""The Recordings widget (desk_widgets/recordings/): lists DeskRecorder's
finished screen/camera/audio files plus transcript sessions, and routes
a selection to the right preview pane. No real DeskRecorder.app and no
real playback needed -- just the listing/selection/persistence logic,
against a real filesystem and a real transcript pool."""
import importlib.util
import os
import sys
import tempfile
import time
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QComboBox, QLabel  # noqa: E402

app = QApplication(sys.argv)

from desk import transcript_pool as pool  # noqa: E402
from desk.recorder_service import RecorderService  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.widget_logs import format_time_iso  # noqa: E402

spec = importlib.util.spec_from_file_location("recordings_widget", REPO_ROOT / "desk_widgets/recordings/widget.py")
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


# --- no service at all ---
current_context.set_recorder_service(None)
w = module.build()
check("without a service the widget says so", "not available" in w._banner.text())
check("the list is empty", w._list.count() == 0)
w.close()

with tempfile.TemporaryDirectory() as tmp:
    desk_dir = Path(tmp)
    service = RecorderService(launcher=lambda *a: None, app_locator=lambda: None)
    service.configure(lambda: desk_dir, None)
    current_context.set_recorder_service(service)

    recordings_dir = service.recordings_dir()
    screen_path = recordings_dir / "screen-20260101-000000.mp4"
    camera_path = recordings_dir / "camera-20260101-000100.mp4"
    audio_path = recordings_dir / "audio-20260101-000200.wav"
    for path in (screen_path, camera_path, audio_path):
        path.write_bytes(b"not-a-real-media-file")
    # distinct, known mtimes (newest last created here -> audio should sort first)
    now = time.time()
    os.utime(screen_path, (now - 300, now - 300))
    os.utime(camera_path, (now - 200, now - 200))
    os.utime(audio_path, (now - 100, now - 100))

    session = "rec-99999999-999999-aaaa"
    pool_dir = service.pool_dir()
    pool.append_segment(pool_dir, pool.Segment(session, 0, 1000, 2000, "hello from the transcript", True))
    pool.append_segment(pool_dir, pool.Segment(session, 1, 2000, 2500, "second bit", False))  # provisional, newest mtime

    w = module.build()
    check("no raw QComboBox is used", not w.findChildren(QComboBox))
    labels = w.findChildren(QLabel)
    check(
        "labels are not user-selectable",
        all(not (l.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse) for l in labels),
    )
    check("the transcript view is read-only", w._transcript_view.isReadOnly())
    check("four entries were found (3 files + 1 transcript session)", w._list.count() == 4)
    check(
        "every kind is represented",
        {w._list.item(i).data(Qt.ItemDataRole.UserRole).kind for i in range(4)}
        == {"screen", "camera", "audio", "transcript"},
    )
    # the transcript session's mtime (just written) is the newest of all four -> row 0
    check("newest entry sorts first", w._list.item(0).data(Qt.ItemDataRole.UserRole).kind == "transcript")
    check("oldest entry sorts last", w._list.item(3).data(Qt.ItemDataRole.UserRole).name == screen_path.name)

    def row_for(kind):
        for i in range(w._list.count()):
            if w._list.item(i).data(Qt.ItemDataRole.UserRole).kind == kind:
                return i
        return None

    def row_for_name(name):
        for i in range(w._list.count()):
            if w._list.item(i).data(Qt.ItemDataRole.UserRole).name == name:
                return i
        return None

    w._list.setCurrentRow(row_for("transcript"))
    check("selecting a transcript shows the transcript pane", w._preview_stack.currentIndex() == 1)
    expected_time = format_time_iso(1000)[11:19]
    check(
        "the transcript text is there, timestamped",
        f"[{expected_time}] hello from the transcript" in w._transcript_view.toPlainText(),
    )
    check("a provisional segment is marked with ~", "~ second bit" in w._transcript_view.toPlainText())

    w._list.setCurrentRow(row_for("audio"))
    check("selecting a recording shows the media pane", w._preview_stack.currentIndex() == 0)
    check("the player was pointed at the right file", w._player.source().toLocalFile() == str(audio_path))
    check("play is enabled for a recording", w._play_button.isEnabled())

    # persistence round trip
    stored = w.get_widget_local_storage()
    check("widget-local storage remembers kind and name", stored == {"kind": "audio", "name": audio_path.name})
    w2 = module.build()
    w2.set_widget_local_storage(stored)
    check("a fresh widget restores the same selection", w2._list.currentRow() == row_for("audio"))
    w2.close()

    # -- right-click context menu: "Repair sample rate" ---------------------
    check(
        "the list has a custom context menu policy wired up",
        w._list.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu,
    )
    # right-clicking empty space (no item there) must not raise
    w._show_context_menu(QPoint(-1, -1))
    check("right-click on empty space is a no-op, not an error", True)
    # right-clicking a non-audio row must return before ever opening a real
    # QMenu (which would block this script forever waiting for a click) --
    # only "audio" entries can have a mislabeled sample rate at all.
    screen_item = w._list.item(row_for("screen"))
    screen_point = w._list.visualItemRect(screen_item).center()
    w._show_context_menu(screen_point)
    check("right-click on a non-audio row returns without opening a menu (would hang otherwise)", True)

    # a real, validly-timestamped WAV, mislabeled the way the old
    # AudioFeature code used to mislabel one -- the actual repair target.
    repair_path = recordings_dir / "audio-20260101-000300.wav"
    true_rate, declared_rate, duration_s = 48000, 44100, 6.0
    nframes = round(true_rate * duration_s)
    with wave.open(str(repair_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(declared_rate)
        wav_file.writeframes(b"\x00\x01" * nframes)
    repair_now = time.time()
    (recordings_dir / (repair_path.name + ".frame0_ms")).write_text(str(int((repair_now - duration_s) * 1000)))
    os.utime(repair_path, (repair_now, repair_now))
    w.refresh()

    repair_entry = w._list.item(row_for_name(repair_path.name)).data(Qt.ItemDataRole.UserRole)
    w._repair_sample_rate(repair_entry)
    check(
        "a successful repair reports the before/after rate on the banner",
        f"{declared_rate} Hz" in w._banner.text() and f"{true_rate} Hz" in w._banner.text(),
    )
    with wave.open(str(repair_path), "rb") as wav_file:
        check("the WAV header now carries the real rate", wav_file.getframerate() == true_rate)

    # an entry with no real WAV/sidecar behind it (the garbage-bytes
    # fixture from above) reports a clean error instead of raising
    bogus_entry = module.Entry("audio", audio_path.name, 0, audio_path, None)
    w._repair_sample_rate(bogus_entry)
    check("a file that can't be repaired reports why on the banner", "Could not repair" in w._banner.text())

    # the selected file disappears from disk
    w._list.setCurrentRow(row_for_name(audio_path.name))
    check("re-selected the about-to-be-deleted file", w._current is not None and w._current.name == audio_path.name)
    audio_path.unlink()
    w.refresh()
    check("a deleted recording drops out of the list", w._list.count() == 4)  # screen, camera, transcript, repair_path
    check("losing the current selection falls back to the placeholder", w._current is None)
    check("the placeholder message is shown", "Select a recording" in w._detail_label.text())

    w.close()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
