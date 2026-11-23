"""desk.audio_repair: fixing a mislabeled WAV sample-rate header without
touching the sample data, against synthetic files/sidecars (pure logic,
no Qt needed)."""
import os
import sys
import tempfile
import time
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk import audio_repair  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def _write_wav(path: Path, *, rate: int, nframes: int, nchannels=1, sampwidth=2) -> bytes:
    frames = bytes(range(256)) * ((nframes * nchannels * sampwidth) // 256 + 1)
    frames = frames[: nframes * nchannels * sampwidth]
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(nchannels)
        wav.setsampwidth(sampwidth)
        wav.setframerate(rate)
        wav.writeframes(frames)
    return frames


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # --- a file mislabeled at 44100 that was really captured at 48000 ---
    path = tmp / "audio-a.wav"
    true_rate = 48000
    duration_s = 10.0
    nframes = round(true_rate * duration_s)
    original_frames = _write_wav(path, rate=44100, nframes=nframes)
    now = time.time()
    start_ms = int((now - duration_s) * 1000)
    (tmp / "audio-a.wav.frame0_ms").write_text(str(start_ms))
    os.utime(path, (now, now))

    check("true_sample_rate recovers the real rate from timing, not the stale header", audio_repair.true_sample_rate(path) == 48000)

    old_rate, new_rate = audio_repair.repair_sample_rate(path)
    check("repair reports the old and new rates", (old_rate, new_rate) == (44100, 48000))
    with wave.open(str(path), "rb") as wav:
        check("the header now says the real rate", wav.getframerate() == 48000)
        check("channel count and sample width are unchanged", wav.getnchannels() == 1 and wav.getsampwidth() == 2)
        check("every sample byte is byte-for-byte unchanged", wav.readframes(wav.getnframes()) == original_frames)

    # --- already correct: nothing to repair ---
    path2 = tmp / "audio-b.wav"
    nframes2 = round(44100 * 5.0)
    _write_wav(path2, rate=44100, nframes=nframes2)
    now2 = time.time()
    (tmp / "audio-b.wav.frame0_ms").write_text(str(int((now2 - 5.0) * 1000)))
    os.utime(path2, (now2, now2))
    try:
        audio_repair.repair_sample_rate(path2)
        check("already-correct rate raises RepairError", False)
    except audio_repair.RepairError as e:
        check("already-correct rate raises RepairError", "nothing to repair" in str(e))
    with wave.open(str(path2), "rb") as wav:
        check("an already-correct file is left completely alone", wav.getframerate() == 44100)

    # --- no sidecar at all ---
    path3 = tmp / "audio-c.wav"
    _write_wav(path3, rate=44100, nframes=1000)
    try:
        audio_repair.true_sample_rate(path3)
        check("a missing sidecar raises RepairError", False)
    except audio_repair.RepairError as e:
        check("a missing sidecar raises RepairError", "frame0_ms" in str(e))

    # --- empty recording (0 frames) ---
    path4 = tmp / "audio-d.wav"
    _write_wav(path4, rate=44100, nframes=0)
    (tmp / "audio-d.wav.frame0_ms").write_text(str(int((time.time() - 1.0) * 1000)))
    try:
        audio_repair.true_sample_rate(path4)
        check("an empty recording raises RepairError", False)
    except audio_repair.RepairError as e:
        check("an empty recording raises RepairError", "no audio" in str(e))

    # --- corrupt sidecar content ---
    path5 = tmp / "audio-e.wav"
    _write_wav(path5, rate=44100, nframes=1000)
    (tmp / "audio-e.wav.frame0_ms").write_text("not-a-number")
    try:
        audio_repair.true_sample_rate(path5)
        check("a corrupt sidecar raises RepairError", False)
    except audio_repair.RepairError:
        check("a corrupt sidecar raises RepairError", True)

    # --- snapping: a slightly-off measured rate still snaps cleanly ---
    path6 = tmp / "audio-f.wav"
    nframes6 = 480700  # not an exact multiple of any standard rate * duration
    _write_wav(path6, rate=22050, nframes=nframes6)
    now6 = time.time()
    (tmp / "audio-f.wav.frame0_ms").write_text(str(int((now6 - 10.0) * 1000)))
    os.utime(path6, (now6, now6))
    check("a noisy measured rate still snaps to the nearest standard rate", audio_repair.true_sample_rate(path6) == 48000)

    # --- stray .repair-tmp file never survives a successful repair ---
    check("no leftover .repair-tmp file after a successful repair", not (tmp / "audio-a.wav.repair-tmp").exists())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
