# Note: the test that places a real ClaudeWidget and spawns a real
# `claude` CLI process (a live Claude API dependency: real network
# calls, real API cost) was split out to
# tests/verify/disabled_verify_questions_discuss_button_claude_api.py
# and disabled there (TODO 9bc522b). The test remaining here (the
# Discuss button's hover/click UI) drives the discuss-starter hook
# through a patch, no live API involved.
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell import current_context  # noqa: E402
from PyQt6.QtCore import QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------- QuestionsWidget's Discuss button ----------


def test_discuss_button_shows_on_hover_and_calls_starter():
    questions_mod = load_widget_module("questions_discuss_verify_mod", "widgets/questions/widget.py")
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / "QUESTIONS.md").write_text(
            "# Questions with optional answers\n\n"
            "## TODO `9743419`: First question\n"
            "Should we use approach A or B?\n"
            "(Answer: )\n"
        )
        with patch.object(questions_mod.current_context, "get_current_desk_directory", return_value=directory):
            widget = questions_mod.build()
            widget.resize(500, 400)
            widget.show()
            app.processEvents()

            assert widget._list.count() == 1
            list_item = widget._list.item(0)
            entry = list_item.data(questions_mod.ENTRY_ROLE)
            assert "First question" in entry.raw_text
            assert "TODO" in entry.raw_text
            assert "(Answer: )" in entry.raw_text

            assert widget._discuss_button.isHidden()
            widget._on_item_entered(list_item)
            assert widget._discuss_button.isVisible()
            assert widget._discuss_item is list_item

            calls = []
            recorded_starter = lambda source_label, item_text: calls.append((source_label, item_text))
            with patch.object(current_context, "get_discuss_starter", return_value=recorded_starter):
                widget._discuss_hovered_entry()
            assert calls == [("QUESTIONS.md", entry.raw_text)]
            # Clicking hides the button again (mirrors the Plan button's
            # own hide-after-open behavior).
            assert widget._discuss_button.isHidden()

            # Leaving the list view hides the button too.
            widget._on_item_entered(list_item)
            assert widget._discuss_button.isVisible()
            widget.eventFilter(widget._list.viewport(), QEvent(QEvent.Type.Leave))
            assert widget._discuss_button.isHidden()
    print("QuestionsWidget: Discuss button shows on hover, calls the discuss-starter hook with "
          "(QUESTIONS.md, entry.raw_text), hides on click/mouse-leave: PASS")


test_discuss_button_shows_on_hover_and_calls_starter()
print("ALL PASS")
