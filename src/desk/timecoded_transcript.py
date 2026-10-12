"""Timecoded transcripts of Claude (Desk) recordings (TODO 9df5246;
plans/agent-widget-command-query.md, Track B).

Each recording's transcript is kept at
`<desk dir>/.desk_temp/timecoded-transcripts/<recording_id>.txt`, with
recording-relative `[mm:ss.mmm]` timecodes plus the recording's absolute
`started_at_ms` (epoch ms, see `desk.widget_logs`) so it can be
correlated with widget logs. The pasted transcription is prefixed with a
note pointing at that file (`with_transcript_note`)."""

from pathlib import Path

from desk.speech import TranscriptionResult
from desk.widget_logs import TIMECODED_TRANSCRIPTS_DIRNAME, format_time_iso

# Between the note and the raw transcription in the pasted text, so the
# user can see where to strip the note and tests can assert on it.
TRANSCRIPT_NOTE_SEPARATOR = "\n--- transcription ---\n"


def format_timecode(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    minutes, ms = divmod(total_ms, 60_000)
    return f"{minutes:02d}:{ms // 1000:02d}.{ms % 1000:03d}"


def render_transcript(recording_id: str, started_at_ms: int, result: TranscriptionResult) -> str:
    lines = [
        f"recording_id: {recording_id}",
        f"started_at_ms: {started_at_ms}",
        f"started_at: {format_time_iso(started_at_ms)}",
        "",
    ]
    if result.segments:
        lines.extend(f"[{format_timecode(segment.start)}] {segment.text}" for segment in result.segments)
    else:
        lines.append(result.text)
    return "\n".join(lines) + "\n"


def transcript_relative_path(recording_id: str, temp_dirname: str) -> str:
    return f"{temp_dirname}/{TIMECODED_TRANSCRIPTS_DIRNAME}/{recording_id}.txt"


def write_transcript(
    base_dir: Path, recording_id: str, started_at_ms: int, result: TranscriptionResult
) -> Path:
    """Writes into `base_dir` (the `.desk_temp` directory) and returns the file."""
    directory = base_dir / TIMECODED_TRANSCRIPTS_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{recording_id}.txt"
    path.write_text(render_transcript(recording_id, started_at_ms, result), encoding="utf-8")
    return path


def with_transcript_note(text: str, relative_path: str) -> str:
    return f"[Timecoded transcript: {relative_path}]{TRANSCRIPT_NOTE_SEPARATOR}{text}"
