# DISABLED (TODO b2ab79f): this test starts a real MicRecorder
# capture via the Claude (Desk) widget's own mic button (a real
# QAudioSource against the actual default microphone), which was
# audibly/visibly activating the system mic during routine regression
# sweeps -- not a failure, not drift, just an unwanted side effect of
# running this file automatically. Split out of
# tests/verify/verify_claude_desk_widget.py (which keeps its other,
# mic-free tests -- session/permission/queueing/window-wiring coverage
# -- running normally) so only the actual hardware-touching coverage
# is disabled. Left disabled until TODO b2ab79f decides how
# hardware-using regression coverage like this should actually be
# integrated (run occasionally by hand, mock the QAudioSource/
# QIODevice layer, or some combination) rather than always running as
# part of the normal sweep. Still a real, working, non-mocked test --
# run it directly (`.venv/bin/python3
# tests/verify/disabled_verify_claude_desk_widget_mic.py`) when you
# want this coverage.
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# desk.shell.window (imported by widget.py's DeskWindow-adjacent pieces
# indirectly) must be importable before QApplication is constructed --
# see tests/verify/verify_claude_desk_widget.py's own comment on this
# same gotcha.
import desk.shell.window  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

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


def wait_until(predicate, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def load_widget_module():
    spec = importlib.util.spec_from_file_location("claude_desk_widget", REPO_ROOT / "widgets" / "claude_desk" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthesize_pcm(text):
    """Real macOS text-to-speech -> raw 16kHz mono 16-bit PCM samples,
    same fixture approach as tests/verify/verify_voice_input_widget
    .py's own synthesize_pcm (TODO fe7d8f2)."""
    import subprocess
    import wave

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "sample.wav"
        subprocess.run(
            ["say", "-o", str(wav_path), "--file-format=WAVE", "--data-format=LEI16@16000", text],
            check=True,
        )
        with wave.open(str(wav_path), "rb") as wf:
            return wf.readframes(wf.getnframes())


def test_mic_button_dictates_into_the_prompt_box_without_sending():
    """TODO fe7d8f2: a real mic-button click starts a real MicRecorder
    (desk.voice_capture, shared with widgets/voice_input/widget.py),
    then injected known synthesized speech (real audio pipeline, same
    technique tests/verify/verify_voice_input_widget.py already uses)
    is transcribed and lands in _prompt_input -- confirmed *not*
    auto-sent (no real Claude session involved in this check at all,
    so send_prompt firing would be directly observable, not just
    theoretically possible)."""
    module = load_widget_module()
    widget = module.build()
    sent = []
    widget._session.send_prompt = lambda text: sent.append(text)

    widget._on_mic_clicked()
    check("mic button switches to Stop", widget._mic_button.text() == "■")
    check("prompt input disabled while recording", not widget._prompt_input.isEnabled())
    check("a real MicRecorder actually started capturing", widget._mic_recorder.is_recording())

    pump(0.5)  # let the real microphone actually deliver some data

    # Override the *content* of what got captured with known,
    # real synthesized speech, then let stop() do its own real
    # teardown (stops the real QAudioSource, emits recording_stopped
    # for real) -- same technique
    # tests/verify/disabled_verify_voice_capture.py's own
    # _start_then_inject_known_audio uses. Calling
    # _process_captured_audio() directly instead would skip
    # recording_stopped entirely, silently leaving the mic button
    # stuck in its Stop state -- confirmed directly, a real bug this
    # test caught in its own first draft, not a hypothetical.
    widget._mic_recorder._captured_chunks = [synthesize_pcm("Testing dictation into Claude Desk")]
    widget._mic_recorder.stop()

    ok = wait_until(lambda: widget._prompt_input.isEnabled())
    check("controls re-enable once transcription finishes", ok)
    check("the dictated text landed in the prompt box", "dictation" in widget._prompt_input.toPlainText().lower())
    check("mic button reverts to Record", widget._mic_button.text() == "●")
    check("nothing was sent to the session -- the user still has to hit Send", sent == [])

    widget._session.stop()
    widget.deleteLater()


test_mic_button_dictates_into_the_prompt_box_without_sending()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
