"""Shared contracts for agent/widget command-query (TODOs 1f74c27,
9df5246, 51db3bd; plans/agent-widget-command-query.md).

Two contracts live here so the log-API track and the recording track
can proceed independently:

1. `WidgetLogStore` + the clock: named, time-stamped, bounded logs a
   widget appends to (via the Bridge API or a python-widget hook) and
   an MCP tool queries by time range. Every timestamp is **epoch
   milliseconds, UTC, int** (`now_ms`); `parse_time_ms` converts the
   other forms a caller may supply.
2. The `recording`/`stopped_recording` desk event names and payload
   shapes Claude (Desk) publishes through the event mediator.

Qt-free and thread-safe (a plain lock), like `desk.event_mediator`: the
Local Web Server's request threads write, the MCP server's event loop
reads. One instance per app run, created in
`desk.server.runner.start_server`."""

import bisect
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# --- Contract 1: log store + clock -------------------------------------

# Per-log ring cap: oldest entries (by timestamp) are dropped beyond it.
MAX_ENTRIES_PER_LOG = 10_000
# Entry text is truncated to this many characters on append.
MAX_ENTRY_TEXT_CHARS = 4096
# A guard against a buggy widget minting an unbounded number of log names.
MAX_LOGS = 500


def now_ms() -> int:
    """The one clock: epoch milliseconds, UTC."""
    return time.time_ns() // 1_000_000


def parse_time_ms(value: Any) -> int:
    """Converts a query-boundary value to epoch ms: an int/float is taken
    as epoch ms already; a string is an ISO-8601 datetime (a trailing `Z`
    is UTC; one with no zone is the Desk machine's local time) or a
    string of digits (epoch ms). Raises ValueError otherwise."""
    if isinstance(value, bool):
        raise ValueError(f"not a time: {value!r}")
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"not an ISO-8601 time: {value!r}") from exc
        return int(parsed.timestamp() * 1000)  # naive -> local time, aware -> its own zone
    raise ValueError(f"not a time: {value!r}")


def format_time_iso(ms: int) -> str:
    """Local-zone ISO-8601 with millisecond precision, for display."""
    return datetime.fromtimestamp(ms / 1000).astimezone().isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class LogEntry:
    t: int  # epoch ms, UTC
    text: str


@dataclass(frozen=True)
class LogSummary:
    name: str
    count: int
    first_t: int | None
    last_t: int | None


class WidgetLogStore:
    """Named logs of (epoch-ms, text) entries, each kept sorted by
    timestamp (a client-supplied `t` may arrive out of order; equal
    timestamps keep arrival order). Ranges are **inclusive on both
    ends**."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._times: dict[str, list[int]] = {}  # parallel to _texts, for bisect
        self._texts: dict[str, list[str]] = {}

    def append(self, log_name: str, entries: list[tuple[int | None, str]]) -> int:
        """Appends `(t, text)` entries; a `None` `t` is stamped with
        arrival time. Returns how many were stored. Raises ValueError for
        an empty name or when `MAX_LOGS` would be exceeded (a new name)."""
        if not log_name:
            raise ValueError("log name must not be empty")
        arrival = now_ms()
        with self._lock:
            if log_name not in self._times:
                if len(self._times) >= MAX_LOGS:
                    raise ValueError(f"too many logs (max {MAX_LOGS})")
                self._times[log_name] = []
                self._texts[log_name] = []
            times, texts = self._times[log_name], self._texts[log_name]
            for t, text in entries:
                stamp = arrival if t is None else int(t)
                index = bisect.bisect_right(times, stamp)  # after equals: stable
                times.insert(index, stamp)
                texts.insert(index, text[:MAX_ENTRY_TEXT_CHARS])
            excess = len(times) - MAX_ENTRIES_PER_LOG
            if excess > 0:
                del times[:excess]
                del texts[:excess]
        return len(entries)

    def query(
        self,
        log_name: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 200,
        newest_first: bool = False,
    ) -> list[LogEntry]:
        """Entries with `start_ms <= t <= end_ms` (either bound optional),
        at most `limit`: the first `limit` in range, or the last `limit`
        when `newest_first` (returned newest-first). An unknown log is
        empty."""
        with self._lock:
            times = self._times.get(log_name)
            if times is None:
                return []
            texts = self._texts[log_name]
            lo = 0 if start_ms is None else bisect.bisect_left(times, start_ms)
            hi = len(times) if end_ms is None else bisect.bisect_right(times, end_ms)
            if newest_first:
                selected = range(hi - 1, max(lo, hi - limit) - 1, -1)
            else:
                selected = range(lo, min(hi, lo + limit))
            return [LogEntry(times[i], texts[i]) for i in selected]

    def list_logs(self) -> list[LogSummary]:
        with self._lock:
            return [
                LogSummary(name, len(times), times[0] if times else None, times[-1] if times else None)
                for name, times in sorted(self._times.items())
            ]

    def clear(self) -> None:
        """For a full Desk switch, same as `EventMediator.clear_all`."""
        with self._lock:
            self._times.clear()
            self._texts.clear()


# --- Contract 2: recording desk events ---------------------------------

RECORDING_EVENT = "recording"
STOPPED_RECORDING_EVENT = "stopped_recording"
# The timecoded transcript of a recording lives at
# `<desk dir>/.desk_temp/TIMECODED_TRANSCRIPTS_DIRNAME/<recording_id>.txt`.
TIMECODED_TRANSCRIPTS_DIRNAME = "timecoded-transcripts"


def new_recording_id(started_at_ms: int) -> str:
    """Also the transcript file's stem: sortable, unique per recording."""
    return f"rec-{started_at_ms}-{secrets.token_hex(2)}"


def recording_payload(recording_id: str, started_at_ms: int) -> dict[str, Any]:
    return {"recording_id": recording_id, "started_at_ms": started_at_ms}


def stopped_recording_payload(recording_id: str, started_at_ms: int, stopped_at_ms: int) -> dict[str, Any]:
    return {"recording_id": recording_id, "started_at_ms": started_at_ms, "stopped_at_ms": stopped_at_ms}
