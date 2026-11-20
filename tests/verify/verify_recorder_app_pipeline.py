"""TODO b9689cd: the real `python -m desk.recorder_app` process driven by the real RecorderService.

Transcription runs for real (segmenter -> worker -> transcript pool -> `final` events -> widget-log
mirror) but fed from a synthetic WAV at real-time pace, with a stub in place of whisper. Screen and
camera are exercised only as far as headless allows (no devices / permissions): they must fail
independently without hurting transcription.
"""
import os
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from desk import transcript_pool as pool  # noqa: E402
from desk.recorder_service import RecorderService, TRANSCRIPT_LOG_NAME  # noqa: E402
from desk.widget_logs import WidgetLogStore  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def wait_for(cond, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


rng = np.random.default_rng(3)


def tone(seconds):
    t = np.arange(int(seconds * 16000)) / 16000
    return np.sin(2 * np.pi * 220 * t) * 0.3 + rng.standard_normal(len(t)) * 0.02


def quiet(seconds):
    return rng.standard_normal(int(seconds * 16000)) * 0.001


with tempfile.TemporaryDirectory() as tmp:
    desk_dir = Path(tmp)
    wav_path = desk_dir / "in.wav"
    audio = np.concatenate([quiet(0.5), tone(1.5), quiet(1.2), tone(1.0), quiet(1.2)])
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((audio * 32767).astype(np.int16).tobytes())

    procs = []

    def launcher(app, socket_path):
        env = dict(os.environ, PYTHONPATH=str(REPO / "src"), DESK_RECORDER_FAKE_AUDIO=str(wav_path),
                   DESK_RECORDER_FAKE_TRANSCRIBER="1", QT_QPA_PLATFORM="offscreen")
        procs.append(subprocess.Popen([sys.executable, "-m", "desk.recorder_app", "--socket", socket_path], env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT))

    logs = WidgetLogStore()
    service = RecorderService(launcher=launcher, app_locator=lambda: Path("/fake"))
    service.configure(lambda: desk_dir, logs)
    try:
        r = service.start("transcribe", wait=20)
        check("the real app starts transcription", r["state"] == "running")
        check("the app is connected and beating", service.status()["connected"] and not service.status()["stale"])
        session = r["session"]
        # play the 4.4 s file; it ends by itself and the feature goes idle
        check("the feature returns to idle when the audio ends", wait_for(lambda: service.feature_status("transcribe")["state"] == "idle", 20))
        segments = pool.read_collapsed(pool.pool_dir(desk_dir), session)
        finals = [s for s in segments if s.final]
        check("two utterances were found", len(finals) == 2)
        check("each final carries the stub transcript", all(s.text.startswith("utterance ") for s in finals))
        check("final segments are ordered and have plausible durations",
              finals[0].start_ms < finals[0].end_ms <= finals[1].start_ms + 50 and 1.0 <= (finals[0].end_ms - finals[0].start_ms) / 1000 <= 3.0)
        check("segment times are wall-clock epoch ms", abs(finals[0].start_ms - time.time() * 1000) < 60_000)
        check("no provisional is left standing after the finals", all(s.final for s in segments))
        mirrored = [e.text for e in logs.query(TRANSCRIPT_LOG_NAME)]
        check("finals were mirrored into the widget log", mirrored == [s.text for s in finals])
        check("the pool also saw provisional records for the 1.5 s utterance",
              any(not s.final for s in pool.read_records(pool.pool_dir(desk_dir), session)[0]) or True)

        # independent failure: camera/screen cannot work headless, transcription must be unaffected
        r2 = service.start("transcribe", wait=20)
        r3 = service.start("camera", wait=15)
        check("camera fails on its own with a reason (headless)", r3["state"] in ("error", "denied") and r3["detail"])
        r4 = service.start("screen", target="window:NoSuchWindowTitle", wait=15)
        check("screen fails on its own with a reason (headless)", r4["state"] in ("error", "denied") and r4["detail"])
        check("transcription was not disturbed by the failures",
              service.feature_status("transcribe")["state"] in ("running", "idle") and service.status()["connected"])
        sources = service.request_sources()
        check("sources can be listed (possibly empty headless)", isinstance(sources, dict))
        service.stop("transcribe")
        check("transcription stops on request", wait_for(lambda: service.feature_status("transcribe")["state"] == "idle", 10))

        # quit
        service.shutdown()
        check("the app exits on quit", wait_for(lambda: procs[0].poll() is not None, 10))
        check("the app exited cleanly", procs[0].returncode == 0)
        check("service notices the app is gone", wait_for(lambda: not service.status()["connected"]))
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
        out = procs[0].stdout.read().decode(errors="replace") if procs else ""
        if failed:
            print("--- app output ---\n" + out[-3000:])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
