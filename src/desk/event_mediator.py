"""Desk's own event message channel service (TODO 6f9c51b) -- a plain
Python, GoF-mediator-pattern pub/sub core: widgets never talk to each
other directly, only ever to one shared `EventMediator` instance, which
tracks per-*instance*-id (never widget-definition-id) subscriptions and
delivers a published message to the right subscribers.

Deliberately Qt-free (thread-safety via a plain `threading.Lock` plus one
`queue.Queue` per subscribed instance, not a Qt signal) so it's usable
identically from both:

- the Local Web Server's async Bridge API handlers (background thread) --
  for `kind: "html"` widgets, see `desk.server.app`'s `events` routes, and
- `kind: "python"` widgets, in-process, via the Qt-friendly wrapper in
  `desk.shell.event_broker` (a GUI-thread `QTimer` polling `drain()`,
  never this module's own blocking `poll()`).

One instance is constructed for the whole app run (see
`desk.server.runner.start_server`, mirroring `desk.shell.bridge.GuiBridge`)
and shared by both call paths above.
"""

import json
import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_FILENAME = "MEDIATED-EVENT-LOG.tsv"
LOG_HEADER = "timestamp\tevent_name\tsender_instance_id\tpayload"

# Bridge API long-poll requests are clamped to this many seconds (TODO
# 6f9c51b's plan, "Key design decisions") so one polling widget can't pin
# a background-thread-pool worker indefinitely.
MAX_POLL_TIMEOUT_SECONDS = 30.0


@dataclass
class MediatedEvent:
    timestamp: str
    name: str
    sender_instance_id: str
    payload: Any


def _encode_payload(payload: Any) -> str:
    """JSON-encodes `payload` for one TSV log row -- this also makes the
    row TSV-safe for free, since json.dumps escapes any literal tab/
    newline inside a string value to a two-character `\\t`/`\\n` escape
    rather than emitting the raw byte, so a payload can never break the
    log's own column/row structure. Falls back to encoding `repr(payload)`
    (still run through json.dumps, so the row stays well-formed) if a
    python-widget-originated payload isn't JSON-serializable at all --
    html-widget-originated payloads always are, since they arrived
    through a JSON request body in the first place."""
    try:
        return json.dumps(payload, separators=(",", ":"))
    except (TypeError, ValueError):
        return json.dumps(repr(payload))


class EventMediator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscriptions: dict[str, set[str]] = {}
        self._queues: dict[str, "queue.Queue[MediatedEvent]"] = {}
        self._log_directory: Path | None = None
        self._log_lock = threading.Lock()

    def set_log_directory(self, directory: Path | None) -> None:
        with self._lock:
            self._log_directory = directory

    @property
    def log_path(self) -> Path | None:
        with self._lock:
            directory = self._log_directory
        return (directory / LOG_FILENAME) if directory is not None else None

    def subscribe(self, instance_id: str, name: str) -> None:
        with self._lock:
            self._subscriptions.setdefault(instance_id, set()).add(name)
            self._queues.setdefault(instance_id, queue.Queue())

    def unsubscribe(self, instance_id: str, name: str) -> None:
        with self._lock:
            names = self._subscriptions.get(instance_id)
            if names is not None:
                names.discard(name)

    def unsubscribe_all(self, instance_id: str) -> None:
        with self._lock:
            self._subscriptions.pop(instance_id, None)
            self._queues.pop(instance_id, None)

    def clear_all(self) -> None:
        """Drops every subscription/queue at once -- for a full Desk
        switch (`DeskWindow.switch_desk`, right alongside the existing
        `_html_widget_local_storage.clear()`), since every widget
        instance's frame is destroyed at that point anyway."""
        with self._lock:
            self._subscriptions.clear()
            self._queues.clear()

    def publish(self, name: str, payload: Any, sender_instance_id: str) -> MediatedEvent:
        """Logs the event, then delivers it to every *other* currently
        -subscribed instance -- the sender itself never receives its own
        publish back (the common pub/sub default; avoids trivial
        self-echo loops). See the Bridge API doc for this documented
        behavior."""
        event = MediatedEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            name=name,
            sender_instance_id=sender_instance_id,
            payload=payload,
        )
        self._log(event)
        with self._lock:
            target_queues = [
                self._queues[instance_id]
                for instance_id, names in self._subscriptions.items()
                if instance_id != sender_instance_id and name in names and instance_id in self._queues
            ]
        for q in target_queues:
            q.put(event)
        return event

    def poll(self, instance_id: str, timeout: float) -> MediatedEvent | None:
        """Blocking wait for the next message for one instance -- only
        called from a background-thread-pool worker (the Bridge API's
        long-poll route, via `run_in_executor`), never the GUI thread or
        the async event loop directly."""
        with self._lock:
            q = self._queues.get(instance_id)
        if q is None:
            return None
        try:
            return q.get(timeout=min(timeout, MAX_POLL_TIMEOUT_SECONDS))
        except queue.Empty:
            return None

    def drain(self, instance_id: str) -> list[MediatedEvent]:
        """Non-blocking: everything currently queued for one instance.
        Used by `desk.shell.event_broker.EventSubscription`'s `QTimer`
        poll, which must never block the GUI thread."""
        with self._lock:
            q = self._queues.get(instance_id)
        if q is None:
            return []
        events = []
        while True:
            try:
                events.append(q.get_nowait())
            except queue.Empty:
                break
        return events

    def _log(self, event: MediatedEvent) -> None:
        path = self.log_path
        if path is None:
            return
        row = f"{event.timestamp}\t{event.name}\t{event.sender_instance_id}\t{_encode_payload(event.payload)}\n"
        with self._log_lock:
            try:
                is_new = not path.exists()
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as f:
                    if is_new:
                        f.write(LOG_HEADER + "\n")
                    f.write(row)
            except OSError:
                pass  # best-effort logging -- must never break message delivery

    def clear_log(self) -> None:
        """Truncates the log back to just its header row (not deleted --
        a live SingleFileWatcher on it still has something valid to
        watch afterward). Used by the Event Log widget's Clear action,
        after confirmation."""
        path = self.log_path
        if path is None:
            return
        with self._log_lock:
            try:
                path.write_text(LOG_HEADER + "\n", encoding="utf-8")
            except OSError:
                pass


def parse_log(text: str) -> list[MediatedEvent]:
    """Parses MEDIATED-EVENT-LOG.tsv content (as read by the Event Log
    widget) into MediatedEvent rows, skipping the header and any
    malformed row (e.g. a partially-written line if read mid-append)
    rather than failing the whole parse."""
    events = []
    lines = text.splitlines()
    for line in lines:
        if not line or line == LOG_HEADER:
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        timestamp, name, sender_instance_id, payload_json = parts
        try:
            payload = json.loads(payload_json)
        except ValueError:
            continue
        events.append(MediatedEvent(timestamp, name, sender_instance_id, payload))
    return events
