import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    DESK_WIDGETS_BUILD_GITIGNORE_ENTRY,
    GITIGNORE_COMMENT,
    PROMOTED_WIDGET_SRC_DIRNAME,
    ensure_desk_widgets_gitignore_entry,
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


def _git_init(directory):
    subprocess.run(["git", "init", "-q"], cwd=directory, check=True)


check(
    "DESK_WIDGETS_BUILD_GITIGNORE_ENTRY is desk_widgets/**/.build/ (project-specific, narrower than Desk's own **/.build/)",
    DESK_WIDGETS_BUILD_GITIGNORE_ENTRY == f"{PROMOTED_WIDGET_SRC_DIRNAME}/**/.build/",
)


def test_noop_when_desk_widgets_does_not_exist():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _git_init(directory)
        calls = []
        ensure_desk_widgets_gitignore_entry(directory, ask=lambda: calls.append(1) or True)
        check("no desk_widgets/ at all: ask() never called", calls == [])
        check("no desk_widgets/ at all: no .gitignore created", not (directory / ".gitignore").exists())


def test_noop_when_not_in_a_git_repo():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        (directory / PROMOTED_WIDGET_SRC_DIRNAME).mkdir()
        # Deliberately no _git_init(directory) -- a tempdir is never
        # itself inside a git repo in this environment.
        calls = []
        ensure_desk_widgets_gitignore_entry(directory, ask=lambda: calls.append(1) or True)
        check("desk_widgets/ exists but no git repo: ask() never called", calls == [])
        check("desk_widgets/ exists but no git repo: no .gitignore created", not (directory / ".gitignore").exists())


def test_fresh_gitignore():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _git_init(directory)
        (directory / PROMOTED_WIDGET_SRC_DIRNAME).mkdir()
        ensure_desk_widgets_gitignore_entry(directory, ask=lambda: True)
        text = (directory / ".gitignore").read_text()
        check(
            "fresh .gitignore gets blank line + comment + the entry",
            text == f"\n{GITIGNORE_COMMENT}\n{DESK_WIDGETS_BUILD_GITIGNORE_ENTRY}\n",
        )


def test_appends_to_existing_gitignore():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _git_init(directory)
        (directory / PROMOTED_WIDGET_SRC_DIRNAME).mkdir()
        (directory / ".gitignore").write_text("node_modules/\n")
        ensure_desk_widgets_gitignore_entry(directory, ask=lambda: True)
        text = (directory / ".gitignore").read_text()
        check(
            "appends after existing content with exactly one blank line",
            text == f"node_modules/\n\n{GITIGNORE_COMMENT}\n{DESK_WIDGETS_BUILD_GITIGNORE_ENTRY}\n",
        )


def test_already_present_is_noop():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _git_init(directory)
        (directory / PROMOTED_WIDGET_SRC_DIRNAME).mkdir()
        existing = f"{DESK_WIDGETS_BUILD_GITIGNORE_ENTRY}\n"
        (directory / ".gitignore").write_text(existing)
        calls = []
        ensure_desk_widgets_gitignore_entry(directory, ask=lambda: calls.append(1) or True)
        check("entry already present: ask() never called", calls == [])
        check("entry already present: .gitignore untouched", (directory / ".gitignore").read_text() == existing)


def test_recheck_before_write_catches_concurrent_add():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _git_init(directory)
        (directory / PROMOTED_WIDGET_SRC_DIRNAME).mkdir()
        gitignore_path = directory / ".gitignore"
        gitignore_path.write_text("node_modules/\n")

        def ask_and_simulate_concurrent_write():
            gitignore_path.write_text(f"node_modules/\n\n{GITIGNORE_COMMENT}\n{DESK_WIDGETS_BUILD_GITIGNORE_ENTRY}\n")
            return True

        ensure_desk_widgets_gitignore_entry(directory, ask=ask_and_simulate_concurrent_write)
        text = gitignore_path.read_text()
        check(
            "re-check before write avoids duplicating a concurrently-added entry",
            text.count(DESK_WIDGETS_BUILD_GITIGNORE_ENTRY) == 1,
        )


def test_declining_the_confirm_writes_nothing():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _git_init(directory)
        (directory / PROMOTED_WIDGET_SRC_DIRNAME).mkdir()
        ensure_desk_widgets_gitignore_entry(directory, ask=lambda: False)
        check("declining leaves .gitignore unwritten", not (directory / ".gitignore").exists())


# ---------- DeskWindow._provision_temp_ui wiring ----------


class _FakeWindow:
    def __init__(self, directory):
        self.current_desk = type("D", (), {"directory": directory})()
        self._temp_ui_manager = type("M", (), {"provision": lambda self, *a, **k: None})()
        self._schema_registry = type("S", (), {"clear_source": lambda self, s: None})()
        self._known_schema_file_sources = set()
        self._schema_file_watcher = type("W", (), {"provision": lambda self, *a, **k: None})()
        self._questions_watcher_calls = 0
        self.confirmed_titles = []

    def _confirm_fn(self, title, message):
        self.confirmed_titles.append(title)

        def confirm():
            return True

        return confirm

    def _ensure_questions_watcher(self):
        self._questions_watcher_calls += 1


_FakeWindow._provision_temp_ui = DeskWindow._provision_temp_ui
_FakeWindow._provision_schema_files = DeskWindow._provision_schema_files


def test_provision_temp_ui_ensures_desk_widgets_gitignore_entry():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _git_init(directory)
        (directory / PROMOTED_WIDGET_SRC_DIRNAME).mkdir()
        win = _FakeWindow(directory)
        win._provision_temp_ui()
        text = (directory / ".gitignore").read_text()
        check(
            "_provision_temp_ui (startup/Desk-switch) also ensures the desk_widgets/**/.build/ entry",
            DESK_WIDGETS_BUILD_GITIGNORE_ENTRY in text,
        )
        check("_provision_temp_ui asked about it under a distinct title", "Custom Widgets" in win.confirmed_titles)


def test_provision_temp_ui_noop_without_desk_widgets():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _git_init(directory)
        win = _FakeWindow(directory)
        win._provision_temp_ui()
        check("no desk_widgets/ yet: _provision_temp_ui doesn't create a .gitignore for it", not (directory / ".gitignore").exists())


test_noop_when_desk_widgets_does_not_exist()
test_noop_when_not_in_a_git_repo()
test_fresh_gitignore()
test_appends_to_existing_gitignore()
test_already_present_is_noop()
test_recheck_before_write_catches_concurrent_add()
test_declining_the_confirm_writes_nothing()
test_provision_temp_ui_ensures_desk_widgets_gitignore_entry()
test_provision_temp_ui_noop_without_desk_widgets()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
