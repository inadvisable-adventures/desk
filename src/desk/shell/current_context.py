"""A minimal, direct-import mechanism for `python` widgets to learn the
current Desk's associated directory -- deferred since item 18 (the Code
Editor widget explicitly scoped this out: "no python widget has a way to
learn the current Desk's directory yet"). See plans/todo-widget.md.

Deliberately just a module-level get/set pair, no signal/notification of
later changes: only one widget (the TODO widget) needs this so far, and
it resolves the directory once at construction with a manual reload
affordance rather than reacting live to Desk switches. A real
"Desk changed" broker signal (mirroring HotReloadBroker) is the right
move once a second caller actually needs live updates -- not before.

Also holds a "widget opener" hook (same minimal-module-level-pair
shape), set once by `DeskWindow` at construction: the first way a
`python` widget can place another widget instance on the canvas (needed
by the TODO widget's edit-conflict handling, TODO d25e557, to spawn a
Scratch widget). See `desk.shell.window.DeskWindow.open_widget_content`.

Also holds a "temp UI write recorder" hook, same shape again: lets the
Question Widget (TODO a02b001) tell `TempUiManager` about its own
answer-append so the manager's file watcher doesn't mistake it for a
real external edit and fire a spurious notification. See
`desk.shell.temp_ui_manager.TempUiManager.record_own_write`.

Also holds a "main window" hook and a "widget path resolver" hook
(TODO f2aede6), same minimal shape again: let the Feedback widget grab
a screenshot of the app's own window and resolve a global screen
position to a human-readable description of whichever widget is
there, without needing to import `desk.shell.window`/
`desk.shell.canvas` directly (the same decoupling the widget-opener
hook already gives `open_widget_content`).

Also holds a "discuss starter" hook (TODO 46e1b42), same shape again:
lets a `python` widget (the Questions widget's own "Discuss" button,
and the Parking Lot widget's own per-row "Discuss" button, TODO
a48e968) kick off the same new-claude-session discussion flow as the
tempui `DiscussParkingLotItem` keyword (TODO c0875bc) -- see
`desk.shell.window.DeskWindow.start_discussion`. Its optional third
argument (`parking_lot_line`, TODO 624ff3a) lets a caller that already
knows a PARKINGLOT.md item's starting line reference it that way
instead of passing the item's full text.

Also holds an "event mediator" hook (TODO 6f9c51b), same shape again:
lets a `python` widget reach the shared `desk.event_mediator
.EventMediator` instance directly (no HTTP, matching every other
python-widget-facing capability here) -- though a widget wanting to
subscribe/receive should generally go through
`desk.shell.event_broker.EventSubscription` (a Qt-friendly wrapper)
rather than calling the mediator's own blocking `poll()` directly from
the GUI thread. See `desk.shell.window.DeskWindow._bind_event_mediator`
for how a widget's own instance id reaches it (the same
"resolved after `build()`, not through it" shape `_bind_claude_widget`
already established).

Also holds a "widget zoomer" hook and a "widget display name resolver"
hook (TODO 7505703), same minimal shape again: let the Event
Subscribers widget zoom/pan the Workspace Canvas to a specific placed
widget instance (by instance id) and show a human-readable label for
one, without needing to import `desk.shell.window`/`desk.shell.canvas`
directly -- see `desk.shell.window.DeskWindow
.zoom_to_widget_by_instance_id`/`_display_name_for_instance`."""
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QWidget

from desk.event_mediator import EventMediator

_current_directory: Path | None = None
_widget_opener: Callable[[str], QWidget | None] | None = None
_centered_widget_opener: Callable[[str], QWidget | None] | None = None
_editor_or_scrap_opener: Callable[[Path], None] | None = None
_temp_ui_write_recorder: Callable[[Path, str], None] | None = None
_main_window: QWidget | None = None
_widget_path_resolver: Callable[[QPoint], str | None] | None = None
_discuss_starter: Callable[[str, str, int | None], None] | None = None
_event_mediator: EventMediator | None = None
_widget_zoomer: Callable[[str], bool] | None = None
_widget_display_name_resolver: Callable[[str], str] | None = None
_file_type_registry_provider: Callable[[], list[dict]] | None = None


def set_current_desk_directory(directory: Path) -> None:
    global _current_directory
    _current_directory = directory


def get_current_desk_directory() -> Path | None:
    return _current_directory


def path_is_external(path: Path) -> bool:
    """Whether `path` is outside `get_current_desk_directory()` -- used
    by widgets that load a single file to show an "[EXTERNAL]" titlebar
    marker (TODO a053e3a). `False` if there's no current Desk directory
    known yet (nothing to be "outside" of)."""
    directory = _current_directory
    if directory is None:
        return False
    try:
        path.resolve().relative_to(directory.resolve())
        return False
    except (ValueError, OSError):
        return True


def set_widget_opener(opener: Callable[[str], QWidget | None]) -> None:
    global _widget_opener
    _widget_opener = opener


def get_widget_opener() -> Callable[[str], QWidget | None] | None:
    return _widget_opener


def set_centered_widget_opener(opener: Callable[[str], QWidget | None]) -> None:
    """Like set_widget_opener, but the opened instance is placed
    centered in the current view (TODO efdad99) -- get_widget_opener's
    own DeskWindow.open_widget_content places at (0, 0) by default,
    which several tempui/programmatic placements elsewhere in this
    codebase (_place_discuss_claude_widget, _auto_place_new_custom_widget)
    deliberately avoid; this hook gives a kind:"python" widget the same
    centered convention without needing to reach into DeskWindow's own
    view/scene math itself."""
    global _centered_widget_opener
    _centered_widget_opener = opener


def get_centered_widget_opener() -> Callable[[str], QWidget | None] | None:
    return _centered_widget_opener


def set_editor_or_scrap_opener(opener: Callable[[Path], None]) -> None:
    """The shared "open an editor for this file, or fall back to an
    explanatory Scratch note" service (TODO da4f9c0) -- originally
    built inline in Project Files' own double-click fallback chain
    (TODO efdad99), extracted here so every viewer widget's Edit
    button (image_viewer/markdown) reuses the exact same logic instead
    of each carrying its own copy. See
    DeskWindow.open_editor_or_scrap. `kind: "html"` widgets reach the
    same service over the real Bridge API instead (TODO 2da314f) --
    this hook is for `kind: "python"` widgets only."""
    global _editor_or_scrap_opener
    _editor_or_scrap_opener = opener


def get_editor_or_scrap_opener() -> Callable[[Path], None] | None:
    return _editor_or_scrap_opener


def set_temp_ui_write_recorder(recorder: Callable[[Path, str], None]) -> None:
    global _temp_ui_write_recorder
    _temp_ui_write_recorder = recorder


def get_temp_ui_write_recorder() -> Callable[[Path, str], None] | None:
    return _temp_ui_write_recorder


def set_main_window(window: QWidget) -> None:
    global _main_window
    _main_window = window


def get_main_window() -> QWidget | None:
    return _main_window


def set_widget_path_resolver(resolver: Callable[[QPoint], str | None]) -> None:
    global _widget_path_resolver
    _widget_path_resolver = resolver


def get_widget_path_resolver() -> Callable[[QPoint], str | None] | None:
    return _widget_path_resolver


def set_discuss_starter(starter: Callable[[str, str, int | None], None]) -> None:
    global _discuss_starter
    _discuss_starter = starter


def get_discuss_starter() -> Callable[[str, str, int | None], None] | None:
    return _discuss_starter


def set_event_mediator(mediator: EventMediator) -> None:
    global _event_mediator
    _event_mediator = mediator


def get_event_mediator() -> EventMediator | None:
    return _event_mediator


def set_widget_zoomer(zoomer: Callable[[str], bool]) -> None:
    global _widget_zoomer
    _widget_zoomer = zoomer


def get_widget_zoomer() -> Callable[[str], bool] | None:
    return _widget_zoomer


def set_widget_display_name_resolver(resolver: Callable[[str], str]) -> None:
    global _widget_display_name_resolver
    _widget_display_name_resolver = resolver


def get_widget_display_name_resolver() -> Callable[[str], str] | None:
    return _widget_display_name_resolver


def set_file_type_registry_provider(provider: Callable[[], list[dict]]) -> None:
    """TODO b5d52c0: lets a `kind: "python"` widget read the current
    file type registry once (e.g. on its own `__init__`) without
    reaching into `DeskWindow` directly -- the same in-process,
    current_context-hook shape every other Desk service reaches a
    python widget through, rather than a real HTTP Bridge API call
    (that mechanism is `kind: "html"`-only). Live updates after the
    initial read arrive separately, via the existing generic
    `bind_event_mediator` mechanism (TODO 6f9c51b) -- see
    `desk.file_type_registry.FILE_TYPE_REGISTRY_UPDATED_EVENT`."""
    global _file_type_registry_provider
    _file_type_registry_provider = provider


def get_file_type_registry_provider() -> Callable[[], list[dict]] | None:
    return _file_type_registry_provider
