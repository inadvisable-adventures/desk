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
lets a `python` widget (the Questions widget's own "Discuss" button)
kick off the same new-claude-session discussion flow as the tempui
`DiscussParkingLotItem` keyword (TODO c0875bc) -- see
`desk.shell.window.DeskWindow.start_discussion`."""
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QWidget

_current_directory: Path | None = None
_widget_opener: Callable[[str], QWidget | None] | None = None
_temp_ui_write_recorder: Callable[[Path, str], None] | None = None
_main_window: QWidget | None = None
_widget_path_resolver: Callable[[QPoint], str | None] | None = None
_discuss_starter: Callable[[str, str], None] | None = None


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


def set_discuss_starter(starter: Callable[[str, str], None]) -> None:
    global _discuss_starter
    _discuss_starter = starter


def get_discuss_starter() -> Callable[[str, str], None] | None:
    return _discuss_starter
