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

from desk.shell import current_context  # noqa: E402
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


# ---------- DeskWindow.open_editor_or_scrap ----------


class _FakeWindow:
    def __init__(self):
        self._widgets = {
            "editor": WidgetInfo(id="editor", path=Path("."), kind="python", name="Editor", entry="widget.py", capabilities=[], default_size=(400, 300)),
            "scratch": WidgetInfo(id="scratch", path=Path("."), kind="python", name="Scratch", entry="widget.py", capabilities=[], default_size=(400, 300)),
            "custom_editor": WidgetInfo(id="custom_editor", path=Path("."), kind="python", name="Custom", entry="widget.py", capabilities=[], default_size=(400, 300)),
        }
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self.opened = []

    def get_file_type_registry_dicts(self):
        return self._registry_dicts if hasattr(self, "_registry_dicts") else []

    def open_widget_content_centered(self, widget_id, size=None, instance_id=None):
        self.opened.append(widget_id)
        return self._contents.get(widget_id) if hasattr(self, "_contents") else None


_FakeWindow.open_editor_or_scrap = DeskWindow.open_editor_or_scrap


class _FakeSetFileWidget:
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


def test_open_editor_or_scrap_uses_registered_edit_handler():
    win = _FakeWindow()
    win._registry_dicts = [{"extensions": [".dat"], "mime_types": [], "handlers": [{"widget_id": "custom_editor", "role": "edit"}]}]
    custom = _FakeSetFileWidget()
    win._contents = {"custom_editor": custom}
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "a.dat"
        path.write_bytes(b"\x00\x01")
        win.open_editor_or_scrap(path)
    check("registered edit handler opened", win.opened == ["custom_editor"])
    check("set_file called on it", custom.set_file_calls == [path])


def test_open_editor_or_scrap_falls_back_to_editor_for_text():
    win = _FakeWindow()
    editor = _FakeSetFileWidget()
    win._contents = {"editor": editor}
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "Dockerfile"
        path.write_text("FROM python:3.13\n")
        win.open_editor_or_scrap(path)
    check("no registry match, real text file: built-in editor opened", win.opened == ["editor"])
    check("set_file called on the editor", editor.set_file_calls == [path])


def test_open_editor_or_scrap_falls_back_to_scratch_for_binary():
    win = _FakeWindow()
    scratch = _FakeScratchWidget()
    win._contents = {"scratch": scratch}
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "a.bin"
        path.write_bytes(b"\x00\x01\x02\xff")
        win.open_editor_or_scrap(path)
    check("no registry match, binary file: scratch fallback opened", win.opened == ["scratch"])
    check("scratch labeled with file name", scratch.label == "Can't open a.bin")
    check("scratch body explains why", "No editor is registered" in scratch.body.text)


# ---------- ProjectFilesWidget delegates its edit-or-scrap step ----------


project_files_mod = load_widget_module(
    "project_files_edit_button_verify_mod", "/Users/mphair/inadvisable-adventures/desk/widgets/project_files/widget.py"
)


def test_project_files_delegates_to_shared_editor_or_scrap_hook():
    current_context.set_current_desk_directory(None)
    current_context.set_file_type_registry_provider(lambda: [])
    try:
        widget = project_files_mod.build()
        opener_calls = []
        current_context.set_editor_or_scrap_opener(lambda path: opener_calls.append(path))
        centered_calls = []
        current_context.set_centered_widget_opener(lambda widget_id: centered_calls.append(widget_id) or None)
        try:
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / "a.bin"
                path.write_bytes(b"\x00\x01")
                widget._open_file(path)
            check("no view handler: delegates to the shared editor-or-scrap hook", opener_calls == [path])
            check("centered opener never asked for a view widget (no registry match)", centered_calls == [])
        finally:
            current_context.set_editor_or_scrap_opener(None)
            current_context.set_centered_widget_opener(None)
    finally:
        current_context.set_current_desk_directory(None)
        current_context.set_file_type_registry_provider(lambda: [])


# ---------- Each viewer widget's own Edit button ----------


def _load_viewer(widget_name):
    return load_widget_module(
        f"{widget_name}_edit_button_verify_mod",
        f"/Users/mphair/inadvisable-adventures/desk/widgets/{widget_name}/widget.py",
    )


def _check_viewer_edit_button(widget_name, sample_path):
    mod = _load_viewer(widget_name)
    widget = mod.build()
    check(f"{widget_name}: Edit button disabled with no file loaded", widget._edit_button.isEnabled() is False)

    widget.set_file(sample_path)
    check(f"{widget_name}: Edit button enabled after set_file", widget._edit_button.isEnabled() is True)

    calls = []
    current_context.set_editor_or_scrap_opener(lambda path: calls.append(path))
    try:
        widget._edit_button.click()
        check(f"{widget_name}: clicking Edit calls the shared opener with the current path", calls == [sample_path])
    finally:
        current_context.set_editor_or_scrap_opener(None)


with tempfile.TemporaryDirectory() as d:
    # svg_viewer was retired and folded into image_viewer (TODO 4d21e7c) --
    # the image_viewer check right below already covers its Edit button
    # via a raster fixture; the SVG-specific rendering path itself is
    # covered separately, by verify_image_viewer_svg_integration.py.
    png_path = Path(d) / "a.png"
    png_path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
            "de0000000c4944415478da6360606060000000050001a5f645400000000049454e44ae426082"
        )
    )
    _check_viewer_edit_button("image_viewer", png_path)

    md_path = Path(d) / "a.md"
    md_path.write_text("# Hello\n")
    _check_viewer_edit_button("markdown", md_path)


def test_markdown_edit_button_disabled_when_tempui_bound():
    mod = _load_viewer("markdown")
    widget = mod.build()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "a.md"
        path.write_text("# Hi\n")
        widget.set_file(path)
        check("markdown: enabled after set_file", widget._edit_button.isEnabled() is True)
        widget.set_tempui_content("label", "# Tempui content\n")
        check("markdown: disabled again once tempui-bound", widget._edit_button.isEnabled() is False)


test_markdown_edit_button_disabled_when_tempui_bound()
test_open_editor_or_scrap_uses_registered_edit_handler()
test_open_editor_or_scrap_falls_back_to_editor_for_text()
test_open_editor_or_scrap_falls_back_to_scratch_for_binary()
test_project_files_delegates_to_shared_editor_or_scrap_hook()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
