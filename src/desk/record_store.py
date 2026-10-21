"""A small record store behind a swappable interface (TODO e814eaf).

Callers (the handoff-request and feedback MCP tools) talk only to the
`RecordStore` protocol, so the backing store can be a directory of files
(`FilesystemRecordStore`, the one shipped for real use) or a document
database later. A record is a plain JSON-able thing -- id, status, title,
a flat string->string `fields` dict, a free-text `body`, timestamps -- and
status is a closed set the store is constructed with. `InMemoryRecordStore`
is the second implementation: it keeps the filesystem one honest and is
what tests use to prove callers are store-agnostic.
"""
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping, Protocol

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class RecordConflict(Exception):
    """A transition's precondition no longer holds (e.g. already claimed)."""


class RecordNotFound(Exception):
    pass


@dataclass(frozen=True)
class Record:
    id: str
    status: str
    title: str
    fields: Mapping[str, str] = field(default_factory=dict)
    body: str = ""
    created: str = ""  # ISO-8601, local zone
    updated: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "title": self.title,
            "fields": dict(self.fields),
            "body": self.body,
            "created": self.created,
            "updated": self.updated,
        }


class RecordStore(Protocol):
    statuses: tuple[str, ...]

    def create(self, title: str, fields: Mapping[str, str], body: str, status: str) -> Record: ...

    def get(self, record_id: str) -> Record | None: ...

    def list(self, status: str | None = None, keyword: str | None = None) -> list[Record]:
        """Newest first. `keyword` is a case-insensitive substring match
        over title, field values and body."""
        ...

    def transition(
        self, record_id: str, from_status: str, to_status: str, fields: Mapping[str, str] | None = None
    ) -> Record:
        """Atomically moves a record `from_status` -> `to_status`, merging
        `fields` into it. Raises RecordNotFound, or RecordConflict if the
        record is not currently in `from_status` (someone else got there
        first)."""
        ...


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def slugify(text: str, max_len: int = 40) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")[:max_len].strip("-")
    return slug or "untitled"


def matches_keyword(record: Record, keyword: str | None) -> bool:
    if not keyword:
        return True
    needle = keyword.lower()
    haystacks = [record.title, record.body, *record.fields.values()]
    return any(needle in h.lower() for h in haystacks)


def _check_status(store_statuses: tuple[str, ...], status: str) -> None:
    if status not in store_statuses:
        raise ValueError(f"unknown status {status!r}; expected one of {', '.join(store_statuses)}")


def _new_id(title: str, taken) -> str:
    base = f"{time.strftime('%Y%m%d-%H%M%S')}-{slugify(title)}"
    candidate, n = base, 2
    while taken(candidate):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


class InMemoryRecordStore:
    def __init__(self, statuses: tuple[str, ...]) -> None:
        self.statuses = statuses
        self._records: dict[str, Record] = {}
        self._lock = threading.Lock()

    def create(self, title, fields, body, status):
        _check_status(self.statuses, status)
        with self._lock:
            stamp = now_iso()
            record = Record(
                _new_id(title, self._records.__contains__), status, title, dict(fields), body, stamp, stamp
            )
            self._records[record.id] = record
            return record

    def get(self, record_id):
        return self._records.get(record_id)

    def list(self, status=None, keyword=None):
        if status is not None:
            _check_status(self.statuses, status)
        found = [
            r for r in self._records.values() if (status is None or r.status == status) and matches_keyword(r, keyword)
        ]
        return sorted(found, key=lambda r: r.created, reverse=True)

    def transition(self, record_id, from_status, to_status, fields=None):
        _check_status(self.statuses, to_status)
        with self._lock:
            record = self._records.get(record_id)
            if record is None:
                raise RecordNotFound(record_id)
            if record.status != from_status:
                raise RecordConflict(f"{record_id} is {record.status!r}, not {from_status!r}")
            merged = {**record.fields, **(fields or {})}
            updated = replace(record, status=to_status, fields=merged, updated=now_iso())
            self._records[record_id] = updated
            return updated


# ---------- filesystem implementation ----------

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)
_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
# Frontmatter keys the codec owns; everything else is a caller field.
_RESERVED = ("id", "title", "created", "updated")


def encode_record(record: Record) -> str:
    """Markdown file text: `---` frontmatter (one `key: <JSON value>` line
    each, so a value is always single-line and unambiguous), then the body."""
    lines = ["---"]
    for key in _RESERVED:
        lines.append(f"{key}: {json.dumps(getattr(record, key))}")
    for key, value in record.fields.items():
        lines.append(f"{key}: {json.dumps(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + record.body


def decode_record(text: str, fallback_id: str, status: str) -> Record:
    """Tolerant: a file with no frontmatter (a hand-written request in the
    older prose convention) still decodes -- title from its first `# `
    heading, whole text as the body, id from its filename."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        heading = _HEADING_RE.search(text)
        return Record(fallback_id, status, heading.group(1).strip() if heading else fallback_id, {}, text)
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, raw = line.partition(": ")
        if not sep:
            continue
        try:
            values[key] = str(json.loads(raw))
        except ValueError:
            values[key] = raw
    extra = {k: v for k, v in values.items() if k not in _RESERVED}
    return Record(
        values.get("id", fallback_id),
        status,
        values.get("title", fallback_id),
        extra,
        match.group(2),
        values.get("created", ""),
        values.get("updated", ""),
    )


class FilesystemRecordStore:
    """One markdown file per record under `root`; the record's status is
    the subdirectory it sits in (`status_dirs` maps status -> subdirectory
    name, "" meaning `root` itself). A status change is an `os.rename`
    between those directories, which is what makes a claim atomic: of two
    simultaneous claimants only one rename finds the source file."""

    def __init__(self, root: Path, status_dirs: Mapping[str, str]) -> None:
        self.root = Path(root)
        self.status_dirs = dict(status_dirs)
        self.statuses = tuple(status_dirs)

    def _dir(self, status: str) -> Path:
        return self.root / self.status_dirs[status]

    def _path(self, status: str, record_id: str) -> Path:
        return self._dir(status) / f"{record_id}.md"

    def _locate(self, record_id: str) -> tuple[str, Path] | None:
        for status in self.statuses:
            path = self._path(status, record_id)
            if path.is_file():
                return status, path
        return None

    def _read(self, status: str, path: Path) -> Record:
        return decode_record(path.read_text(encoding="utf-8"), path.stem, status)

    def _write(self, path: Path, record: Record) -> None:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(encode_record(record), encoding="utf-8")
        os.replace(tmp, path)

    def create(self, title, fields, body, status):
        _check_status(self.statuses, status)
        self._dir(status).mkdir(parents=True, exist_ok=True)
        stamp = now_iso()
        while True:
            record_id = _new_id(title, lambda c: self._locate(c) is not None)
            record = Record(record_id, status, title, dict(fields), body, stamp, stamp)
            try:
                # "x": never overwrite an existing record, even on a race.
                with open(self._path(status, record_id), "x", encoding="utf-8") as f:
                    f.write(encode_record(record))
                return record
            except FileExistsError:
                continue

    def get(self, record_id):
        if "/" in record_id or "\\" in record_id or record_id.startswith("."):
            return None
        found = self._locate(record_id)
        return None if found is None else self._read(*found)

    def list(self, status=None, keyword=None):
        if status is not None:
            _check_status(self.statuses, status)
        records: list[Record] = []
        for st in [status] if status else self.statuses:
            directory = self._dir(st)
            if not directory.is_dir():
                continue
            for path in directory.glob("*.md"):
                if path.name.lower() == "readme.md":
                    continue
                record = self._read(st, path)
                if matches_keyword(record, keyword):
                    records.append(record)
        return sorted(records, key=lambda r: (r.created, r.id), reverse=True)

    def transition(self, record_id, from_status, to_status, fields=None):
        _check_status(self.statuses, from_status)
        _check_status(self.statuses, to_status)
        source = self._path(from_status, record_id)
        target = self._path(to_status, record_id)
        self._dir(to_status).mkdir(parents=True, exist_ok=True)
        try:
            os.rename(source, target)
        except FileNotFoundError:
            found = self._locate(record_id)
            if found is None:
                raise RecordNotFound(record_id) from None
            raise RecordConflict(f"{record_id} is {found[0]!r}, not {from_status!r}") from None
        record = self._read(to_status, target)
        updated = replace(record, fields={**record.fields, **(fields or {})}, updated=now_iso())
        self._write(target, updated)
        return updated
