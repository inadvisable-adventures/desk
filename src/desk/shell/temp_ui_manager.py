import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from watchdog.events import (
    FileCreatedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from desk.git_utils import find_git_root
from desk.temp_ui import (
    DOC_FILENAME,
    DOC_TEMPLATE,
    TEMP_UI_DIRNAME,
    ensure_gitignore_entry,
    is_temp_ui_filename,
)

DEBOUNCE_SECONDS = 0.3

Confirm = Callable[[], bool]


class _Relay(QObject):
    """Owns the pyqtSignals a background watchdog callback reports
    through -- same shape as _CommitResultRelay/_FileChangeRelay in
    widgets/todo/widget.py."""

    added = pyqtSignal(Path)
    edited = pyqtSignal(Path)


class _DirectoryHandler(FileSystemEventHandler):
    """Watches a whole directory (unlike the TODO widget's single-file
    watcher) for UUID-named files being created or modified, debouncing
    per-path bursts. Ignores non-UUID filenames (including
    desk-temporary-ui.md, which naturally fails the UUID check) and
    self-recorded writes (the Question Widget's own answer-append)."""

    def __init__(self, directory: Path, relay: _Relay, manager: "TempUiManager") -> None:
        # .resolve(): watchdog's FSEvents backend reports the *resolved*
        # path, which silently never matches an unresolved directory on
        # macOS (tempfile.mkdtemp() and some real directories are
        # symlinks) -- see LEARNINGS.md's "WidgetWatcher never fires..."
        # and its TODO d25e557 recurrence.
        self._directory = directory.resolve()
        self._relay = relay
        self._manager = manager
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        # A common "atomic write" idiom -- write to a scratch name, then
        # rename into place (editors/safe-write tools routinely do this;
        # see LEARNINGS.md) -- reports as a FileMovedEvent, not
        # Created/Modified. Its meaningful path is dest_path (where the
        # file landed), not src_path (the scratch name, which never
        # matches is_temp_ui_filename anyway) -- confirmed directly that
        # without this, such a write is silently never detected at all.
        # See plans/fix-temp-ui-watcher-missed-atomic-write.md.
        if isinstance(event, FileMovedEvent):
            raw_path = event.dest_path
        elif isinstance(event, (FileCreatedEvent, FileModifiedEvent)):
            raw_path = event.src_path
        else:
            return
        path = Path(raw_path).resolve()
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
        self._observer: Observer | None = None
        self._watched_directory: Path | None = None
        self._provisioned_directory: Path | None = None
        self._last_written: dict[str, str] = {}
        # Classifies added-vs-edited by whether a filename has ever been
        # seen before (see _DirectoryHandler.on_any_event's docstring
        # comment for why this can't be decided from the raw watchdog
        # event type).
        self._known_files: set[str] = set()

    def provision(
        self, directory: Path, ask_create_dir: Confirm, ask_gitignore: Confirm
    ) -> Path | None:
        if directory == self._provisioned_directory:
            return self._watched_directory
        self._provisioned_directory = directory

        temp_dir = directory / TEMP_UI_DIRNAME
        if not temp_dir.is_dir():
            if not ask_create_dir():
                self._stop_watching()
                return None
            temp_dir.mkdir(parents=True, exist_ok=True)

        doc_path = temp_dir / DOC_FILENAME
        if not doc_path.is_file():
            doc_path.write_text(DOC_TEMPLATE)

        git_root = find_git_root(directory)
        if git_root is not None:
            ensure_gitignore_entry(git_root, ask_gitignore)

        self._start_watching(temp_dir)
        return temp_dir

    def record_own_write(self, path: Path, text: str) -> None:
        """Wired into current_context.set_temp_ui_write_recorder so the
        Question Widget's own answer-append doesn't spawn a spurious
        "edited externally" notification for itself."""
        self._last_written[path.resolve().name] = text

    def _start_watching(self, directory: Path) -> None:
        if self._observer is not None and self._watched_directory == directory:
            return
        self._stop_watching()
        self._known_files.clear()
        self._last_written.clear()
        observer = Observer()
        observer.schedule(_DirectoryHandler(directory, self._relay, self), str(directory), recursive=False)
        observer.start()
        self._observer = observer
        self._watched_directory = directory

    def _stop_watching(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer = None
        self._watched_directory = None

    def _handle_change(self, path: Path) -> None:
        if not path.is_file():
            return
        current_text = path.read_text()
        if current_text == self._last_written.get(path.name):
            return  # our own write (e.g. the Question Widget's answer-append) echoing back

        if path.name not in self._known_files:
            self._known_files.add(path.name)
            self._relay.added.emit(path)
        else:
            self._relay.edited.emit(path)

    def stop(self) -> None:
        self._stop_watching()
