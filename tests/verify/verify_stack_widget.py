import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "widgets/stack")

from PyQt6.QtWidgets import QApplication

from desk.shell import current_context
from desk.stack_file import StackFrame, parse_stack_file, render_stack_file

app = QApplication(sys.argv)

import widget as stack_mod


def test_render_parse_round_trip():
    frames = [
        StackFrame(title="Outer investigation", notes="Line one.\nLine two."),
        StackFrame(title="Nested sub-question", notes=""),
        StackFrame(title="Deepest thread", notes="Final notes here."),
    ]
    rendered = render_stack_file(frames)
    parsed = parse_stack_file(rendered)
    assert parsed == frames, (parsed, frames)
    print("render_stack_file/parse_stack_file round-trip: PASS")


def test_render_order_bottom_to_top():
    frames = [StackFrame(title="First (bottom)"), StackFrame(title="Second (top)")]
    rendered = render_stack_file(frames)
    assert rendered.index("First (bottom)") < rendered.index("Second (top)")
    print("render order is bottom-of-stack-first, top-last: PASS")


def test_parse_ignores_preamble():
    text = "# Stack\n\nsome preamble junk\n\n## Real Frame\nnotes\n"
    frames = parse_stack_file(text)
    assert len(frames) == 1
    assert frames[0].title == "Real Frame"
    print("parse ignores content before the first ## heading: PASS")


def test_push_and_pop():
    w = stack_mod.build()
    assert w._rows == []
    w._push()
    w._rows[0].title_edit.setText("First")
    w._push()
    w._rows[1].title_edit.setText("Second")
    assert len(w._rows) == 2
    # Top of stack (most recently pushed) is visually first in the layout.
    assert w._rows_layout.itemAt(0).widget() is w._rows[1]
    assert w._rows_layout.itemAt(1).widget() is w._rows[0]

    w._pop()
    assert len(w._rows) == 1
    assert w._rows[0].title_edit.text() == "First"
    print("push/pop maintain correct stack order and visual layout: PASS")


def test_widget_local_storage_round_trip():
    w = stack_mod.build()
    w._push()
    w._rows[0].title_edit.setText("Bottom")
    w._rows[0].notes_edit.setPlainText("bottom notes")
    w._push()
    w._rows[1].title_edit.setText("Top")
    w._rows[1].notes_edit.setPlainText("top notes")

    data = w.get_widget_local_storage()
    assert data == {
        "frames": [
            {"title": "Bottom", "notes": "bottom notes"},
            {"title": "Top", "notes": "top notes"},
        ]
    }

    w2 = stack_mod.build()
    w2.set_widget_local_storage(data)
    assert len(w2._rows) == 2
    assert w2._rows[0].title_edit.text() == "Bottom"
    assert w2._rows[1].title_edit.text() == "Top"
    # Visual order preserved too.
    assert w2._rows_layout.itemAt(0).widget() is w2._rows[1]
    print("get/set_widget_local_storage round-trip preserves order: PASS")


def test_save_as_markdown_writes_real_file():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        w = stack_mod.build()
        w._push()
        w._rows[0].title_edit.setText("Only frame")
        w._rows[0].notes_edit.setPlainText("some notes")
        w._save_as_markdown()

        matches = list(directory.glob("STACK-*.md"))
        assert len(matches) == 1, matches
        content = matches[0].read_text()
        assert content == render_stack_file(w._current_frames())
        assert "Saved to" in w._status_label.text()
    print("Save as Markdown writes a real STACK-<timestamp>.md file: PASS")


def test_load_replaces_stack_with_confirmation():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        stack_path = directory / "existing-stack.md"
        stack_path.write_text(render_stack_file([StackFrame(title="Loaded frame", notes="loaded notes")]))

        w = stack_mod.build()
        w._push()
        w._rows[0].title_edit.setText("Original frame")

        with patch.object(stack_mod.QFileDialog, "getOpenFileName", return_value=(str(stack_path), "")):
            with patch.object(w, "_show_popup", return_value="Yes"):
                w._load()

        assert len(w._rows) == 1
        assert w._rows[0].title_edit.text() == "Loaded frame"
    print("Load replaces the stack after confirmation: PASS")


def test_load_declined_confirmation_keeps_stack():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        stack_path = directory / "existing-stack.md"
        stack_path.write_text(render_stack_file([StackFrame(title="Loaded frame")]))

        w = stack_mod.build()
        w._push()
        w._rows[0].title_edit.setText("Original frame")

        with patch.object(stack_mod.QFileDialog, "getOpenFileName", return_value=(str(stack_path), "")):
            with patch.object(w, "_show_popup", return_value="No"):
                w._load()

        assert len(w._rows) == 1
        assert w._rows[0].title_edit.text() == "Original frame"
    print("declining Load's confirmation leaves the current stack untouched: PASS")


def test_real_desk_save_load_round_trip():
    from desk.desks import Desk, WidgetState, save_desk, load_desk

    with tempfile.TemporaryDirectory() as d:
        desk_path = Path(d) / "test.desk"
        w = stack_mod.build()
        w._push()
        w._rows[0].title_edit.setText("Bottom")
        w._push()
        w._rows[1].title_edit.setText("Top")

        ws = WidgetState("stack", 0.0, 0.0, 400.0, 500.0, instance_id="s1", state=w.get_widget_local_storage())
        save_desk(Desk(path=desk_path, widgets=[ws]))

        loaded = load_desk(desk_path)
        w2 = stack_mod.build()
        w2.set_widget_local_storage(loaded.widgets[0].state)
        assert [r.title_edit.text() for r in w2._rows] == ["Bottom", "Top"]
    print("real Desk save/load round-trip preserves the stack: PASS")


test_render_parse_round_trip()
test_render_order_bottom_to_top()
test_parse_ignores_preamble()
test_push_and_pop()
test_widget_local_storage_round_trip()
test_save_as_markdown_writes_real_file()
test_load_replaces_stack_with_confirmation()
test_load_declined_confirmation_keeps_stack()
test_real_desk_save_load_round_trip()
print("ALL PASS")
