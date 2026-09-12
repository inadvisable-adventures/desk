import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "widgets" / "installed_jobs"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.shell import current_context  # noqa: E402
from desk.installed_jobs import INSTALLED_JOBS_UPDATED_EVENT  # noqa: E402

import widget as installed_jobs_widget  # noqa: E402

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


def _reset_context():
    current_context.set_installed_jobs_provider(None)
    current_context.set_installed_job_uninstaller(None)
    current_context.set_editor_or_scrap_opener(None)
    current_context.set_popup_opener(None)
    current_context.set_current_desk_directory(None)


JOB_A = {"name": "greet", "version_hash": "abc123def456", "installed_at": "2026-01-01T00:00:00"}
JOB_B = {"name": "cleanup", "version_hash": "fedcba987654", "installed_at": "2026-01-02T00:00:00"}


def test_list_populates_from_provider():
    _reset_context()
    current_context.set_installed_jobs_provider(lambda: [JOB_A, JOB_B])
    widget = installed_jobs_widget.build()
    check("both installed jobs appear as rows", widget._list.count() == 2)
    check("status label reflects the count", widget._status_label.text() == "2 installed.")


def test_empty_list_shows_a_clear_status():
    _reset_context()
    current_context.set_installed_jobs_provider(lambda: [])
    widget = installed_jobs_widget.build()
    check("no rows when nothing is installed", widget._list.count() == 0)
    check("status label says so", widget._status_label.text() == "No installed jobs.")


def test_no_provider_registered_is_not_a_crash():
    _reset_context()
    widget = installed_jobs_widget.build()
    check("an unregistered provider degrades to an empty list, not a crash", widget._list.count() == 0)


def test_mediated_event_refreshes_the_list():
    _reset_context()
    current_context.set_installed_jobs_provider(lambda: [JOB_A])
    widget = installed_jobs_widget.build()
    check("starts with one row", widget._list.count() == 1)

    widget._on_mediated_event(INSTALLED_JOBS_UPDATED_EVENT, {"jobs": [JOB_A, JOB_B]}, "")
    check("a live INSTALLED_JOBS_UPDATED_EVENT refreshes the list to two rows", widget._list.count() == 2)

    widget._on_mediated_event(INSTALLED_JOBS_UPDATED_EVENT, {"jobs": []}, "")
    check("and back down to zero when everything is uninstalled elsewhere", widget._list.count() == 0)

    widget._on_mediated_event("some.other.event", {"jobs": [JOB_A, JOB_B]}, "")
    check("an unrelated event name is ignored", widget._list.count() == 0)


def test_view_source_opens_an_editor_for_every_file_in_the_job_directory():
    _reset_context()
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        job_dir = directory / "desk-installed-jobs" / "greet"
        job_dir.mkdir(parents=True)
        (job_dir / "main.py").write_text("print('hi')\n")
        (job_dir / "helper.py").write_text("X = 1\n")

        current_context.set_current_desk_directory(directory)
        opened = []
        current_context.set_editor_or_scrap_opener(lambda path: opened.append(path))
        current_context.set_installed_jobs_provider(lambda: [JOB_A])

        widget = installed_jobs_widget.build()
        widget._view_source("greet")
        check("opens exactly one editor per file in the job's directory", len(opened) == 2)
        check("opens main.py", job_dir / "main.py" in opened)
        check("opens helper.py", job_dir / "helper.py" in opened)


def test_uninstall_confirms_then_calls_the_uninstaller():
    _reset_context()
    current_context.set_installed_jobs_provider(lambda: [JOB_A])
    uninstalled = []
    current_context.set_installed_job_uninstaller(lambda name: uninstalled.append(name) or True)

    current_context.set_popup_opener(lambda title, message, buttons, default: "Cancel")
    widget = installed_jobs_widget.build()
    widget._uninstall("greet")
    check("canceling the confirmation does not uninstall", uninstalled == [])

    current_context.set_popup_opener(lambda title, message, buttons, default: "Uninstall")
    widget._uninstall("greet")
    check("confirming calls the uninstaller with the right name", uninstalled == ["greet"])


def test_uninstall_with_no_popup_opener_still_calls_the_uninstaller():
    """No popup service registered (e.g. very early startup) shouldn't
    silently block a user-requested uninstall -- degrades to
    "no confirmation available", not "no uninstall possible"."""
    _reset_context()
    current_context.set_installed_jobs_provider(lambda: [JOB_A])
    uninstalled = []
    current_context.set_installed_job_uninstaller(lambda name: uninstalled.append(name) or True)
    widget = installed_jobs_widget.build()
    widget._uninstall("greet")
    check("uninstall proceeds when no popup opener is registered", uninstalled == ["greet"])


test_list_populates_from_provider()
test_empty_list_shows_a_clear_status()
test_no_provider_registered_is_not_a_crash()
test_mediated_event_refreshes_the_list()
test_view_source_opens_an_editor_for_every_file_in_the_job_directory()
test_uninstall_confirms_then_calls_the_uninstaller()
test_uninstall_with_no_popup_opener_still_calls_the_uninstaller()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
