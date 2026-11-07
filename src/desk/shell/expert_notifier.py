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

from desk.expert_registry import ExpertRegistry, ExpertRegistryError

POLL_INTERVAL_SECONDS = 10.0


class ExpertNotifier(QObject):
    # A list of {"kind": "answer" | "question", "question": {...}}.
    announced = pyqtSignal(list)

    def __init__(self, registry_provider, interval: float = POLL_INTERVAL_SECONDS, parent=None) -> None:
        super().__init__(parent)
        self._registry_provider = registry_provider  # a callable, so a test can swap the registry
        self._interval = interval
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
        """One poll. Each finding is stamped as announced *before* it is emitted, so a crash can lose a
        banner but never repeat one."""
        registry: ExpertRegistry = self._registry_provider()
        if not registry.cluster_exists():
            return []
        found: list[dict] = []
        try:
            for question in registry.unannounced_answers():
                found.append({"kind": "answer", "question": question})
            for question in registry.unannounced_questions_for_user():
                found.append({"kind": "question", "question": question})
            for item in found:
                registry.mark_announced(item["question"]["question_id"], item["kind"])
        except ExpertRegistryError:
            return []
        if found:
            self.announced.emit(found)
        return found
