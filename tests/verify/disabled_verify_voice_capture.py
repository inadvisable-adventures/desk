# DISABLED (TODO b2ab79f): every test in this file starts a real
# MicRecorder capture (a real QAudioSource against the actual default
# microphone), which was audibly/visibly activating the system mic
# during routine regression sweeps -- not a failure, not drift, just
# an unwanted side effect of running this file automatically. Left
# disabled until TODO b2ab79f decides how hardware-using regression
# coverage like this should actually be integrated (run occasionally
# by hand, mock the QAudioSource/QIODevice layer, or some combination)
# rather than always running as part of the normal sweep. Still a
# real, working, non-mocked test of desk.voice_capture.MicRecorder --
# run it directly (`.venv/bin/python3
# tests/verify/disabled_verify_voice_capture.py`) when you want that
# coverage.
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import desk.speech as speech  # noqa: E402
from desk.voice_capture import MicRecorder  # noqa: E402

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


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def wait_until(predicate, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def synthesize_pcm(text: str) -> bytes:
    """Real macOS text-to-speech -> raw 16kHz mono 16-bit PCM samples --
    same fixture approach as tests/verify/verify_speech_transcription
    .py's own _synthesize_wav: a real, non-mocked audio pipeline,
    produced at test time so no audio fixture needs to be checked into
    the repo."""
    import wave

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "sample.wav"
        subprocess.run(
            ["say", "-o", str(wav_path), "--file-format=WAVE", "--data-format=LEI16@16000", text],
            check=True,
        )
        with wave.open(str(wav_path), "rb") as wf:
            return wf.readframes(wf.getnframes())


def test_real_mic_capture_start_stop():
    recorder = MicRecorder()
    started = []
    recorder.recording_started.connect(lambda: started.append(True))
    check("not recording before start()", recorder.is_recording() is False)

    recorder.start()
    check("recording_started fired", started == [True])
    check("is_recording() is True once started", recorder.is_recording() is True)
    check("a real QAudioSource was actually created", recorder._audio_source is not None)

    pump(0.5)  # let the real microphone actually deliver some data
    check("real PCM bytes were captured from the real microphone", len(recorder._captured_chunks) > 0)

    recorder._audio_source.stop()
    recorder._audio_source = None
    recorder._audio_io = None
    check("is_recording() is False once the audio source is cleared", recorder.is_recording() is False)


def _start_then_inject_known_audio(recorder: MicRecorder, text: str) -> None:
    """Starts a real recording (real QAudioSource, same as
    test_real_mic_capture_start_stop), then overrides whatever the
    real microphone actually captured with known, real
    synthesized-speech PCM before the caller calls recorder.stop() --
    same technique tests/verify/verify_voice_input_widget.py's own
    widget-level tests use to control exactly what "audio" gets
    transcribed. stop() itself still does the real teardown (stops the
    real QAudioSource, emits recording_stopped for real) -- only the
    *content* of what was "captured" is substituted."""
    recorder.start()
    pump(0.1)
    recorder._captured_chunks = [synthesize_pcm(text)]


def test_stop_transcribes_injected_audio_end_to_end():
    recorder = MicRecorder()
    stopped = []
    results = []
    errors = []
    recorder.recording_stopped.connect(lambda: stopped.append(True))
    recorder.transcription_finished.connect(lambda result, error: (results.append(result), errors.append(error)))

    _start_then_inject_known_audio(recorder, "Testing the shared recorder")
    recorder.stop()

    check("recording_stopped fired synchronously, before transcription finishes", stopped == [True])
    ok = wait_until(lambda: results or errors and errors[0] is not None)
    check("transcription completes within the timeout", ok)
    check("no error reported", errors and errors[0] is None)
    check("a real TranscriptionResult was produced", results and isinstance(results[0], speech.TranscriptionResult))
    check("the known synthesized speech was transcribed correctly", results and "shared recorder" in results[0].text.lower())
    check("is_recording() is False again after stop()", recorder.is_recording() is False)


def test_no_audio_captured_reports_an_error():
    recorder = MicRecorder()
    recorder.start()
    pump(0.1)
    recorder._captured_chunks = []  # simulates a capture that genuinely produced nothing
    errors = []
    recorder.error.connect(lambda message: errors.append(message))

    recorder.stop()

    check("an empty capture reports a real error, not a crash", errors == ["No audio captured."])


def test_wav_file_is_deleted_after_transcription():
    import desk.voice_capture as voice_capture

    written_paths = []
    original_write_wav = voice_capture._write_wav

    def spying_write_wav(pcm_bytes):
        path = original_write_wav(pcm_bytes)
        written_paths.append(path)
        return path

    voice_capture._write_wav = spying_write_wav
    try:
        recorder = MicRecorder()
        _start_then_inject_known_audio(recorder, "Cleanup check")
        results = []
        recorder.transcription_finished.connect(lambda result, error: results.append((result, error)))

        recorder.stop()

        ok = wait_until(lambda: len(written_paths) == 1 and results)
        check("transcription completed for the cleanup test", ok)
        check("a real temporary WAV file was actually written", len(written_paths) == 1)
        check("the temporary WAV file is deleted once transcription finishes", written_paths and not written_paths[0].exists())
    finally:
        voice_capture._write_wav = original_write_wav


test_real_mic_capture_start_stop()
test_stop_transcribes_injected_audio_end_to_end()
test_no_audio_captured_reports_an_error()
test_wav_file_is_deleted_after_transcription()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
