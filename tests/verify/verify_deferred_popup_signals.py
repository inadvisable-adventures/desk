import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.qt_utils import deferred  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.desk_picker import DeskPicker, _DeskListPopup  # noqa: E402
from pathlib import Path  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


def test_deferred_does_not_call_synchronously():
    calls = []
    wrapped = deferred(lambda: calls.append(1))
    wrapped()
    assert calls == [], "deferred() must not call fn synchronously"
    app.processEvents()
    import time

    time.sleep(0.05)
    app.processEvents()
    assert calls == [1], "deferred() must call fn once the event loop processes it"
    print("deferred() defers, doesn't call synchronously: PASS")


def test_deferred_passes_args_through():
    received = []
    wrapped = deferred(lambda a, b: received.append((a, b)))
    wrapped("x", 2)
    app.processEvents()
    import time

    time.sleep(0.05)
    app.processEvents()
    assert received == [("x", 2)]
    print("deferred() forwards arguments correctly: PASS")


def test_desk_picker_signals_deferred_end_to_end():
    picker = DeskPicker()
    picker.set_current("current", Path("/tmp"))
    picker.set_mru([Path("/tmp/other.desk")], Path("/tmp/current.desk"))

    received = []
    picker.desk_chosen.connect(lambda p: received.append(("desk_chosen", p)))
    picker.new_desk_requested.connect(lambda: received.append(("new_desk_requested",)))

    picker._on_name_clicked()
    popup = picker.findChild(_DeskListPopup)
    assert popup is not None

    # First row is an MRU entry (a Path, not an action row) -- see
    # DeskPicker.set_mru/_DeskListPopup.__init__ for the ordering.
    target_item = popup._list.item(0)
    assert target_item is not None
    popup._activate_item(target_item)

    # Must not have fired synchronously.
    assert received == [], "DeskPicker.desk_chosen must not fire synchronously from the popup click"
    app.processEvents()
    import time

    time.sleep(0.05)
    app.processEvents()
    assert len(received) == 1
    assert received[0][0] == "desk_chosen"
    print("DeskPicker.desk_chosen fires deferred, end-to-end from a real popup click: PASS")


def test_widget_spawn_menu_signals_deferred_via_context_menu():
    view = WorkspaceView()
    view.resize(400, 300)
    view.show()
    app.processEvents()
    view.set_widget_catalog({})

    received = []
    view.widget_add_requested.connect(lambda wid, pos: received.append(("widget_add", wid)))

    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtCore import QPoint

    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(50, 50))
    view.contextMenuEvent(event)
    app.processEvents()

    from desk.shell.widget_spawn_menu import WidgetSpawnMenu

    spawn_menu = view.findChild(WidgetSpawnMenu)
    assert spawn_menu is not None
    # Exercises contextMenuEvent's own deferred-wrapped connection --
    # WidgetSpawnMenu's own internal item-activation logic is already
    # covered by its own verification script.
    spawn_menu.widget_chosen.emit("editor")

    assert received == [], "widget_add_requested must not fire synchronously from the menu click"
    app.processEvents()
    import time

    time.sleep(0.05)
    app.processEvents()
    assert received == [("widget_add", "editor")]
    print("WorkspaceView.widget_add_requested fires deferred, end-to-end from a real menu click: PASS")


test_deferred_does_not_call_synchronously()
test_deferred_passes_args_through()
test_desk_picker_signals_deferred_end_to_end()
test_widget_spawn_menu_signals_deferred_via_context_menu()
print("ALL PASS")
