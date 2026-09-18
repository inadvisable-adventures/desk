import os
import sys
import tempfile
import uuid as uuid_mod
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.schema_registry import SchemaRegistry  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.shell.promoted_widget_source_watcher import PromotedWidgetSourceWatcher  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402

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


# ---------- fake window scaffolding (mirrors verify_widget_error_indicator.py) ----------


class _FakeHandle:
    token = "tok"

    def widget_url(self, widget_id):
        return f"http://fake/{widget_id}"


class _FakeWindow:
    def __init__(self, directory):
        self.current_desk = Desk(path=directory / "test.desk")
        self._widgets = {}
        self._handle = _FakeHandle()
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self._broker = HotReloadBroker()
        self._custom_widget_sources = {}
        self._custom_widget_definitions = {}
        self._custom_widget_content_hash = {}
        # TODO 4eb3d9e: _register_custom_widget/_place_widget/
        # _on_widget_stale_clicked now also touch these.
        self._promoted_widget_source_watcher = PromotedWidgetSourceWatcher()
        self._promoted_widget_source_dirty = set()
        self._schema_registry = SchemaRegistry()


_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._chromium_profile_dir = DeskWindow._chromium_profile_dir
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._bind_error_indicator = DeskWindow._bind_error_indicator
_FakeWindow._check_schema_conflict = DeskWindow._check_schema_conflict
_FakeWindow._is_instance_currently_placed = DeskWindow._is_instance_currently_placed
_FakeWindow._notify_schema_conflict = DeskWindow._notify_schema_conflict
_FakeWindow._show_schema_conflict_popup = DeskWindow._show_schema_conflict_popup
_FakeWindow.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id
_FakeWindow._resolve_desk_relative_path = DeskWindow._resolve_desk_relative_path
_FakeWindow.screenshot_widget_instance = DeskWindow.screenshot_widget_instance
_FakeWindow.screenshot_desk = DeskWindow.screenshot_desk


def _python_widget_info(directory):
    return WidgetInfo(
        id="ordinary_python", path=directory, kind="python", name="Ordinary",
        entry="widget.py", capabilities=[], default_size=None,
    )


def _write_widget_py(directory, body):
    (directory / "widget.py").write_text(body)


_SIMPLE_WIDGET_BODY = """
from PyQt6.QtWidgets import QLabel

def build():
    return QLabel("hello")
"""


def test_screenshot_widget_instance_saves_a_real_png():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        info = _python_widget_info(directory)
        _write_widget_py(directory, _SIMPLE_WIDGET_BODY)
        instance_id = uuid_mod.uuid4().hex[:8]
        frame = win._place_widget("ordinary_python", info, (0, 0), (400, 300), instance_id=instance_id)
        check("a real frame was placed", frame is not None)

        out_path = directory / "shots" / "widget.png"
        result = win.screenshot_widget_instance(instance_id, "shots/widget.png")
        check("screenshot_widget_instance returns True on success", result is True)
        check("a real, non-empty PNG file was written", out_path.is_file() and out_path.stat().st_size > 0)
        check("PNG magic bytes are present", out_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n")


def test_screenshot_widget_instance_returns_false_for_an_unknown_instance():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        result = win.screenshot_widget_instance("no-such-instance", "shots/nope.png")
        check("unknown instance id returns False, not a crash", result is False)
        check("no file was written for a failed lookup", not (directory / "shots" / "nope.png").exists())


def test_screenshot_desk_saves_a_real_png_of_the_canvas():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        out_path = directory / "canvas.png"
        result = win.screenshot_desk("canvas.png")
        check("screenshot_desk returns True on success", result is True)
        check("a real, non-empty PNG file was written", out_path.is_file() and out_path.stat().st_size > 0)


def test_relative_path_resolves_against_current_desk_directory():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        resolved = win._resolve_desk_relative_path("sub/dir/shot.png")
        check("relative path resolves against current_desk.directory", resolved == directory / "sub" / "dir" / "shot.png")


def test_absolute_path_is_used_as_is():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as other_dir:
            absolute_target = Path(other_dir) / "elsewhere.png"
            result = win.screenshot_desk(str(absolute_target))
            check("an absolute path is used as-is, not resolved against the Desk directory", result is True)
            check("the file was actually written at the absolute path given", absolute_target.is_file())


def test_missing_parent_directories_are_created():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        deep_path = directory / "does" / "not" / "exist" / "yet" / "shot.png"
        check("target directory doesn't exist yet", not deep_path.parent.exists())
        result = win.screenshot_desk("does/not/exist/yet/shot.png")
        check("screenshot_desk creates missing parent directories, mirroring desk.fs.writeFile's own fix", result is True and deep_path.is_file())


test_screenshot_widget_instance_saves_a_real_png()
test_screenshot_widget_instance_returns_false_for_an_unknown_instance()
test_screenshot_desk_saves_a_real_png_of_the_canvas()
test_relative_path_resolves_against_current_desk_directory()
test_absolute_path_is_used_as_is()
test_missing_parent_directories_are_created()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
