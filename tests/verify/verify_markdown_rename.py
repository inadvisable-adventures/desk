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
    assert "markdown_old_basic" in widgets
    old = widgets["markdown_old_basic"]
    assert old.deprecated is True
    assert old.name == "Markdown (Old, Basic)"

    assert "markdown" in widgets
    new = widgets["markdown"]
    assert new.deprecated is False
    assert new.name == "Markdown"
    print("discover_widgets reflects the rename correctly: PASS")


def test_spawn_menu_groups_reflect_deprecation():
    widgets = discover_widgets(Path("widgets"))
    menu = WidgetSpawnMenu(widgets)
    active_names = {menu._group_items["Active"].child(i).text(0) for i in range(menu._group_items["Active"].childCount())}
    deprecated_names = {
        menu._group_items["Deprecated"].child(i).text(0)
        for i in range(menu._group_items["Deprecated"].childCount())
    }
    assert "Markdown (Old, Basic)" in deprecated_names, deprecated_names
    assert "Markdown" in active_names, active_names
    assert menu._group_items["Deprecated"].isExpanded() is False
    menu.close()
    print("real WidgetSpawnMenu shows the deprecated widget in the collapsed Deprecated group: PASS")


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


def test_both_widgets_still_build():
    new_mod = load_widget_module("new_markdown_mod", "widgets/markdown/widget.py")
    w1 = new_mod.build()
    assert type(w1).__name__ == "MarkdownWidget"

    old_mod = load_widget_module("old_markdown_mod", "widgets/markdown_old_basic/widget.py")
    w2 = old_mod.build()
    assert type(w2).__name__ == "MarkdownWidget"
    print("both renamed widgets still build() successfully: PASS")


test_discover_widgets_reflects_rename()
test_spawn_menu_groups_reflect_deprecation()
test_temp_ui_widget_id_for_open_markdown()
test_both_widgets_still_build()
print("ALL PASS")
