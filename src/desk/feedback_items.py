"""Feedback items kept in the shared `../FEEDBACK/` directory (TODO 540e886).

A thin layer over `RecordStore` that keeps the existing on-disk
convention: files named `FEEDBACK-DESK-<slug>-<YYYY-MM-DD>-<HHMM>.md`,
plain markdown (no frontmatter), with triage state expressed by placement
-- top level is `open`, otherwise `parkinglot/`, `implemented/` or
`external/`. Triage moves stay with Desk's maintainers, so this module
offers create/list/get only."""
import re
import time
from pathlib import Path

from desk.record_store import FilesystemRecordStore, Record, RecordStore, slugify

OPEN = "open"
PARKINGLOT = "parkinglot"
IMPLEMENTED = "implemented"
EXTERNAL = "external"
STATUSES = (OPEN, PARKINGLOT, IMPLEMENTED, EXTERNAL)
STATUS_DIRS = {OPEN: "", PARKINGLOT: "parkinglot", IMPLEMENTED: "implemented", EXTERNAL: "external"}

DEFAULT_DIRECTORY = "../FEEDBACK"
FILENAME_PREFIX = "FEEDBACK-DESK-"

_TIMESTAMP_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})$")
_HEADING_RE = re.compile(r"^#\s+(?:Feedback:\s*)?(.+)$", re.MULTILINE)


class _FeedbackCodec:
    """Files are plain markdown: the body IS the file. Title and creation
    time are recovered from the first heading and the filename."""

    def encode(self, record: Record) -> str:
        return record.body

    def decode(self, text: str, record_id: str, status: str) -> Record:
        heading = _HEADING_RE.search(text)
        title = heading.group(1).strip() if heading else record_id
        created = ""
        match = _TIMESTAMP_RE.search(record_id)
        if match:
            y, mo, d, h, mi = match.groups()
            created = f"{y}-{mo}-{d}T{h}:{mi}"
        return Record(record_id, status, title, {}, text, created, created)


def _new_feedback_id(title: str, taken) -> str:
    base = f"{FILENAME_PREFIX}{slugify(title, 60)}-{time.strftime('%Y-%m-%d-%H%M')}"
    candidate, n = base, 2
    while taken(candidate):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def filesystem_store(directory: Path) -> FilesystemRecordStore:
    return FilesystemRecordStore(directory, STATUS_DIRS, _FeedbackCodec(), _new_feedback_id)


def create_feedback(store: RecordStore, title: str, body: str) -> Record:
    """A new open item, written as `# Feedback: <title>` plus the body --
    the shape existing feedback files already have."""
    return store.create(title, {}, f"# Feedback: {title}\n\n{body.strip()}\n", OPEN)
