import hashlib
import logging
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMainWindow, QMessageBox, QWidget

from desk.custom_widgets import materialize
from desk.desks import DESK_SUFFIX, Desk, WidgetState, desk_state_dict, load_desk, save_desk
from desk.file_type_registry import (
    FILE_TYPE_REGISTRY_UPDATED_EVENT,
    entry_from_dict,
    entry_to_dict,
    find_edit_handler,
    looks_like_text_file,
)
from desk.file_watch import SingleFileWatcher
from desk.hotreload import HotReloadBroker
from desk.questions_file import find_nearest_questions_file, parse_questions_file
from desk.recent_desks import add_to_mru, prune_missing_mru_entries
from desk.server.bridge_client import DOM_SNAPSHOT_JS
from desk.server.runner import ServerHandle
from desk.shell import current_context
from desk.shell.canvas import WorkspaceView
from desk.shell.chromium_widget import ChromiumWidget
from desk.shell.new_desk_dialog import NewDeskDialog
from desk.shell.python_widget import PythonWidgetHost
from desk.shell.temp_ui_manager import TempUiManager
from desk.shell.widget_frame import WidgetFrame
from desk.temp_ui import (
    CUSTOM_WIDGET_SRC_DIRNAME,
    CustomWidgetDefinition,
    DOC_FILENAME,
    MARKDOWN_KEYWORD,
    OPEN_IMAGE_KEYWORD,
    PROMOTED_WIDGET_SRC_DIRNAME,
    RESERVED_TEMPUI_KEYWORDS,
    SCRATCH_KEYWORD,
    TEMP_UI_DIRNAME,
    detect_temp_ui_kind,
    is_temp_ui_filename,
    parse_define_widget,
    parse_discuss_parking_lot_item,
    parse_lightning_round,
    parse_markdown_tempui,
    parse_open_image,
    parse_open_markdown,
    parse_scratch,
    parse_temp_ui,
    sync_custom_widgets_doc_section,
)
from desk.widgets import WidgetInfo, discover_widgets

logger = logging.getLogger(__name__)

QUESTION_WIDGET_ID = "question"
LIGHTNING_ROUND_WIDGET_ID = "lightning_round"
# The widget formerly known as "markdown_ex"/"Markdown (Extended)" --
# renamed to the new default "markdown"/"Markdown" (TODO 858752b),
# replacing the old plain widget (renamed to "markdown_old_basic" and
# deprecated, TODO 96013cf).
MARKDOWN_WIDGET_ID = "markdown"
SCRATCH_WIDGET_ID = "scratch"
CLAUDE_WIDGET_ID = "claude"
QUESTIONS_WIDGET_ID = "questions"
IMAGE_VIEWER_WIDGET_ID = "image_viewer"
EDITOR_WIDGET_ID = "editor"
CRASH_LOG_WIDGET_ID = "crash_log"
# TODO 7f51230: crash logs now live in .desk_temp/DESK-CRASH-*.log --
# matches desk.crash_handler's own filename convention.
CRASH_LOG_GLOB = "DESK-CRASH-*.log"

# Which widget kind opens a dropped file (TODO 5915ac2), by extension --
# only these widget kinds currently expose set_file. Everything not
# listed here falls back to the Editor -- Project Files' own
# double-click handling now goes through a richer viewer/editor/scrap
# fallback chain instead (TODO efdad99), but drag-and-drop here is
# still this simpler by-extension map. Raster image suffixes are deliberately
# NOT listed here (see IMAGE_DROP_SUFFIXES/_on_files_dropped below) --
# those get copy-into-.desk_temp-plus-tempui handling instead of this
# by-reference one (TODO 6e731c1). .svg maps to Image Viewer (TODO
# 4d21e7c folded the formerly-standalone SVG Viewer widget into it).
EXTERNAL_DROP_WIDGET_BY_SUFFIX = {
    ".md": MARKDOWN_WIDGET_ID,
    ".svg": IMAGE_VIEWER_WIDGET_ID,
}
# A dropped file with one of these suffixes (TODO 6e731c1) is copied
# into .desk_temp and displayed through a new OpenImage tempui file
# instead of EXTERNAL_DROP_WIDGET_BY_SUFFIX's by-reference handling --
# see _on_files_dropped/_drop_image_as_temp_ui. .svg is deliberately
# excluded: it already has correct, existing by-reference handling
# above, and isn't raster data needing a copy.
IMAGE_DROP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico"}
# Every widget kind that renders a TempUI file (TODO a02b001/TODO
# 11aeb43/TODO 42dd260/TODO f8d9cec/TODO 6e731c1) and needs the same
# instance_id-equals-source-file-uuid reconnection handling -- see
# _load_desk_widgets/_bind_temp_ui_widget. A manually-placed
# markdown/scratch/image-viewer instance's restore is a safe no-op
# under this (see _bind_temp_ui_content): its instance_id won't match
# any real .desk_temp/ filename, so it just falls through unchanged,
# same as its existing no-persistence-across-reload behavior.
TEMP_UI_WIDGET_IDS = {
    QUESTION_WIDGET_ID,
    LIGHTNING_ROUND_WIDGET_ID,
    MARKDOWN_WIDGET_ID,
    SCRATCH_WIDGET_ID,
    IMAGE_VIEWER_WIDGET_ID,
}

WIDGET_SPACING = 700
# TODO fbd0554: the well-known project-convention filename this
# codebase's own development-process.md itself names -- a plain
# literal, not a piece of shared behavior worth its own module.
DEVELOPMENT_PROCESS_FILENAME = "development-process.md"
# TODO 1a96c9f: development-process.md's own "When working on Desk
# itself" section points to these two -- seeded alongside it (see
# _seed_development_process) since a new project needs all three
# together: the top-level file's relative links to them would
# otherwise be dead, and shared_development_process.md carries the
# actual generic process content development-process.md itself no
# longer does.
SHARED_DEVELOPMENT_PROCESS_FILENAME = "shared_development_process.md"
NOT_DESK_DEVELOPMENT_PROCESS_FILENAME = "specifically-not-working-on-desk-itself-development-process.md"
# TODO cb2790d: a new Desk's default-widgets seeding looks for this exact
# filename, same convention as the other well-known-filename constants
# above.
README_FILENAME = "README.md"

Confirm = Callable[[], bool]


@dataclass
class NewDeskProvisioning:
    """Pre-decided answers from `NewDeskDialog` (TODO 4716585), passed
    through `new_desk` -> `switch_desk` -> `_provision_temp_ui` so
    provisioning never re-prompts for something the single New Desk
    dialog already asked."""

    create_temp_ui: bool
    create_gitignore: bool


class DeskWindow(QMainWindow):
    """Owns the single currently-open Desk for this window (only one
    window exists for now, and it can only have one Desk open at a time —
    see design-docs/architecture.md's Desk Model)."""

    def __init__(
        self,
        widgets: dict[str, WidgetInfo],
        handle: ServerHandle,
        broker: HotReloadBroker,
        desk_path: Path,
        widgets_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Desk")
        self.resize(1280, 800)

        self._widgets = widgets
        self._widgets_dir = widgets_dir
        self._handle = handle
        self._broker = broker

        self.view = WorkspaceView()
        self.setCentralWidget(self.view)

        self.view.desk_picker.desk_chosen.connect(self._on_desk_chosen)
        self.view.desk_picker.browse_requested.connect(self._on_browse_requested)
        self.view.desk_picker.new_desk_requested.connect(self._on_new_desk_requested)
        self.view.desk_picker.rename_requested.connect(self._on_rename_requested)
        self.view.desk_picker.directory_change_requested.connect(
            self._on_directory_change_requested
        )
        self.view.set_widget_catalog(widgets)
        self.view.widget_add_requested.connect(self._on_widget_add_requested)
        self.view.widget_close_requested.connect(self._on_widget_close_requested)
        self.view.files_dropped.connect(self._on_files_dropped)
        self.view.paste_requested.connect(self._on_paste_requested)
        self.view.tempui_promote_requested.connect(self._on_tempui_promote_requested)
        self.view.widget_stale_clicked.connect(self._on_widget_stale_clicked)
        if widgets_dir is not None:
            broker.widget_changed.connect(self._on_widget_changed_refresh_catalog)

        # Tempui-DSL-defined custom widgets (TODO 91b3f42): keyword ->
        # its CustomWidgetDefinition/source ("tempui" | "desk")/
        # originating .desk_temp file path (tempui-sourced only, used
        # to delete it on promotion). See _register_custom_widget.
        self._custom_widget_definitions: dict[str, CustomWidgetDefinition] = {}
        self._custom_widget_sources: dict[str, str] = {}
        self._custom_widget_source_paths: dict[str, Path] = {}
        # keyword -> a short content hash of its currently-registered
        # definition (TODO 5995ffd). See _register_custom_widget (who
        # computes it) and _refresh_stale_indicators_for (who compares
        # it against every already-placed instance's own
        # WidgetFrame.placed_content_hash).
        self._custom_widget_content_hash: dict[str, str] = {}

        # kind:"html" widget-local storage (TODO 5734529): instance_id
        # -> whatever that instance's own JS last pushed via the Bridge
        # API's self.setLocalStorage. See _get_widget_local_storage/
        # _bind_widget_local_storage.
        self._html_widget_local_storage: dict[str, dict] = {}

        # The event mediator message channel (TODO 6f9c51b) -- the same
        # instance the Local Web Server's Bridge API routes already use
        # (constructed once in desk.server.runner.start_server, shared via
        # handle.event_mediator), so a publish from a kind:"html" widget
        # and a subscribe from a kind:"python" widget go through the exact
        # same mediator. See _bind_event_mediator/_refresh_picker below.
        self._event_mediator = handle.event_mediator

        # (caller_instance_id, target_instance_id) pairs the Desk user has
        # already approved for the introspect Bridge capability (TODO
        # 9767c1a) -- in-memory, per-session only, never persisted to
        # .desk/disk (a security-relevant grant; "ask again next time" is
        # the safe default absent a real, designed persistence mechanism).
        # See request_introspect_permission/switch_desk.
        self._introspect_grants: set[tuple[str, str]] = set()

        self._temp_ui_manager = TempUiManager()
        self._temp_ui_manager.file_added.connect(self._on_temp_ui_file_added)
        self._temp_ui_manager.file_edited.connect(self._on_temp_ui_file_edited)

        # Global QUESTIONS.md watcher (TODO a801180) -- unlike the
        # per-widget SingleFileWatcher a Questions widget instance owns
        # itself, this one lives for the whole window so a newly-added
        # question notifies even when no Questions widget is currently
        # open, matching the .desk_temp mechanism's own "notify
        # regardless of whether a widget for it exists yet" behavior.
        self._questions_watcher = SingleFileWatcher(self)
        self._questions_watcher.changed.connect(self._on_questions_file_changed)
        self._questions_path: Path | None = None
        self._known_question_keys: set[tuple] | None = None

        self.current_desk = load_desk(desk_path) if desk_path.is_file() else Desk(path=desk_path)
        # Must run before _load_desk_widgets: it's the only place that
        # populates current_context's current-desk-directory (a plain,
        # resolved-once-at-construction module global -- see
        # desk.shell.current_context), and _load_desk_widgets can
        # construct a python widget (e.g. a saved TodoWidget) that reads
        # it synchronously in its own __init__. Doing this after used to
        # be harmless (both calls finish before the event loop starts, so
        # a widget's own manual Reload button could still pick up the
        # correct directory) but became a permanent bug once TODO
        # d25e557 replaced that button with file-watching, which never
        # fires on initial load -- see plans/fix-todo-widget-load
        # -regression.md.
        self._refresh_picker()
        # Registers this Desk's own promoted custom widgets (TODO
        # 91b3f42) before _provision_temp_ui/_load_desk_widgets below --
        # doesn't need .desk_temp to exist at all (sourced from the
        # .desk file itself). _provision_temp_ui now runs before
        # _load_desk_widgets (matching switch_desk's own, already
        # -existing ordering below -- this was a harmless asymmetry
        # between the two, not an intentional constraint: the one
        # documented ordering requirement near here is about
        # _refresh_picker above, unaffected by moving this), so a
        # still-tempui-sourced (not yet promoted) custom widget's
        # .desk_temp definition file can be scanned and registered too,
        # in time for _load_desk_widgets to resolve any already-placed
        # instance of it.
        self._register_custom_widgets_from_desk(self.current_desk)
        self._provision_temp_ui()
        self._register_custom_widgets_from_desk_temp(self.current_desk.directory)
        self._load_desk_widgets(self.current_desk)
        self.view.set_view_state(
            self.current_desk.pan_x, self.current_desk.pan_y, self.current_desk.scale
        )
        current_context.set_widget_opener(self.open_widget_content)
        current_context.set_centered_widget_opener(self.open_widget_content_centered)
        current_context.set_editor_or_scrap_opener(self.open_editor_or_scrap)
        current_context.set_temp_ui_write_recorder(self._temp_ui_manager.record_own_write)
        current_context.set_main_window(self)
        current_context.set_widget_path_resolver(self.view.describe_widget_at_global_pos)
        current_context.set_discuss_starter(self.start_discussion)
        current_context.set_event_mediator(self._event_mediator)
        current_context.set_widget_zoomer(self.zoom_to_widget_by_instance_id)
        current_context.set_widget_display_name_resolver(self._display_name_for_instance)
        self._sync_tempui_doc()
        self._open_crash_log_widgets()

    def _load_desk_widgets(self, desk: Desk) -> None:
        if desk.widgets:
            for state in desk.widgets:
                widget = self._widgets.get(state.widget_id)
                if widget is None:
                    continue
                frame = self._place_widget(
                    state.widget_id,
                    widget,
                    (state.x, state.y),
                    (round(state.width), round(state.height)),
                    instance_id=state.instance_id,
                    restore=True,
                )
                if state.widget_id in TEMP_UI_WIDGET_IDS:
                    # A TempUI-backed widget's instance_id is always its
                    # source file's uuid (TODO a02b001, TODO 11aeb43) --
                    # this is how it reconnects to the right .desk_temp
                    # file across a restart/reload without needing any
                    # change to the fixed build() -> QWidget contract
                    # every widget kind relies on. See
                    # plans/temporary-ui.md/plans/lightning-round-tempui.md.
                    self._bind_temp_ui_widget(frame, desk.directory, state.instance_id)
                if state.widget_id == CRASH_LOG_WIDGET_ID:
                    # Same "instance_id equals source filename"
                    # reconnection idea as the tempui widgets above, just
                    # keyed by the crash log's own filename rather than a
                    # DSL-detected uuid (TODO 7f51230) -- lets a Crash Log
                    # widget the user left open survive a restart without
                    # _open_crash_log_widgets treating it as new.
                    self._bind_crash_log_widget(frame, desk.directory, state.instance_id)
                self._bind_widget_local_storage(frame, state.state)
                if state.locked:
                    frame.set_locked(True)
                if state.placed_content_hash is not None:
                    # TODO 5995ffd: apply the hash this instance was
                    # placed with, then compare against whatever's
                    # currently registered for this keyword -- the main
                    # case this whole feature is for: a Desk reopened
                    # after the widget's source changed since this
                    # instance was last saved.
                    frame.placed_content_hash = state.placed_content_hash
                    current_hash = self._custom_widget_content_hash.get(state.widget_id)
                    frame.set_stale(current_hash is not None and current_hash != state.placed_content_hash)
        else:
            self._seed_new_desk_widgets(desk)

    def _seed_new_desk_widgets(self, desk: Desk) -> None:
        """A Desk with no saved widgets (a genuinely new Desk, in
        practice -- see plans/new-desk-default-widgets.md) used to get
        every discovered widget placed side by side, a leftover
        bootstrapping default rather than a meaningful onboarding
        experience (TODO cb2790d). Instead: a Markdown viewer on the
        project's README.md if it has one, else a Scratch widget seeded
        with a minimal starter template."""
        readme_path = desk.directory / README_FILENAME
        if readme_path.is_file():
            widget = self._widgets.get(MARKDOWN_WIDGET_ID)
            if widget is None:
                return
            content = self.open_widget_content(MARKDOWN_WIDGET_ID, pos=(0, 0), size=widget.default_size)
            if content is not None and hasattr(content, "set_file"):
                content.set_file(readme_path)
            return

        widget = self._widgets.get(SCRATCH_WIDGET_ID)
        if widget is None:
            return
        content = self.open_widget_content(SCRATCH_WIDGET_ID, pos=(0, 0), size=widget.default_size)
        if content is None:
            return
        title = f"{desk.name} README"
        if hasattr(content, "set_label"):
            content.set_label(title)
        if hasattr(content, "body"):
            content.body.setPlainText(f"# {title}\n\n## What this project is about or exploring...\n")

    def _place_widget(
        self,
        widget_id: str,
        widget: WidgetInfo,
        pos: tuple[float, float],
        size: tuple[int, int] | None,
        instance_id: str | None = None,
        restore: bool = False,
        claude_extra_instructions: str = "",
    ) -> WidgetFrame:
        if widget_id == CLAUDE_WIDGET_ID and instance_id is None:
            # A claude widget's instance_id doubles as its claude
            # --session-id, which must be a valid UUID -- so a fresh
            # placement needs a full uuid4, not the default 8-hex-char
            # instance_id. A restore passes its saved (already-uuid)
            # instance_id through. See plans/claude-widget-session
            # -resume.md.
            instance_id = str(uuid.uuid4())
        if widget.kind == "python":
            host = PythonWidgetHost(widget_id, widget.path, widget.entry, self._broker)
            proxy = self.view.add_widget(
                host, title=widget.name, pos=pos, size=size, instance_id=instance_id
            )
        else:
            # Resolved here, before ChromiumWidget's own construction
            # (TODO 5734529), rather than left to WidgetFrame's usual
            # internal default: the Bridge client script's source is
            # baked in at construction time, so the instance id it
            # embeds (for the Bridge API's self.getLocalStorage/
            # setLocalStorage, keyed per-instance) has to be known
            # before that call, not set retroactively afterward.
            if instance_id is None:
                instance_id = uuid.uuid4().hex[:8]
            chromium_widget = ChromiumWidget(
                widget_id,
                instance_id,
                self._handle.widget_url(widget_id),
                self._handle.token,
                self._broker,
            )
            proxy = self.view.add_widget(
                chromium_widget, title=widget.name, pos=pos, size=size, instance_id=instance_id
            )
        frame = proxy.widget()
        if widget_id == CLAUDE_WIDGET_ID:
            self._bind_claude_widget(
                frame, resume=restore, extra_instructions=claude_extra_instructions
            )
        self._bind_external_indicator(frame)
        self._bind_event_mediator(frame)
        # Only while still tempui-sourced (TODO 6857997) -- once
        # promoted, the widget's [TEMPUI] button has nothing left to
        # offer, so it never shows for a "desk"-sourced instance,
        # freshly placed or restored alike.
        if self._custom_widget_sources.get(widget_id) == "tempui":
            frame.set_tempui_promotable(True)
        # TODO 5995ffd: a *fresh* placement is always current by
        # construction -- it's about to load whatever's registered
        # right now. A restored instance instead gets its saved hash
        # applied by _load_desk_widgets, since that's the one that can
        # legitimately be stale.
        if not restore:
            current_hash = self._custom_widget_content_hash.get(widget_id)
            if current_hash is not None:
                frame.placed_content_hash = current_hash
                frame.set_stale(False)
        return frame

    def _bind_external_indicator(self, frame: WidgetFrame) -> None:
        """Wires a freshly-placed widget's "[EXTERNAL]" titlebar marker
        (TODO a053e3a), duck-typed the same way as `hasattr(content,
        "set_file")` elsewhere in this file: any widget exposing
        `external_path_changed` gets it connected, plus one immediate
        `refresh_external_path_status()` call, since the widget may already
        have loaded its file during its own `__init__`/`build()` --
        before this connection could possibly have existed."""
        if not isinstance(frame.content, PythonWidgetHost):
            return
        content = frame.content.current
        if content is None or not hasattr(content, "external_path_changed"):
            return
        content.external_path_changed.connect(frame.set_external)
        content.refresh_external_path_status()

    def _bind_event_mediator(self, frame: WidgetFrame) -> None:
        """Wires a freshly-placed python widget to the event mediator
        message channel (TODO 6f9c51b), duck-typed the same way as
        _bind_external_indicator: any widget exposing
        `bind_event_mediator(instance_id, mediator)` gets it called with
        its own real instance id (never the widget-definition id) and the
        shared EventMediator instance -- the same "resolved after
        build(), not through it" shape _bind_claude_widget already
        established for start_session. A widget that doesn't define this
        method is simply left alone; publishing/subscribing is opt-in."""
        if not isinstance(frame.content, PythonWidgetHost):
            return
        content = frame.content.current
        if content is None or not hasattr(content, "bind_event_mediator"):
            return
        content.bind_event_mediator(frame.instance_id, self._event_mediator)

    def _bind_claude_widget(
        self, frame: WidgetFrame, resume: bool, extra_instructions: str = ""
    ) -> None:
        """Launches `claude` in a just-placed claude widget, bound to the
        widget's instance_id as its session id -- fresh (--session-id +
        prompt) or resuming (--resume, no prompt). Duck-typed on
        start_session so window.py needn't import the widget class,
        matching _bind_temp_ui_widget's style. extra_instructions (TODO
        c0875bc) is appended to the fresh-launch prompt only -- e.g. a
        tempui DiscussParkingLotItem file's "let's discuss ..." text --
        and ignored on resume, same as the rest of the initial prompt."""
        if not isinstance(frame.content, PythonWidgetHost):
            return
        content = frame.content.current
        if content is not None and hasattr(content, "start_session"):
            content.start_session(frame.instance_id, resume=resume, extra_instructions=extra_instructions)
            # Quitting claude ends the PTY (it's exec'd -- see the claude
            # widget); close the widget then, rather than leaving it (TODO
            # 5ddbef0). Deferred so removal doesn't run synchronously
            # inside the QSocketNotifier callback that detected EOF, which
            # would delete the widget out from under its own notifier.
            instance_id = frame.instance_id
            content.process_exited.connect(
                lambda iid=instance_id: QTimer.singleShot(
                    0, lambda: self.close_widget_by_instance_id(iid)
                )
            )

    def _place_discuss_claude_widget(
        self,
        source_label: str,
        item_text: str = "",
        parking_lot_line: int | None = None,
        instance_id: str | None = None,
    ) -> WidgetFrame | None:
        """Places a new claude widget with a fresh session prompted to
        discuss something -- shared by the tempui DiscussParkingLotItem
        keyword's _activate_temp_ui branch (TODO c0875bc,
        source_label="PARKINGLOT.md") and start_discussion below (TODO
        46e1b42). What to discuss is either a line number in
        source_label (parking_lot_line, TODO 624ff3a -- the new session
        reads that file itself rather than being handed a copy of the
        item's text, which could break the launch for a long item) or,
        for the Questions-widget path, the full item_text verbatim
        (unaffected by that TODO -- QUESTIONS.md entries aren't
        line-number-addressed the way PARKINGLOT.md items are, and
        this path hasn't shown the same launch problem). Either way, a
        shared trailing instruction tells the new session to have the
        discussion right there instead of starting another new Desk
        discussion of its own -- delivered via a standalone
        `.desk_temp` instructions file, not spliced into the launch
        command line itself (TODO 51be2bc, see
        _write_discuss_instructions_file). Returns None (placing
        nothing) if the "claude" widget kind isn't registered."""
        widget = self._widgets.get(CLAUDE_WIDGET_ID)
        if widget is None:
            return None
        if parking_lot_line is not None:
            what = (
                f"the item starting at line {parking_lot_line} of {source_label} -- "
                f"read that file yourself for its current, full text (line numbers "
                f"may have shifted slightly if the file has changed since this "
                f"reference was written; use the nearby heading as an anchor if the "
                f"line itself looks off)"
            )
        else:
            what = f"an item from {source_label}: {item_text}"
        instructions_body = (
            f"Discuss {what}.\n\n"
            f"Have this discussion here, in this session -- do not "
            f"immediately start a new Desk discussion of your own about it "
            f"(for example by writing another DiscussParkingLotItem tempui "
            f"file) unless the user explicitly asks for that."
        )
        extra_instructions = self._write_discuss_instructions_file(instructions_body)
        center = self.view.mapToScene(self.view.viewport().rect().center())
        return self._place_widget(
            CLAUDE_WIDGET_ID,
            widget,
            (center.x(), center.y()),
            widget.default_size,
            instance_id=instance_id,
            claude_extra_instructions=extra_instructions,
        )

    def _write_discuss_instructions_file(self, body: str) -> str:
        """Writes a Discuss session's actual instructions to a
        standalone file under `.desk_temp`, rather than splicing them
        into the claude launch command line -- see TODO 51be2bc. A
        long, hand-written-prose command line typed whole into an
        interactive PTY in one shot (ClaudeWidget.type_into_shell) is
        risky regardless of correct shell-quoting (TODO fc17b55/TODO
        51be2bc): this sidesteps that entirely by keeping the command
        line itself short and free of any `'` character, no matter how
        long or apostrophe-heavy the actual discussion content is.
        Returns the short instruction to splice in instead. The file's
        name is deliberately not a bare UUID (a random hex token with a
        prefix and extension instead), so the temp-ui file watcher --
        which treats any bare-UUID-named file in this directory as a
        new temp-ui widget, see is_temp_ui_filename -- never mistakes
        it for one."""
        directory = current_context.get_current_desk_directory()
        if directory is None:
            # No current Desk directory known yet (an edge case, not
            # the normal path) -- fall back to the old inline approach
            # rather than crashing the whole widget placement.
            return f" {body}"
        temp_dir = directory / TEMP_UI_DIRNAME
        temp_dir.mkdir(parents=True, exist_ok=True)
        path = temp_dir / f"discuss-instructions-{uuid.uuid4().hex}.md"
        path.write_text(body, encoding="utf-8")
        return f" Read the file at {path} now and follow its instructions for what to discuss and how."

    def start_discussion(
        self, source_label: str, item_text: str = "", parking_lot_line: int | None = None
    ) -> None:
        """The current_context "discuss starter" hook (TODO 46e1b42) --
        lets a python widget (the Questions widget's own Discuss
        button, and the Parking Lot widget's own per-row Discuss
        button, TODO a48e968) kick off the same new-claude-session
        discussion flow as the tempui DiscussParkingLotItem keyword,
        without needing to import desk.shell.window directly. Each call
        is an independent, fresh session (no instance_id/dedup --
        unlike a tempui file, there's no natural stable identity to
        dedup a button click against). `item_text` defaults to "" so a
        caller that already has a reliable `parking_lot_line` (TODO
        624ff3a) doesn't need to pass an unused positional -- see
        _place_discuss_claude_widget for how the two are used."""
        self._place_discuss_claude_widget(source_label, item_text, parking_lot_line)

    def open_widget(
        self,
        widget_id: str,
        pos: tuple[float, float] | None = None,
        size: tuple[int, int] | None = None,
        instance_id: str | None = None,
    ) -> str:
        """Places a new widget instance, returning its instance_id. Used by
        the Bridge API's widgets.open (see plans/desk-bridge-api.md) and
        available for any other programmatic placement need. An explicit
        instance_id is used by the Temporary UI feature (TODO a02b001) to
        make a Question Widget's instance_id equal to its source file's
        uuid."""
        widget = self._widgets[widget_id]
        frame = self._place_widget(
            widget_id, widget, pos or (0, 0), size or widget.default_size, instance_id=instance_id
        )
        return frame.instance_id

    def open_widget_content(
        self,
        widget_id: str,
        pos: tuple[float, float] | None = None,
        size: tuple[int, int] | None = None,
        instance_id: str | None = None,
    ) -> QWidget | None:
        """Like open_widget, but returns the actual widget instance built
        by the placed widget's own widget.py:build() rather than just an
        instance id -- for callers (e.g. the TODO widget's edit-conflict
        handling, TODO d25e557) that need to configure the new instance's
        content immediately, not just place it. Returns None for `kind:
        "html"` widgets, or if the build failed (only the error
        placeholder from PythonWidgetHost._rebuild exists) -- see
        desk.shell.current_context's widget-opener hook."""
        instance_id = self.open_widget(widget_id, pos, size, instance_id)
        frame = self.find_frame_by_instance_id(instance_id)
        if frame is None or not isinstance(frame.content, PythonWidgetHost):
            return None
        return frame.content.current

    def open_widget_content_centered(
        self, widget_id: str, size: tuple[int, int] | None = None, instance_id: str | None = None
    ) -> QWidget | None:
        """Like open_widget_content, but placed centered in the current
        view (TODO efdad99) instead of open_widget's own `(0, 0)`
        default -- the same centering math
        `_place_discuss_claude_widget`/`_auto_place_new_custom_widget`
        already use. Bound to `current_context
        .set_centered_widget_opener` for a `kind: "python"` widget that
        wants this placement convention without reaching into the
        view/scene directly."""
        widget = self._widgets.get(widget_id)
        if widget is None:
            return None
        center = self.view.mapToScene(self.view.viewport().rect().center())
        return self.open_widget_content(
            widget_id, pos=(center.x(), center.y()), size=size or widget.default_size, instance_id=instance_id
        )

    def open_editor_or_scrap(self, path: Path) -> None:
        """The shared "open an editor for `path`, or fall back to an
        explanatory Scratch note" service (TODO da4f9c0) -- extracted
        from what TODO efdad99 originally built inline in
        ProjectFilesWidget._open_file's own edit-or-scrap step, so
        every viewer widget's Edit button (image_viewer/markdown)
        reuses this exact logic instead of each carrying its own copy.
        Bound to current_context.set_editor_or_scrap_opener."""
        registry = [entry_from_dict(d) for d in self.get_file_type_registry_dicts()]
        widget_id = find_edit_handler(registry, path)
        if widget_id is None and looks_like_text_file(path):
            widget_id = EDITOR_WIDGET_ID
        if widget_id is not None:
            widget = self.open_widget_content_centered(widget_id)
            if widget is not None and hasattr(widget, "set_file"):
                # A broken set_file() must never propagate out of here
                # (TODO 810a5d6) -- this may run inside a Qt slot (a
                # viewer widget's Edit button click), and an uncaught
                # exception there is fatal to the whole process in
                # this PyQt6 setup.
                try:
                    widget.set_file(path)
                except Exception:
                    logger.error("Failed to open %s in the %r widget", path, widget_id, exc_info=True)
            return
        scratch = self.open_widget_content_centered(SCRATCH_WIDGET_ID)
        if scratch is None or not hasattr(scratch, "set_label") or not hasattr(scratch, "body"):
            return
        scratch.set_label(f"Can't open {path.name}")
        scratch.body.setPlainText(
            f"No editor is registered for this file type "
            f"({path.suffix or 'no extension'}), and it doesn't look like plain text."
        )

    def _bind_temp_ui_widget(self, frame: WidgetFrame, directory: Path, uuid_str: str) -> None:
        if not isinstance(frame.content, PythonWidgetHost):
            return
        content = frame.content.current
        if content is not None:
            self._bind_temp_ui_content(content, directory / TEMP_UI_DIRNAME / uuid_str, directory)

    def _bind_crash_log_widget(self, frame: WidgetFrame, directory: Path, filename: str) -> None:
        """Points a Crash Log widget instance at its log file (TODO
        7f51230) -- used both by _open_crash_log_widgets (fresh
        placement) and _load_desk_widgets' restore path, same "one
        place decides the binding" shape as _bind_temp_ui_content.
        Also wires the widget's `dismissed` signal (emitted after the
        user confirms deleting the log file) to actually remove this
        frame, mirroring how the Claude widget's `process_exited`
        signal already triggers close_widget_by_instance_id."""
        if not isinstance(frame.content, PythonWidgetHost):
            return
        content = frame.content.current
        if content is None:
            return
        if hasattr(content, "set_file"):
            content.set_file(directory / TEMP_UI_DIRNAME / filename)
        if hasattr(content, "dismissed"):
            instance_id = frame.instance_id
            content.dismissed.connect(lambda: self.close_widget_by_instance_id(instance_id))

    def _open_crash_log_widgets(self) -> None:
        """On app startup (TODO 7f51230), opens a fresh Crash Log widget
        for every `.desk_temp/DESK-CRASH-*.log` file that isn't already
        covered by a restored frame (find_frame_by_instance_id, keyed by
        the log's own filename -- see _bind_crash_log_widget). Scoped to
        startup only, not re-run on every desk switch. Leaving a widget
        open persists it like any other placed widget (_capture_desk_state
        saves every current frame); closing it without deleting the file
        means it reopens next startup -- deliberate, see
        plans/crash-log-widget.md."""
        directory = self.current_desk.directory
        temp_dir = directory / TEMP_UI_DIRNAME
        if not temp_dir.is_dir():
            return
        widget = self._widgets.get(CRASH_LOG_WIDGET_ID)
        if widget is None:
            return
        for index, path in enumerate(sorted(temp_dir.glob(CRASH_LOG_GLOB))):
            if self.find_frame_by_instance_id(path.name) is not None:
                continue
            pos = (index * WIDGET_SPACING, WIDGET_SPACING)
            frame = self._place_widget(
                CRASH_LOG_WIDGET_ID, widget, pos, widget.default_size, instance_id=path.name
            )
            self._bind_crash_log_widget(frame, directory, path.name)

    def _bind_widget_local_storage(self, frame: WidgetFrame, data: dict) -> None:
        """Restores a widget's "widget-local storage" (TODO fb76057) --
        only called from the Desk-reload restore path, since a fresh
        placement has no prior data to restore. Duck-typed the same way
        `hasattr(content, "set_file")` already is elsewhere in this
        file: a `python`-kind widget that doesn't implement
        `set_widget_local_storage` is a safe no-op, not an error.

        A `kind: "html"` widget (TODO 5734529) has no such Python
        -level method to call -- its own JS restores itself by calling
        the Bridge API's `self.getLocalStorage()`, which reads from
        `_html_widget_local_storage`. Seeding that dict here, *before*
        `ChromiumWidget.load()`'s page has any chance to run its own
        startup JS (this call is synchronous Python; the page's script
        only runs later, asynchronously), means a widget calling
        `getLocalStorage()` from its own startup code always sees the
        restored data, never a race against an empty default."""
        if isinstance(frame.content, PythonWidgetHost):
            content = frame.content.current
            if content is None or not hasattr(content, "set_widget_local_storage"):
                return
            content.set_widget_local_storage(data)
        elif isinstance(frame.content, ChromiumWidget):
            self._html_widget_local_storage[frame.instance_id] = data

    def _get_widget_local_storage(self, frame: WidgetFrame) -> dict:
        """The counterpart read side, called by `_capture_desk_state`
        on every save -- pull-based, not push-based, since a Desk save
        already re-reads every other per-widget field (geometry) fresh
        at save time rather than tracking live changes. A `python`-kind
        widget that doesn't implement `get_widget_local_storage`
        contributes an empty dict, same as it always implicitly had
        before this TODO.

        A `kind: "html"` widget (TODO 5734529) instead contributes
        whatever its own JS most recently pushed via the Bridge API's
        `self.setLocalStorage(data)` -- `_html_widget_local_storage`,
        not re-read from the widget itself (there's no synchronous way
        to ask a browser page "what's your current state" the way a
        Python method call can)."""
        if isinstance(frame.content, PythonWidgetHost):
            content = frame.content.current
            if content is None or not hasattr(content, "get_widget_local_storage"):
                return {}
            return content.get_widget_local_storage()
        if isinstance(frame.content, ChromiumWidget):
            return self._html_widget_local_storage.get(frame.instance_id, {})
        return {}

    def get_html_widget_local_storage(self, instance_id: str) -> dict:
        """The Bridge API's `self.getLocalStorage` (TODO 5734529),
        called via `GuiBridge` from the (background-thread) Local Web
        Server. `{}` for an instance that's never pushed anything yet
        (a brand-new widget with nothing to restore), not an error."""
        return self._html_widget_local_storage.get(instance_id, {})

    def get_widget_info(self, widget_id: str) -> WidgetInfo | None:
        """The Bridge API's `require_caller` fallback (TODO f693275),
        called via `GuiBridge` from the (background-thread) Local Web
        Server: `self._widgets` holds both real, on-disk widgets *and*
        registered tempui-DSL-defined custom widgets (TODO 91b3f42,
        `_register_custom_widget`), unlike `discover_widgets(widgets_dir)`
        (a pure filesystem scan), which can never find the latter --
        see PARKINGLOT.md's former entry on this, now resolved here."""
        return self._widgets.get(widget_id)

    def _display_name_for_instance(self, instance_id: str) -> str:
        """A human-readable label for a placed widget instance (its
        kind's display name plus a short instance-id fragment) -- used
        by the introspect permission dialog (TODO 9767c1a) so the Desk
        user sees "Browser (a1b2c3d4)", not a bare instance id. Falls
        back to the raw instance id if the frame can't be found (should
        not normally happen for a caller that just made a live Bridge
        request, but this is a display label, not a security check --
        never worth raising over)."""
        frame = self.find_frame_by_instance_id(instance_id)
        if frame is None:
            return instance_id
        widget_info = self._widgets.get(frame.content.widget_id)
        kind_name = widget_info.name if widget_info is not None else frame.content.widget_id
        return f"{kind_name} ({instance_id[:8]})"

    def request_introspect_permission(self, caller_instance_id: str, target_instance_id: str) -> bool:
        """The introspect Bridge capability's permission gate (TODO
        9767c1a), called via `GuiBridge` from the (background-thread)
        Local Web Server: unlike every other Bridge capability (a
        static declaration in the caller's own manifest/`DefineWidget`),
        this also requires the Desk *user*'s in-the-moment confirmation
        -- inspecting another widget's rendered DOM and console output
        is materially more sensitive than anything else the Bridge API
        currently grants. Shows a blocking confirmation dialog (the same
        `_confirm_fn`/`QMessageBox.question` shape every other
        consequential action already uses) the first time this (caller,
        target) pair asks in this session; a later call for the same
        pair reuses the recorded grant without re-prompting (a widget
        that legitimately polls another's DOM/console repeatedly -- e.g.
        a live viewer -- shouldn't be re-prompted every call). Grants
        are in-memory only, cleared on `switch_desk`, never persisted to
        `.desk`/disk."""
        grant_key = (caller_instance_id, target_instance_id)
        if grant_key in self._introspect_grants:
            return True
        caller_name = self._display_name_for_instance(caller_instance_id)
        target_name = self._display_name_for_instance(target_instance_id)
        approved = self._confirm_fn(
            "Allow DOM/Console Inspection?",
            f"“{caller_name}” wants to inspect “{target_name}”’s DOM and console log. Allow?",
        )()
        if approved:
            self._introspect_grants.add(grant_key)
        return approved

    def start_dom_snapshot(self, target_instance_id: str, resolve: Callable[[object], None]) -> None:
        """The introspect Bridge capability's `GuiBridge.call_async`
        starter (TODO 9767c1a) -- must run on the GUI thread and must
        never block it (see `GuiBridge.call_async`'s own docstring for
        why): kicks off the target's own `QWebEnginePage.runJavaScript`
        (genuinely async -- its own callback fires later, still on the
        GUI thread) and calls `resolve` once that callback delivers the
        DOM tree, bundled with the target's already-available
        (synchronous) console log. Resolves with `{"error": ...}`
        (never raises) if the target instance isn't found or isn't a
        `kind: "html"` widget -- there's nothing to snapshot either
        way, and this runs from an async callback context where a raised
        exception wouldn't reach the original caller anyway."""
        frame = self.find_frame_by_instance_id(target_instance_id)
        if frame is None or not isinstance(frame.content, ChromiumWidget):
            resolve({"error": f"Unknown or non-html target widget: {target_instance_id!r}"})
            return
        console_log = [
            {"level": entry.level, "message": entry.message, "line": entry.line, "source": entry.source}
            for entry in frame.content.get_console_log()
        ]
        frame.content.page().runJavaScript(
            DOM_SNAPSHOT_JS, lambda dom: resolve({"dom": dom, "console": console_log})
        )

    def set_html_widget_local_storage(self, instance_id: str, data: dict) -> None:
        """The Bridge API's `self.setLocalStorage` (TODO 5734529) --
        just updates the in-memory store; like the `python`-kind
        equivalent, this is pull-based from the *next* actual Desk
        save (`_get_widget_local_storage` above), not an immediate
        disk write on every call."""
        self._html_widget_local_storage[instance_id] = data

    def _bind_temp_ui_content(self, content, tempui_path: Path, directory: Path) -> None:
        """Wires a freshly-placed or restored TempUI-backed widget's
        content to its source tempui_path -- Question/LightningRound
        render the tempui file itself (set_source_file); OpenMarkdown
        instead parses out its *target* Markdown path and opens that
        (set_file), since it's a pure fire-and-forget viewer action
        with no answer to render back into the tempui file. OpenImage
        (TODO 6e731c1) is the identical shape, pointing at an image
        instead of a Markdown file. Scratch (TODO f8d9cec) is the same
        fire-and-forget shape as OpenMarkdown, just seeding a label +
        initial body text instead of a path. Markdown (TODO 9743419) is
        the same shape again, but renders its own content directly
        (set_tempui_content) rather than pointing at a separate file the
        way OpenMarkdown does. Shared by both the notification-click
        path (_activate_temp_ui) and the Desk-reload restore path
        (_bind_temp_ui_widget) so there's one place deciding which
        method gets which path."""
        try:
            kind = detect_temp_ui_kind(tempui_path.read_text())
        except OSError:
            kind = "question"
        if kind == "open_markdown":
            if not hasattr(content, "set_file"):
                return
            target = self._resolve_open_markdown_target(tempui_path, directory)
            if target is not None:
                content.set_file(target)
        elif kind == "open_image":
            if not hasattr(content, "set_file"):
                return
            target = self._resolve_open_image_target(tempui_path, directory)
            if target is not None:
                content.set_file(target)
        elif kind == "scratch":
            if not hasattr(content, "set_label"):
                return
            try:
                parsed = parse_scratch(tempui_path.read_text())
            except OSError:
                parsed = None
            if parsed is not None:
                label, body = parsed
                content.set_label(label)
                content.body.setPlainText(body)
        elif kind == "markdown_content":
            if not hasattr(content, "set_tempui_content"):
                return
            try:
                parsed = parse_markdown_tempui(tempui_path.read_text())
            except OSError:
                parsed = None
            if parsed is not None:
                label, markdown_content = parsed
                content.set_tempui_content(label, markdown_content)
        elif hasattr(content, "set_source_file"):
            content.set_source_file(tempui_path)

    @staticmethod
    def _resolve_open_markdown_target(tempui_path: Path, directory: Path) -> Path | None:
        try:
            raw = parse_open_markdown(tempui_path.read_text())
        except OSError:
            return None
        if not raw:
            return None
        target = Path(raw)
        return target if target.is_absolute() else (directory / target).resolve()

    @staticmethod
    def _resolve_open_image_target(tempui_path: Path, directory: Path) -> Path | None:
        try:
            raw = parse_open_image(tempui_path.read_text())
        except OSError:
            return None
        if not raw:
            return None
        target = Path(raw)
        return target if target.is_absolute() else (directory / target).resolve()

    def find_frame_by_instance_id(self, instance_id: str) -> WidgetFrame | None:
        for frame in self.view._frames:
            if frame.instance_id == instance_id:
                return frame
        return None

    def close_widget_by_instance_id(self, instance_id: str) -> bool:
        """No confirmation prompt -- unlike close_widget (the close
        button's flow, item 19), this is a deliberate API call (Bridge
        widgets.close), not an accidental-click risk. Returns whether a
        matching instance was found and removed."""
        frame = self.find_frame_by_instance_id(instance_id)
        if frame is None:
            return False
        self.view.remove_widget(frame)
        # Belt-and-suspenders for kind:"html" widgets specifically (TODO
        # 6f9c51b): they have no destroyed-signal-based cleanup path the
        # way a python widget's own EventSubscription does -- harmless
        # no-op if that already ran first.
        self._event_mediator.unsubscribe_all(instance_id)
        self.save_current_desk()
        return True

    def zoom_to_widget_by_instance_id(self, instance_id: str) -> bool:
        """TODO 7505703: lets a python widget (the Event Subscribers
        widget's per-row eye button, reached via
        current_context.get_widget_zoomer()) zoom/pan the Workspace
        Canvas to a specific placed widget instance by its instance id
        -- same "resolve then act, return whether found" shape as
        close_widget_by_instance_id above."""
        frame = self.find_frame_by_instance_id(instance_id)
        if frame is None:
            return False
        self.view.zoom_to_widget(frame)
        return True

    def _capture_desk_state(self) -> Desk:
        widget_states = []
        for frame in self.view._frames:
            proxy = frame.graphicsProxyWidget()
            if proxy is None:
                continue
            pos = proxy.pos()
            size = proxy.size()
            widget_states.append(
                WidgetState(
                    frame.content.widget_id,
                    pos.x(),
                    pos.y(),
                    size.width(),
                    size.height(),
                    instance_id=frame.instance_id,
                    state=self._get_widget_local_storage(frame),
                    locked=frame.locked,
                    placed_content_hash=frame.placed_content_hash,
                )
            )
        pan_x, pan_y, scale = self.view.get_view_state()
        return Desk(
            path=self.current_desk.path,
            widgets=widget_states,
            pan_x=pan_x,
            pan_y=pan_y,
            scale=scale,
            # Carried over from the current in-memory Desk, not
            # re-derived from anything on the canvas -- promoted custom
            # widget definitions (TODO 91b3f42) aren't placed widget
            # instances themselves, so there's nothing in view._frames
            # to capture them from.
            custom_widgets=self.current_desk.custom_widgets,
            # Same reasoning (TODO b5d52c0): the file type registry
            # isn't derived from placed widgets either -- carry it over
            # unchanged, or every save would silently wipe it back to [].
            file_type_registry=self.current_desk.file_type_registry,
        )

    def get_state_dict(self) -> dict:
        """The Bridge API's workspace.getState -- see
        plans/desk-bridge-api.md."""
        return desk_state_dict(self._capture_desk_state())

    def save_current_desk(self) -> None:
        desk = self._capture_desk_state()
        save_desk(desk)
        self.current_desk = desk
        add_to_mru(desk.path)
        self._refresh_picker()

    def get_file_type_registry_dicts(self) -> list[dict]:
        """TODO b5d52c0: the current Desk's file type registry, as
        JSON-serializable dicts -- shared by the Bridge API's
        filetypes.get (see desk.server.app) and a kind:"python"
        widget's own current_context.get_file_type_registry_provider()
        initial read, so the two never drift apart (same reasoning as
        get_state_dict)."""
        return [entry_to_dict(entry) for entry in self.current_desk.file_type_registry]

    def set_file_type_registry(self, entries: list[dict], sender_instance_id: str) -> None:
        """TODO b5d52c0: replaces the current Desk's file type registry
        and persists it, then publishes FILE_TYPE_REGISTRY_UPDATED_EVENT
        (payload: the new entries) to every *other* subscribed instance
        -- see desk.event_mediator.EventMediator.publish's own
        never-echoes-to-the-sender behavior. The event payload carries
        the new registry directly, so a subscriber (e.g. Project Files'
        bind_event_mediator) never needs a separate re-fetch call to
        learn what changed."""
        self.current_desk.file_type_registry = [entry_from_dict(e) for e in entries]
        self.save_current_desk()
        self._event_mediator.publish(FILE_TYPE_REGISTRY_UPDATED_EVENT, {"entries": entries}, sender_instance_id)

    def switch_desk(
        self,
        path: Path,
        confirm: Confirm | None = None,
        provisioning: "NewDeskProvisioning | None" = None,
    ) -> None:
        """`provisioning`, if given (only by `new_desk`, sourced from
        `NewDeskDialog`'s checkboxes), skips `_provision_temp_ui`'s own
        confirm dialogs in favor of these pre-decided answers -- see
        plans/fix-new-desk-flow-crash.md."""
        if path == self.current_desk.path:
            return
        confirm = confirm or self._confirm_fn("Switch Desk", f"Switch to “{path.stem}”?")
        if not confirm():
            return
        self.save_current_desk()
        self.view.clear_widgets()
        # Custom widget definitions (TODO 91b3f42) are per-Desk-directory
        # state, unlike the real widgets/ catalog (shared app-wide) --
        # forget the previous Desk's before registering the new one's,
        # so a keyword from the Desk being left doesn't linger and
        # resolve for the new one. The old mounted server route (if
        # any) is simply orphaned, not actively torn down -- harmless,
        # since removing it from self._widgets already makes it
        # unreachable via any placement/dispatch path in this app.
        for keyword in list(self._custom_widget_definitions):
            self._widgets.pop(keyword, None)
        self._custom_widget_definitions.clear()
        self._custom_widget_sources.clear()
        self._custom_widget_source_paths.clear()
        # Per-instance state (TODO 5734529), meaningless once
        # view.clear_widgets() above already destroyed the frames it
        # belonged to -- cleared here so it doesn't accumulate stale
        # entries across many Desk switches in one long session.
        self._html_widget_local_storage.clear()
        # Same reasoning, same spot (TODO 6f9c51b): every subscription
        # belonged to a frame view.clear_widgets() just destroyed.
        self._event_mediator.clear_all()
        # Same reasoning again (TODO 9767c1a): every introspect grant
        # named instance ids that belonged to frames just destroyed too.
        self._introspect_grants.clear()
        new_desk = load_desk(path) if path.is_file() else Desk(path=path)
        self.current_desk = new_desk
        # Set before _provision_temp_ui/_load_desk_widgets below, both
        # of which can synchronously construct/query a widget that
        # reads this (TODO 4716585 -- matches __init__'s own documented
        # ordering rationale for the exact same reason). All directory
        # -level provisioning also now runs before any widget is placed,
        # so a freshly-seeded widget (TODO cb2790d) never starts doing
        # its own work concurrently with a still-open provisioning
        # decision. The picker's own visual refresh (MRU included)
        # stays at the end, after add_to_mru -- that's cosmetic, not a
        # construction-time dependency.
        current_context.set_current_desk_directory(new_desk.directory)
        self._register_custom_widgets_from_desk(new_desk)
        self._provision_temp_ui(provisioning)
        self._register_custom_widgets_from_desk_temp(new_desk.directory)
        self._load_desk_widgets(new_desk)
        self.view.set_view_state(new_desk.pan_x, new_desk.pan_y, new_desk.scale)
        self._sync_tempui_doc()
        add_to_mru(path)
        self._refresh_picker()

    def close_widget(self, frame: WidgetFrame, confirm: Confirm | None = None) -> None:
        confirm = confirm or self._confirm_fn(
            "Remove Widget", "Remove this widget from the Desk?"
        )
        if not confirm():
            return
        self.view.remove_widget(frame)
        self._event_mediator.unsubscribe_all(frame.instance_id)
        self.save_current_desk()

    def change_current_desk_directory(self, new_directory: Path, confirm: Confirm | None = None) -> None:
        if new_directory == self.current_desk.directory:
            return
        confirm = confirm or self._confirm_fn(
            "Change Desk Directory", f"Move this Desk to “{new_directory}”?"
        )
        if not confirm():
            return
        new_path = new_directory / self.current_desk.path.name
        self.current_desk = Desk(
            path=new_path,
            widgets=self.current_desk.widgets,
            pan_x=self.current_desk.pan_x,
            pan_y=self.current_desk.pan_y,
            scale=self.current_desk.scale,
        )
        self.save_current_desk()
        self._provision_temp_ui()

    def new_desk(
        self,
        name: str,
        directory: Path,
        *,
        create_temp_ui: bool = True,
        create_gitignore: bool = True,
        copy_development_process: bool = False,
    ) -> None:
        """Creates a new, empty Desk named `name` in `directory` and
        switches to it. Naming the Desk *is* the intent, so (unlike
        switch_desk) there's no "Switch to X?" confirmation. The three
        keyword args are `NewDeskDialog`'s checkbox answers (TODO
        4716585) -- decided upfront, not asked again mid-flow."""
        name = name.strip()
        if not name:
            return
        path = directory / (name + DESK_SUFFIX)
        if path.exists():
            self._warn("New Desk", f"A Desk named “{name}” already exists here.")
            return
        if copy_development_process:
            # Reads from the *current* (about-to-be-left) Desk's
            # directory -- must run before switch_desk below reassigns
            # self.current_desk.
            self._seed_development_process(directory)
            self._seed_todo_item_ids_script(directory)
        self.switch_desk(
            path,
            confirm=lambda: True,
            provisioning=NewDeskProvisioning(create_temp_ui, create_gitignore),
        )
        # Re-checked immediately before the actual on-disk creation
        # (TODO 4716585): switch_desk above does real work
        # (provisioning, placing widgets) that takes real time, during
        # which something else could have created a .desk file at this
        # exact path. Recoverable: nothing has been written to disk yet
        # at this point, so aborting here just means this session's
        # in-memory Desk doesn't get saved over it.
        if path.exists():
            self._warn("New Desk", f"A Desk named “{name}” already exists here.")
            return
        # switch_desk only creates the new Desk in memory; persist it to
        # disk right away so it's a real file (added to the MRU, browsable)
        # rather than only materializing on the next transition.
        self.save_current_desk()

    def rename_current_desk(self, new_name: str) -> None:
        """Renames the current Desk's `.desk` file (a Desk's name is just
        its file stem -- see desks.py), preserving its widgets/view and
        leaving its directory, and thus its .desk_temp, untouched."""
        new_name = new_name.strip()
        if not new_name:
            return
        new_path = self.current_desk.directory / (new_name + DESK_SUFFIX)
        if new_path == self.current_desk.path:
            return
        if new_path.exists():
            self._warn("Rename Desk", f"A Desk named “{new_name}” already exists here.")
            return
        self.save_current_desk()  # ensure the .desk file exists before renaming it
        self.current_desk.path.rename(new_path)
        self.current_desk = Desk(
            path=new_path,
            widgets=self.current_desk.widgets,
            pan_x=self.current_desk.pan_x,
            pan_y=self.current_desk.pan_y,
            scale=self.current_desk.scale,
        )
        # add_to_mru's own load_mru() filters out the now-nonexistent old
        # path (it keeps only is_file() entries), so the stale name drops
        # out of the persisted MRU automatically.
        add_to_mru(new_path)
        self._refresh_picker()

    def _provision_temp_ui(self, provisioning: "NewDeskProvisioning | None" = None) -> None:
        """Ensures .desk_temp/desk-temporary-ui.md/.gitignore entry exist
        for the current Desk's directory (TODO a02b001) -- called at boot
        and whenever the directory actually changes. TempUiManager itself
        guards against re-prompting for a directory it already
        provisioned, so this can be called unconditionally here.

        `provisioning`, if given, skips the confirm dialogs below in
        favor of its pre-decided answers (TODO 4716585 -- used only by
        `new_desk`, sourced from `NewDeskDialog`'s checkboxes, so the
        user never gets asked the same question twice: once in that
        dialog, once again here)."""
        directory = self.current_desk.directory
        if provisioning is not None:
            ask_create_dir: Confirm = lambda: provisioning.create_temp_ui
            ask_gitignore: Confirm = lambda: provisioning.create_gitignore
        else:
            ask_create_dir = self._confirm_fn(
                "Temporary UI",
                f"Create “{TEMP_UI_DIRNAME}” in “{directory}” so agents can create "
                "temporary UI here?",
            )
            ask_gitignore = self._confirm_fn("Temporary UI", f"Add “{TEMP_UI_DIRNAME}” to .gitignore?")
        self._temp_ui_manager.provision(directory, ask_create_dir, ask_gitignore)
        self._ensure_questions_watcher()

    def _ensure_questions_watcher(self) -> None:
        """(Re)watches the nearest QUESTIONS.md for the current Desk's
        directory (TODO a801180) -- called alongside _provision_temp_ui
        (boot, desk switch, directory change) since a QUESTIONS.md
        relevant to the current Desk can change out from under any of
        those. Re-seeds the known-question baseline whenever the
        resolved path changes so pre-existing entries never spuriously
        notify -- only entries added *after* this point do."""
        directory = self.current_desk.directory
        questions_path = find_nearest_questions_file(directory)
        self._questions_path = questions_path
        if questions_path is None:
            self._questions_watcher.stop()
            self._known_question_keys = None
            return
        self._questions_watcher.watch(questions_path)
        _, entries = parse_questions_file(questions_path)
        self._known_question_keys = {tuple(entry.todo_ids) for entry in entries}

    def _on_questions_file_changed(self) -> None:
        """A real external change to the watched QUESTIONS.md (self
        -writes are already suppressed by SingleFileWatcher itself) --
        surfaces a top-right notification only for genuinely *new*
        question entries (comparing against the baseline captured by
        _ensure_questions_watcher/the previous call here), not every
        edit (e.g. filling in an existing answer shouldn't re-notify)."""
        questions_path = self._questions_path
        if questions_path is None or not questions_path.is_file():
            return
        _, entries = parse_questions_file(questions_path)
        keys = {tuple(entry.todo_ids) for entry in entries}
        new_keys = keys - (self._known_question_keys or set())
        self._known_question_keys = keys
        if not new_keys:
            return
        new_entries = [entry for entry in entries if tuple(entry.todo_ids) in new_keys]
        text = (
            new_entries[0].title
            if len(new_entries) == 1
            else f"{len(new_entries)} new questions in QUESTIONS.md"
        )
        self.view.notify_temp_ui(questions_path, text, self._focus_questions_widget)

    def _find_frame_by_widget_id(self, widget_id: str) -> WidgetFrame | None:
        for frame in self.view._frames:
            if isinstance(frame.content, PythonWidgetHost) and frame.content.widget_id == widget_id:
                return frame
        return None

    def _focus_questions_widget(self) -> None:
        """Click-handler for the "new question(s)" notification: centers
        on an already-open Questions widget if one exists, otherwise
        opens a fresh one centered in the current view -- mirrors
        _activate_temp_ui's own "center if it exists, otherwise create
        it centered" shape."""
        frame = self._find_frame_by_widget_id(QUESTIONS_WIDGET_ID)
        if frame is None:
            widget = self._widgets.get(QUESTIONS_WIDGET_ID)
            if widget is None:
                return
            center = self.view.mapToScene(self.view.viewport().rect().center())
            frame = self._place_widget(
                QUESTIONS_WIDGET_ID, widget, (center.x(), center.y()), widget.default_size
            )
        proxy = frame.graphicsProxyWidget()
        if proxy is not None:
            self.view.centerOn(proxy.sceneBoundingRect().center())

    def _on_temp_ui_file_added(self, path: Path) -> None:
        if self._handle_define_widget_file(path, is_new=True):
            return
        self._notify_temp_ui(path)

    def _on_temp_ui_file_edited(self, path: Path) -> None:
        if self._handle_define_widget_file(path):
            return
        if self._refresh_live_temp_ui(path):
            return
        self._notify_temp_ui(path)

    def _refresh_live_temp_ui(self, path: Path) -> bool:
        """Live-refreshes an already-placed tempui-bound widget in
        place when its source file is genuinely edited externally
        (TODO 67ab2df), instead of only letting a notification click
        center the view on now-stale content -- re-invokes the exact
        same `_bind_temp_ui_content` dispatch used for a fresh
        placement/restore, since it already reads the file fresh and
        routes to whichever method each kind needs.

        Returns `True` if a live refresh actually happened, in which
        case the caller should skip the usual notification (the widget
        already visibly updated, so a banner saying the same thing
        would be redundant). Returns `False` if there's no already
        -placed frame for this file yet, or if the frame's content
        reports unsaved local edits via the optional
        `has_unsaved_local_edits()` duck-typed hook (e.g. the Scratch
        widget, TODO 9ee505f) that a blind refresh would clobber -- in
        both cases the caller falls through to the existing
        notification path unchanged."""
        frame = self.find_frame_by_instance_id(path.name)
        if frame is None or not isinstance(frame.content, PythonWidgetHost):
            return False
        content = frame.content.current
        if content is None:
            return False
        if hasattr(content, "has_unsaved_local_edits") and content.has_unsaved_local_edits():
            return False
        self._bind_temp_ui_content(content, path, self.current_desk.directory)
        return True

    def _notify_temp_ui(self, path: Path) -> None:
        text = f"New question: {path.name}"
        try:
            content_text = path.read_text()
            kind = detect_temp_ui_kind(content_text, self._custom_widget_definitions.keys())
            if kind == "lightning_round":
                lr_doc = parse_lightning_round(content_text)
                if lr_doc.prompt or lr_doc.name:
                    text = lr_doc.prompt or lr_doc.name
            elif kind == "open_markdown":
                target = parse_open_markdown(content_text)
                if target:
                    text = f"Open {target}"
            elif kind == "open_image":
                target = parse_open_image(content_text)
                if target:
                    text = f"Open {target}"
            elif kind == "scratch":
                parsed = parse_scratch(content_text)
                if parsed and parsed[0]:
                    text = f"Scratch: {parsed[0]}"
            elif kind == "markdown_content":
                parsed = parse_markdown_tempui(content_text)
                if parsed and parsed[0]:
                    text = f"Markdown: {parsed[0]}"
            elif kind == "discuss_parking_lot_item":
                parsed = parse_discuss_parking_lot_item(content_text)
                if parsed and parsed[0]:
                    text = f"Discuss: {parsed[0]}"
            elif kind.startswith("custom:"):
                definition = self._custom_widget_definitions.get(kind.split(":", 1)[1])
                if definition is not None:
                    text = f"New {definition.label}"
            else:
                doc = parse_temp_ui(content_text)
                if doc.question:
                    text = doc.question
        except OSError:
            pass
        self.view.notify_temp_ui(path, text, lambda: self._activate_temp_ui(path))

    def _temp_ui_widget_id_for(self, path: Path) -> str:
        """Which widget kind renders this TempUI file -- read from its
        own content (see detect_temp_ui_kind), not assumed, since a
        notification/saved-widget-state caller may be seeing it for the
        first time. Falls back to the original "question" kind if the
        file can't be read (e.g. TOCTOU: deleted between the watcher
        firing and this running)."""
        try:
            kind = detect_temp_ui_kind(path.read_text(), self._custom_widget_definitions.keys())
        except OSError:
            kind = "question"
        if kind == "lightning_round":
            return LIGHTNING_ROUND_WIDGET_ID
        if kind in ("open_markdown", "markdown_content"):
            return MARKDOWN_WIDGET_ID
        if kind == "open_image":
            return IMAGE_VIEWER_WIDGET_ID
        if kind == "scratch":
            return SCRATCH_WIDGET_ID
        if kind == "discuss_parking_lot_item":
            return CLAUDE_WIDGET_ID
        if kind.startswith("custom:"):
            return kind.split(":", 1)[1]
        return QUESTION_WIDGET_ID

    def _activate_temp_ui(self, path: Path) -> None:
        """Shared click-handler for both an "added" and an "edited"
        temp-UI notification -- TODO a02b001 specifies "center if a
        widget already exists, otherwise create it" for edited, and just
        "create it, centered" for added; in practice a file that was
        *just* added can't already have a placed widget, so the two
        specs collapse into this one behavior."""
        uuid_str = path.name
        frame = self.find_frame_by_instance_id(uuid_str)
        if frame is not None:
            proxy = frame.graphicsProxyWidget()
            if proxy is not None:
                self.view.centerOn(proxy.sceneBoundingRect().center())
            return

        widget_id = self._temp_ui_widget_id_for(path)
        widget = self._widgets.get(widget_id)
        if widget is None:
            return
        center = self.view.mapToScene(self.view.viewport().rect().center())
        if widget_id == CLAUDE_WIDGET_ID:
            # DiscussParkingLotItem (TODO c0875bc): a claude widget's
            # session starts *inside* _place_widget itself (see
            # _bind_claude_widget), before the generic
            # open_widget_content -> _bind_temp_ui_content two-step
            # below would get a chance to run -- too late to append the
            # item text to the prompt by then, so this goes through the
            # shared _place_discuss_claude_widget helper instead (also
            # used by the Questions widget's Discuss button, TODO
            # 46e1b42), passing this file's own uuid as instance_id so
            # a repeat notification click just centers on it (the
            # find_frame_by_instance_id check above), not restarts it.
            # Passes a line-number reference, not the item's full text
            # (TODO 624ff3a -- splicing the full text into the launch
            # prompt could break the new session's launch).
            try:
                parsed = parse_discuss_parking_lot_item(path.read_text())
            except OSError:
                parsed = None
            line_number = parsed[1] if parsed is not None else None
            self._place_discuss_claude_widget(
                "PARKINGLOT.md", parking_lot_line=line_number, instance_id=uuid_str
            )
            return
        content = self.open_widget_content(
            widget_id,
            pos=(center.x(), center.y()),
            size=widget.default_size,
            instance_id=uuid_str,
        )
        if content is not None:
            self._bind_temp_ui_content(content, path, self.current_desk.directory)

    def _confirm_fn(self, title: str, message: str) -> Confirm:
        def confirm() -> bool:
            result = QMessageBox.question(self, title, message)
            return result == QMessageBox.StandardButton.Yes

        return confirm

    def _prompt_fn(self, title: str, label: str, default: str = "") -> Callable[[], str | None]:
        """Mirrors _confirm_fn: returns a zero-arg callable so headless
        tests can substitute a canned answer instead of driving a real
        modal QInputDialog. Returns the entered text, or None if
        cancelled."""

        def prompt() -> str | None:
            text, ok = QInputDialog.getText(self, title, label, text=default)
            return text if ok else None

        return prompt

    def _warn(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def _info(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    def _warn_with_selectable_text(self, title: str, message: str) -> None:
        """Like _warn, but the message text is selectable/copyable --
        QMessageBox.warning's static convenience method doesn't allow
        that, so this constructs the box directly. Used for TODO
        8f5568f's missing-MRU-file warning, which needs to give the
        full path in selectable text -- an explicit, TODO-specified
        exception to CLAUDE.md's general "labels shouldn't be user
        -selectable" convention."""
        box = QMessageBox(QMessageBox.Icon.Warning, title, message, QMessageBox.StandardButton.Ok, self)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.exec()

    def _refresh_picker(self) -> None:
        self.view.desk_picker.set_current(self.current_desk.name, self.current_desk.directory)
        self.view.desk_picker.set_mru(prune_missing_mru_entries(), self.current_desk.path)
        # Keeps python widgets' access to "the current Desk's directory"
        # (see desk.shell.current_context, deferred since item 18) in sync
        # with everything else this method already refreshes.
        current_context.set_current_desk_directory(self.current_desk.directory)
        # Same choke point, for the same reason (TODO 6f9c51b): keeps
        # MEDIATED-EVENT-LOG.tsv's location in sync with the current Desk.
        # Lives under .desk_temp (TODO 585d235), not the project directory
        # directly -- it's Desk-generated bookkeeping, the same category of
        # thing as crash logs/tempui docs/custom-widget source.
        self._event_mediator.set_log_directory(self.current_desk.directory / TEMP_UI_DIRNAME)
        # Same choke point, for the same reason (TODO b5d52c0): a python
        # widget placed after a Desk switch reads the *new* Desk's own
        # file type registry, not a stale one left over from before.
        current_context.set_file_type_registry_provider(self.get_file_type_registry_dicts)

    def _on_desk_chosen(self, path: Path) -> None:
        """Guards against an MRU entry whose file vanished between the
        picker last refreshing and this click (TODO 8f5568f) --
        without this, switch_desk's existing "path doesn't exist"
        handling (Desk(path=path)) would silently create a brand-new,
        empty Desk at that now-nonexistent path instead of warning."""
        if not path.is_file():
            self._warn_with_selectable_text(
                "Desk Not Found", f"This Desk's file is no longer there:\n\n{path}"
            )
            self._refresh_picker()  # prunes the now-confirmed-stale entry
            return
        self.switch_desk(path)

    def _on_browse_requested(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Desk", str(self.current_desk.directory), "Desk files (*.desk)"
        )
        if filename:
            self.switch_desk(Path(filename))

    def _on_directory_change_requested(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Change Desk Directory", str(self.current_desk.directory)
        )
        if directory:
            self.change_current_desk_directory(Path(directory))

    def _on_new_desk_requested(self) -> None:
        """Opens NewDeskDialog (TODO 4716585) -- one consolidated
        dialog collecting name/path/checkboxes, replacing what used to
        be up to five sequential modal popups (name, directory, an
        optional development-process.md copy confirm, a .desk_temp
        confirm, a .gitignore confirm). See
        plans/fix-new-desk-flow-crash.md for why that mattered beyond
        just convenience."""
        source = self.current_desk.directory / DEVELOPMENT_PROCESS_FILENAME
        dialog = NewDeskDialog(
            default_directory=self.current_desk.directory,
            dev_process_filename=DEVELOPMENT_PROCESS_FILENAME if source.is_file() else None,
            parent=self,
        )
        dialog.created.connect(self._on_new_desk_dialog_submitted)
        dialog.show()

    def _on_new_desk_dialog_submitted(
        self,
        name: str,
        directory: str,
        create_temp_ui: bool,
        create_gitignore: bool,
        copy_development_process: bool,
    ) -> None:
        self.new_desk(
            name,
            Path(directory),
            create_temp_ui=create_temp_ui,
            create_gitignore=create_gitignore,
            copy_development_process=copy_development_process,
        )

    def _seed_development_process(self, directory: Path) -> None:
        """Copies the current Desk's development-process.md, and (TODO
        1a96c9f) its shared_development_process.md/specifically-not
        -working-on-desk-itself-development-process.md peers, into
        `directory` (TODO fbd0554) -- each independently a no-op if the
        current Desk has none to source from, or if `directory` already
        has its own (never silently overwritten). The existence check
        already runs immediately before the write with nothing in
        between (TODO 4716585's re-check-immediately-before-create
        requirement) -- confirmed correct as-is, no change needed
        here."""
        for filename in (
            DEVELOPMENT_PROCESS_FILENAME,
            SHARED_DEVELOPMENT_PROCESS_FILENAME,
            NOT_DESK_DEVELOPMENT_PROCESS_FILENAME,
        ):
            source = self.current_desk.directory / filename
            destination = directory / filename
            if not source.is_file() or destination.exists():
                continue
            destination.write_text(source.read_text())

    def _seed_todo_item_ids_script(self, directory: Path) -> None:
        """Copies the current Desk's scripts/todo_item_ids.py into
        `directory` (TODO c458012) -- same no-op-if-nothing-to-source
        -from/never-overwrite posture as _seed_development_process
        above, since development-process.md's own "Item IDs" section
        tells you to run this exact script, and copying the doc without
        it would leave that instruction broken in the new project.
        Unlike the doc, this also creates the destination's scripts/
        directory (won't exist yet in a brand-new project) and sets the
        copy executable -- explicit 0o755, not copied from the source
        file's own mode bits, since umask/source-filesystem quirks
        shouldn't leak into the destination."""
        source = self.current_desk.directory / "scripts" / "todo_item_ids.py"
        destination = directory / "scripts" / "todo_item_ids.py"
        if not source.is_file() or destination.exists():
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text())
        destination.chmod(0o755)

    # -- TempUI-defined custom widgets (TODO 91b3f42) --------------------

    def _register_custom_widget(self, definition: CustomWidgetDefinition, source: str) -> bool:
        """Registers a tempui-DSL-defined custom widget kind: decodes
        its base64 HTML to a real directory (desk.custom_widgets
        .materialize), adds a `kind: "html"` WidgetInfo to the live
        catalog, and mounts it on the already-running Local Web Server
        -- the same three steps regardless of whether `definition` came
        from a .desk_temp DefineWidget file (source="tempui") or this
        Desk's own saved .desk file (source="desk"). Refuses (logs,
        returns False, doesn't raise) to shadow a built-in DSL keyword
        or an existing widget catalog id from a *different* source --
        matching this DSL's general "unrecognized/conflicting input is
        ignored" posture. Re-registering the same keyword from the
        *same* source (e.g. a DefineWidget file being edited) just
        refreshes it in place."""
        keyword = definition.keyword
        if keyword in RESERVED_TEMPUI_KEYWORDS:
            logger.warning("Refusing to register custom widget %r: a reserved DSL keyword", keyword)
            return False
        existing_source = self._custom_widget_sources.get(keyword)
        if existing_source is None and keyword in self._widgets:
            logger.warning("Refusing to register custom widget %r: shadows an existing widget id", keyword)
            return False
        if existing_source is not None and existing_source != source:
            logger.warning(
                "Custom widget %r already registered from %r; ignoring redefinition from %r",
                keyword,
                existing_source,
                source,
            )
            return False

        directory = materialize(self.current_desk.directory / TEMP_UI_DIRNAME, definition)
        if directory is None:
            return False
        # TODO 5995ffd: hashing the already-available base64 text
        # directly (a deterministic encoding of the decoded HTML) is
        # equivalent to hashing the decoded document itself, and avoids
        # a second decode here.
        content_hash = hashlib.md5(definition.html_b64.encode("ascii")).hexdigest()[:12]
        info = WidgetInfo(
            id=keyword,
            path=directory,
            kind="html",
            name=definition.label,
            entry="index.html",
            # TODO f693275: previously always [] -- a DefineWidget
            # tempui file now has its own Capability line(s), the same
            # coarse, resource-level capability strings a real
            # widgets/<id>/widget.json declares.
            capabilities=definition.capabilities,
            default_size=definition.default_size,
            # Only a still-tempui-sourced widget is excluded from the
            # spawn menu (TODO 6857997/2b2a642) -- once promoted
            # (source="desk"), it's a permanent, first-class part of
            # this Desk and should be placeable the normal way too, not
            # just re-invokable via tempui.
            tempui_only=(source == "tempui"),
            content_hash=content_hash,
        )
        self._widgets[keyword] = info
        self._custom_widget_definitions[keyword] = definition
        self._custom_widget_sources[keyword] = source
        self._custom_widget_content_hash[keyword] = content_hash
        self._handle.mount_html_widget(keyword, directory, info)
        self.view.set_widget_catalog(self._widgets)
        self._refresh_stale_indicators_for(keyword)
        return True

    def _refresh_stale_indicators_for(self, keyword: str) -> None:
        """Recomputes the "[STALE]" marker (TODO 5995ffd) on every
        already-placed instance of `keyword`, against its
        just-registered content hash -- called at the end of every
        _register_custom_widget call (fresh or a same-source refresh).
        This is what catches a *live* edit to an already-registered
        DefineWidget file while an instance is already on the canvas:
        that instance's own placed_content_hash still holds whatever
        was true when it was placed, so it now differs from the
        keyword's newly-updated hash. A no-op for a frame whose
        placed_content_hash is still None (never set -- an ordinary
        widget, or a custom widget instance placed before this field
        existed)."""
        current_hash = self._custom_widget_content_hash.get(keyword)
        for frame in self.view._frames:
            if frame.content.widget_id != keyword or frame.placed_content_hash is None:
                continue
            frame.set_stale(current_hash is not None and current_hash != frame.placed_content_hash)

    def _on_widget_stale_clicked(self, frame: WidgetFrame) -> None:
        """The `[STALE]` titlebar button's handler (TODO 3e2c4f2): shows
        both content hashes and offers to reload *this specific
        instance* now, or leave it running its current content. Reloads
        only `frame.content` directly, never via
        `HotReloadBroker.widget_changed` -- that would reload every
        placed instance of this keyword, defeating the whole point of a
        per-instance choice."""
        if not isinstance(frame.content, ChromiumWidget):
            return
        keyword = frame.content.widget_id
        current_hash = self._custom_widget_content_hash.get(keyword)
        if current_hash is None or current_hash == frame.placed_content_hash:
            # Nothing stale anymore -- e.g. already reloaded, or the
            # definition changed back to what this instance already has.
            return
        if not self._confirm_stale_reload(frame.placed_content_hash, current_hash):
            return
        frame.content.reload()
        frame.placed_content_hash = current_hash
        frame.set_stale(False)

    def _confirm_stale_reload(self, placed_hash: str | None, current_hash: str) -> bool:
        """Split out so headless verification can monkeypatch just this
        one method instead of driving a real modal QMessageBox --
        mirrors widgets/event_log/widget.py's own _confirm_clear."""
        box = QMessageBox(self)
        box.setWindowTitle("Widget Content Updated")
        box.setText(
            "This widget instance predates the currently-registered definition for its kind."
        )
        box.setInformativeText(f"Placed with: {placed_hash}\nCurrently registered: {current_hash}")
        reload_button = box.addButton("Reload Now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Keep for Now", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is reload_button

    def _register_custom_widgets_from_desk(self, desk: Desk) -> None:
        """Registers every custom widget already promoted into `desk`'s
        own saved .desk file (TODO 91b3f42) -- "registered just like
        built-in widgets," at startup and on Desk switch."""
        for definition in desk.custom_widgets:
            self._register_custom_widget(definition, source="desk")

    def _register_custom_widgets_from_desk_temp(self, directory: Path) -> None:
        """Scans `directory/.desk_temp` for any not-yet-promoted
        DefineWidget tempui files and registers each (TODO 91b3f42) --
        a no-op if `.desk_temp` doesn't exist (nothing provisioned, or
        the user declined to create it). Runs at startup and on Desk
        switch, after _provision_temp_ui, so a still-tempui-sourced
        custom widget's own catalog entry is ready before
        _load_desk_widgets tries to resolve any already-placed instance
        of it."""
        temp_dir = directory / TEMP_UI_DIRNAME
        if not temp_dir.is_dir():
            return
        for path in sorted(temp_dir.iterdir()):
            if not path.is_file() or not is_temp_ui_filename(path.name):
                continue
            try:
                text = path.read_text()
            except OSError:
                continue
            if detect_temp_ui_kind(text) != "define_widget":
                continue
            definition = parse_define_widget(text)
            if definition is None:
                continue
            if self._register_custom_widget(definition, source="tempui"):
                self._custom_widget_source_paths[definition.keyword] = path

    def _handle_define_widget_file(self, path: Path, is_new: bool = False) -> bool:
        """Returns True if `path` is a DefineWidget tempui file (TODO
        91b3f42) -- handled entirely here (register + doc sync), never
        as an openable widget notification, since a widget *type*
        definition has nothing to open. Called first from both
        _on_temp_ui_file_added/_on_temp_ui_file_edited; False for
        anything else, so the caller falls through to the normal
        notify/live-refresh flow.

        `is_new` (TODO 5ff02d2, only ever passed True from
        _on_temp_ui_file_added) auto-places one instance of a keyword
        that's genuinely new -- never already present in
        _custom_widget_definitions before this call -- since otherwise
        DefineWidget is the only tempui kind that can silently succeed
        with no visible next step (see
        design-docs/custom-widget-authoring.md section 2). Deliberately
        does not fire for a re-save of an already-known keyword, nor
        for _register_custom_widgets_from_desk_temp's own bulk startup
        /Desk-switch rescan (which never calls this method at all) --
        both would otherwise place a duplicate instance every time."""
        try:
            text = path.read_text()
        except OSError:
            return False
        if detect_temp_ui_kind(text) != "define_widget":
            return False
        definition = parse_define_widget(text)
        if definition is None:
            return False
        keyword_already_known = definition.keyword in self._custom_widget_definitions
        if self._register_custom_widget(definition, source="tempui"):
            self._custom_widget_source_paths[definition.keyword] = path
            self._sync_tempui_doc()
            if is_new and not keyword_already_known:
                self._auto_place_new_custom_widget(definition.keyword)
        return True

    def _auto_place_new_custom_widget(self, keyword: str) -> None:
        """Places one instance of a brand-new DefineWidget kind, centered
        in the current view -- same positioning as
        _place_discuss_claude_widget/_activate_temp_ui's own
        auto-placements. See _handle_define_widget_file's is_new
        docstring for when this runs."""
        widget = self._widgets.get(keyword)
        if widget is None:
            return
        center = self.view.mapToScene(self.view.viewport().rect().center())
        self._place_widget(keyword, widget, (center.x(), center.y()), widget.default_size)

    def _sync_tempui_doc(self) -> None:
        """Keeps desk-temporary-ui.md's dynamic custom-widgets section
        current (TODO 91b3f42) -- called at startup, on Desk switch,
        and whenever a new DefineWidget item is registered live. A
        no-op if the doc doesn't exist yet at all (e.g. the user
        declined to create .desk_temp) -- see
        desk.temp_ui.sync_custom_widgets_doc_section."""
        doc_path = self.current_desk.directory / TEMP_UI_DIRNAME / DOC_FILENAME
        entries = [
            (definition, self._custom_widget_sources.get(keyword, "tempui"))
            for keyword, definition in self._custom_widget_definitions.items()
        ]
        sync_custom_widgets_doc_section(doc_path, entries)

    def _on_tempui_promote_requested(self, frame: WidgetFrame) -> None:
        """The [TEMPUI] titlebar button's handler (TODO 91b3f42): on
        confirm, saves the widget's definition permanently into the
        current .desk file, removes the original DefineWidget tempui
        file (the .desk file becomes the sole remaining source of
        truth), and re-syncs the doc. No re-mounting is needed --
        materialize always regenerates the same shared
        .desk_temp/custom_widgets/<keyword>/ cache directory regardless
        of source, so the already-mounted server route keeps serving
        the exact same content uninterrupted; only which side is
        authoritative changes."""
        if not isinstance(frame.content, ChromiumWidget):
            return
        keyword = frame.content.widget_id
        definition = self._custom_widget_definitions.get(keyword)
        if definition is None:
            return
        if self._custom_widget_sources.get(keyword) == "desk":
            self._info("Already part of the Desk", f"“{definition.label}” is already saved in this Desk.")
            return
        if not self._confirm_fn(
            "Promote to Desk",
            f"Save “{definition.label}” permanently in this Desk, and remove its "
            "definition from tempui?",
        )():
            return
        self.current_desk.custom_widgets.append(definition)
        self._custom_widget_sources[keyword] = "desk"
        self.save_current_desk()
        source_path = self._custom_widget_source_paths.pop(keyword, None)
        if source_path is not None and source_path.is_file():
            source_path.unlink()
        self._relocate_promoted_widget_source(keyword)
        # TODO 6857997/2b2a642: the widget is now a permanent, first
        # -class part of this Desk -- flip the already-registered
        # WidgetInfo in place (no need to re-materialize/re-mount,
        # neither of which promotion changes) so it's no longer
        # excluded from the spawn menu, refresh the catalog so that
        # takes effect immediately, and hide this frame's own button
        # (nothing left for it to offer).
        info = self._widgets.get(keyword)
        if info is not None:
            info.tempui_only = False
        self.view.set_widget_catalog(self._widgets)
        frame.set_tempui_promotable(False)
        self._sync_tempui_doc()

    def _relocate_promoted_widget_source(self, keyword: str) -> None:
        """TODO 59c5a70: moves a promoted widget's authoring source
        directory (see "Authoring from real source" in
        tempui-custom-widgets.md, TODO b324217) out of
        .desk_temp/widgets/<keyword>/ -- gitignored, disposable-support
        territory -- into a permanent, non-gitignored desk_widgets/
        <keyword>/ project subdirectory, matching the promoted
        definition's own move into the .desk file. Not every custom
        widget has a source directory to move (a hand-authored, inline
        -only one never did) -- a missing source directory is a silent
        no-op, not an error. A pre-existing destination is left alone
        (logged, not raised): the .desk file promotion above has
        already succeeded by this point, and a problem with this
        secondary bookkeeping step shouldn't make the whole promotion
        look like it failed."""
        source_dir = self.current_desk.directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / keyword
        if not source_dir.is_dir():
            return
        destination_dir = self.current_desk.directory / PROMOTED_WIDGET_SRC_DIRNAME / keyword
        if destination_dir.exists():
            logger.warning(
                "Not relocating promoted widget %r's authoring source: %s already exists",
                keyword,
                destination_dir,
            )
            return
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_dir), str(destination_dir))

    def _on_rename_requested(self) -> None:
        name = self._prompt_fn(
            "Rename Desk", "New name for this Desk:", self.current_desk.name
        )()
        if name:
            self.rename_current_desk(name)

    def _on_widget_add_requested(self, widget_id: str, scene_pos: QPointF) -> None:
        widget = self._widgets.get(widget_id)
        if widget is None:
            return
        self._place_widget(widget_id, widget, (scene_pos.x(), scene_pos.y()), widget.default_size)

    def _on_widget_close_requested(self, frame: WidgetFrame) -> None:
        self.close_widget(frame)

    def _on_files_dropped(self, paths: list[Path], scene_pos: QPointF) -> None:
        """Opens each file dropped onto the canvas (TODO 5915ac2) by
        reference to wherever it already lives on disk -- never copied
        into the project -- in whichever widget kind its extension maps
        to (EXTERNAL_DROP_WIDGET_BY_SUFFIX, falling back to the Editor).
        A file outside the current Desk directory (the common case for
        a drag from Finder) automatically picks up the existing
        "[EXTERNAL]" titlebar indicator (TODO a053e3a) the moment
        set_file resolves it -- no separate step needed for that.
        Multiple files fan out with the same WIDGET_SPACING offset
        _load_desk_widgets' own no-saved-state fallback uses, starting
        from the drop's own scene position.

        A raster image (IMAGE_DROP_SUFFIXES, TODO 6e731c1) is handled
        entirely differently -- copied into .desk_temp and displayed
        through a new OpenImage tempui file (_drop_image_as_temp_ui)
        rather than opened by reference -- since falling back to the
        Editor for binary image bytes would just render garbage."""
        for index, path in enumerate(paths):
            pos = (scene_pos.x() + index * WIDGET_SPACING, scene_pos.y())
            if path.suffix.lower() in IMAGE_DROP_SUFFIXES:
                self._drop_image_as_temp_ui(path, pos)
                continue
            widget_id = EXTERNAL_DROP_WIDGET_BY_SUFFIX.get(path.suffix.lower(), EDITOR_WIDGET_ID)
            widget = self._widgets.get(widget_id)
            if widget is None:
                continue
            content = self.open_widget_content(widget_id, pos=pos, size=widget.default_size)
            if content is not None and hasattr(content, "set_file"):
                content.set_file(path)

    def _drop_image_as_temp_ui(self, path: Path, pos: tuple[float, float]) -> None:
        """TODO 6e731c1: copies a dropped image's bytes into .desk_temp
        (a short random prefix avoids collisions across repeated drops
        of same-named files, while keeping the original name readable
        -- original bytes/format preserved as-is, unlike the existing
        clipboard-image paste path, _paste_image_as_project_file, which
        re-encodes to PNG since a QImage from the clipboard has no
        "original file bytes" to preserve), writes a new UUID-named
        OpenImage tempui file pointing at the copy (suppressed via
        record_own_write, same mechanism _paste_text_as_temp_ui already
        uses, so the directory watcher doesn't also fire a redundant
        notification for a file about to be opened immediately anyway),
        then immediately places and binds an Image Viewer instance at
        the drop position -- matches how every other dropped file type
        already places immediately, no notification-then-click detour."""
        directory = self.current_desk.directory
        temp_dir = directory / TEMP_UI_DIRNAME
        if not temp_dir.is_dir():
            return
        try:
            data = path.read_bytes()
        except OSError:
            return
        saved_name = f"{uuid.uuid4().hex[:8]}-{path.name}"
        saved_path = temp_dir / saved_name
        try:
            saved_path.write_bytes(data)
        except OSError:
            return

        # Written relative to the *Desk* directory (matching
        # OpenMarkdown's own documented "absolute or relative to the
        # current Desk's directory" convention, which
        # _resolve_open_image_target/_resolve_open_markdown_target both
        # resolve against) -- not just the bare filename, since the
        # saved copy actually lives one level down, in .desk_temp/.
        content_text = f"{OPEN_IMAGE_KEYWORD} {TEMP_UI_DIRNAME}/{saved_name}"
        tempui_path = temp_dir / str(uuid.uuid4())
        tempui_path.write_text(content_text)
        self._temp_ui_manager.record_own_write(tempui_path, content_text)

        widget_id = self._temp_ui_widget_id_for(tempui_path)
        widget = self._widgets.get(widget_id)
        if widget is None:
            return
        content = self.open_widget_content(
            widget_id, pos=pos, size=widget.default_size, instance_id=tempui_path.name
        )
        if content is not None:
            self._bind_temp_ui_content(content, tempui_path, directory)

    def _on_paste_requested(self, scene_pos: QPointF) -> None:
        """Handles the widget menu's "Paste" entry (TODO f74945e).
        Text (markdown or not) is written as a new tempui file and
        opened immediately at the click position; content the
        clipboard offers as an explicit "text/markdown" flavor (RFC
        7763 -- a deliberately conservative signal, not content
        -sniffing) uses the Markdown DSL entry (TODO 9743419), anything
        else textual uses the Scratch DSL entry (TODO f8d9cec). Content
        with no text at all but a clipboard image is saved directly as
        a new file in the project directory instead -- there's no
        tempui DSL for binary content, and nothing to open it in."""
        directory = self.current_desk.directory
        mime = QApplication.clipboard().mimeData()
        if mime is None:
            return
        if mime.hasText() and mime.text().strip():
            self._paste_text_as_temp_ui(mime.text(), mime.hasFormat("text/markdown"), directory, scene_pos)
        elif mime.hasImage():
            self._paste_image_as_project_file(directory)

    def _paste_text_as_temp_ui(
        self, text: str, is_markdown: bool, directory: Path, scene_pos: QPointF
    ) -> None:
        temp_dir = directory / TEMP_UI_DIRNAME
        if not temp_dir.is_dir():
            return
        first_line = next((line.strip().lstrip("#").strip() for line in text.splitlines() if line.strip()), "")
        label = first_line or "Pasted content"
        keyword = MARKDOWN_KEYWORD if is_markdown else SCRATCH_KEYWORD
        content_text = f"{keyword} {label}\n{text}"
        path = temp_dir / str(uuid.uuid4())
        path.write_text(content_text)
        # Suppresses the directory watcher's own "file added" notification
        # for this exact write (same mechanism TempUiManager already uses
        # for e.g. the Question Widget's own answer-append) -- this paste
        # is opened immediately below, so a redundant top-right banner a
        # moment later would just be noise.
        self._temp_ui_manager.record_own_write(path, content_text)

        widget_id = self._temp_ui_widget_id_for(path)
        widget = self._widgets.get(widget_id)
        if widget is None:
            return
        content = self.open_widget_content(
            widget_id, pos=(scene_pos.x(), scene_pos.y()), size=widget.default_size, instance_id=path.name
        )
        if content is not None:
            self._bind_temp_ui_content(content, path, directory)

    def _paste_image_as_project_file(self, directory: Path) -> None:
        image = QApplication.clipboard().image()
        if image.isNull():
            return
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        image.save(str(directory / f"PASTED-ITEM-{timestamp}.png"), "PNG")

    def _on_widget_changed_refresh_catalog(self, _widget_id: str) -> None:
        """Keeps the widget catalog (add-widget menu, recognized
        widget_ids) live: a directory added/removed/changed under
        widgets_dir has no effect until this re-runs discover_widgets() --
        see plans/generalized-hot-reload.md. Cheap: a handful of small
        widget.json reads, on every debounced widget-changed event.

        discover_widgets only ever scans the real widgets_dir, so it
        knows nothing about tempui-DSL-defined custom widgets (TODO
        91b3f42) -- snapshot their current catalog entries first and
        merge them back in, or a hot-reload triggered by an unrelated
        real widget's own source change would otherwise silently drop
        every custom widget from the live catalog."""
        custom_entries = {
            keyword: self._widgets[keyword]
            for keyword in self._custom_widget_definitions
            if keyword in self._widgets
        }
        self._widgets = discover_widgets(self._widgets_dir)
        self._widgets.update(custom_entries)
        self.view.set_widget_catalog(self._widgets)
