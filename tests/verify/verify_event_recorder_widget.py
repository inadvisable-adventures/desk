import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

REPO_ROOT = "/Users/mphair/inadvisable-adventures/desk"

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


spec = importlib.util.spec_from_file_location("event_recorder_check", REPO_ROOT + "/widgets/event_recorder/widget.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def make_mouse_move(pos=QPointF(0, 0)):
    return QMouseEvent(
        QEvent.Type.MouseMove, pos, pos, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier
    )


def make_wheel(pos=QPointF(0, 0)):
    return QWheelEvent(
        pos,
        pos,
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


# ---------- _describe_event: a duck-typed fake is fine here (a plain
# function call, no QWidget.event() dispatch involved -- constructing
# and *dispatching* a real QNativeGestureEvent segfaulted in this
# offscreen environment during TODO 3846190's own verification,
# unrelated to the correctness of the logic under test here). ----------


class _FakeNativeGestureEvent:
    def __init__(self, gesture_type, value):
        self._gesture_type = gesture_type
        self._value = value

    def type(self):
        return QEvent.Type.NativeGesture

    def gestureType(self):
        return self._gesture_type

    def value(self):
        return self._value


def test_describe_event_native_gesture():
    fake = _FakeNativeGestureEvent(Qt.NativeGestureType.ZoomNativeGesture, 0.125)
    detail = mod._describe_event(fake)
    check("native gesture detail mentions gesture type", "ZoomNativeGesture" in detail)
    check("native gesture detail mentions value", "0.125" in detail)


test_describe_event_native_gesture()


# ---------- _RecordingSurface: only captures while recording ----------


def test_surface_only_captures_while_recording():
    surface = mod._RecordingSurface()
    surface.event(make_mouse_move())
    check("nothing captured before start()", surface._events == [])

    surface.start()
    surface.event(make_mouse_move())
    surface.event(make_mouse_move())
    check("2 events captured while recording", len(surface._events) == 2)

    events = surface.stop()
    check("stop() returns the captured events", len(events) == 2)
    surface.event(make_mouse_move())
    check("nothing captured after stop()", len(surface._events) == 2)


test_surface_only_captures_while_recording()


# ---------- _collapse_adjacent ----------


def test_collapse_adjacent_groups_only_true_runs():
    raw = [
        (0.0, QEvent.Type.MouseMove, "pos=(0,0)"),
        (5.0, QEvent.Type.MouseMove, "pos=(1,1)"),
        (10.0, QEvent.Type.MouseMove, "pos=(2,2)"),
        (15.0, QEvent.Type.Wheel, "delta=1"),
        (20.0, QEvent.Type.MouseMove, "pos=(3,3)"),  # same type as the first run, but NOT adjacent -- separate group
    ]
    groups = mod._collapse_adjacent(raw)
    check("3 groups produced (not 2 -- the two MouseMove runs are non-adjacent)", len(groups) == 3)
    check("group 0 is MouseMove x3", groups[0]["type_name"] == "MouseMove" and groups[0]["count"] == 3)
    check("group 0 spans 0..10ms", groups[0]["start_ms"] == 0.0 and groups[0]["end_ms"] == 10.0)
    check(
        "group 0 first/last detail correct",
        groups[0]["first_detail"] == "pos=(0,0)" and groups[0]["last_detail"] == "pos=(2,2)",
    )
    check("group 1 is Wheel x1", groups[1]["type_name"] == "Wheel" and groups[1]["count"] == 1)
    check(
        "group 2 is a separate MouseMove x1 (not merged with group 0)",
        groups[2]["type_name"] == "MouseMove" and groups[2]["count"] == 1,
    )

    displayed = [mod._group_to_display_dict(g) for g in groups]
    check("_group_to_display_dict strips the raw enum, keeps JSON-safe fields", all("_type" not in d for d in displayed))


test_collapse_adjacent_groups_only_true_runs()


# ---------- full widget flow (bypassing the real 5s timer) ----------


def test_full_widget_flow_and_table_population():
    widget = mod.EventRecorderWidget()
    check("starts on the results page", widget._stack.currentWidget() is widget._results_table)

    widget._start_recording()
    check("switches to the recording surface", widget._stack.currentWidget() is widget._surface)
    check("record button disabled while recording", not widget._record_button.isEnabled())

    widget._surface.event(make_wheel())
    widget._surface.event(make_wheel())
    widget._surface.event(make_mouse_move())

    widget._stop_recording()
    check("switches back to the results page", widget._stack.currentWidget() is widget._results_table)
    check("record button re-enabled after stopping", widget._record_button.isEnabled())
    check("2 groups shown (Wheel x2, MouseMove x1)", len(widget._groups) == 2)
    check("results table has 2 rows", widget._results_table.rowCount() == 2)
    check(
        "row 0 shows Wheel / 2",
        widget._results_table.item(0, 0).text() == "Wheel" and widget._results_table.item(0, 1).text() == "2",
    )
    check(
        "row 1 shows MouseMove / 1",
        widget._results_table.item(1, 0).text() == "MouseMove" and widget._results_table.item(1, 1).text() == "1",
    )


test_full_widget_flow_and_table_population()


# ---------- widget-local storage round-trip ----------


def test_widget_local_storage_roundtrip():
    widget = mod.EventRecorderWidget()
    widget._start_recording()
    widget._surface.event(make_mouse_move())
    widget._surface.event(make_mouse_move())
    widget._stop_recording()

    saved = widget.get_widget_local_storage()
    check("saved payload has recorded_at/groups", set(saved.keys()) == {"recorded_at", "groups"})
    check("saved groups is JSON-safe (round-trips through a plain dict copy)", saved == dict(saved))

    widget2 = mod.EventRecorderWidget()
    check("fresh instance starts with no groups", widget2._groups == [])
    widget2.set_widget_local_storage(saved)
    check("restored groups match", widget2._groups == widget._groups)
    check("restored table populated", widget2._results_table.rowCount() == 1)


def test_empty_local_storage_is_a_noop():
    widget = mod.EventRecorderWidget()
    check("no recording yet: empty local storage", widget.get_widget_local_storage() == {})
    widget.set_widget_local_storage({})
    check("set_widget_local_storage({}) is a no-op", widget._groups == [])


test_widget_local_storage_roundtrip()
test_empty_local_storage_is_a_noop()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
