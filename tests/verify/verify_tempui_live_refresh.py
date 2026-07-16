import importlib.util
import os
import sys
import tempfile
import uuid
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.window import DeskWindow  # noqa: E402
from desk.shell.python_widget import PythonWidgetHost  # noqa: E402
from desk.temp_ui import append_answer  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


question_mod = load_widget_module("question_live_mod", "widgets/question/widget.py")
lightning_mod = load_widget_module("lightning_live_mod", "widgets/lightning_round/widget.py")
scratch_mod = load_widget_module("scratch_live_mod", "widgets/scratch/widget.py")
markdown_mod = load_widget_module("markdown_live_mod", "widgets/markdown/widget.py")


class _FakeHost(PythonWidgetHost):
    def __init__(self, current):
        from PyQt6.QtWidgets import QWidget

        QWidget.__init__(self)
        self._current = current
        self.widget_id = "fake"


class _FakeFrame:
    def __init__(self, content, instance_id):
        self.content = content
        self.instance_id = instance_id


class _FakeWindow:
    def __init__(self, frames, directory):
        self._frames = {f.instance_id: f for f in frames}
        self.current_desk = type("D", (), {"directory": directory})()

    def find_frame_by_instance_id(self, instance_id):
        return self._frames.get(instance_id)


_FakeWindow._refresh_live_temp_ui = DeskWindow._refresh_live_temp_ui
_FakeWindow._bind_temp_ui_content = DeskWindow._bind_temp_ui_content
_FakeWindow._resolve_open_markdown_target = staticmethod(DeskWindow._resolve_open_markdown_target)


def test_question_live_refreshes():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        uid = str(uuid.uuid4())
        path = directory / uid
        path.write_text("Question First version?\nOption A\nOption B\n")

        content = question_mod.build()
        content.set_source_file(path)
        assert content._question_label.text() == "First version?"

        frame = _FakeFrame(_FakeHost(content), uid)
        win = _FakeWindow([frame], directory)

        path.write_text("Question Updated version?\nOption A\nOption B\n")
        refreshed = win._refresh_live_temp_ui(path)
        assert refreshed is True
        assert content._question_label.text() == "Updated version?"
    print("Question widget live-refreshes on external edit: PASS")


def test_question_stays_answered_after_refresh():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        uid = str(uuid.uuid4())
        path = directory / uid
        path.write_text("Question Q?\nOption A\nOption B\n")

        content = question_mod.build()
        content.set_source_file(path)
        content._choose("A")  # writes Answer A, disables buttons

        frame = _FakeFrame(_FakeHost(content), uid)
        win = _FakeWindow([frame], directory)

        # External edit adds nothing new but re-triggers the path.
        text = path.read_text()
        path.write_text(text)  # touch, simulating an external "edit"
        win._refresh_live_temp_ui(path)

        assert all(not b.isEnabled() for b in content._option_buttons)
        assert any("✓ A" in b.text() for b in content._option_buttons)
    print("Question stays correctly answered/disabled after a live refresh: PASS")


def test_lightning_round_live_refreshes():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        uid = str(uuid.uuid4())
        path = directory / uid
        path.write_text("LightningRound\tDrill\tPrompt?\nOption N\nOption V\nLRItem\trun\tunanswered\n")

        content = lightning_mod.build()
        content.set_source_file(path)
        assert content._item_label.text() == "run"

        content._choose("V")  # answers "run"

        frame = _FakeFrame(_FakeHost(content), uid)
        win = _FakeWindow([frame], directory)

        # External edit appends a new item.
        current_text = path.read_text()
        path.write_text(current_text + "LRItem\tjump\tunanswered\n")
        refreshed = win._refresh_live_temp_ui(path)
        assert refreshed is True
        assert content._item_label.text() == "jump"
    print("LightningRound widget live-refreshes and preserves answered state: PASS")


def test_markdown_tempui_live_refreshes():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        uid = str(uuid.uuid4())
        path = directory / uid
        path.write_text("Markdown My Notes\n# First\n")

        content = markdown_mod.build()
        content.set_tempui_content("My Notes", "# First")

        frame = _FakeFrame(_FakeHost(content), uid)
        win = _FakeWindow([frame], directory)

        path.write_text("Markdown My Notes\n# Second, updated\n")
        refreshed = win._refresh_live_temp_ui(path)
        assert refreshed is True
        assert content._tempui_content == "# Second, updated"
    print("Markdown tempui-bound widget live-refreshes: PASS")


def test_scratch_live_refreshes_when_untouched():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        uid = str(uuid.uuid4())
        path = directory / uid
        path.write_text("Scratch My Label\noriginal body\n")

        content = scratch_mod.build()
        content.set_label("My Label")
        content.body.setPlainText("original body")

        frame = _FakeFrame(_FakeHost(content), uid)
        win = _FakeWindow([frame], directory)

        assert content.has_unsaved_local_edits() is False
        path.write_text("Scratch My Label\nupdated body from outside\n")
        refreshed = win._refresh_live_temp_ui(path)
        assert refreshed is True
        assert content.body.toPlainText() == "updated body from outside"
    print("Scratch widget live-refreshes when untouched by the user: PASS")


def test_scratch_does_not_clobber_local_edits():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        uid = str(uuid.uuid4())
        path = directory / uid
        path.write_text("Scratch My Label\noriginal body\n")

        content = scratch_mod.build()
        content.set_label("My Label")
        content.body.setPlainText("original body")

        # Simulate real user typing (not setPlainText, which always
        # resets isModified() -- confirmed directly earlier).
        content.body.insertPlainText(" -- user typed this")
        assert content.has_unsaved_local_edits() is True

        frame = _FakeFrame(_FakeHost(content), uid)
        win = _FakeWindow([frame], directory)

        path.write_text("Scratch My Label\nexternal change that should NOT clobber\n")
        refreshed = win._refresh_live_temp_ui(path)
        assert refreshed is False, "must not report a refresh happened"
        assert "user typed this" in content.body.toPlainText()
        assert "external change" not in content.body.toPlainText()
    print("Scratch widget does NOT clobber unsaved local edits: PASS")


def test_falls_through_when_no_frame_exists():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        uid = str(uuid.uuid4())
        path = directory / uid
        path.write_text("Question Q?\nOption A\n")
        win = _FakeWindow([], directory)
        assert win._refresh_live_temp_ui(path) is False
    print("falls through (no live refresh) when no frame is placed yet: PASS")


test_question_live_refreshes()
test_question_stays_answered_after_refresh()
test_lightning_round_live_refreshes()
test_markdown_tempui_live_refreshes()
test_scratch_live_refreshes_when_untouched()
test_scratch_does_not_clobber_local_edits()
test_falls_through_when_no_frame_exists()
print("ALL PASS")
