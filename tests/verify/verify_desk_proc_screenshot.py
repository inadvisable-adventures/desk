import os
import struct
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


def _png_dimensions(path: Path) -> tuple[int, int]:
    """Reads width/height straight out of a PNG's own IHDR chunk (TODO
    94d2b94) -- no image library needed, just the fixed byte layout
    every PNG has: an 8-byte signature, then a 4-byte length + 4-byte
    'IHDR' type, then big-endian width/height (4 bytes each)."""
    data = path.read_bytes()
    width, height = struct.unpack(">II", data[16:24])
    return width, height


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


def test_max_width_scales_down_a_wider_capture_proportionally():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        native_path = directory / "native.png"
        scaled_path = directory / "scaled.png"
        win.screenshot_desk("native.png")
        native_width, native_height = _png_dimensions(native_path)
        check("sanity: the canvas capture is wide enough for this test to mean anything", native_width > 100)

        result = win.screenshot_desk("scaled.png", max_width=100)
        check("screenshot_desk with max_width still returns True on success", result is True)
        scaled_width, scaled_height = _png_dimensions(scaled_path)
        check("the capture was scaled down to exactly max_width", scaled_width == 100)
        check(
            "height was scaled down proportionally, not stretched/cropped to a fixed size",
            abs(scaled_height / scaled_width - native_height / native_width) < 0.02,
        )


def test_max_width_never_scales_up_a_narrower_capture():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        native_path = directory / "native.png"
        win.screenshot_desk("native.png")
        native_width, native_height = _png_dimensions(native_path)

        upscaled_path = directory / "upscaled.png"
        win.screenshot_desk("upscaled.png", max_width=native_width * 10)
        upscaled_width, upscaled_height = _png_dimensions(upscaled_path)
        check(
            "a max_width larger than the native capture is a no-op, never scales up",
            (upscaled_width, upscaled_height) == (native_width, native_height),
        )


def test_omitting_max_width_is_byte_identical_to_before_this_feature():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        default_path = directory / "default.png"
        explicit_none_path = directory / "explicit_none.png"
        win.screenshot_desk("default.png")
        win.screenshot_desk("explicit_none.png", max_width=None)
        check(
            "omitting max_width and passing max_width=None produce byte-identical output (the pre-existing default)",
            default_path.read_bytes() == explicit_none_path.read_bytes(),
        )


def test_max_width_also_applies_to_screenshot_widget_instance():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        info = _python_widget_info(directory)
        _write_widget_py(directory, _SIMPLE_WIDGET_BODY)
        instance_id = uuid_mod.uuid4().hex[:8]
        win._place_widget("ordinary_python", info, (0, 0), (400, 300), instance_id=instance_id)

        native_path = directory / "widget_native.png"
        win.screenshot_widget_instance(instance_id, "widget_native.png")
        native_width, _ = _png_dimensions(native_path)
        check("sanity: the widget frame capture is wide enough for this test to mean anything", native_width > 50)

        scaled_path = directory / "widget_scaled.png"
        result = win.screenshot_widget_instance(instance_id, "widget_scaled.png", max_width=40)
        check("screenshot_widget_instance with max_width still returns True", result is True)
        check("screenshot_widget_instance's own capture is scaled down too", _png_dimensions(scaled_path)[0] == 40)


def test_deskprocapi_passes_max_width_through():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "desk_proc_runner_widget_test", REPO_ROOT / "widgets/desk_proc_runner/widget.py"
    )
    runner_widget = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner_widget)

    calls = []

    class _FakeMainWindow:
        def screenshot_desk(self, path, max_width=None):
            calls.append(("desk", path, max_width))
            return True

        def screenshot_widget_instance(self, instance_id, path, max_width=None):
            calls.append(("widget", instance_id, path, max_width))
            return True

    from desk.shell import current_context

    previous_window = current_context.get_main_window()
    previous_caller = current_context.get_gui_thread_caller()
    try:
        current_context.set_main_window(_FakeMainWindow())
        current_context.set_gui_thread_caller(lambda fn: fn())
        api = runner_widget.DeskProcApi()
        api.screenshot_desk("d.png", max_width=42)
        api.screenshot_widget("inst", "w.png", max_width=7)
    finally:
        current_context.set_main_window(previous_window)
        current_context.set_gui_thread_caller(previous_caller)

    check(
        "DeskProcApi.screenshot_desk/screenshot_widget pass max_width straight through to DeskWindow",
        calls == [("desk", "d.png", 42), ("widget", "inst", "w.png", 7)],
    )


def test_changelog_and_doc_cover_max_width():
    from desk.temp_ui import CURRENT_TAGS, _DESK_PROC_DOC, _NEW_FEATURES

    tag = "screenshot tools accept max_width downsampling #600160"
    check("tag is in CURRENT_TAGS with a _NEW_FEATURES entry", tag in CURRENT_TAGS and tag in _NEW_FEATURES)
    flat = " ".join(_DESK_PROC_DOC.split())
    check("tempui-desk-proc.md documents max_width on screenshot_widget", "screenshot_widget(instance_id: str, path: str, max_width" in flat)
    check("tempui-desk-proc.md documents max_width on screenshot_desk", "screenshot_desk(path: str, max_width" in flat)
    check("tempui-desk-proc.md says it never scales up", "never up" in flat)


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
test_max_width_scales_down_a_wider_capture_proportionally()
test_max_width_never_scales_up_a_narrower_capture()
test_omitting_max_width_is_byte_identical_to_before_this_feature()
test_max_width_also_applies_to_screenshot_widget_instance()
test_deskprocapi_passes_max_width_through()
test_changelog_and_doc_cover_max_width()
test_relative_path_resolves_against_current_desk_directory()
test_absolute_path_is_used_as_is()
test_missing_parent_directories_are_created()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
