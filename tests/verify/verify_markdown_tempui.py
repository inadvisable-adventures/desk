import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import detect_temp_ui_kind, parse_markdown_tempui  # noqa: E402
from desk.shell import current_context  # noqa: E402

from PyQt6.QtWidgets import QApplication, QFileDialog  # noqa: E402

app = QApplication(sys.argv)


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


md_mod = load_widget_module("markdown_tempui_mod", "widgets/markdown/widget.py")


def test_detect_and_parse():
    text = "Markdown Investigation summary\n# Investigation summary\n\nFound the bug.\n"
    assert detect_temp_ui_kind(text) == "markdown_content"
    label, content = parse_markdown_tempui(text)
    assert label == "Investigation summary"
    assert content == "# Investigation summary\n\nFound the bug.", repr(content)
    print("detect + parse_markdown_tempui: PASS")


def test_slugify():
    assert md_mod._slugify("# My Investigation Notes") == "my-investigation-notes"
    assert md_mod._slugify("###   Weird!!  Punctuation???") == "weird-punctuation"
    assert md_mod._slugify("") == "untitled"
    assert md_mod._slugify("###") == "untitled"
    print("_slugify: PASS")


def test_temp_ui_widget_id_for_markdown_content():
    import types

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "abc"
        path.write_text("Markdown My notes\ncontent\n")
        # Minimal stand-in for `self`: the real method only reads
        # self._custom_widget_definitions (TODO 91b3f42), nothing else.
        fake_self = types.SimpleNamespace(_custom_widget_definitions={})
        widget_id = DeskWindow._temp_ui_widget_id_for(fake_self, path)
        assert widget_id == "markdown", widget_id
    print("_temp_ui_widget_id_for resolves markdown_content to 'markdown': PASS")


def test_bind_temp_ui_content_markdown():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        tempui_path = directory / "abc"
        tempui_path.write_text("Markdown My Notes\n# My Notes\n\nSome content.\n")

        widget = md_mod.build()
        DeskWindow._bind_temp_ui_content(None, widget, tempui_path, directory)

        assert widget._tempui_bound is True
        assert widget._tempui_content == "# My Notes\n\nSome content."
        assert widget._label.text() == "My Notes"
        assert widget._open_button.text() == "Save As"
    print("DeskWindow._bind_temp_ui_content wires set_tempui_content correctly: PASS")


def test_set_tempui_content_renders_and_switches_button():
    widget = md_mod.build()
    widget.set_tempui_content("Label here", "# Heading\n\nBody text.")
    assert widget._open_button.text() == "Save As"
    assert widget._current_path is None
    # Rendered into the TOC (at least one top-level heading).
    assert widget._toc.topLevelItemCount() >= 1
    print("set_tempui_content renders content and switches Open -> Save As: PASS")


def test_save_as_writes_file_and_opens_new_instance():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)

        widget = md_mod.build()
        widget.set_tempui_content("Label", "# My Investigation Notes\n\nFound it.")

        opened = []

        def fake_opener(widget_id):
            assert widget_id == "markdown"
            new_widget = md_mod.build()
            opened.append(new_widget)
            return new_widget

        current_context.set_widget_opener(fake_opener)

        default_target = directory / "my-investigation-notes.md"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(default_target), "")):
            widget._save_as()

        assert default_target.is_file()
        assert default_target.read_text() == "# My Investigation Notes\n\nFound it."
        assert len(opened) == 1
        assert opened[0]._current_path == default_target
        # Original tempui-bound instance is untouched.
        assert widget._tempui_bound is True
        assert widget._open_button.text() == "Save As"
        current_context.set_widget_opener(None)
    print("Save As writes the file, opens a new instance, leaves the original tempui widget open: PASS")


def test_notify_text_for_markdown_content():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "abc"
        path.write_text("Markdown My Label\ncontent\n")
        content_text = path.read_text()
        kind = detect_temp_ui_kind(content_text)
        assert kind == "markdown_content"
        parsed = parse_markdown_tempui(content_text)
        assert parsed[0] == "My Label"
    print("notify-text derivation inputs correct: PASS")


test_detect_and_parse()
test_slugify()
test_temp_ui_widget_id_for_markdown_content()
test_bind_temp_ui_content_markdown()
test_set_tempui_content_renders_and_switches_button()
test_save_as_writes_file_and_opens_new_instance()
test_notify_text_for_markdown_content()
print("ALL PASS")
