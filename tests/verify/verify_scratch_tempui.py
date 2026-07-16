import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "widgets/scratch")

# Import desk.shell.window (pulls in QtWebEngineWidgets via desk.shell.canvas)
# BEFORE constructing any QApplication.
from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import detect_temp_ui_kind, parse_scratch  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import widget as scratch_mod  # noqa: E402


def test_detect_and_parse():
    text = "Scratch Investigation notes\nFound the bug in file_watch.py.\nStill need to check.\n"
    assert detect_temp_ui_kind(text) == "scratch"
    label, body = parse_scratch(text)
    assert label == "Investigation notes", label
    assert body == "Found the bug in file_watch.py.\nStill need to check.", repr(body)
    print("detect + parse_scratch basic: PASS")


def test_parse_scratch_no_label():
    label, body = parse_scratch("Scratch\nJust body, no label.\n")
    assert label == ""
    assert body == "Just body, no label."
    print("parse_scratch with empty label: PASS")


def test_parse_scratch_not_scratch():
    assert parse_scratch("Question something\n") is None
    assert parse_scratch("") is None
    print("parse_scratch returns None for non-scratch text: PASS")


def test_other_kinds_unaffected():
    assert detect_temp_ui_kind("Question hi\nOption A\n") == "question"
    assert detect_temp_ui_kind("LightningRound\tname\tprompt\n") == "lightning_round"
    assert detect_temp_ui_kind("OpenMarkdown ./x.md\n") == "open_markdown"
    print("other tempui kinds unaffected: PASS")


def test_temp_ui_widget_id_for_real_method():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "abc"
        path.write_text("Scratch My Notes\nbody\n")
        # Unbound call against a minimal stand-in for `self`: the real
        # method only reads self._custom_widget_definitions (TODO
        # 91b3f42), nothing else, so this exercises it without
        # constructing a full DeskWindow (which needs a
        # ServerHandle/HotReloadBroker/widget catalog).
        import types

        fake_self = types.SimpleNamespace(_custom_widget_definitions={})
        widget_id = DeskWindow._temp_ui_widget_id_for(fake_self, path)
        assert widget_id == "scratch", widget_id
    print("DeskWindow._temp_ui_widget_id_for real method: PASS")


def test_bind_temp_ui_content_real_method():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        tempui_path = directory / "abc"
        tempui_path.write_text("Scratch My Notes\nline one\nline two\n")

        scratch = scratch_mod.build()
        DeskWindow._bind_temp_ui_content(None, scratch, tempui_path, directory)

        assert scratch.label_text == "My Notes"
        assert scratch.body.toPlainText() == "line one\nline two"
    print("DeskWindow._bind_temp_ui_content real method: PASS")


def test_notify_text_real_method():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "abc"
        path.write_text("Scratch My Notes\nbody\n")
        content_text = path.read_text()
        kind = detect_temp_ui_kind(content_text)
        assert kind == "scratch"
        parsed = parse_scratch(content_text)
        assert parsed[0] == "My Notes"
    print("notify-text derivation inputs correct: PASS")


test_detect_and_parse()
test_parse_scratch_no_label()
test_parse_scratch_not_scratch()
test_other_kinds_unaffected()
test_temp_ui_widget_id_for_real_method()
test_bind_temp_ui_content_real_method()
test_notify_text_real_method()
print("ALL PASS")
