import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.window import DeskWindow, CRASH_LOG_WIDGET_ID  # noqa: E402
from desk.shell.python_widget import PythonWidgetHost  # noqa: E402
from desk import crash_handler  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.temp_ui import TEMP_UI_DIRNAME  # noqa: E402

from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

app = QApplication(sys.argv)


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crash_log_mod = load_widget_module("crash_log_verify_mod", "widgets/crash_log/widget.py")


def test_log_path_under_desk_temp_creates_dir():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        with patch.object(current_context, "get_current_desk_directory", return_value=directory):
            path = crash_handler._log_path()
            assert path.parent == directory / TEMP_UI_DIRNAME
            assert path.parent.is_dir()
    print("_log_path resolves under .desk_temp, creating it: PASS")


def test_sanitize_src_and_venv():
    text = (
        'File "/Users/alice/some-project/src/desk/foo.py", line 42, in bar\n'
        "    raise ValueError()\n"
        'File "/Users/alice/some-project/.venv/lib/python3.11/site-packages/PyQt6/QtCore.py", line 7\n'
        'File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python.py", line 1\n'
    )
    result = crash_log_mod.sanitize_crash_log(text)
    assert 'File "src/desk/foo.py", line 42, in bar' in result
    assert 'File ".venv/lib/python3.11/site-packages/PyQt6/QtCore.py", line 7' in result
    # No src/.venv segment -- left unchanged.
    assert 'File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python.py", line 1' in result
    print("sanitize_crash_log strips src/.venv prefixes, leaves unmatched paths alone: PASS")


def test_sanitize_idempotent():
    text = 'File "/Users/alice/proj/src/desk/foo.py", line 1\n'
    once = crash_log_mod.sanitize_crash_log(text)
    twice = crash_log_mod.sanitize_crash_log(once)
    assert once == twice
    print("sanitize_crash_log is idempotent: PASS")


def test_widget_set_file_and_sanitize():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "DESK-CRASH-2026-01-01T00-00-00.log"
        path.write_text('File "/Users/alice/proj/src/desk/foo.py", line 1\n')
        widget = crash_log_mod.CrashLogWidget()
        widget.set_file(path)
        assert "/Users/alice/proj/src/desk/foo.py" in widget._body.toPlainText()  # not sanitized yet
        widget._sanitize()
        assert "src/desk/foo.py" in widget._body.toPlainText()
        # File on disk is untouched.
        assert "/Users/alice/proj/src/desk/foo.py" in path.read_text()
    print("widget set_file loads raw text; sanitize only changes the displayed text: PASS")


def test_widget_delete_log_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "DESK-CRASH-2026-01-01T00-00-00.log"
        path.write_text("boom")
        widget = crash_log_mod.CrashLogWidget()
        widget.set_file(path)
        dismissed = []
        widget.dismissed.connect(lambda: dismissed.append(True))
        with patch.object(widget, "_confirm_delete", return_value=True):
            widget._delete_log_file()
        assert not path.exists()
        assert dismissed == [True]
    print("Delete Log File (confirmed) deletes the file and emits dismissed: PASS")


def test_widget_delete_log_file_cancelled():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "DESK-CRASH-2026-01-01T00-00-00.log"
        path.write_text("boom")
        widget = crash_log_mod.CrashLogWidget()
        widget.set_file(path)
        dismissed = []
        widget.dismissed.connect(lambda: dismissed.append(True))
        with patch.object(widget, "_confirm_delete", return_value=False):
            widget._delete_log_file()
        assert path.exists()
        assert dismissed == []
    print("Delete Log File cancelled: file kept, no dismiss: PASS")


class _FakeHost(PythonWidgetHost):
    def __init__(self, current):
        QWidget.__init__(self)
        self._current = current
        self.widget_id = CRASH_LOG_WIDGET_ID


class _FakeFrame:
    def __init__(self, content, instance_id):
        self.content = content
        self.instance_id = instance_id


class _FakeWidgetInfo:
    def __init__(self, default_size=(100, 100)):
        self.default_size = default_size


class _FakeWindow:
    def __init__(self, directory, existing_frames=None):
        self.current_desk = type("D", (), {"directory": directory})()
        self._widgets = {CRASH_LOG_WIDGET_ID: _FakeWidgetInfo()}
        self._frames_by_id = {f.instance_id: f for f in (existing_frames or [])}
        self.placed = []
        self.closed = []

    def find_frame_by_instance_id(self, instance_id):
        return self._frames_by_id.get(instance_id)

    def _place_widget(self, widget_id, widget, pos, size, instance_id=None, restore=False):
        content = crash_log_mod.CrashLogWidget()
        frame = _FakeFrame(_FakeHost(content), instance_id)
        self.placed.append((widget_id, pos, size, instance_id))
        self._frames_by_id[instance_id] = frame
        return frame

    def close_widget_by_instance_id(self, instance_id):
        self.closed.append(instance_id)


_FakeWindow._open_crash_log_widgets = DeskWindow._open_crash_log_widgets
_FakeWindow._bind_crash_log_widget = DeskWindow._bind_crash_log_widget


def test_open_crash_log_widgets_places_new_ones():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / TEMP_UI_DIRNAME
        temp_dir.mkdir()
        log1 = temp_dir / "DESK-CRASH-2026-01-01T00-00-00.log"
        log1.write_text("boom 1")
        log2 = temp_dir / "DESK-CRASH-2026-01-02T00-00-00.log"
        log2.write_text("boom 2")

        win = _FakeWindow(directory)
        win._open_crash_log_widgets()

        assert len(win.placed) == 2
        placed_instance_ids = {p[3] for p in win.placed}
        assert placed_instance_ids == {log1.name, log2.name}
        for frame in win._frames_by_id.values():
            content = frame.content.current
            assert content._path is not None
    print("_open_crash_log_widgets places a widget per crash log, bound to its file: PASS")


def test_open_crash_log_widgets_skips_already_restored():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / TEMP_UI_DIRNAME
        temp_dir.mkdir()
        log1 = temp_dir / "DESK-CRASH-2026-01-01T00-00-00.log"
        log1.write_text("boom 1")

        existing_content = crash_log_mod.CrashLogWidget()
        existing_frame = _FakeFrame(_FakeHost(existing_content), log1.name)

        win = _FakeWindow(directory, existing_frames=[existing_frame])
        win._open_crash_log_widgets()

        assert win.placed == []  # already covered by a restored frame
    print("_open_crash_log_widgets does not duplicate an already-restored crash log widget: PASS")


def test_bind_crash_log_widget_wires_dismiss():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / TEMP_UI_DIRNAME
        temp_dir.mkdir()
        log1 = temp_dir / "DESK-CRASH-2026-01-01T00-00-00.log"
        log1.write_text("boom")

        content = crash_log_mod.CrashLogWidget()
        frame = _FakeFrame(_FakeHost(content), log1.name)
        win = _FakeWindow(directory)
        win._bind_crash_log_widget(frame, directory, log1.name)
        assert content._path == log1

        with patch.object(content, "_confirm_delete", return_value=True):
            content._delete_log_file()
        assert win.closed == [log1.name]
    print("_bind_crash_log_widget binds the file and wires dismiss -> close_widget_by_instance_id: PASS")


test_log_path_under_desk_temp_creates_dir()
test_sanitize_src_and_venv()
test_sanitize_idempotent()
test_widget_set_file_and_sanitize()
test_widget_delete_log_file()
test_widget_delete_log_file_cancelled()
test_open_crash_log_widgets_places_new_ones()
test_open_crash_log_widgets_skips_already_restored()
test_bind_crash_log_widget_wires_dismiss()
print("ALL PASS")
