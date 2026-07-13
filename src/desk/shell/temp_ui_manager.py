import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from desk.file_watch import SelfWriteMemory
from desk.git_utils import find_git_root
from desk.temp_ui import (
    DOC_FILENAME,
    TEMP_UI_DIRNAME,
    ensure_docs_current,
    ensure_gitignore_entry,
    is_temp_ui_filename,
    write_tempui_docs,
)
from desk_services.file_watcher import WatchHandle, get_service

DEBOUNCE_SECONDS = 0.3

Confirm = Callable[[], bool]


class _Relay(QObject):
    """Owns the pyqtSignals a background watchdog callback reports
    through -- same shape as _CommitResultRelay/_FileChangeRelay in
    widgets/todo/widget.py."""

    added = pyqtSignal(Path)
    edited = pyqtSignal(Path)


class _DirectoryHandler:
    """Watches a whole directory (unlike the TODO widget's single-file
    watcher) for UUID-named files being created or modified, debouncing
    per-path bursts. Ignores non-UUID filenames (including
    desk-temporary-ui.md and the other tempui-*.md docs it references,
    TODO e57ce5f -- all of which naturally fail the UUID check) and
    self-recorded writes (the Question Widget's own answer-append).

    Was a watchdog FileSystemEventHandler before TODO 578cb6b's
    migration onto the shared `desk_services.file_watcher` service,
    which now centrally handles the two gotchas this class used to
    (symlink-resolved event paths; an atomic write landing as a
    FileMovedEvent whose real path is dest_path, not src_path -- see
    LEARNINGS.md and plans/fix-temp-ui-watcher-missed-atomic-write.md).
    The old event.is_directory early-exit is dropped as redundant, not
    a behavior change: TempUiManager._handle_change's own
    `path.is_file()` check already discards directory-entry events."""

    def __init__(self, directory: Path, manager: "TempUiManager") -> None:
        self._directory = directory.resolve()
        self._manager = manager
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_change(self, path: Path) -> None:
        if path.parent != self._directory or not is_temp_ui_filename(path.name):
            return
        # A brand-new file reliably fires *both* a Created and a
        # Modified event in quick succession (the write itself modifies
        # what it just created) -- classifying "added vs. edited" from
        # whichever event happens to be the last one before the
        # debounce fires would make new files inconsistently report as
        # "edited" instead. Classification is decided once, in
        # TempUiManager._handle_change, based on whether the file has
        # ever been seen before -- not from the raw event type.
        with self._lock:
            existing = self._timers.get(path.name)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(DEBOUNCE_SECONDS, self._manager._handle_change, args=(path,))
            timer.daemon = True
            self._timers[path.name] = timer
            timer.start()


class TempUiManager(QObject):
    """Owns the .desk_temp directory watcher, directory provisioning, and
    self-write suppression for the Temporary UI feature (TODO a02b001).
    One instance per DeskWindow, for the app's lifetime -- see
    plans/temporary-ui.md."""

    file_added = pyqtSignal(Path)
    file_edited = pyqtSignal(Path)

    def __init__(self) -> None:
        super().__init__()
        self._relay = _Relay()
        self._relay.added.connect(self.file_added.emit)
        self._relay.edited.connect(self.file_edited.emit)
        self._handle: WatchHandle | None = None
        self._watched_directory: Path | None = None
        self._provisioned_directory: Path | None = None
        self._writes = SelfWriteMemory()
        # Classifies added-vs-edited by whether a filename has ever been
        # seen before (see _DirectoryHandler.on_change's inline comment
        # for why this can't be decided from the raw watchdog event
        # type).
        self._known_files: set[str] = set()

    def provision(
        self, directory: Path, ask_create_dir: Confirm, ask_gitignore: Confirm
    ) -> Path | None:
        if directory == self._provisioned_directory:
            return self._watched_directory
        self._provisioned_directory = directory

        temp_dir = directory / TEMP_UI_DIRNAME
        want_temp_dir = temp_dir.is_dir() or ask_create_dir()
        if want_temp_dir and not temp_dir.is_dir():
            # Re-checked immediately before creating (TODO 4716585):
            # ask_create_dir() can pump a modal dialog's own nested
            # event loop for an arbitrary amount of time, during which
            # the directory could already have been created by
            # something else -- if so, there's nothing left to do here.
            temp_dir.mkdir(parents=True, exist_ok=True)

        # Independent of the .desk_temp decision above (TODO 4716585):
        # these used to be one all-or-nothing confirm, but they're two
        # separate checkboxes in the New Desk dialog now, so declining
        # .desk_temp must not also silently skip .gitignore.
        git_root = find_git_root(directory)
        if git_root is not None:
            ensure_gitignore_entry(git_root, ask_gitignore)

        if not want_temp_dir:
            self._stop_watching()
            return None

        doc_path = temp_dir / DOC_FILENAME
        if not doc_path.is_file():
            # TODO e57ce5f: writes the main doc plus every split-out
            # tempui-*.md doc it references, fresh.
            write_tempui_docs(temp_dir)
        else:
            # TODO f7b1611/e57ce5f: before opening a Desk, make sure
            # the already-existing doc set's main content -- and every
            # split-out file -- isn't a stale/missing copy from before
            # some later improvement.
            ensure_docs_current(temp_dir)

        self._start_watching(temp_dir)
        return temp_dir

    def record_own_write(self, path: Path, text: str) -> None:
        """Wired into current_context.set_temp_ui_write_recorder so the
        Question Widget's own answer-append doesn't spawn a spurious
        "edited externally" notification for itself. Backed by the same
        `desk.file_watch.SelfWriteMemory` helper `SingleFileWatcher`
        uses (TODO cee6f74) -- one implementation of "was this change
        notification just an echo of our own write" instead of two."""
        self._writes.record(path.resolve().name, text)

    def _start_watching(self, directory: Path) -> None:
        if self._handle is not None and self._watched_directory == directory:
            return
        self._stop_watching()
        self._known_files.clear()
        self._writes = SelfWriteMemory()
        handler = _DirectoryHandler(directory, self)
        self._handle = get_service().watch(directory, handler.on_change, recursive=False)
        self._watched_directory = directory

    def _stop_watching(self) -> None:
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        self._watched_directory = None

    def _handle_change(self, path: Path) -> None:
        if not path.is_file():
            return
        current_text = path.read_text()
        if self._writes.is_own_write(path.name, current_text):
            return  # our own write (e.g. the Question Widget's answer-append) echoing back

        if path.name not in self._known_files:
            self._known_files.add(path.name)
            self._relay.added.emit(path)
        else:
            self._relay.edited.emit(path)

    def stop(self) -> None:
        self._stop_watching()
