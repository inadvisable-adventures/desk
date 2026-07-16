import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.event_mediator import EventMediator  # noqa: E402
from desk.shell.new_desk_dialog import NewDeskDialog  # noqa: E402
from desk.shell.temp_ui_manager import TempUiManager  # noqa: E402
from desk.temp_ui import ensure_gitignore_entry, GITIGNORE_ENTRIES, GITIGNORE_COMMENT  # noqa: E402
from desk.shell.window import DeskWindow, NewDeskProvisioning  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


# ---------- NewDeskDialog ----------


def test_dialog_default_path_and_browse():
    with tempfile.TemporaryDirectory() as d:
        default_dir = Path(d)
        dialog = NewDeskDialog(default_directory=default_dir, dev_process_filename=None)
        assert dialog._path_field.text() == str(default_dir)
        assert dialog._dev_process_checkbox is None

        other = default_dir / "sub"
        other.mkdir()
        from unittest.mock import patch

        with patch("desk.shell.new_desk_dialog.QFileDialog.getExistingDirectory", return_value=str(other)):
            dialog._browse()
        assert dialog._path_field.text() == str(other)
        assert dialog._directory == other
    print("dialog shows default path, Browse updates it: PASS")


def test_dialog_dev_process_checkbox_shown_when_offered():
    with tempfile.TemporaryDirectory() as d:
        dialog = NewDeskDialog(default_directory=Path(d), dev_process_filename="development-process.md")
        assert dialog._dev_process_checkbox is not None
        assert not dialog._dev_process_checkbox.isChecked()  # unchecked by default
    print("dev-process checkbox shown (unchecked) when offered: PASS")


def test_dialog_submit_emits_created():
    with tempfile.TemporaryDirectory() as d:
        dialog = NewDeskDialog(default_directory=Path(d), dev_process_filename="development-process.md")
        dialog._name_field.setText("My Project")
        dialog._gitignore_checkbox.setChecked(False)
        dialog._dev_process_checkbox.setChecked(True)
        received = []
        dialog.created.connect(lambda *args: received.append(args))
        dialog._submit()
        assert received == [("My Project", str(Path(d)), True, False, True)]
    print("Create emits the collected answers: PASS")


def test_dialog_submit_with_empty_name_does_not_emit():
    with tempfile.TemporaryDirectory() as d:
        dialog = NewDeskDialog(default_directory=Path(d), dev_process_filename=None)
        received = []
        dialog.created.connect(lambda *args: received.append(args))
        dialog._submit()
        assert received == []
    print("empty name does not emit created: PASS")


# ---------- ensure_gitignore_entry ----------


def test_gitignore_fresh_file():
    with tempfile.TemporaryDirectory() as d:
        git_root = Path(d)
        ensure_gitignore_entry(git_root, ask=lambda: True)
        text = (git_root / ".gitignore").read_text()
        expected_block = "\n".join(GITIGNORE_ENTRIES)
        assert text == f"\n{GITIGNORE_COMMENT}\n{expected_block}\n", repr(text)
    print("fresh .gitignore gets blank line + comment + all entries: PASS")


def test_gitignore_appends_with_blank_line_trailing_newline():
    with tempfile.TemporaryDirectory() as d:
        git_root = Path(d)
        (git_root / ".gitignore").write_text("node_modules/\n")
        ensure_gitignore_entry(git_root, ask=lambda: True)
        text = (git_root / ".gitignore").read_text()
        expected_block = "\n".join(GITIGNORE_ENTRIES)
        assert text == f"node_modules/\n\n{GITIGNORE_COMMENT}\n{expected_block}\n", repr(text)
    print("appending after content with trailing newline gets exactly one blank line: PASS")


def test_gitignore_appends_without_trailing_newline():
    with tempfile.TemporaryDirectory() as d:
        git_root = Path(d)
        (git_root / ".gitignore").write_text("node_modules/")  # no trailing newline
        ensure_gitignore_entry(git_root, ask=lambda: True)
        text = (git_root / ".gitignore").read_text()
        expected_block = "\n".join(GITIGNORE_ENTRIES)
        assert text == f"node_modules/\n\n{GITIGNORE_COMMENT}\n{expected_block}\n", repr(text)
    print("appending after content without trailing newline gets exactly one blank line: PASS")


def test_gitignore_already_present_is_noop():
    with tempfile.TemporaryDirectory() as d:
        git_root = Path(d)
        existing = "\n".join(GITIGNORE_ENTRIES) + "\n"
        (git_root / ".gitignore").write_text(existing)
        calls = []
        ensure_gitignore_entry(git_root, ask=lambda: calls.append(1) or True)
        assert calls == []  # ask() never called
        assert (git_root / ".gitignore").read_text() == existing
    print("all entries already present: no-op, ask() never called: PASS")


def test_gitignore_recheck_before_write_catches_concurrent_add():
    with tempfile.TemporaryDirectory() as d:
        git_root = Path(d)
        gitignore_path = git_root / ".gitignore"
        gitignore_path.write_text("node_modules/\n")
        expected_block = "\n".join(GITIGNORE_ENTRIES)

        def ask_and_simulate_concurrent_write():
            # Simulates another process adding the entries while ask()'s
            # own modal dialog was still up.
            gitignore_path.write_text(f"node_modules/\n\n{GITIGNORE_COMMENT}\n{expected_block}\n")
            return True

        ensure_gitignore_entry(git_root, ask=ask_and_simulate_concurrent_write)
        text = gitignore_path.read_text()
        # Written exactly once each, not duplicated by a stale-prefix rewrite.
        for entry in GITIGNORE_ENTRIES:
            assert text.count(entry) == 1, text
    print("re-check before write avoids duplicating concurrently-added entries: PASS")


# ---------- TempUiManager.provision ----------


def test_provision_recheck_before_mkdir_handles_concurrent_creation():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / ".desk_temp"
        manager = TempUiManager()

        def ask_and_simulate_concurrent_mkdir():
            temp_dir.mkdir()
            return True

        result = manager.provision(directory, ask_and_simulate_concurrent_mkdir, lambda: False)
        assert result == temp_dir
        assert temp_dir.is_dir()
    print("provision's re-check before mkdir tolerates concurrent creation: PASS")


def test_provision_declining_temp_ui_still_does_gitignore():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        import subprocess

        subprocess.run(["git", "init", "-q"], cwd=directory, check=True)
        manager = TempUiManager()
        result = manager.provision(directory, ask_create_dir=lambda: False, ask_gitignore=lambda: True)
        assert result is None
        assert not (directory / ".desk_temp").exists()
        gitignore_text = (directory / ".gitignore").read_text()
        for entry in GITIGNORE_ENTRIES:
            assert entry in gitignore_text
    print("declining .desk_temp still independently honors the .gitignore checkbox: PASS")


# ---------- DeskWindow ordering (unbound methods on a fake double) ----------


class _FakeWidgetInfo:
    default_size = (100, 100)


class _FakeWindow:
    def __init__(self, directory):
        self.current_desk = type("D", (), {"directory": directory, "path": directory / "x.desk", "name": "x"})()
        self._widgets = {}
        self.calls = []

    def _confirm_fn(self, title, message):
        def confirm():
            self.calls.append(("confirm_fn_called", title))
            return True

        return confirm

    def _warn(self, title, message):
        self.calls.append(("warn", title, message))

    class _TempUiManager:
        def __init__(self, outer):
            self._outer = outer

        def provision(self, directory, ask_create_dir, ask_gitignore):
            self._outer.calls.append(("provision", directory, ask_create_dir(), ask_gitignore()))
            return directory / ".desk_temp"

    def __post_init(self):
        pass


_FakeWindow._provision_temp_ui = DeskWindow._provision_temp_ui
_FakeWindow._ensure_questions_watcher = lambda self: self.calls.append(("ensure_questions_watcher",))


def test_provision_temp_ui_with_predecided_answers_skips_confirm():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        win._temp_ui_manager = _FakeWindow._TempUiManager(win)
        win._provision_temp_ui(NewDeskProvisioning(create_temp_ui=False, create_gitignore=True))
        assert ("provision", Path(d), False, True) in win.calls
        assert not any(c[0] == "confirm_fn_called" for c in win.calls)
    print("pre-decided NewDeskProvisioning skips confirm dialogs entirely: PASS")


def test_provision_temp_ui_without_answers_uses_confirm():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        win._temp_ui_manager = _FakeWindow._TempUiManager(win)
        win._provision_temp_ui(None)
        assert any(c[0] == "confirm_fn_called" for c in win.calls)
    print("no pre-decided answers: falls back to confirm dialogs as before: PASS")


class _OrderTrackingWindow:
    def __init__(self, directory):
        self.current_desk = type(
            "D", (), {"path": Path("/old.desk"), "directory": Path("/old"), "custom_widgets": []}
        )()
        self.order = []
        self._directory_to_switch_to = directory
        # TODO 91b3f42: switch_desk now also touches these directly
        # (forgetting the previous Desk's custom widgets) before
        # registering the new Desk's.
        self._widgets = {}
        self._custom_widget_definitions = {}
        self._custom_widget_sources = {}
        self._custom_widget_source_paths = {}
        # TODO 5734529: switch_desk also clears this alongside the
        # custom-widget dicts above.
        self._html_widget_local_storage = {}
        # TODO 6f9c51b: switch_desk also calls self._event_mediator.clear_all().
        self._event_mediator = EventMediator()
        # switch_desk also clears this Bridge API introspection-grant cache.
        self._introspect_grants = set()

    def save_current_desk(self):
        self.order.append("save_current_desk")

    class _View:
        def clear_widgets(self):
            pass

        def set_view_state(self, *a):
            pass

    view = _View()

    def _provision_temp_ui(self, provisioning=None):
        self.order.append("provision_temp_ui")

    def _load_desk_widgets(self, desk):
        self.order.append("load_desk_widgets")

    def _refresh_picker(self):
        self.order.append("refresh_picker")

    def _register_custom_widgets_from_desk(self, desk):
        self.order.append("register_custom_widgets_from_desk")

    def _register_custom_widgets_from_desk_temp(self, directory):
        self.order.append("register_custom_widgets_from_desk_temp")

    def _sync_tempui_doc(self):
        self.order.append("sync_tempui_doc")


import desk.shell.window as window_mod  # noqa: E402


def test_switch_desk_provisions_before_loading_widgets():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _OrderTrackingWindow(directory)
        win.__class__.switch_desk = DeskWindow.switch_desk
        set_dir_calls = []
        orig_set_dir = window_mod.current_context.set_current_desk_directory
        window_mod.current_context.set_current_desk_directory = (
            lambda d: (set_dir_calls.append(d), win.order.append("set_current_desk_directory"))
        )
        try:
            new_path = directory / "new.desk"
            win.switch_desk(new_path, confirm=lambda: True)
        finally:
            window_mod.current_context.set_current_desk_directory = orig_set_dir

        assert win.order.index("set_current_desk_directory") < win.order.index("provision_temp_ui")
        assert win.order.index("provision_temp_ui") < win.order.index("load_desk_widgets")
        # TODO 91b3f42: the new Desk's custom widgets from its own .desk
        # file register before provisioning (doesn't need .desk_temp);
        # its still-tempui-sourced ones register after provisioning
        # (needs .desk_temp to exist) but before widgets are loaded
        # (which needs the catalog ready); the doc syncs last.
        assert win.order.index("register_custom_widgets_from_desk") < win.order.index("provision_temp_ui")
        assert win.order.index("provision_temp_ui") < win.order.index("register_custom_widgets_from_desk_temp")
        assert win.order.index("register_custom_widgets_from_desk_temp") < win.order.index("load_desk_widgets")
        assert win.order.index("sync_tempui_doc") > win.order.index("load_desk_widgets")
    print("switch_desk sets current_desk_directory + provisions before loading widgets: PASS")


test_dialog_default_path_and_browse()
test_dialog_dev_process_checkbox_shown_when_offered()
test_dialog_submit_emits_created()
test_dialog_submit_with_empty_name_does_not_emit()
test_gitignore_fresh_file()
test_gitignore_appends_with_blank_line_trailing_newline()
test_gitignore_appends_without_trailing_newline()
test_gitignore_already_present_is_noop()
test_gitignore_recheck_before_write_catches_concurrent_add()
test_provision_recheck_before_mkdir_handles_concurrent_creation()
test_provision_declining_temp_ui_still_does_gitignore()
test_provision_temp_ui_with_predecided_answers_skips_confirm()
test_provision_temp_ui_without_answers_uses_confirm()
test_switch_desk_provisions_before_loading_widgets()
print("ALL PASS")
