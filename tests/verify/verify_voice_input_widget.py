import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtGui import QGuiApplication  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton  # noqa: E402

import desk.speech as speech  # noqa: E402

app = QApplication(sys.argv)

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")
WIDGET_DIR = REPO_ROOT / "widgets" / "voice_input"

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


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthesize_pcm(text: str) -> bytes:
    """Real macOS text-to-speech -> raw 16kHz mono 16-bit PCM samples,
    matching tests/verify/verify_speech_transcription.py's own fixture
    approach: a real, non-mocked audio pipeline, produced at test time
    so no audio fixture needs to be checked into the repo."""
    import tempfile
    import wave

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "sample.wav"
        subprocess.run(
            ["say", "-o", str(wav_path), "--file-format=WAVE", "--data-format=LEI16@16000", text],
            check=True,
        )
        with wave.open(str(wav_path), "rb") as wf:
            return wf.readframes(wf.getnframes())


def test_widget_json_is_well_formed():
    manifest = json.loads((WIDGET_DIR / "widget.json").read_text())
    check("widget.json declares kind: python", manifest["kind"] == "python")
    check("widget.json entry is widget.py", manifest["entry"] == "widget.py")
    check("widget.json declares no capabilities (this is a kind:python widget, not HTML/Bridge)", manifest["capabilities"] == [])


voice_input_mod = load_module("voice_input_widget", "widgets/voice_input/widget.py")


def test_build_returns_expected_control_tree():
    widget = voice_input_mod.build()
    buttons = widget.findChildren(QPushButton)
    labels = widget.findChildren(QLabel)
    text_edits = widget.findChildren(QPlainTextEdit)
    check("exactly one record button and one copy button exist", len(buttons) == 2)
    check("a record button with the expected initial text exists", any(b.text() == "● Record" for b in buttons))
    check("a copy button exists", any(b.text() == "Copy" for b in buttons))
    check("copy button starts disabled (nothing transcribed yet)", widget._copy_button.isEnabled() is False)
    check("a status label exists", len(labels) >= 1)
    check("a text edit for the transcription result exists", len(text_edits) == 1)
    widget.deleteLater()


def test_record_toggle_starts_and_stops_real_capture():
    widget = voice_input_mod.build()
    widget._on_record_clicked()
    check("clicking record switches the button to Stop", widget._record_button.text() == "■ Stop")
    check("status reflects recording", "Recording" in widget._status_label.text())
    check("a real QAudioSource was actually started", widget._audio_source is not None)

    pump(0.5)  # let the real microphone actually deliver some data

    # Stop via the internal helper directly (not the click handler) so
    # this test controls exactly what "audio" was captured, independent
    # of whatever the real microphone happened to pick up -- the real
    # QAudioSource/QIODevice wiring itself was already exercised above.
    widget._audio_source.stop()
    widget._audio_source = None
    widget._audio_io = None
    widget._captured_chunks = [synthesize_pcm("Testing one two three")]
    widget._record_button.setText("● Record")
    widget._process_captured_audio()

    ok = wait_until(lambda: widget._status_label.text() in ("Done.",) or "error" in widget._status_label.text().lower() or widget._status_label.styleSheet() == voice_input_mod.ERROR_STYLE)
    check("transcription completed (success or error) within the timeout", ok)
    check("known synthesized speech transcribes into the text edit", "testing" in widget._text_edit.toPlainText().lower())
    check("copy button re-enabled once text is present", widget._copy_button.isEnabled() is True)

    widget._on_copy_clicked()
    check("copy button places the transcribed text on the real system clipboard", QGuiApplication.clipboard().text() == widget._text_edit.toPlainText())

    widget.deleteLater()


def test_wav_file_is_deleted_after_transcription():
    written_paths = []
    original_write_wav = voice_input_mod._write_wav

    def spying_write_wav(pcm_bytes):
        path = original_write_wav(pcm_bytes)
        written_paths.append(path)
        return path

    voice_input_mod._write_wav = spying_write_wav
    try:
        widget = voice_input_mod.build()
        widget._on_record_clicked()
        widget._audio_source.stop()
        widget._audio_source = None
        widget._audio_io = None
        widget._captured_chunks = [synthesize_pcm("Cleanup check")]
        widget._record_button.setText("● Record")
        widget._process_captured_audio()

        ok = wait_until(lambda: len(written_paths) == 1 and widget._status_label.text() == "Done.")
        check("transcription completed for the cleanup test", ok)
        check("the temporary WAV file was actually written at some point", len(written_paths) == 1)
        check("the temporary WAV file is deleted once transcription finishes", written_paths and not written_paths[0].exists())
        widget.deleteLater()
    finally:
        voice_input_mod._write_wav = original_write_wav


def test_unavailable_model_surfaces_as_a_visible_error():
    original_repo = speech.MODEL_REPO
    speech.MODEL_REPO = "mlx-community/whisper-this-repo-does-not-exist"
    try:
        widget = voice_input_mod.build()
        widget._on_record_clicked()
        widget._audio_source.stop()
        widget._audio_source = None
        widget._audio_io = None
        widget._captured_chunks = [synthesize_pcm("Should not transcribe")]
        widget._record_button.setText("● Record")
        widget._process_captured_audio()

        ok = wait_until(lambda: widget._status_label.styleSheet() == voice_input_mod.ERROR_STYLE)
        check("an unavailable model surfaces a real, visible error status", ok)
        check("the error message names the download script", "download_whisper_model.py" in widget._status_label.text())
        widget.deleteLater()
    finally:
        speech.MODEL_REPO = original_repo


test_widget_json_is_well_formed()
test_build_returns_expected_control_tree()
test_record_toggle_starts_and_stops_real_capture()
test_wav_file_is_deleted_after_transcription()
test_unavailable_model_surfaces_as_a_visible_error()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
