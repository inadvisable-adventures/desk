import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.window import DeskWindow  # noqa: E402 -- before QApplication
from desk.shell.python_widget import PythonWidgetHost  # noqa: E402
from desk.desks import Desk, WidgetState, desk_state_dict, load_desk, save_desk  # noqa: E402

from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

app = QApplication(sys.argv)


def test_state_round_trips_through_save_load():
    with tempfile.TemporaryDirectory() as d:
        desk_path = Path(d) / "test.desk"
        ws = WidgetState("todo", 10.0, 20.0, 300.0, 200.0, instance_id="abc123", state={"foo": "bar", "n": 3})
        desk = Desk(path=desk_path, widgets=[ws])
        save_desk(desk)

        loaded = load_desk(desk_path)
        assert len(loaded.widgets) == 1
        assert loaded.widgets[0].state == {"foo": "bar", "n": 3}, loaded.widgets[0].state
    print("state round-trips through save_desk/load_desk: PASS")


def test_old_desk_file_without_state_key():
    with tempfile.TemporaryDirectory() as d:
        desk_path = Path(d) / "old.desk"
        old_shape = {
            "widgets": [
                {"widget_id": "todo", "instance_id": "abc123", "x": 0, "y": 0, "width": 300, "height": 200}
            ],
            "pan_x": 0.0,
            "pan_y": 0.0,
            "scale": 1.0,
        }
        desk_path.write_text(json.dumps(old_shape))
        loaded = load_desk(desk_path)
        assert loaded.widgets[0].state == {}
    print("old-shaped .desk file (no state key) loads with default {}: PASS")


def test_desk_state_dict_includes_state():
    ws = WidgetState("todo", 0.0, 0.0, 100.0, 100.0, instance_id="x", state={"a": 1})
    desk = Desk(path=Path("/tmp/x.desk"), widgets=[ws])
    d = desk_state_dict(desk)
    assert d["widgets"][0]["state"] == {"a": 1}
    print("desk_state_dict includes state: PASS")


class _FakeHost(PythonWidgetHost):
    """Registers as a real PythonWidgetHost (isinstance check) without
    running its real, heavier construction (widget module loading)."""

    def __init__(self, current):
        QWidget.__init__(self)
        self._current = current
        self.widget_id = "fake"


class _FakeFrame:
    def __init__(self, content):
        self.content = content
        self.instance_id = "fake-instance"


class _WithStorage(QWidget):
    def __init__(self):
        super().__init__()
        self._data = {"count": 0}

    def get_widget_local_storage(self):
        return dict(self._data)

    def set_widget_local_storage(self, data):
        self._data = dict(data)


class _WithoutStorage(QWidget):
    pass


def test_bind_and_get_real_methods():
    content = _WithStorage()
    frame = _FakeFrame(_FakeHost(content))

    # Restore path.
    DeskWindow._bind_widget_local_storage(None, frame, {"count": 42})
    assert content._data == {"count": 42}

    # Save path. _get_widget_local_storage is no longer a staticmethod
    # (TODO 5734529 -- it now also needs self._html_widget_local_storage
    # for a ChromiumWidget-backed frame), so this unbound call needs a
    # fake self too, same as _bind_widget_local_storage above.
    got = DeskWindow._get_widget_local_storage(None, frame)
    assert got == {"count": 42}
    print("_bind_widget_local_storage/_get_widget_local_storage real methods work: PASS")


def test_no_storage_methods_is_safe_no_op():
    content = _WithoutStorage()
    frame = _FakeFrame(_FakeHost(content))

    DeskWindow._bind_widget_local_storage(None, frame, {"x": 1})  # must not raise
    got = DeskWindow._get_widget_local_storage(None, frame)
    assert got == {}
    print("widget without storage methods is a safe no-op: PASS")


test_state_round_trips_through_save_load()
test_old_desk_file_without_state_key()
test_desk_state_dict_includes_state()
test_bind_and_get_real_methods()
test_no_storage_methods_is_safe_no_op()
print("ALL PASS")
