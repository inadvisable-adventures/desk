import uuid
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QPointF, QTimer
from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMainWindow, QMessageBox, QWidget

from desk.desks import DESK_SUFFIX, Desk, WidgetState, desk_state_dict, load_desk, save_desk
from desk.file_watch import SingleFileWatcher
from desk.hotreload import HotReloadBroker
from desk.questions_file import find_nearest_questions_file, parse_questions_file
from desk.recent_desks import add_to_mru, load_mru
from desk.server.runner import ServerHandle
from desk.shell import current_context
from desk.shell.canvas import WorkspaceView
from desk.shell.chromium_widget import ChromiumWidget
from desk.shell.python_widget import PythonWidgetHost
from desk.shell.temp_ui_manager import TempUiManager
from desk.shell.widget_frame import WidgetFrame
from desk.temp_ui import (
    TEMP_UI_DIRNAME,
    detect_temp_ui_kind,
    parse_lightning_round,
    parse_markdown_tempui,
    parse_open_markdown,
    parse_scratch,
    parse_temp_ui,
)
from desk.widgets import WidgetInfo, discover_widgets

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
SVG_VIEWER_WIDGET_ID = "svg_viewer"
EDITOR_WIDGET_ID = "editor"

# Which widget kind opens a dropped file (TODO 5915ac2), by extension --
# only these three widget kinds currently expose set_file. Everything not
# listed here falls back to the Editor, same as File Explorer's own
# always-Editor "open" action.
EXTERNAL_DROP_WIDGET_BY_SUFFIX = {
    ".md": MARKDOWN_WIDGET_ID,
    ".svg": SVG_VIEWER_WIDGET_ID,
}
# Every widget kind that renders a TempUI file (TODO a02b001/TODO
# 11aeb43/TODO 42dd260/TODO f8d9cec) and needs the same instance_id
# -equals-source-file-uuid reconnection handling -- see
# _load_desk_widgets/_bind_temp_ui_widget. A manually-placed
# markdown/scratch instance's restore is a safe no-op under this (see
# _bind_temp_ui_content): its instance_id won't match any real
# .desk_temp/ filename, so it just falls through unchanged, same as
# its existing no-persistence-across-reload behavior.
TEMP_UI_WIDGET_IDS = {
    QUESTION_WIDGET_ID,
    LIGHTNING_ROUND_WIDGET_ID,
    MARKDOWN_WIDGET_ID,
    SCRATCH_WIDGET_ID,
}

WIDGET_SPACING = 700
# TODO fbd0554: the well-known project-convention filename this
# codebase's own development-process.md itself names -- a plain
# literal, not a piece of shared behavior worth its own module.
DEVELOPMENT_PROCESS_FILENAME = "development-process.md"

Confirm = Callable[[], bool]


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
        if widgets_dir is not None:
            broker.widget_changed.connect(self._on_widget_changed_refresh_catalog)

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
        self._load_desk_widgets(self.current_desk)
        self.view.set_view_state(
            self.current_desk.pan_x, self.current_desk.pan_y, self.current_desk.scale
        )
        current_context.set_widget_opener(self.open_widget_content)
        current_context.set_temp_ui_write_recorder(self._temp_ui_manager.record_own_write)
        self._provision_temp_ui()

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
                self._bind_widget_local_storage(frame, state.state)
        else:
            for index, (widget_id, widget) in enumerate(sorted(self._widgets.items())):
                pos = (index * WIDGET_SPACING, 0)
                self._place_widget(widget_id, widget, pos, widget.default_size)

    def _place_widget(
        self,
        widget_id: str,
        widget: WidgetInfo,
        pos: tuple[float, float],
        size: tuple[int, int] | None,
        instance_id: str | None = None,
        restore: bool = False,
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
            chromium_widget = ChromiumWidget(
                widget_id, self._handle.widget_url(widget_id), self._handle.token, self._broker
            )
            proxy = self.view.add_widget(
                chromium_widget, title=widget.name, pos=pos, size=size, instance_id=instance_id
            )
        frame = proxy.widget()
        if widget_id == CLAUDE_WIDGET_ID:
            self._bind_claude_widget(frame, resume=restore)
        self._bind_external_indicator(frame)
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

    def _bind_claude_widget(self, frame: WidgetFrame, resume: bool) -> None:
        """Launches `claude` in a just-placed claude widget, bound to the
        widget's instance_id as its session id -- fresh (--session-id +
        prompt) or resuming (--resume, no prompt). Duck-typed on
        start_session so window.py needn't import the widget class,
        matching _bind_temp_ui_widget's style."""
        if not isinstance(frame.content, PythonWidgetHost):
            return
        content = frame.content.current
        if content is not None and hasattr(content, "start_session"):
            content.start_session(frame.instance_id, resume=resume)
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

    def _bind_temp_ui_widget(self, frame: WidgetFrame, directory: Path, uuid_str: str) -> None:
        if not isinstance(frame.content, PythonWidgetHost):
            return
        content = frame.content.current
        if content is not None:
            self._bind_temp_ui_content(content, directory / TEMP_UI_DIRNAME / uuid_str, directory)

    def _bind_widget_local_storage(self, frame: WidgetFrame, data: dict) -> None:
        """Restores a widget's "widget-local storage" (TODO fb76057) --
        only called from the Desk-reload restore path, since a fresh
        placement has no prior data to restore. Duck-typed the same way
        `hasattr(content, "set_file")` already is elsewhere in this
        file: a widget that doesn't implement `set_widget_local_storage`
        is a safe no-op, not an error."""
        if not isinstance(frame.content, PythonWidgetHost):
            return
        content = frame.content.current
        if content is None or not hasattr(content, "set_widget_local_storage"):
            return
        content.set_widget_local_storage(data)

    @staticmethod
    def _get_widget_local_storage(frame: WidgetFrame) -> dict:
        """The counterpart read side, called by `_capture_desk_state`
        on every save -- pull-based, not push-based, since a Desk save
        already re-reads every other per-widget field (geometry) fresh
        at save time rather than tracking live changes. A widget that
        doesn't implement `get_widget_local_storage` contributes an
        empty dict, same as it always implicitly had before this TODO."""
        if not isinstance(frame.content, PythonWidgetHost):
            return {}
        content = frame.content.current
        if content is None or not hasattr(content, "get_widget_local_storage"):
            return {}
        return content.get_widget_local_storage()

    def _bind_temp_ui_content(self, content, tempui_path: Path, directory: Path) -> None:
        """Wires a freshly-placed or restored TempUI-backed widget's
        content to its source tempui_path -- Question/LightningRound
        render the tempui file itself (set_source_file); OpenMarkdown
        instead parses out its *target* Markdown path and opens that
        (set_file), since it's a pure fire-and-forget viewer action
        with no answer to render back into the tempui file. Scratch
        (TODO f8d9cec) is the same fire-and-forget shape as OpenMarkdown,
        just seeding a label + initial body text instead of a path.
        Markdown (TODO 9743419) is the same shape again, but renders
        its own content directly (set_tempui_content) rather than
        pointing at a separate file the way OpenMarkdown does. Shared
        by both the notification-click path (_activate_temp_ui) and the
        Desk-reload restore path (_bind_temp_ui_widget) so there's one
        place deciding which method gets which path."""
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
        self.save_current_desk()
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
                )
            )
        pan_x, pan_y, scale = self.view.get_view_state()
        return Desk(
            path=self.current_desk.path, widgets=widget_states, pan_x=pan_x, pan_y=pan_y, scale=scale
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

    def switch_desk(self, path: Path, confirm: Confirm | None = None) -> None:
        if path == self.current_desk.path:
            return
        confirm = confirm or self._confirm_fn("Switch Desk", f"Switch to “{path.stem}”?")
        if not confirm():
            return
        self.save_current_desk()
        self.view.clear_widgets()
        new_desk = load_desk(path) if path.is_file() else Desk(path=path)
        self.current_desk = new_desk
        self._load_desk_widgets(new_desk)
        self.view.set_view_state(new_desk.pan_x, new_desk.pan_y, new_desk.scale)
        add_to_mru(path)
        self._refresh_picker()
        self._provision_temp_ui()

    def close_widget(self, frame: WidgetFrame, confirm: Confirm | None = None) -> None:
        confirm = confirm or self._confirm_fn(
            "Remove Widget", "Remove this widget from the Desk?"
        )
        if not confirm():
            return
        self.view.remove_widget(frame)
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

    def new_desk(self, name: str, directory: Path) -> None:
        """Creates a new, empty Desk named `name` in `directory` and
        switches to it. Naming the Desk *is* the intent, so (unlike
        switch_desk) there's no "Switch to X?" confirmation."""
        name = name.strip()
        if not name:
            return
        path = directory / (name + DESK_SUFFIX)
        if path.exists():
            self._warn("New Desk", f"A Desk named “{name}” already exists here.")
            return
        self.switch_desk(path, confirm=lambda: True)
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

    def _provision_temp_ui(self) -> None:
        """Ensures .desk_temp/desk-temporary-ui.md/.gitignore entry exist
        for the current Desk's directory (TODO a02b001) -- called at boot
        and whenever the directory actually changes. TempUiManager itself
        guards against re-prompting for a directory it already
        provisioned, so this can be called unconditionally here."""
        directory = self.current_desk.directory
        self._temp_ui_manager.provision(
            directory,
            self._confirm_fn(
                "Temporary UI",
                f"Create “{TEMP_UI_DIRNAME}” in “{directory}” so agents can create "
                "temporary UI here?",
            ),
            self._confirm_fn("Temporary UI", f"Add “{TEMP_UI_DIRNAME}” to .gitignore?"),
        )
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
        self._notify_temp_ui(path)

    def _on_temp_ui_file_edited(self, path: Path) -> None:
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
            kind = detect_temp_ui_kind(content_text)
            if kind == "lightning_round":
                lr_doc = parse_lightning_round(content_text)
                if lr_doc.prompt or lr_doc.name:
                    text = lr_doc.prompt or lr_doc.name
            elif kind == "open_markdown":
                target = parse_open_markdown(content_text)
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
            kind = detect_temp_ui_kind(path.read_text())
        except OSError:
            kind = "question"
        if kind == "lightning_round":
            return LIGHTNING_ROUND_WIDGET_ID
        if kind in ("open_markdown", "markdown_content"):
            return MARKDOWN_WIDGET_ID
        if kind == "scratch":
            return SCRATCH_WIDGET_ID
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

    def _refresh_picker(self) -> None:
        self.view.desk_picker.set_current(self.current_desk.name, self.current_desk.directory)
        self.view.desk_picker.set_mru(load_mru(), self.current_desk.path)
        # Keeps python widgets' access to "the current Desk's directory"
        # (see desk.shell.current_context, deferred since item 18) in sync
        # with everything else this method already refreshes.
        current_context.set_current_desk_directory(self.current_desk.directory)

    def _on_desk_chosen(self, path: Path) -> None:
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
        name = self._prompt_fn("New Desk", "Name for the new Desk:")()
        if not name:
            return
        chosen = QFileDialog.getExistingDirectory(
            self, "New Desk Directory", str(self.current_desk.directory)
        )
        if not chosen:
            return
        directory = Path(chosen)
        source = self.current_desk.directory / DEVELOPMENT_PROCESS_FILENAME
        destination = directory / DEVELOPMENT_PROCESS_FILENAME
        if source.is_file() and source.resolve() != destination.resolve():
            confirm = self._confirm_fn(
                "New Desk",
                f"Initialize the new Desk's directory with a copy of "
                f"“{DEVELOPMENT_PROCESS_FILENAME}”?",
            )
            if confirm():
                self._seed_development_process(directory)
        self.new_desk(name, directory)

    def _seed_development_process(self, directory: Path) -> None:
        """Copies the current Desk's development-process.md into
        `directory` (TODO fbd0554) -- a no-op if the current Desk has
        none to source from, or if `directory` already has its own
        (never silently overwritten)."""
        source = self.current_desk.directory / DEVELOPMENT_PROCESS_FILENAME
        destination = directory / DEVELOPMENT_PROCESS_FILENAME
        if not source.is_file() or destination.exists():
            return
        destination.write_text(source.read_text())

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
        from the drop's own scene position."""
        for index, path in enumerate(paths):
            widget_id = EXTERNAL_DROP_WIDGET_BY_SUFFIX.get(path.suffix.lower(), EDITOR_WIDGET_ID)
            widget = self._widgets.get(widget_id)
            if widget is None:
                continue
            pos = (scene_pos.x() + index * WIDGET_SPACING, scene_pos.y())
            content = self.open_widget_content(widget_id, pos=pos, size=widget.default_size)
            if content is not None and hasattr(content, "set_file"):
                content.set_file(path)

    def _on_widget_changed_refresh_catalog(self, _widget_id: str) -> None:
        """Keeps the widget catalog (add-widget menu, recognized
        widget_ids) live: a directory added/removed/changed under
        widgets_dir has no effect until this re-runs discover_widgets() --
        see plans/generalized-hot-reload.md. Cheap: a handful of small
        widget.json reads, on every debounced widget-changed event."""
        self._widgets = discover_widgets(self._widgets_dir)
        self.view.set_widget_catalog(self._widgets)
