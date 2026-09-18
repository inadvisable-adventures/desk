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

from desk.shell.window import DeskWindow, JOB_RUNNER_WIDGET_ID, TEMP_UI_WIDGET_IDS  # noqa: E402

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


def test_job_runner_id_is_in_temp_ui_widget_ids():
    check(
        "JOB_RUNNER_WIDGET_ID is in TEMP_UI_WIDGET_IDS (needed for restore reconnection)",
        JOB_RUNNER_WIDGET_ID in TEMP_UI_WIDGET_IDS,
    )


def test_temp_ui_widget_id_for_resolves_job_files_to_the_job_runner():
    with tempfile.TemporaryDirectory() as d:
        job_path = Path(d) / "some-uuid"
        job_path.write_text(f"Job\thtml\tFetch things\nScript\t{_b64('<html></html>')}\n")
        win = _FakeWindow()
        check(
            "_temp_ui_widget_id_for resolves a real Job file to JOB_RUNNER_WIDGET_ID",
            win._temp_ui_widget_id_for(job_path) == JOB_RUNNER_WIDGET_ID,
        )


def test_notify_temp_ui_composes_job_summary_text():
    with tempfile.TemporaryDirectory() as d:
        job_path = Path(d) / "some-uuid"
        job_path.write_text(f"Job\tpython\tClean up old scratch files\nScript\t{_b64('pass')}\n")
        win = _FakeWindow()
        win._notify_temp_ui(job_path)
        check("notify_temp_ui was called exactly once", len(win.view.notifications) == 1)
        _, text, banner_style = win.view.notifications[0]
        check("the notification text names the Job's declared summary", text == "Job: Clean up old scratch files")
        check("a Job's own notification uses the default banner style, not desk_proc", banner_style == "default")


def test_notify_temp_ui_falls_back_gracefully_for_a_malformed_job_file():
    with tempfile.TemporaryDirectory() as d:
        job_path = Path(d) / "some-uuid"
        job_path.write_text("Job\tpython\n")  # no Script line -- parse_job returns None
        win = _FakeWindow()
        win._notify_temp_ui(job_path)
        _, text, _banner_style = win.view.notifications[0]
        check("a malformed Job file still gets a real (fallback) notification, not a crash", text != "")


test_job_runner_id_is_in_temp_ui_widget_ids()
test_temp_ui_widget_id_for_resolves_job_files_to_the_job_runner()
test_notify_temp_ui_composes_job_summary_text()
test_notify_temp_ui_falls_back_gracefully_for_a_malformed_job_file()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
