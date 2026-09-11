import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.shell.temp_ui_notifications import (  # noqa: E402
    BANNER_STYLE,
    DESK_PROC_BANNER_STYLE,
    DESK_PROC_CAPTION_TEXT,
    TempUiNotificationStack,
    _NotificationBanner,
)

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


def _labels_of(widget):
    from PyQt6.QtWidgets import QLabel

    return widget.findChildren(QLabel)


def test_default_banner_has_no_desk_proc_caption():
    banner = _NotificationBanner("Some ordinary notification")
    labels = _labels_of(banner)
    texts = [label.text() for label in labels]
    check("default banner shows only the given text, no DESK PROC caption", DESK_PROC_CAPTION_TEXT not in texts)
    check("default banner uses the default stylesheet", banner.styleSheet() == BANNER_STYLE)


def test_desk_proc_banner_shows_a_bold_non_selectable_caption():
    from PyQt6.QtCore import Qt

    banner = _NotificationBanner("Reveal and screenshot the Editor widget", banner_style="desk_proc")
    labels = _labels_of(banner)
    texts = [label.text() for label in labels]
    check("desk_proc banner shows the DESK PROC caption", DESK_PROC_CAPTION_TEXT in texts)
    check("desk_proc banner still shows the given summary text", "Reveal and screenshot the Editor widget" in texts)
    check("desk_proc banner uses the distinct desk_proc stylesheet", banner.styleSheet() == DESK_PROC_BANNER_STYLE)
    check("the distinct stylesheet really is different from the default one", DESK_PROC_BANNER_STYLE != BANNER_STYLE)

    caption_label = next(label for label in labels if label.text() == DESK_PROC_CAPTION_TEXT)
    check("the DESK PROC caption is bold", caption_label.font().bold())
    check(
        "the DESK PROC caption is not user-selectable (this project's labels-aren't-selectable convention)",
        caption_label.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction,
    )


def test_notification_stack_threads_banner_style_through_to_the_banner():
    stack = TempUiNotificationStack()
    stack.notify(Path("/tmp/some-uuid"), "A Desk Proc summary", lambda: None, banner_style="desk_proc")
    banner = stack._banners[Path("/tmp/some-uuid")]
    check("TempUiNotificationStack.notify passes banner_style through to the real banner", banner.styleSheet() == DESK_PROC_BANNER_STYLE)

    stack.notify(Path("/tmp/other-uuid"), "An ordinary summary", lambda: None)
    other_banner = stack._banners[Path("/tmp/other-uuid")]
    check("omitting banner_style defaults to the ordinary stylesheet", other_banner.styleSheet() == BANNER_STYLE)


test_default_banner_has_no_desk_proc_caption()
test_desk_proc_banner_shows_a_bold_non_selectable_caption()
test_notification_stack_threads_banner_style_through_to_the_banner()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
