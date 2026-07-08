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
`desk.shell.temp_ui_manager.TempUiManager.record_own_write`."""
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtWidgets import QWidget

_current_directory: Path | None = None
_widget_opener: Callable[[str], QWidget | None] | None = None
_temp_ui_write_recorder: Callable[[Path, str], None] | None = None


def set_current_desk_directory(directory: Path) -> None:
    global _current_directory
    _current_directory = directory


def get_current_desk_directory() -> Path | None:
    return _current_directory


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
