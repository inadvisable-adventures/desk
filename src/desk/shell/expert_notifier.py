"""Finds expert-registry events the user has not been told about yet (TODO d15791d):
answers that arrived for an asker, and new open questions for the built-in
`user` expert. A daemon thread polls the registry (each poll shells out to
psql, so never on the GUI thread) and hands the findings to the GUI thread
through a Qt signal; the window turns them into top-right banners.

Polling only starts doing anything once the registry's cluster exists, so a
Desk that never uses experts never provisions Postgres for this.
"""
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from desk.shell import current_context
from desk.expert_registry import ExpertRegistry, ExpertRegistryError

POLL_INTERVAL_SECONDS = 10.0


def current_origin() -> str:
    """This Desk's identity in the registry: its directory (empty if none is known yet)."""
    directory = current_context.get_current_desk_directory()
    return str(directory) if directory is not None else ""


class ExpertNotifier(QObject):
    # A list of {"kind": "answer" | "question", "question": {...}}.
    announced = pyqtSignal(list)
    # Questions to the built-in `desk` expert nobody answered in time (already marked accepted by the fallback).
    fallback_needed = pyqtSignal(list)

    def __init__(self, registry_provider, interval: float = POLL_INTERVAL_SECONDS, parent=None,
                 origin_provider=None) -> None:
        super().__init__(parent)
        self._registry_provider = registry_provider  # a callable, so a test can swap the registry
        self._interval = interval
        self._origin_provider = origin_provider or current_origin
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="expert-notifier", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self._interval)

    def poll_once(self) -> list[dict]:
        """One poll: check in, then atomically claim this Desk's announcements (see
        ExpertRegistry.claim_announcements -- they are stamped as announced by the claim itself, so a crash can
        lose a banner but never repeat one, and no other Desk shows the same one)."""
        registry: ExpertRegistry = self._registry_provider()
        if not registry.cluster_exists():
            return []
        try:
            origin = self._origin_provider()
            registry.heartbeat(origin)
            found = registry.claim_announcements(origin)
            fallback = registry.claim_fallback(origin)
        except ExpertRegistryError:
            return []
        if fallback:
            self.fallback_needed.emit(fallback)
        if found:
            self.announced.emit(found)
        return found
