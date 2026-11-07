import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.window import DeskWindow  # noqa: E402
from desk.widgets import discover_widgets  # noqa: E402
from desk.shell.widget_spawn_menu import WidgetSpawnMenu  # noqa: E402
from desk.temp_ui import detect_temp_ui_kind  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


def test_discover_widgets_reflects_rename():
    widgets = discover_widgets(Path("widgets"))
    assert "markdown_ex" not in widgets
    assert "markdown_old_basic" not in widgets  # removed, TODO 5a1b231

    assert "markdown" in widgets
    new = widgets["markdown"]
    assert new.deprecated is False
    assert new.name == "Markdown"
    print("discover_widgets reflects the rename correctly: PASS")


def test_spawn_menu_lists_markdown_only():
    widgets = discover_widgets(Path("widgets"))
    menu = WidgetSpawnMenu(widgets)
    active = menu._group_items["Active"]
    active_names = {active.child(i).text(0) for i in range(active.childCount())}
    assert "Markdown" in active_names, active_names
    assert "Markdown (Old, Basic)" not in active_names
    menu.close()
    print("real WidgetSpawnMenu lists Markdown and no longer the old basic widget: PASS")


def test_temp_ui_widget_id_for_open_markdown():
    import tempfile
    import types

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "abc"
        path.write_text("OpenMarkdown ./notes.md\n")
        # Minimal stand-in for `self`: the real method only reads
        # self._custom_widget_definitions (TODO 91b3f42), nothing else.
        fake_self = types.SimpleNamespace(_custom_widget_definitions={})
        widget_id = DeskWindow._temp_ui_widget_id_for(fake_self, path)
        assert widget_id == "markdown", widget_id
    print("_temp_ui_widget_id_for still resolves OpenMarkdown to the renamed 'markdown' id: PASS")


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_markdown_widget_still_builds():
    new_mod = load_widget_module("new_markdown_mod", "widgets/markdown/widget.py")
    w1 = new_mod.build()
    assert type(w1).__name__ == "MarkdownWidget"
    print("markdown widget still build()s successfully: PASS")


test_discover_widgets_reflects_rename()
test_spawn_menu_lists_markdown_only()
test_temp_ui_widget_id_for_open_markdown()
test_markdown_widget_still_builds()
print("ALL PASS")
