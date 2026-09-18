import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# TODO 78bfa41: QWebEngineWidgets must be imported before a
# QApplication is constructed -- desk.shell.window pulls in
# ChromiumWidget (and therefore QWebEngineView) transitively.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.shell.temp_ui_manager import TempUiManager  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import TEMP_UI_DIRNAME  # noqa: E402

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


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


# ---------- TempUiManager.notify_dev_process_peers_seeded ----------


def _added_scratch_files(temp_dir, before):
    after = {p.name for p in temp_dir.iterdir() if p.is_file()}
    return after - before


def test_notify_writes_a_real_scratch_note_after_provisioning():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        manager = TempUiManager()
        temp_dir = manager.provision(directory, ask_create_dir=lambda: True, ask_gitignore=lambda: False)
        check("provision created .desk_temp", temp_dir is not None and temp_dir.is_dir())
        before = {p.name for p in temp_dir.iterdir() if p.is_file()}

        added_files = []
        manager.file_added.connect(lambda path: added_files.append(path))

        manager.notify_dev_process_peers_seeded(directory)
        pump(0.2)

        new_names = _added_scratch_files(temp_dir, before)
        check("exactly one new file appeared in .desk_temp", len(new_names) == 1)
        check("file_added signal fired for the new note", len(added_files) == 1)
        if new_names:
            note_text = (temp_dir / next(iter(new_names))).read_text()
            check("note starts with a real Scratch heading", note_text.startswith("Scratch development-process.md peers were just seeded"))
            check("note names shared_development_process.md", "shared_development_process.md" in note_text)
            check(
                "note names specifically-not-working-on-desk-itself-development-process.md",
                "specifically-not-working-on-desk-itself-development-process.md" in note_text,
            )
            check("note points at the fork-development-process-doc plan", "plans/fork-development-process-doc.md" in note_text)
        manager.stop()


def test_notify_is_a_noop_when_directory_is_not_being_watched():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        manager = TempUiManager()
        # Never provisioned/watched for this directory at all.
        added_files = []
        manager.file_added.connect(lambda path: added_files.append(path))

        manager.notify_dev_process_peers_seeded(directory)
        pump(0.1)

        check("no signal fired for an unwatched directory", added_files == [])
        check(".desk_temp was never even created", not (directory / TEMP_UI_DIRNAME).exists())
        manager.stop()


# ---------- DeskWindow.new_desk wiring ----------


class _FakeTempUiManager:
    def __init__(self, order):
        self.calls = []
        self._order = order

    def notify_dev_process_peers_seeded(self, directory):
        self.calls.append(directory)
        self._order.append("notify_dev_process_peers_seeded")


class _FakeWindow:
    def __init__(self, directory, seed_returns):
        self.current_desk = type("D", (), {"directory": directory, "path": directory / "x.desk"})()
        self.order = []
        self._temp_ui_manager = _FakeTempUiManager(self.order)
        self._seed_returns = seed_returns
        self.switch_desk_calls = []

    def _warn(self, title, message):
        self.order.append("warn")

    def _seed_development_process(self, directory):
        self.order.append("seed_development_process")
        return self._seed_returns

    def _seed_todo_item_ids_script(self, directory):
        self.order.append("seed_todo_item_ids_script")

    def switch_desk(self, path, confirm=None, provisioning=None):
        self.order.append("switch_desk")
        self.switch_desk_calls.append((path, provisioning))

    def save_current_desk(self):
        self.order.append("save_current_desk")


_FakeWindow.new_desk = DeskWindow.new_desk


def test_new_desk_calls_notify_after_switch_desk_when_breadcrumb_warranted():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory, seed_returns=True)
        win.new_desk("MyProject", directory, copy_development_process=True)

        check(
            "notify_dev_process_peers_seeded was called exactly once, with the right directory",
            win._temp_ui_manager.calls == [directory],
        )
        check(
            "seeding, then switch_desk, then the notify breadcrumb, then save_current_desk",
            win.order == [
                "seed_development_process",
                "seed_todo_item_ids_script",
                "switch_desk",
                "notify_dev_process_peers_seeded",
                "save_current_desk",
            ],
        )


def test_new_desk_does_not_call_notify_when_breadcrumb_not_warranted():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory, seed_returns=False)
        win.new_desk("MyProject", directory, copy_development_process=True)

        check("notify_dev_process_peers_seeded was never called", win._temp_ui_manager.calls == [])


def test_new_desk_does_not_call_notify_when_copy_development_process_is_false():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory, seed_returns=True)  # would warrant it, but...
        win.new_desk("MyProject", directory, copy_development_process=False)

        check("seeding never ran", "seed_development_process" not in win.order)
        check("notify_dev_process_peers_seeded was never called", win._temp_ui_manager.calls == [])


# ---------- shared_development_process.md documents the ../FEEDBACK/ convention ----------


def test_shared_development_process_documents_feedback_convention():
    doc = (REPO_ROOT / "shared_development_process.md").read_text()
    check("doc mentions ../FEEDBACK/", "../FEEDBACK/" in doc)
    check("doc mentions the implemented/ archival step", "../FEEDBACK/implemented/" in doc)
    check("doc mentions the FEEDBACK-DESK naming convention", "FEEDBACK-DESK-" in doc)
    check("doc says to cite it in TODO.md/PARKINGLOT.md", "PARKINGLOT.md" in doc and "TODO.md" in doc)


test_notify_writes_a_real_scratch_note_after_provisioning()
test_notify_is_a_noop_when_directory_is_not_being_watched()
test_new_desk_calls_notify_after_switch_desk_when_breadcrumb_warranted()
test_new_desk_does_not_call_notify_when_breadcrumb_not_warranted()
test_new_desk_does_not_call_notify_when_copy_development_process_is_false()
test_shared_development_process_documents_feedback_convention()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
