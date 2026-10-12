# TODO 9df5246 (Track B): timecoded transcript file, pasted note + separator,
# recording/stopped_recording event payloads. No microphone, no whisper model.
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication  # noqa: E402

from desk import speech, timecoded_transcript as tt, widget_logs  # noqa: E402
from desk.shell import current_context  # noqa: E402

app = QApplication(sys.argv)
failed = 0


def check(name, ok):
    global failed
    print(("PASS" if ok else "FAIL"), name)
    failed += 0 if ok else 1


class FakeMediator:
    def __init__(self):
        self.published = []

    def publish(self, name, payload, sender):
        self.published.append((name, payload, sender))


spec = importlib.util.spec_from_file_location("claude_desk_widget", REPO_ROOT / "widgets/claude_desk/widget.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# --- pure formatting
check("timecode format", tt.format_timecode(65.4321) == "01:05.432" and tt.format_timecode(0) == "00:00.000")
result = speech.TranscriptionResult(
    text="hello there. second bit",
    words=[],
    segments=[speech.TranscriptSegment(0.0, 1.2, "hello there."), speech.TranscriptSegment(1.2, 3.0, "second bit")],
)
rendered = tt.render_transcript("rec-1-abcd", 1700000000000, result)
check("header has started_at_ms", "started_at_ms: 1700000000000" in rendered)
check("segment lines timecoded", "[00:00.000] hello there.\n[00:01.200] second bit\n" in rendered)
check("fallback without segments", tt.render_transcript("r", 1, speech.TranscriptionResult("plain", [])).endswith("plain\n"))
check(
    "note + separator + raw text",
    tt.with_transcript_note("raw", ".desk_temp/x.txt") == f"[Timecoded transcript: .desk_temp/x.txt]{tt.TRANSCRIPT_NOTE_SEPARATOR}raw",
)

# --- widget wiring
with tempfile.TemporaryDirectory() as tmp:
    desk_dir = Path(tmp)
    current_context.set_current_desk_directory(desk_dir)
    widget = module.build()
    mediator = FakeMediator()
    widget.bind_event_mediator("inst-1", mediator)
    mediator.published.clear()

    rec = widget._mic_recorder
    rec.recording_id, rec.started_at_ms, rec.stopped_at_ms = "rec-100-ab12", 100, 250
    widget._on_mic_recording_started()
    widget._on_mic_recording_stopped()
    check(
        "events published in order with contract payloads",
        mediator.published
        == [
            (widget_logs.RECORDING_EVENT, {"recording_id": "rec-100-ab12", "started_at_ms": 100}, "inst-1"),
            (
                widget_logs.STOPPED_RECORDING_EVENT,
                {"recording_id": "rec-100-ab12", "started_at_ms": 100, "stopped_at_ms": 250},
                "inst-1",
            ),
        ],
    )

    widget._on_mic_transcription_finished(result, None)
    text = widget._prompt_input.toPlainText()
    directory = current_context.get_current_desk_directory()
    base = directory / ".desk_temp"
    transcript = base / "timecoded-transcripts" / "rec-100-ab12.txt"
    check("transcript file written", transcript.is_file())
    check("pasted text starts with relative note", text.startswith("[Timecoded transcript: .desk_temp/timecoded-transcripts/rec-100-ab12.txt]"))
    check("pasted text ends with separator + raw transcription", text.endswith(tt.TRANSCRIPT_NOTE_SEPARATOR + "hello there. second bit"))

# unbound widget publishes nothing and doesn't crash
unbound = module.build()
unbound._on_mic_recording_stopped()
check("unbound widget doesn't crash on recording events", True)

print("FAILED" if failed else "ALL PASSED")
sys.exit(1 if failed else 0)
