import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.window import DeskWindow  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


class _FakeProxy:
    def __init__(self, x=0.0, y=0.0, w=100.0, h=100.0):
        self._x, self._y, self._w, self._h = x, y, w, h

    def pos(self):
        class P:
            def x(self_inner):
                return self._x

            def y(self_inner):
                return self._y

        p = P()
        p.x = lambda: self._x
        p.y = lambda: self._y
        return p

    def size(self):
        class S:
            pass

        s = S()
        s.width = lambda: self._w
        s.height = lambda: self._h
        return s


class _FakeContent:
    widget_id = "editor"


class _FakeFrame:
    def __init__(self, locked, instance_id="abc12345"):
        self.locked = locked
        self.instance_id = instance_id
        self.content = _FakeContent()
        self._proxy = _FakeProxy()
        self.placed_content_hash = None

    def graphicsProxyWidget(self):
        return self._proxy


class _FakeView:
    def __init__(self, frames):
        self._frames = frames

    def get_view_state(self):
        return 0.0, 0.0, 1.0


class _FakeWindow:
    def __init__(self, frames):
        self.view = _FakeView(frames)
        from pathlib import Path

        self.current_desk = type(
            "D", (), {"path": Path("/tmp/x.desk"), "custom_widgets": [], "file_type_registry": []}
        )()

    def _get_widget_local_storage(self, frame):
        return {}


_FakeWindow._capture_desk_state = DeskWindow._capture_desk_state


def test_capture_desk_state_includes_locked():
    frame_locked = _FakeFrame(locked=True, instance_id="locked01")
    frame_unlocked = _FakeFrame(locked=False, instance_id="unlocked1")
    win = _FakeWindow([frame_locked, frame_unlocked])
    desk = win._capture_desk_state()
    by_id = {w.instance_id: w for w in desk.widgets}
    assert by_id["locked01"].locked is True
    assert by_id["unlocked1"].locked is False
    print("_capture_desk_state captures each frame's locked flag: PASS")


test_capture_desk_state_includes_locked()
print("ALL PASS")
