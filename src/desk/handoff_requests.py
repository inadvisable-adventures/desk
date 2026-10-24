"""Cross-project / cross-agent task handoff requests (TODO e814eaf).

A request is a record in a `RecordStore` with the lifecycle new ->
in-progress -> complete. The store is chosen by the caller; this module
only knows the lifecycle, so the same tools work over a directory of
files or a document database. `filesystem_store` is the layout used
today: a directory with `new/`, `in-progress/` and `complete/`
subdirectories (the `ae-sam-requests/` convention)."""
from pathlib import Path

from desk.record_store import FilesystemRecordStore, Record, RecordStore

NEW = "new"
IN_PROGRESS = "in-progress"
COMPLETE = "complete"
STATUSES = (NEW, IN_PROGRESS, COMPLETE)
OUTCOMES = ("done", "partial", "declined", "not-applicable")

DEFAULT_DIRECTORY = "handoff-requests"


def filesystem_store(directory: Path) -> FilesystemRecordStore:
    return FilesystemRecordStore(directory, {s: s for s in STATUSES})


def create_request(
    store: RecordStore,
    title: str,
    what: str,
    why: str = "",
    constraints: str = "",
    target_project: str = "",
    requested_by: str = "",
) -> Record:
    sections = [f"## What\n\n{what.strip()}"]
    if why.strip():
        sections.append(f"## Why\n\n{why.strip()}")
    if constraints.strip():
        sections.append(f"## Constraints\n\n{constraints.strip()}")
    fields = {"target_project": target_project, "requested_by": requested_by}
    return store.create(title, {k: v for k, v in fields.items() if v}, "\n\n".join(sections) + "\n", NEW)


def claim_request(store: RecordStore, record_id: str, claimed_by: str = "") -> Record:
    """new -> in-progress; raises RecordConflict if someone else already
    claimed it, RecordNotFound if it does not exist."""
    return store.transition(record_id, NEW, IN_PROGRESS, {"claimed_by": claimed_by} if claimed_by else None)


def complete_request(store: RecordStore, record_id: str, outcome: str, note: str = "") -> Record:
    """in-progress -> complete, recording a structured outcome."""
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}")
    fields = {"outcome": outcome}
    if note.strip():
        fields["outcome_note"] = note.strip()
    return store.transition(record_id, IN_PROGRESS, COMPLETE, fields)
