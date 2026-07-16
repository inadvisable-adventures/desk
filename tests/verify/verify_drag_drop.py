import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import (  # noqa: E402
    DeskWindow,
    EDITOR_WIDGET_ID,
    MARKDOWN_WIDGET_ID,
    IMAGE_VIEWER_WIDGET_ID,
    WIDGET_SPACING,
)

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


# A real QDropEvent constructed and dispatched purely from Python (rather
# than delivered by Qt's own event loop) is fragile/flaky in PyQt6 --
# confirmed directly: an identical construct-then-call sequence segfaulted
# on one run and succeeded on another (a dangling-pointer-style crash, not
# a deterministic logic bug -- see LEARNINGS.md-style "avoid manually
# constructing this Qt type" gotchas elsewhere in this codebase). dropEvent
# only ever calls .mimeData()/.position()/.acceptProposedAction() on
# whatever object it's given, so a plain duck-typed fake exercises the
# exact same code path without that risk.
class _FakeUrl:
    def __init__(self, path, is_local=True):
        self._path = path
        self._is_local = is_local

    def isLocalFile(self):
        return self._is_local

    def toLocalFile(self):
        return self._path


class _FakeMimeData:
    def __init__(self, urls):
        self._urls = urls

    def urls(self):
        return self._urls


class _FakeDropEvent:
    def __init__(self, mime_data, pos=QPointF(50.0, 60.0)):
        self._mime = mime_data
        self._pos = pos
        self._accepted = False

    def mimeData(self):
        return self._mime

    def position(self):
        return self._pos

    def acceptProposedAction(self):
        self._accepted = True

    def isAccepted(self):
        return self._accepted


def test_drop_with_local_files_emits_signal():
    view = WorkspaceView()
    with tempfile.TemporaryDirectory() as d:
        p1 = Path(d) / "notes.md"
        p1.write_text("# hi")
        received = []
        view.files_dropped.connect(lambda paths, pos: received.append((paths, pos)))
        event = _FakeDropEvent(_FakeMimeData([_FakeUrl(str(p1))]))
        view.dropEvent(event)
        assert event.isAccepted()
        assert len(received) == 1
        paths, scene_pos = received[0]
        assert paths == [p1]
    print("dropEvent with local file URL emits files_dropped: PASS")


def test_local_file_urls_filters_correctly():
    # Not exercised via the full dropEvent/super() chain here: the "no
    # local urls" branch falls through to the real QGraphicsView.dropEvent,
    # which (correctly) rejects a duck-typed fake event object -- so the
    # filtering helper itself is tested directly instead, which is the
    # only new logic in that branch anyway.
    view = WorkspaceView()
    assert view._local_file_urls(_FakeMimeData([])) == []
    assert view._local_file_urls(_FakeMimeData([_FakeUrl("https://example.com/x", is_local=False)])) == []
    local = _FakeUrl("/tmp/x.md")
    assert view._local_file_urls(_FakeMimeData([local])) == [local]
    print("_local_file_urls filters out empty/non-local URLs: PASS")


class _FakeWidgetInfo:
    def __init__(self, default_size=(100, 100)):
        self.default_size = default_size


class _FakeWindow:
    def __init__(self):
        self._widgets = {
            MARKDOWN_WIDGET_ID: _FakeWidgetInfo(),
            IMAGE_VIEWER_WIDGET_ID: _FakeWidgetInfo(),
            EDITOR_WIDGET_ID: _FakeWidgetInfo(),
        }
        self.opened = []

    def open_widget_content(self, widget_id, pos=None, size=None, instance_id=None):
        self.opened.append((widget_id, pos, size))
        return _FakeContent()


class _FakeContent:
    def __init__(self):
        self.set_file_calls = []

    def set_file(self, path):
        self.set_file_calls.append(path)


_FakeWindow._on_files_dropped = DeskWindow._on_files_dropped


def test_dispatch_by_extension():
    win = _FakeWindow()
    paths = [Path("/tmp/a.md"), Path("/tmp/b.svg"), Path("/tmp/c.txt")]
    win._on_files_dropped(paths, QPointF(100.0, 200.0))
    assert [op[0] for op in win.opened] == [MARKDOWN_WIDGET_ID, IMAGE_VIEWER_WIDGET_ID, EDITOR_WIDGET_ID]
    # positions fan out by WIDGET_SPACING starting at the drop point
    assert win.opened[0][1] == (100.0, 200.0)
    assert win.opened[1][1] == (100.0 + WIDGET_SPACING, 200.0)
    assert win.opened[2][1] == (100.0 + 2 * WIDGET_SPACING, 200.0)
    print("extension dispatch + fan-out positions: PASS")


def test_case_insensitive_suffix():
    win = _FakeWindow()
    win._on_files_dropped([Path("/tmp/A.MD")], QPointF(0.0, 0.0))
    assert win.opened[0][0] == MARKDOWN_WIDGET_ID
    print("suffix matching is case-insensitive: PASS")


test_drop_with_local_files_emits_signal()
test_local_file_urls_filters_correctly()
test_dispatch_by_extension()
test_case_insensitive_suffix()
print("ALL PASS")
