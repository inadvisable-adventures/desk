import base64
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# desk.shell.window must be importable before QApplication -- see other
# verify scripts' identical comment on this same gotcha.
import desk.shell.window  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.shell.window import DeskWindow, DESK_PROC_RUNNER_WIDGET_ID, TEMP_UI_WIDGET_IDS  # noqa: E402

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


class _FakeView:
    def __init__(self):
        self.notifications = []

    def notify_temp_ui(self, path, text, on_click, banner_style="default"):
        self.notifications.append((path, text, banner_style))


class _FakeWindow:
    def __init__(self):
        self._custom_widget_definitions = {}
        self.view = _FakeView()


_FakeWindow._temp_ui_widget_id_for = DeskWindow._temp_ui_widget_id_for
_FakeWindow._notify_temp_ui = DeskWindow._notify_temp_ui


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_desk_proc_runner_id_is_in_temp_ui_widget_ids():
    check(
        "DESK_PROC_RUNNER_WIDGET_ID is in TEMP_UI_WIDGET_IDS (needed for restore reconnection)",
        DESK_PROC_RUNNER_WIDGET_ID in TEMP_UI_WIDGET_IDS,
    )


def test_temp_ui_widget_id_for_resolves_desk_proc_files_to_the_desk_proc_runner():
    with tempfile.TemporaryDirectory() as d:
        proc_path = Path(d) / "some-uuid"
        proc_path.write_text(f"DeskProc\tFetch things\nScript\t{_b64('pass')}\n")
        win = _FakeWindow()
        check(
            "_temp_ui_widget_id_for resolves a real DeskProc file to DESK_PROC_RUNNER_WIDGET_ID",
            win._temp_ui_widget_id_for(proc_path) == DESK_PROC_RUNNER_WIDGET_ID,
        )


def test_notify_temp_ui_composes_desk_proc_summary_text_with_the_desk_proc_banner_style():
    with tempfile.TemporaryDirectory() as d:
        proc_path = Path(d) / "some-uuid"
        proc_path.write_text(f"DeskProc\tClean up old scratch files\nScript\t{_b64('pass')}\n")
        win = _FakeWindow()
        win._notify_temp_ui(proc_path)
        check("notify_temp_ui was called exactly once", len(win.view.notifications) == 1)
        _, text, banner_style = win.view.notifications[0]
        check("the notification text names the Desk Proc's declared summary", text == "Desk Proc: Clean up old scratch files")
        check("the notification uses the distinct desk_proc banner style", banner_style == "desk_proc")


def test_notify_temp_ui_falls_back_gracefully_for_a_malformed_desk_proc_file():
    with tempfile.TemporaryDirectory() as d:
        proc_path = Path(d) / "some-uuid"
        proc_path.write_text("DeskProc\n")  # no Script line -- parse_desk_proc returns None
        win = _FakeWindow()
        win._notify_temp_ui(proc_path)
        _, text, banner_style = win.view.notifications[0]
        check("a malformed DeskProc file still gets a real (fallback) notification, not a crash", text != "")
        # kind is still "desk_proc" (detect_temp_ui_kind only looks at
        # the keyword, not whether parse_desk_proc actually succeeds) --
        # the banner style should reflect that regardless.
        check("still gets the desk_proc banner style even when parsing the summary failed", banner_style == "desk_proc")


def test_an_ordinary_question_file_uses_the_default_banner_style():
    with tempfile.TemporaryDirectory() as d:
        question_path = Path(d) / "some-uuid"
        question_path.write_text("What color?\nOption Red\nOption Blue\n")
        win = _FakeWindow()
        win._notify_temp_ui(question_path)
        _, _text, banner_style = win.view.notifications[0]
        check("an ordinary Question file uses the default banner style, not desk_proc", banner_style == "default")


test_desk_proc_runner_id_is_in_temp_ui_widget_ids()
test_temp_ui_widget_id_for_resolves_desk_proc_files_to_the_desk_proc_runner()
test_notify_temp_ui_composes_desk_proc_summary_text_with_the_desk_proc_banner_style()
test_notify_temp_ui_falls_back_gracefully_for_a_malformed_desk_proc_file()
test_an_ordinary_question_file_uses_the_default_banner_style()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
