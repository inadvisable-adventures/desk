import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.window import DeskWindow  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


class _FakeWindow:
    def __init__(self, directory):
        self.current_desk = type("D", (), {"directory": directory})()
        self.warn_calls = []
        self.switch_desk_calls = []
        self.save_calls = []
        self._path_to_create_during_switch = None

    def _warn(self, title, message):
        self.warn_calls.append((title, message))

    def switch_desk(self, path, confirm=None, provisioning=None):
        self.switch_desk_calls.append(path)
        if self._path_to_create_during_switch is not None:
            self._path_to_create_during_switch.write_text("someone else's desk")

    def save_current_desk(self):
        self.save_calls.append(True)

    def _seed_development_process(self, directory):
        pass


_FakeWindow.new_desk = DeskWindow.new_desk


def test_new_desk_aborts_if_path_appears_during_switch_desk():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        target = directory / "MyDesk.desk"
        win._path_to_create_during_switch = target  # simulates a race

        win.new_desk("MyDesk", directory)

        assert win.switch_desk_calls == [target]
        assert len(win.warn_calls) == 1
        assert "already exists" in win.warn_calls[0][1]
        assert win.save_calls == []  # never saved over the concurrently-created file
    print("new_desk aborts recoverably if the path appears during switch_desk: PASS")


def test_new_desk_normal_path_saves():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win.new_desk("MyDesk", directory)
        assert win.switch_desk_calls
        assert win.warn_calls == []
        assert win.save_calls == [True]
    print("new_desk normal path (no race) still saves: PASS")


test_new_desk_aborts_if_path_appears_during_switch_desk()
test_new_desk_normal_path_saves()
print("ALL PASS")
