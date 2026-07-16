import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.widget_frame import WidgetFrame  # noqa: E402
from desk_services.popups.service import PopupsService  # noqa: E402

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


def make_view():
    view = WorkspaceView()
    view.resize(1000, 800)
    view.show()
    return view


def make_popup_frame(view, title="Popup"):
    body = QLabel("message")
    frame = WidgetFrame(title, body, is_popup=True)
    frame.resize(300, 150)
    view.add_popup(frame)
    return frame


def test_popup_chrome_hides_lock_eye_bring_send():
    view = make_view()
    frame = make_popup_frame(view)
    titlebar = frame._titlebar
    check("popup titlebar shows the close button", titlebar.close_button.isVisible())
    check("popup titlebar hides the lock button", not titlebar.lock_button.isVisible())
    check("popup titlebar hides the unlock button", not titlebar.unlock_button.isVisible())
    check("popup titlebar hides the eye button", not titlebar.eye_button.isVisible())
    check("popup titlebar hides bring-to-front", not titlebar.bring_to_front_button.isVisible())
    check("popup titlebar hides send-to-back", not titlebar.send_to_back_button.isVisible())
    check("popup titlebar hides the tempui-promote button", not titlebar.tempui_promote_button.isVisible())
    check("popup titlebar hides the stale button", not titlebar.stale_button.isVisible())


def test_popup_is_always_frontmost():
    view = make_view()
    content = QLabel("normal widget content")
    content.resize(200, 150)
    view.add_widget(content, title="Normal", pos=(0, 0), size=(200, 150))
    normal_frame = view._frames[0]
    view.bring_to_front(normal_frame)

    popup = make_popup_frame(view)
    popup_z = popup.graphicsProxyWidget().zValue()
    normal_z = normal_frame.graphicsProxyWidget().zValue()
    check("a freshly-added popup's z-value is above the normal frame's", popup_z > normal_z)

    # Bringing the normal frame to front again must not out-rank the popup --
    # _frame_z_values() only ever iterates _frames, never _popup_frames.
    view.bring_to_front(normal_frame)
    check(
        "bring_to_front on a normal frame never out-ranks an open popup",
        popup.graphicsProxyWidget().zValue() > normal_frame.graphicsProxyWidget().zValue(),
    )


def test_popup_not_in_normal_frame_pool():
    view = make_view()
    make_popup_frame(view)
    check("a popup is tracked in _popup_frames, not _frames", len(view._frames) == 0 and len(view._popup_frames) == 1)
    check("_frame_z_values() (bring/send-to-back's pool) excludes popups", list(view._frame_z_values()) == [])


def test_popup_rescales_with_zoom():
    view = make_view()
    frame = make_popup_frame(view)
    from desk.shell.widget_frame import TITLEBAR_HEIGHT

    before_height = frame._titlebar.height()
    view._rescale(2.0)
    after_height = frame._titlebar.height()
    check(
        "a popup's titlebar counter-scales on zoom, same as a normal frame's",
        before_height == round(TITLEBAR_HEIGHT) and after_height == round(TITLEBAR_HEIGHT / 2.0),
    )


def test_show_blocking_resolves_on_button_click():
    view = make_view()
    service = PopupsService()
    service.attach_view(view)

    results = []
    service.show("Confirm", "Are you sure?", ["Yes", "No"], "No", results.append)
    check("show() places exactly one popup", len(view._popup_frames) == 1)

    frame = view._popup_frames[0]
    yes_button = None
    for button in frame.content.findChildren(QPushButton):
        if button.text() == "Yes":
            yes_button = button
    check("the popup body has a Yes button", yes_button is not None)
    yes_button.click()

    check("clicking a button resolves on_result with that button's label", results == ["Yes"])
    check("the popup is removed from the canvas after resolving", len(view._popup_frames) == 0)


def test_close_button_resolves_none_and_does_not_touch_normal_close_flow():
    view = make_view()
    service = PopupsService()
    service.attach_view(view)

    close_requested = []
    view.widget_close_requested.connect(lambda f: close_requested.append(f))

    results = []
    service.show("Info", "Something happened.", ["OK"], "OK", results.append)
    frame = view._popup_frames[0]

    # Simulate the close (X) button the same way WorkspaceView.mouseReleaseEvent
    # does for a popup frame: emit popup_closed directly.
    view.popup_closed.emit(frame)

    check("closing a popup resolves on_result with None", results == [None])
    check("the popup is removed from the canvas", len(view._popup_frames) == 0)
    check("closing a popup never emits widget_close_requested", close_requested == [])


def test_clear_widgets_resolves_any_open_popup():
    view = make_view()
    service = PopupsService()
    service.attach_view(view)

    results = []
    service.show("Confirm", "...", ["Yes", "No"], "No", results.append)
    check("a popup is open before clear_widgets", len(view._popup_frames) == 1)

    view.clear_widgets()

    check("clear_widgets resolves a still-open popup with None instead of hanging", results == [None])
    check("clear_widgets removes the popup from _popup_frames", len(view._popup_frames) == 0)


def test_popup_never_persisted_in_desk_state_frames():
    view = make_view()
    content = QLabel("normal")
    content.resize(200, 150)
    view.add_widget(content, title="Normal", pos=(0, 0), size=(200, 150))
    make_popup_frame(view)
    check(
        "DeskWindow-style iteration over view._frames (persistence) never sees a popup",
        all(not frame.is_popup for frame in view._frames),
    )


test_popup_chrome_hides_lock_eye_bring_send()
test_popup_is_always_frontmost()
test_popup_not_in_normal_frame_pool()
test_popup_rescales_with_zoom()
test_show_blocking_resolves_on_button_click()
test_close_button_resolves_none_and_does_not_touch_normal_close_flow()
test_clear_widgets_resolves_any_open_popup()
test_popup_never_persisted_in_desk_state_frames()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
