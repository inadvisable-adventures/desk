import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.file_type_registry import (  # noqa: E402
    FileTypeHandler,
    FileTypeRegistryEntry,
    find_edit_handler,
    find_view_handler,
    looks_like_text_file,
)
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
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


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


file_explorer_mod = load_widget_module(
    "file_explorer_fallback_verify_mod", "/Users/mphair/inadvisable-adventures/desk/widgets/project_files/widget.py"
)

# ---------- lookup helpers (pure functions) ----------


def test_find_view_handler_registry_match_by_extension():
    registry = [FileTypeRegistryEntry(extensions=[".svg"], handlers=[FileTypeHandler(widget_id="svg_viewer", role="view")])]
    check("registry match by extension", find_view_handler(registry, Path("a.svg")) == "svg_viewer")


def test_find_view_handler_registry_match_by_mime():
    registry = [FileTypeRegistryEntry(mime_types=["text/markdown"], handlers=[FileTypeHandler(widget_id="markdown", role="view")])]
    check("registry match by mime type", find_view_handler(registry, Path("a.md")) == "markdown")


def test_find_view_handler_builtin_fallback():
    check("builtin fallback for .svg with empty registry", find_view_handler([], Path("a.svg")) == "image_viewer")
    check("builtin fallback for .png with empty registry", find_view_handler([], Path("a.png")) == "image_viewer")
    check("no builtin fallback for unknown extension", find_view_handler([], Path("a.xyz")) is None)


def test_find_edit_handler_has_no_builtin_fallback():
    check("find_edit_handler has no builtin fallback for .txt", find_edit_handler([], Path("a.txt")) is None)
    registry = [FileTypeRegistryEntry(extensions=[".txt"], handlers=[FileTypeHandler(widget_id="editor", role="edit")])]
    check("find_edit_handler finds a registered edit handler", find_edit_handler(registry, Path("a.txt")) == "editor")


def test_looks_like_text_file():
    with tempfile.TemporaryDirectory() as d:
        text_path = Path(d) / "a.txt"
        text_path.write_text("hello\nworld\n")
        check("plain text file looks like text", looks_like_text_file(text_path) is True)

        binary_path = Path(d) / "a.bin"
        binary_path.write_bytes(b"\x00\x01\x02\xff\xfe")
        check("binary file does not look like text", looks_like_text_file(binary_path) is False)

        missing_path = Path(d) / "missing.txt"
        check("missing file does not look like text", looks_like_text_file(missing_path) is False)


# ---------- DeskWindow.open_widget_content_centered ----------


class _FakeWindow:
    def __init__(self, directory):
        self._widgets = {
            "scratch": WidgetInfo(
                id="scratch", path=Path("."), kind="python", name="Scratch", entry="widget.py",
                capabilities=[], default_size=(400, 300),
            )
        }
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self.open_widget_content_calls = []

    def open_widget_content(self, widget_id, pos=None, size=None, instance_id=None):
        self.open_widget_content_calls.append({"widget_id": widget_id, "pos": pos, "size": size, "instance_id": instance_id})
        return "fake-content"


_FakeWindow.open_widget_content_centered = DeskWindow.open_widget_content_centered


def test_open_widget_content_centered_computes_scene_center():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        expected_center = win.view.mapToScene(win.view.viewport().rect().center())
        result = win.open_widget_content_centered("scratch")
        check("delegates to open_widget_content", result == "fake-content")
        check("exactly one call made", len(win.open_widget_content_calls) == 1)
        call = win.open_widget_content_calls[0]
        check("widget_id passed through", call["widget_id"] == "scratch")
        check("pos is the view's current scene center", call["pos"] == (expected_center.x(), expected_center.y()))
        check("size defaults to the widget's own default_size", call["size"] == (400, 300))


def test_open_widget_content_centered_unknown_widget_id_is_noop():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        result = win.open_widget_content_centered("nonexistent")
        check("unknown widget_id returns None", result is None)
        check("no call made for an unknown widget_id", len(win.open_widget_content_calls) == 0)


# ---------- File Explorer's full dispatch chain ----------


class _FakeCenteredOpener:
    def __init__(self):
        self.calls = []
        self.widgets_by_id = {}

    def __call__(self, widget_id):
        self.calls.append(widget_id)
        return self.widgets_by_id.get(widget_id)


class _FakeViewerWidget:
    def __init__(self):
        self.set_file_calls = []

    def set_file(self, path):
        self.set_file_calls.append(path)


class _FakeScratchWidget:
    def __init__(self):
        self.label = None
        self.body = _FakeBody()

    def set_label(self, text):
        self.label = text


class _FakeBody:
    def __init__(self):
        self.text = None

    def setPlainText(self, text):
        self.text = text


def _make_explorer(registry_entries=None):
    from desk.shell import current_context

    with tempfile.TemporaryDirectory() as d:
        pass  # directory not actually needed for _open_file directly
    current_context.set_current_desk_directory(None)
    current_context.set_file_type_registry_provider(lambda: registry_entries or [])
    widget = file_explorer_mod.build()
    return widget


def test_registered_view_handler_opens_that_widget():
    widget = _make_explorer([{"extensions": [".svg"], "mime_types": [], "handlers": [{"widget_id": "svg_viewer", "role": "view"}]}])
    opener = _FakeCenteredOpener()
    viewer = _FakeViewerWidget()
    opener.widgets_by_id["svg_viewer"] = viewer
    from desk.shell import current_context

    current_context.set_centered_widget_opener(opener)
    try:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.svg"
            path.write_text("<svg></svg>")
            widget._open_file(path)
        check("opener called with the registered view widget id", opener.calls == ["svg_viewer"])
        check("set_file called on the viewer widget", viewer.set_file_calls == [path])
    finally:
        current_context.set_centered_widget_opener(None)


# TODO da4f9c0: the edit-handler/built-in-editor/scratch fallback logic
# these three tests originally exercised directly through _open_file
# was extracted into the shared DeskWindow.open_editor_or_scrap
# service (see verify_viewer_widgets_edit_button.py for its own direct
# coverage) -- _open_file now just delegates to
# current_context.get_editor_or_scrap_opener() for the "no view
# handler" case, so these now confirm the delegation happens with the
# right path, not the fallback logic itself (which moved elsewhere).


def test_no_view_handler_delegates_to_shared_editor_or_scrap_hook():
    widget = _make_explorer([])
    from desk.shell import current_context

    # _open_file's very first check is get_centered_widget_opener() --
    # needs to be non-None to reach the view-handler lookup at all
    # (which then falls through to the editor_or_scrap delegation
    # below, since the registry here has no view handler to find).
    current_context.set_centered_widget_opener(_FakeCenteredOpener())
    delegated_calls = []
    current_context.set_editor_or_scrap_opener(lambda path: delegated_calls.append(path))
    try:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.dat"
            path.write_bytes(b"\x00\x01")
            widget._open_file(path)
        check("no view handler: delegates to the shared editor-or-scrap hook", delegated_calls == [path])
    finally:
        current_context.set_centered_widget_opener(None)
        current_context.set_editor_or_scrap_opener(None)


def test_no_view_handler_and_no_shared_hook_registered_is_a_noop():
    widget = _make_explorer([])
    from desk.shell import current_context

    current_context.set_centered_widget_opener(_FakeCenteredOpener())
    current_context.set_editor_or_scrap_opener(None)
    try:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.dat"
            path.write_bytes(b"\x00\x01")
            try:
                widget._open_file(path)
                check("no shared hook registered: no raise", True)
            except Exception as e:  # noqa: BLE001
                check(f"no shared hook registered: no raise (raised {e!r})", False)
    finally:
        current_context.set_centered_widget_opener(None)


def test_broken_set_file_does_not_raise():
    # Exercises _open_in_widget's own set_file call (the "view handler
    # found" path _open_file still handles directly) -- the edit/text
    # -editor/scratch fallback's own broken-set_file safety now lives
    # in DeskWindow.open_editor_or_scrap instead (TODO da4f9c0).
    class _BrokenWidget:
        def set_file(self, path):
            raise RuntimeError("boom")

    widget = _make_explorer([{"extensions": [".txt"], "mime_types": [], "handlers": [{"widget_id": "text_viewer", "role": "view"}]}])
    opener = _FakeCenteredOpener()
    opener.widgets_by_id["text_viewer"] = _BrokenWidget()
    from desk.shell import current_context

    current_context.set_centered_widget_opener(opener)
    try:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.txt"
            path.write_text("hello")
            try:
                widget._open_file(path)
                check("broken set_file does not raise out of _open_file", True)
            except Exception as e:  # noqa: BLE001
                check(f"broken set_file does not raise out of _open_file (raised {e!r})", False)
    finally:
        current_context.set_centered_widget_opener(None)


test_find_view_handler_registry_match_by_extension()
test_find_view_handler_registry_match_by_mime()
test_find_view_handler_builtin_fallback()
test_find_edit_handler_has_no_builtin_fallback()
test_looks_like_text_file()
test_open_widget_content_centered_computes_scene_center()
test_open_widget_content_centered_unknown_widget_id_is_noop()
test_registered_view_handler_opens_that_widget()
test_no_view_handler_delegates_to_shared_editor_or_scrap_hook()
test_no_view_handler_and_no_shared_hook_registered_is_a_noop()
test_broken_set_file_does_not_raise()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
