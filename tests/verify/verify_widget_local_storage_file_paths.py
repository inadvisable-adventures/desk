import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.persisted_path import resolve_persisted_path  # noqa: E402


def load_widget_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


markdown_old_basic_mod = load_widget_module(
    "markdown_old_basic_widget", "widgets/markdown_old_basic/widget.py"
)
markdown_mod = load_widget_module("markdown_widget_mod", "widgets/markdown/widget.py")
editor_mod = load_widget_module("editor_widget_mod", "widgets/editor/widget.py")


def test_resolve_persisted_path():
    assert resolve_persisted_path(None) is None
    assert resolve_persisted_path("") is None
    assert resolve_persisted_path("/definitely/does/not/exist.md") is None
    with tempfile.TemporaryDirectory() as d:
        real = Path(d) / "real.md"
        real.write_text("hi")
        assert resolve_persisted_path(str(real)) == real
    print("resolve_persisted_path: PASS")


def test_markdown_old_basic_round_trip():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "notes.md"
        path.write_text("# Hello")
        widget = markdown_old_basic_mod.MarkdownWidget()
        widget.set_file(path)
        data = widget.get_widget_local_storage()
        assert data == {"path": str(path)}, data

        fresh = markdown_old_basic_mod.MarkdownWidget()
        fresh.set_widget_local_storage(data)
        assert fresh._current_path == path

        missing = markdown_old_basic_mod.MarkdownWidget()
        missing.set_widget_local_storage({"path": str(Path(d) / "gone.md")})
        assert missing._current_path is None
    print("markdown_old_basic widget-local storage round-trip + missing-file recovery: PASS")


def test_editor_round_trip():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "script.py"
        path.write_text("print('hi')")
        widget = editor_mod.EditorWidget()
        widget.set_file(path)
        data = widget.get_widget_local_storage()
        assert data == {"path": str(path)}, data

        fresh = editor_mod.EditorWidget()
        fresh.set_widget_local_storage(data)
        assert fresh._current_path == path
        assert fresh.editor.text() == "print('hi')"

        missing = editor_mod.EditorWidget()
        missing.set_widget_local_storage({"path": str(Path(d) / "gone.py")})
        assert missing._current_path is None
    print("editor widget-local storage round-trip + missing-file recovery: PASS")


def test_markdown_ex_round_trip_and_tempui_not_persisted():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "doc.md"
        path.write_text("# Doc\n\nSome text.")
        widget = markdown_mod.MarkdownWidget()
        widget.set_file(path)
        data = widget.get_widget_local_storage()
        assert data == {"path": str(path)}, data

        fresh = markdown_mod.MarkdownWidget()
        fresh.set_widget_local_storage(data)
        assert fresh._current_path == path

        missing = markdown_mod.MarkdownWidget()
        missing.set_widget_local_storage({"path": str(Path(d) / "gone.md")})
        assert missing._current_path is None

        tempui_widget = markdown_mod.MarkdownWidget()
        tempui_widget.set_tempui_content("My Doc", "# My Doc\n\nContent.")
        assert tempui_widget.get_widget_local_storage() == {}
    print("markdown (TOC/Mermaid) widget-local storage round-trip + tempui-bound not persisted: PASS")


test_resolve_persisted_path()
test_markdown_old_basic_round_trip()
test_editor_round_trip()
test_markdown_ex_round_trip_and_tempui_not_persisted()
print("ALL PASS")
