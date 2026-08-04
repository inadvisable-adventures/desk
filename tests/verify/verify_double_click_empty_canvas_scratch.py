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
from desk.widgets import WidgetInfo  # noqa: E402
from PyQt6.QtCore import QPointF, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLineEdit  # noqa: E402

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


def double_click(view, pos):
    # Real Qt event delivery (via the viewport's actual event pipeline),
    # not a hand-built QMouseEvent handed straight to
    # view.mouseDoubleClickEvent -- confirmed directly that the latter
    # never reaches a QGraphicsProxyWidget-embedded widget's own
    # mouseDoubleClickEvent (e.g. the Scratch title label's inline-edit
    # trigger), while this does.
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos.toPoint())


def screen_pos_of(view, frame, widget):
    """Same recipe as verify_lock_widgets.py's own screen_pos_of."""
    proxy = frame.graphicsProxyWidget()
    local_point = widget.mapTo(frame, widget.rect().center())
    scene_point = proxy.mapToScene(QPointF(local_point))
    return view.mapFromScene(scene_point)


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
_FakeWindow._on_empty_canvas_double_clicked = DeskWindow._on_empty_canvas_double_clicked


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


def test_double_click_empty_canvas_places_a_focused_scratch():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        win = _FakeWindow(directory, widgets={SCRATCH_WIDGET_ID: _scratch_widget_info()})
        win.view.empty_canvas_double_clicked.connect(win._on_empty_canvas_double_clicked)
        app.processEvents()

        check("no widgets on the canvas yet", len(win.view._frames) == 0)

        click_pos = QPointF(120, 90)
        double_click(win.view, click_pos)
        app.processEvents()

        check("double-clicking empty canvas placed exactly one widget", len(win.view._frames) == 1)
        frame = win.view._frames[0]
        proxy = frame.graphicsProxyWidget()
        click_scene_pos = win.view.mapToScene(click_pos.toPoint())
        check(
            "the new Scratch's top-left corner is at the double-click's scene position",
            abs(proxy.pos().x() - click_scene_pos.x()) < 1 and abs(proxy.pos().y() - click_scene_pos.y()) < 1,
        )
        content = frame.content.current
        check("the new Scratch's body has real Qt focus", content.body.hasFocus())


def test_double_click_on_a_placed_widget_does_not_create_a_scratch():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        win = _FakeWindow(directory, widgets={SCRATCH_WIDGET_ID: _scratch_widget_info()})
        win.view.empty_canvas_double_clicked.connect(win._on_empty_canvas_double_clicked)
        app.processEvents()

        content = QLineEdit()
        proxy = win.view.add_widget(content, title="Other", pos=(0, 0), size=(300, 200))
        frame = proxy.widget()
        app.processEvents()
        check("exactly one widget placed directly (not via double-click)", len(win.view._frames) == 1)

        inner_pos = QPointF(screen_pos_of(win.view, frame, content))
        double_click(win.view, inner_pos)
        app.processEvents()

        check(
            "double-clicking an existing widget's content did not create a second (Scratch) widget",
            len(win.view._frames) == 1,
        )


def test_double_click_on_scratch_title_label_still_enters_edit_mode():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        win = _FakeWindow(directory, widgets={SCRATCH_WIDGET_ID: _scratch_widget_info()})
        win.view.empty_canvas_double_clicked.connect(win._on_empty_canvas_double_clicked)
        app.processEvents()

        content = win.open_widget_content(SCRATCH_WIDGET_ID, pos=(0, 0))
        frame = win.find_frame_by_instance_id(win.view._frames[0].instance_id)
        app.processEvents()
        check("exactly one Scratch placed directly (not via double-click)", len(win.view._frames) == 1)

        label = content._title_row._display
        label_pos = QPointF(screen_pos_of(win.view, frame, label))
        double_click(win.view, label_pos)
        app.processEvents()

        check(
            "double-clicking the Scratch title label still entered its own inline-edit mode",
            content._title_row._stack.currentWidget() is content._title_row._edit,
        )
        check(
            "double-clicking the title label did not create a second Scratch",
            len(win.view._frames) == 1,
        )


def test_hover_button_shadows_the_canvas_for_real_clicks_at_its_position():
    """Directly dispatching a QMouseEvent to view.mouseDoubleClickEvent
    (as the other tests here do) always lands on the view regardless of
    position -- that would make a "double-click on the button" variant
    of that approach meaningless (it'd just prove the view's own gate
    logic, not real Qt event routing). Instead this confirms the actual
    mechanism the plan relies on: Qt delivers a real click at this
    pixel to the topmost viewport-child widget there via
    QWidget.childAt, the exact same routing WorkspaceView.
    describe_widget_at_global_pos already depends on elsewhere for this
    same trio of pinned HUD widgets -- so a real double-click physically
    over the button is delivered to the button itself, never reaching
    WorkspaceView.mouseDoubleClickEvent at all."""
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        win = _FakeWindow(directory, widgets={SCRATCH_WIDGET_ID: _scratch_widget_info()})
        app.processEvents()

        button = win.view.new_scratch_button
        button_center = button.geometry().center()
        check(
            "the viewport's real child-widget hit-test resolves the button's own position to the button itself",
            win.view.viewport().childAt(button_center) is button,
        )

        clicked_count = 0

        def _on_clicked():
            nonlocal clicked_count
            clicked_count += 1

        button.clicked.connect(_on_clicked)
        QTest.mouseDClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check("a real double-click delivered to the button still triggers its own click behavior", clicked_count >= 1)
        check("no Scratch was created by a double-click that never reached the canvas handler", len(win.view._frames) == 0)


test_double_click_empty_canvas_places_a_focused_scratch()
test_double_click_on_a_placed_widget_does_not_create_a_scratch()
test_double_click_on_scratch_title_label_still_enters_edit_mode()
test_hover_button_shadows_the_canvas_for_real_clicks_at_its_position()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
