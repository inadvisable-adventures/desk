"""The shared transcript pool (TODO b9689cd, plans/desk-recorder-app.md).

Transcription (DeskRecorder.app) appends **segments** to one append-only
JSON-lines file per recording session, in
`<desk dir>/.desk_temp/transcript-pool/<session_id>.jsonl`. Any widget (or
agent, via the MCP tool) reads them; the writer knows nothing about
readers. A segment is re-appended with the same `seq` when it changes (a
provisional one becoming final), and the LAST line for a `seq` wins
(`collapse`). Times are epoch milliseconds (the same clock as
`desk.widget_logs`). Transcripts are sensitive: the directory is under
`.desk_temp`, which is gitignored.

`read_records` tails a file by byte offset, returning only complete lines,
so a reader never sees a half-written line and keeps its own position.
"""
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

TRANSCRIPT_POOL_DIRNAME = "transcript-pool"
_SESSION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


@dataclass(frozen=True)
class Segment:
    session: str
    seq: int
    start_ms: int
    end_ms: int
    text: str
    final: bool


@dataclass(frozen=True)
class SessionInfo:
    session: str
    size: int
    modified_ms: int


def pool_dir(desk_dir: Path) -> Path:
    return desk_dir / ".desk_temp" / TRANSCRIPT_POOL_DIRNAME


def valid_session_id(session: str) -> bool:
    return bool(_SESSION_RE.match(session)) and session not in (".", "..")


def session_path(pool: Path, session: str) -> Path:
    if not valid_session_id(session):
        raise ValueError(f"invalid session id: {session!r}")
    return pool / f"{session}.jsonl"


def append_segment(pool: Path, segment: Segment) -> None:
    """One `write` of one whole line, in append mode."""
    path = session_path(pool, segment.session)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(segment), ensure_ascii=False) + "\n"
    with open(path, "ab") as handle:
        handle.write(line.encode("utf-8"))


def list_sessions(pool: Path) -> list[SessionInfo]:
    """Oldest first (session ids start with their start time)."""
    if not pool.is_dir():
        return []
    sessions = []
    for path in sorted(pool.glob("*.jsonl")):
        if not valid_session_id(path.stem):
            continue
        stat = path.stat()
        sessions.append(SessionInfo(path.stem, stat.st_size, int(stat.st_mtime * 1000)))
    return sessions


def _parse_line(raw: bytes) -> Segment | None:
    try:
        data = json.loads(raw.decode("utf-8"))
        return Segment(
            session=str(data["session"]),
            seq=int(data["seq"]),
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            text=str(data["text"]),
            final=bool(data["final"]),
        )
    except (ValueError, KeyError, TypeError):
        return None  # a corrupt line is skipped, never fatal to a reader


def read_records(pool: Path, session: str, offset: int = 0) -> tuple[list[Segment], int]:
    """Raw segments appended at or after byte `offset`, and the offset to
    pass next time. Only complete (newline-terminated) lines are consumed."""
    path = session_path(pool, session)
    if not path.is_file():
        return [], offset
    with open(path, "rb") as handle:
        handle.seek(offset)
        data = handle.read()
    end = data.rfind(b"\n")
    if end < 0:
        return [], offset
    segments = [s for s in (_parse_line(raw) for raw in data[: end + 1].split(b"\n") if raw) if s is not None]
    return segments, offset + end + 1


def collapse(records: list[Segment]) -> list[Segment]:
    """The latest record per `seq`, ordered by `seq`."""
    latest: dict[int, Segment] = {}
    for record in records:
        latest[record.seq] = record
    return [latest[seq] for seq in sorted(latest)]


def read_collapsed(pool: Path, session: str) -> list[Segment]:
    return collapse(read_records(pool, session, 0)[0])


def segment_dict(segment: Segment) -> dict:
    return asdict(segment)
