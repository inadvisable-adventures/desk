import threading
import uuid
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from desk.file_watch import SelfWriteMemory
from desk.git_utils import find_git_root
from desk.shell.schema_file_watcher import SCHEMA_FILES_DIRNAME
from desk.temp_ui import (
    DOC_FILENAME,
    TEMP_UI_DIRNAME,
    TEMPUI_DOC_VERSION,
    ensure_docs_current,
    ensure_gitignore_entry,
    is_temp_ui_filename,
    sync_app_dsl_tool,
    sync_shared_components,
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
            previous_version = None
        else:
            # TODO f7b1611/e57ce5f: before opening a Desk, make sure
            # the already-existing doc set's main content -- and every
            # split-out file -- isn't a stale/missing copy from before
            # some later improvement.
            _, previous_version = ensure_docs_current(temp_dir)

        # TODO 3b1ef3d: always re-mirrored, not gated by "already
        # exists" like the doc branch above -- every open/switch gets
        # the current shared-components/ library.
        sync_shared_components(temp_dir)
        # TODO 48e3b39: same always-fresh mirroring for the
        # app-structure DSL's own codegen tool.
        sync_app_dsl_tool(temp_dir)
        # TODO 9aef267: an ephemeral home for top-level desk.state.*
        # schema files -- created once, never wiped/reseeded (unlike
        # the two syncs above, nothing here is mirrored from a
        # canonical source; a schema file is directly authored by a
        # user/agent, so there's nothing to overwrite).
        (temp_dir / SCHEMA_FILES_DIRNAME).mkdir(exist_ok=True)

        # Must run before _notify_docs_upgraded below (TODO 7c7b676):
        # _start_watching clears self._known_files, which that method
        # adds its own note's filename to.
        self._start_watching(temp_dir)

        if previous_version is not None:
            self._notify_docs_upgraded(temp_dir, previous_version)

        return temp_dir

    def _write_scratch_note(self, temp_dir: Path, title: str, body: str) -> None:
        """Shared by every same-directory Scratch-note breadcrumb this
        class writes (TODO 7c7b676/7f984ec) -- written directly and
        reported via the same file_added path a watcher-observed file
        would take (_relay.added.emit + recording the filename in
        _known_files), rather than relying on the watcher to notice
        this write itself: _start_watching's underlying
        get_service().watch(...) isn't guaranteed to already be
        observing the instant it returns, so a file written immediately
        after isn't guaranteed to be seen (the same class of concern
        TODO 578cb6b's migration had to reason about for real)."""
        note_path = temp_dir / str(uuid.uuid4())
        note_path.write_text(f"Scratch {title}\n{body}\n")
        self._known_files.add(note_path.name)
        self._relay.added.emit(note_path)

    def _notify_docs_upgraded(self, temp_dir: Path, previous_version: int) -> None:
        """A same-directory Scratch note (TODO 7c7b676) when
        ensure_docs_current found the doc set's embedded version
        genuinely differed from TEMPUI_DOC_VERSION -- not for a mere
        repair (a missing split file with an already-current version)
        or a brand-new .desk_temp, neither of which is "a convention
        changed" in the sense worth surfacing."""
        self._write_scratch_note(
            temp_dir,
            "Desk's tempui conventions changed",
            f"This project's tempui docs were just refreshed from version "
            f"{previous_version} to {TEMPUI_DOC_VERSION}. See "
            "tempui-breaking-changes.md for what changed in between -- some "
            "of it may affect widgets already built in this project.",
        )

    def notify_dev_process_peers_seeded(self, directory: Path) -> None:
        """A same-directory Scratch note (TODO 7f984ec) when
        DeskWindow._seed_development_process just copied
        shared_development_process.md/specifically-not-working-on-desk
        -itself-development-process.md into a project that already had
        its own pre-existing, pre-split development-process.md (left
        untouched, per that method's own no-overwrite rule) -- without
        this, the two new peer files land with nothing explaining what
        they are or that a manual rewrite is still needed. Called from
        DeskWindow.new_desk *after* switch_desk has provisioned
        .desk_temp and started the watcher (unlike
        _notify_docs_upgraded above, this can't run any earlier: the
        seeding itself happens before switch_desk, when there may not
        even be a .desk_temp yet to write into). A no-op if .desk_temp
        isn't currently being watched for this directory (e.g.
        create_temp_ui was declined) -- there's nowhere for the note to
        go."""
        temp_dir = directory / TEMP_UI_DIRNAME
        if self._watched_directory != temp_dir:
            return
        self._write_scratch_note(
            temp_dir,
            "development-process.md peers were just seeded",
            "This project already had its own development-process.md, so "
            "it was left untouched, but shared_development_process.md and "
            "specifically-not-working-on-desk-itself-development-process.md "
            "were just copied in alongside it. Your existing "
            "development-process.md still needs a manual rewrite to "
            "actually reference the new peer files -- see "
            "plans/fork-development-process-doc.md for the template this "
            "project's own doc split originally used. If "
            "scripts/todo_item_ids.py was also just seeded, "
            "how-to-convert-item-id-one-time.md came with it.",
        )

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
