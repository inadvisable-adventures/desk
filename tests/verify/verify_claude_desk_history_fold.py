"""Verifies TODO `ed5c62f`: tool-invocation fold/collapse in the
Claude (Desk) widget's history view. See
`plans/claude-desk-history-fold.md`. Follows
`verify_claude_desk_widget.py`'s own established shape -- a real
widget built via `module.build()`, `_on_tool_use`/`_on_tool_result`
called directly, no real `ClaudeSession`/network calls."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# desk.shell.window must be importable before QApplication is
# constructed -- see verify_claude_desk_widget.py's own comment on
# this exact gotcha.
import desk.shell.window  # noqa: E402,F401

from PyQt6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent, QTextCursor  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def _load_widget_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "claude_desk_history_fold_check", REPO_ROOT / "widgets" / "claude_desk" / "widget.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _point_for_position(widget, position: int) -> QPointF:
    cursor = QTextCursor(widget._history.document())
    cursor.setPosition(position)
    rect = widget._history.cursorRect(cursor)
    return QPointF(rect.center())


def _mouse_event(kind: QEvent.Type, point: QPointF) -> QMouseEvent:
    button = Qt.MouseButton.LeftButton
    buttons = button if kind == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton
    return QMouseEvent(kind, point, point, button, buttons, Qt.KeyboardModifier.NoModifier)


def _click(widget, position: int) -> None:
    point = _point_for_position(widget, position)
    viewport = widget._history.viewport()
    widget.eventFilter(viewport, _mouse_event(QEvent.Type.MouseButtonPress, point))
    widget.eventFilter(viewport, _mouse_event(QEvent.Type.MouseButtonRelease, point))


module = _load_widget_module()

LONG_CONTENT = "line one is reasonably long on its own right here\n" + "line two follows after a real newline"
LONG_SINGLE_LINE = "x" * 200
SHORT_SINGLE_LINE = "short"


# -- _truncate_for_header --------------------------------------------


def test_truncate_short_single_line_unchanged():
    check("short single-line text passes through unchanged", module._truncate_for_header(SHORT_SINGLE_LINE) == SHORT_SINGLE_LINE)


def test_truncate_long_single_line():
    result = module._truncate_for_header(LONG_SINGLE_LINE, max_chars=20)
    check("truncated to the requested length plus ellipsis", result == ("x" * 20) + "…")
    check("truncated result differs from the original", result != LONG_SINGLE_LINE)


def test_truncate_short_but_multiline():
    text = "fits\nbut has more after it"
    result = module._truncate_for_header(text, max_chars=80)
    check("a short first line still gets truncated when more lines follow", result == "fits…")
    check("differs from the original even though the first line alone would fit", result != text)


# -- Short tool calls: unchanged, no fold entry -----------------------


def test_short_tool_use_creates_no_fold_entry():
    widget = module.build()
    widget._on_tool_use("id1", "Write", {"path": "x"})
    check("no fold entry for a short tool call", widget._history_fold_entries == [])
    check("plain header line, exactly as before this change", "[tool] Write(path='x')" in widget._history.toPlainText())


def test_short_tool_result_creates_no_fold_entry():
    widget = module.build()
    widget._on_tool_result("id1", "ok", False)
    check("no fold entry for a short tool result", widget._history_fold_entries == [])
    check("plain result line, exactly as before this change", "[tool result] ok" in widget._history.toPlainText())


# -- Long tool calls/results: folded, collapsed by default ------------


def test_long_tool_use_is_folded():
    widget = module.build()
    widget._on_tool_use("id1", "Write", {"content": LONG_SINGLE_LINE})
    check("exactly one fold entry", len(widget._history_fold_entries) == 1)
    entry = widget._history_fold_entries[0]
    check("starts collapsed", entry.expanded is False)

    document = widget._history.document()
    block = document.findBlockByNumber(entry.first_detail_block)
    all_hidden = True
    while block.isValid() and block.blockNumber() <= entry.last_detail_block:
        all_hidden = all_hidden and not block.isVisible()
        block = block.next()
    check("every detail block starts hidden", all_hidden)

    header_cursor = QTextCursor(document)
    header_cursor.setPosition(entry.header_start)
    header_cursor.setPosition(entry.header_end, QTextCursor.MoveMode.KeepAnchor)
    check("header shows a truncated preview, not the full args", LONG_SINGLE_LINE not in header_cursor.selectedText())
    check("the full args are still present somewhere in the full text (just hidden)", LONG_SINGLE_LINE in widget._history.toPlainText())


def test_long_tool_result_is_folded_for_both_markers():
    for is_error, marker in [(False, "tool result"), (True, "tool error")]:
        widget = module.build()
        widget._on_tool_result("id1", LONG_CONTENT, is_error)
        check(f"exactly one fold entry ({marker})", len(widget._history_fold_entries) == 1)
        entry = widget._history_fold_entries[0]
        header_cursor = QTextCursor(widget._history.document())
        header_cursor.setPosition(entry.header_start)
        header_cursor.setPosition(entry.header_end, QTextCursor.MoveMode.KeepAnchor)
        check(f"header starts with the right marker ({marker})", header_cursor.selectedText().startswith(f"[{marker}]"))
        check(f"the full content is still present, just hidden ({marker})", LONG_CONTENT.splitlines()[1] in widget._history.toPlainText())


# -- Click to toggle ----------------------------------------------------


def test_clicking_header_toggles_and_click_again_reverts():
    widget = module.build()
    widget._on_tool_use("id1", "Write", {"content": LONG_SINGLE_LINE})
    entry = widget._history_fold_entries[0]

    _click(widget, entry.header_start)
    check("first click expands", entry.expanded is True)
    document = widget._history.document()
    block = document.findBlockByNumber(entry.first_detail_block)
    check("detail block now visible", block.isVisible() is True)

    _click(widget, entry.header_start)
    check("second click collapses again", entry.expanded is False)
    block = document.findBlockByNumber(entry.first_detail_block)
    check("detail block hidden again", block.isVisible() is False)


def test_drag_starting_on_header_does_not_toggle():
    widget = module.build()
    widget._on_tool_use("id1", "Write", {"content": LONG_SINGLE_LINE})
    entry = widget._history_fold_entries[0]

    press_point = _point_for_position(widget, entry.header_start)
    # Release far away -- not the same fold entry (or no entry at all).
    release_point = QPointF(press_point.x(), press_point.y() + 5000)
    viewport = widget._history.viewport()
    widget.eventFilter(viewport, _mouse_event(QEvent.Type.MouseButtonPress, press_point))
    widget.eventFilter(viewport, _mouse_event(QEvent.Type.MouseButtonRelease, release_point))

    check("a press-then-release-elsewhere never toggles the fold", entry.expanded is False)


# -- Toggling doesn't disturb other entries' stored offsets -------------


def test_toggling_one_entry_leaves_others_and_reload_entries_unchanged():
    widget = module.build()
    widget._on_tool_use("id1", "Write", {"content": LONG_SINGLE_LINE})
    first_entry = widget._history_fold_entries[0]

    widget._prompt_input.setPlainText("a user message")
    widget._on_send_clicked()
    reload_entry_before = widget._history_user_entries[0]

    widget._on_tool_result("id2", LONG_CONTENT, False)
    second_entry = widget._history_fold_entries[1]
    first_entry_before = (first_entry.header_start, first_entry.header_end)
    second_entry_before = (second_entry.header_start, second_entry.header_end)

    widget._toggle_fold(first_entry)

    check("toggling the first entry doesn't move its own header offsets", (first_entry.header_start, first_entry.header_end) == first_entry_before)
    check("toggling the first entry leaves a later fold entry's offsets untouched", (second_entry.header_start, second_entry.header_end) == second_entry_before)
    check("toggling a fold entry leaves an existing reload-hover entry's offsets untouched", widget._history_user_entries[0] == reload_entry_before)


# -- One-time hint --------------------------------------------------------


def test_hint_shown_exactly_once():
    widget = module.build()
    widget._on_tool_use("id1", "Write", {"content": LONG_SINGLE_LINE})
    widget._on_tool_result("id2", LONG_CONTENT, False)
    check("hint line appears exactly once", widget._history.toPlainText().count(module.FOLD_HINT_TEXT) == 1)


# -- Extra-selection bookkeeping -------------------------------------------


def test_fold_header_selections_track_collapsed_entries_only():
    widget = module.build()
    widget._on_tool_use("id1", "Write", {"content": LONG_SINGLE_LINE})
    widget._on_tool_result("id2", LONG_CONTENT, False)
    check("two collapsed entries -> two header selections", len(widget._history_fold_header_selections) == 2)

    widget._toggle_fold(widget._history_fold_entries[0])
    check("expanding one entry drops its own header selection", len(widget._history_fold_header_selections) == 1)


test_truncate_short_single_line_unchanged()
test_truncate_long_single_line()
test_truncate_short_but_multiline()
test_short_tool_use_creates_no_fold_entry()
test_short_tool_result_creates_no_fold_entry()
test_long_tool_use_is_folded()
test_long_tool_result_is_folded_for_both_markers()
test_clicking_header_toggles_and_click_again_reverts()
test_drag_starting_on_header_does_not_toggle()
test_toggling_one_entry_leaves_others_and_reload_entries_unchanged()
test_hint_shown_exactly_once()
test_fold_header_selections_track_collapsed_entries_only()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
