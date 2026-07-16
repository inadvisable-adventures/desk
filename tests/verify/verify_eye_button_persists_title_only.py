import os
import sys
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402

from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.widget_frame import WidgetFrame, _TitleBar  # noqa: E402

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


# ---------- _refresh_button_visibility ----------


def test_eye_button_persists_through_title_only_when_unlocked():
    bar = _TitleBar("My Widget")
    bar.show()
    check("eye visible in full state", bar.eye_button.isVisible())
    bar.set_buttons_hidden(True)
    check("eye still visible in title_only state", bar.eye_button.isVisible())
    check("close button hidden in title_only state", not bar.close_button.isVisible())
    check("lock button hidden in title_only state", not bar.lock_button.isVisible())


def test_eye_button_still_hidden_while_locked():
    bar = _TitleBar("My Widget")
    bar.show()
    bar.set_locked(True)
    check("eye hidden while locked (full state)", not bar.eye_button.isVisible())
    bar.set_buttons_hidden(True)
    check("eye still hidden while locked + title_only", not bar.eye_button.isVisible())
    bar.set_locked(False)
    bar.set_buttons_hidden(False)
    check("eye visible again once unlocked and buttons shown", bar.eye_button.isVisible())


# ---------- min_title_only_width_px / min_full_width_px ----------


def test_min_title_only_width_includes_eye_button_when_unlocked():
    bar = _TitleBar("My Widget")
    from desk.shell.widget_frame import TITLEBAR_BUTTON_SPACING, TITLEBAR_CONTENT_MARGIN, MIN_TITLE_WIDTH, _button_target_width

    title_only_baseline = TITLEBAR_CONTENT_MARGIN * 2 + MIN_TITLE_WIDTH
    expected = title_only_baseline + TITLEBAR_BUTTON_SPACING + _button_target_width(bar.eye_button)
    check("min_title_only_width_px includes the eye button's width", bar.min_title_only_width_px() == expected)


def test_min_title_only_width_excludes_eye_button_when_locked():
    bar = _TitleBar("My Widget")
    from desk.shell.widget_frame import TITLEBAR_CONTENT_MARGIN, MIN_TITLE_WIDTH

    bar.set_locked(True)
    check("min_title_only_width_px excludes the eye button while locked", bar.min_title_only_width_px() == TITLEBAR_CONTENT_MARGIN * 2 + MIN_TITLE_WIDTH)


def test_min_full_width_does_not_double_count_eye_button():
    bar = _TitleBar("My Widget")
    from desk.shell.widget_frame import TITLEBAR_BUTTON_SPACING, _button_target_width

    # Every OTHER currently-relevant button (unlocked, not
    # tempui-promotable, not stale): lock/bring_to_front/send_to_back/close.
    other_buttons = [bar.lock_button, bar.bring_to_front_button, bar.send_to_back_button, bar.close_button]
    expected_extra = sum(_button_target_width(b) for b in other_buttons) + len(other_buttons) * TITLEBAR_BUTTON_SPACING
    actual_extra = bar.min_full_width_px() - bar.min_title_only_width_px()
    check("min_full_width_px adds exactly the other buttons' width, not the eye button again", actual_extra == expected_extra)


# ---------- end-to-end chrome-state degrade on a real WidgetFrame ----------


def test_chrome_degrades_correctly_with_widened_title_only_threshold():
    view = WorkspaceView()
    view.resize(800, 600)
    view.show()
    content = QLabel("content")
    frame = WidgetFrame("My Widget", content, instance_id=uuid.uuid4().hex[:8])
    frame.show()
    frame.set_view_scale(1.0)

    min_title_only = frame._titlebar.min_title_only_width_px()
    min_full = frame._titlebar.min_full_width_px()
    check("full requires strictly more width than title_only (eye button adds real width)", min_full > min_title_only)

    # Between the two thresholds: title_only state, eye button visible.
    between_width = (min_title_only + min_full) // 2
    frame.resize(between_width, 200)
    frame._update_chrome_state()
    check("mid-range width: chrome_state is title_only", frame.chrome_state == "title_only")
    check("mid-range width: eye button still visible", frame._titlebar.eye_button.isVisible())
    check("mid-range width: close button hidden", not frame._titlebar.close_button.isVisible())

    # Below min_title_only (which now also accounts for the eye
    # button): greeked.
    frame.resize(max(1, min_title_only - 5), 200)
    frame._update_chrome_state()
    check("below the widened title_only threshold: chrome_state is greeked", frame.chrome_state == "greeked")


test_eye_button_persists_through_title_only_when_unlocked()
test_eye_button_still_hidden_while_locked()
test_min_title_only_width_includes_eye_button_when_unlocked()
test_min_title_only_width_excludes_eye_button_when_locked()
test_min_full_width_does_not_double_count_eye_button()
test_chrome_degrades_correctly_with_widened_title_only_threshold()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
