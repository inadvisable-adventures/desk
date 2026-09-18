import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.desks import Desk  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import DeskWindow, SCRATCH_WIDGET_ID  # noqa: E402
from desk.shell.promoted_widget_source_watcher import PromotedWidgetSourceWatcher  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402
from PyQt6.QtWidgets import QApplication, QGraphicsProxyWidget  # noqa: E402

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


class _FakeHandle:
    def widget_url(self, widget_id):
        return f"http://fake/{widget_id}"

    token = "tok"


class _FakeWindow:
    def __init__(self, directory, widgets):
        self.current_desk = Desk(path=directory / "test.desk")
        self._widgets = widgets
        self._handle = _FakeHandle()
        self._custom_widget_definitions = {}
        self._custom_widget_sources = {}
        self._custom_widget_content_hash = {}
        # TODO 4eb3d9e: _register_custom_widget/_place_widget/
        # _on_widget_stale_clicked now also touch these.
        self._promoted_widget_source_watcher = PromotedWidgetSourceWatcher()
        self._promoted_widget_source_dirty = set()
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self._broker = HotReloadBroker()
        self._event_mediator = EventMediator()


_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_error_indicator = DeskWindow._bind_error_indicator
_FakeWindow.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id
_FakeWindow.open_widget = DeskWindow.open_widget
_FakeWindow.open_widget_content = DeskWindow.open_widget_content
_FakeWindow.open_widget_content_centered = DeskWindow.open_widget_content_centered
_FakeWindow._open_focused_scratch = DeskWindow._open_focused_scratch
_FakeWindow._on_new_scratch_requested = DeskWindow._on_new_scratch_requested


def _scratch_widget_info():
    return WidgetInfo(
        id=SCRATCH_WIDGET_ID,
        path=Path("widgets") / SCRATCH_WIDGET_ID,
        kind="python",
        name="Scratch",
        entry="widget.py",
        capabilities=[],
        default_size=(400, 300),
    )


def test_button_is_visible_immediately():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        win = _FakeWindow(directory, widgets={SCRATCH_WIDGET_ID: _scratch_widget_info()})
        app.processEvents()
        check("the new-Scratch button is visible right after construction", win.view.new_scratch_button.isVisible())


def test_clicking_places_a_centered_focused_scratch():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        win = _FakeWindow(directory, widgets={SCRATCH_WIDGET_ID: _scratch_widget_info()})
        app.processEvents()

        check("no widgets on the canvas yet", len(win.view._frames) == 0)

        win.view.new_scratch_requested.connect(win._on_new_scratch_requested)
        win.view.new_scratch_button.clicked.emit()
        app.processEvents()

        check("clicking the button placed exactly one widget", len(win.view._frames) == 1)
        frame = win.view._frames[0]

        # open_widget_content_centered's own convention (matched here,
        # not redefined): pos is the viewport's center point used
        # directly as the placed widget's top-left corner -- the same
        # math _place_discuss_claude_widget/open_editor_or_scrap already
        # rely on elsewhere in this codebase.
        center = win.view.mapToScene(win.view.viewport().rect().center())
        proxy = frame.graphicsProxyWidget()
        check(
            "the new Scratch is placed at the current viewport's center point",
            abs(proxy.pos().x() - center.x()) < 5 and abs(proxy.pos().y() - center.y()) < 5,
        )

        focus_item = win.view.scene().focusItem()
        check(
            "the new Scratch's proxy is the scene's focused item right after creation",
            isinstance(focus_item, QGraphicsProxyWidget) and focus_item is proxy,
        )
        content = frame.content.current
        check("the new Scratch's body widget has real Qt focus", content.body.hasFocus())


test_button_is_visible_immediately()
test_clicking_places_a_centered_focused_scratch()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
