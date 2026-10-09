"""TODO f9e24e0: OpenWithWidget optional label field (see plans/open-with-widget-label.md)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

import desk.shell.widget_frame  # noqa: E402,F401
from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    CURRENT_TAGS, SPLIT_DOC_CONTENT, _NEW_FEATURES, detect_temp_ui_kind, parse_open_with_widget,
    parse_open_with_widget_label,
)
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


three = "OpenWithWidget\tsheet\t./a b.tsv\n"
four = "OpenWithWidget\thmsvc_manager\t/x/p.desk\tNew microservice\n"
check("three-field file still parses", parse_open_with_widget(three) == ("sheet", "./a b.tsv"))
check("three-field file has no label", parse_open_with_widget_label(three) is None)
check("four-field file parses as before", parse_open_with_widget(four) == ("hmsvc_manager", "/x/p.desk"))
check("label is read", parse_open_with_widget_label(four) == "New microservice")
check("blank label is None", parse_open_with_widget_label("OpenWithWidget\tw\tp\t  \n") is None)
check("non-OpenWithWidget file has no label", parse_open_with_widget_label("Scratch hi\n") is None)
check("kind detection unchanged", detect_temp_ui_kind(four) == "open_with_widget:hmsvc_manager")


class FakeView:
    def __init__(self):
        self.notes = []

    def notify_temp_ui(self, path, text, cb, banner_style="default"):
        self.notes.append(text)


class FakeWin:
    _notify_temp_ui = DeskWindow._notify_temp_ui

    def __init__(self):
        self.view = FakeView()
        self._custom_widget_definitions = {}


with tempfile.TemporaryDirectory() as t:
    for name, content, expected in (
        ("plain", three, "Open ./a b.tsv"),
        ("labelled", four, "New microservice"),
    ):
        f = Path(t) / name
        f.write_text(content)
        win = FakeWin()
        win._notify_temp_ui(f)
        check(f"notification text ({name})", win.view.notes == [expected])

tag = next(t for t in CURRENT_TAGS if "OpenWithWidget optional label" in t)
check("changelog entry", tag in _NEW_FEATURES)
check("doc documents the label field", "path[<TAB>label]" in SPLIT_DOC_CONTENT["tempui-open-with-widget.md"])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
