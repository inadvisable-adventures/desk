import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from desk.shell.window import DeskWindow, QUESTIONS_WIDGET_ID  # noqa: E402
from desk.shell.python_widget import PythonWidgetHost  # noqa: E402

app = QApplication(sys.argv)

SAMPLE = """# Questions with optional answers

## TODO `aaaaaaa`: first question

body

(Answer: )

"""


class _FakeWatcher:
    def __init__(self):
        self.watched = None
        self.stopped = False

    def watch(self, path):
        self.watched = path

    def stop(self):
        self.stopped = True


class _FakeFrame:
    def __init__(self, widget_id):
        self.content = _FakeHost(widget_id)
        self._proxy = _FakeProxy()

    def graphicsProxyWidget(self):
        return self._proxy


class _FakeHost(PythonWidgetHost):
    def __init__(self, widget_id):
        QWidget.__init__(self)
        self.widget_id = widget_id


class _FakeRect:
    def center(self):
        return "CENTER"


class _FakeProxy:
    def sceneBoundingRect(self):
        return _FakeRect()


class _FakeView:
    def __init__(self, frames):
        self._frames = frames
        self.notify_calls = []
        self.center_on_calls = []

    def notify_temp_ui(self, path, text, on_clicked):
        self.notify_calls.append((path, text, on_clicked))

    def centerOn(self, point):
        self.center_on_calls.append(point)

    def mapToScene(self, point):
        return _FakePoint()

    def viewport(self):
        return _FakeViewport()


class _FakeViewport:
    def rect(self):
        return _FakeRectWithCenter()


class _FakeRectWithCenter:
    def center(self):
        return "VIEWPORT_CENTER"


class _FakePoint:
    def x(self):
        return 0.0

    def y(self):
        return 0.0


class _FakeWindow:
    def __init__(self, directory, frames=None):
        self.current_desk = type("D", (), {"directory": directory})()
        self._questions_watcher = _FakeWatcher()
        self._questions_path = None
        self._known_question_keys = None
        self.view = _FakeView(frames or [])
        self._widgets = {}
        self.placed = []

    def _place_widget(self, widget_id, widget, pos, size):
        self.placed.append((widget_id, widget, pos, size))
        return _FakeFrame(widget_id)


_FakeWindow._ensure_questions_watcher = DeskWindow._ensure_questions_watcher
_FakeWindow._on_questions_file_changed = DeskWindow._on_questions_file_changed
_FakeWindow._find_frame_by_widget_id = DeskWindow._find_frame_by_widget_id
_FakeWindow._focus_questions_widget = DeskWindow._focus_questions_widget


def test_ensure_watcher_seeds_baseline():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        path = directory / "QUESTIONS.md"
        path.write_text(SAMPLE)
        win = _FakeWindow(directory)
        win._ensure_questions_watcher()
        assert win._questions_watcher.watched == path
        assert win._known_question_keys == {("aaaaaaa",)}
    print("ensure_questions_watcher seeds baseline: PASS")


def test_ensure_watcher_no_file():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._ensure_questions_watcher()
        assert win._known_question_keys is None
        assert win._questions_watcher.stopped is True
    print("ensure_questions_watcher handles no QUESTIONS.md: PASS")


def test_new_question_notifies():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        path = directory / "QUESTIONS.md"
        path.write_text(SAMPLE)
        win = _FakeWindow(directory)
        win._ensure_questions_watcher()

        path.write_text(
            SAMPLE + "## TODO `bbbbbbb`: second question\n\nnew body\n\n(Answer: )\n\n"
        )
        win._on_questions_file_changed()
        assert len(win.view.notify_calls) == 1
        notified_path, text, _on_clicked = win.view.notify_calls[0]
        assert notified_path == path
        assert "second question" in text
        assert win._known_question_keys == {("aaaaaaa",), ("bbbbbbb",)}
    print("new question triggers exactly one notification: PASS")


def test_answering_does_not_notify():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        path = directory / "QUESTIONS.md"
        path.write_text(SAMPLE)
        win = _FakeWindow(directory)
        win._ensure_questions_watcher()

        path.write_text(SAMPLE.replace("(Answer: )", "(Answer: now answered)"))
        win._on_questions_file_changed()
        assert win.view.notify_calls == []
    print("answering an existing entry does not spuriously notify: PASS")


def test_focus_existing_widget_centers():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        existing = _FakeFrame(QUESTIONS_WIDGET_ID)
        win = _FakeWindow(directory, frames=[existing])
        win._focus_questions_widget()
        assert win.view.center_on_calls == ["CENTER"]
        assert win.placed == []  # did not open a new one
    print("focusing an already-open Questions widget centers on it: PASS")


def test_focus_opens_new_widget_when_none_open():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory, frames=[])
        fake_widget_info = type("W", (), {"default_size": (480, 560)})()
        win._widgets[QUESTIONS_WIDGET_ID] = fake_widget_info
        win._focus_questions_widget()
        assert len(win.placed) == 1
        assert win.placed[0][0] == QUESTIONS_WIDGET_ID
        assert win.placed[0][1] is fake_widget_info
        assert win.view.center_on_calls == ["CENTER"]  # centers the newly-placed frame too
    print("focusing with no Questions widget open places and centers a new one: PASS")


test_ensure_watcher_seeds_baseline()
test_ensure_watcher_no_file()
test_new_question_notifies()
test_answering_does_not_notify()
test_focus_existing_widget_centers()
test_focus_opens_new_widget_when_none_open()
print("ALL PASS")
