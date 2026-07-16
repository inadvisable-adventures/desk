# DISABLED (see tests/verify/README.md) -- TODO ba0bd9a tracks
# investigating this. Current failure: Fails with FileNotFoundError reading scripts/build_widget.py
# directly -- TODO 029047b deleted that file. This script was already
# flagged as expected-stale during that same TODO's own verification but
# never actually updated/removed. Reasonable suspicion: same category as
# disabled_verify_build_widget.py -- needs its assertion rewritten
# against the new .desk_temp/build_widget.py generated location, or
# removed if redundant with newer coverage.

import base64
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

from desk.desks import Desk  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    CUSTOM_WIDGET_SRC_DIRNAME,
    CUSTOM_WIDGETS_DOC_FILENAME,
    PROMOTED_WIDGET_SRC_DIRNAME,
    SPLIT_DOC_CONTENT,
    TEMP_UI_DIRNAME,
    TEMPUI_DOC_VERSION,
    CustomWidgetDefinition,
)

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


SAMPLE_HTML_B64 = base64.b64encode(b"<html><body>Hi</body></html>").decode()


def _definition(keyword="KanbanBoard", label="Kanban Board"):
    return CustomWidgetDefinition(keyword=keyword, label=label, html_b64=SAMPLE_HTML_B64, default_size=(600, 400))


class _FakeHandle:
    def __init__(self):
        self.widgets = {}
        self.mounted = []
        self.token = "tok"

    def widget_url(self, widget_id):
        return f"http://fake/{widget_id}"

    def mount_html_widget(self, widget_id, directory, info):
        self.widgets[widget_id] = info
        self.mounted.append((widget_id, directory))


class _FakeWindow:
    def __init__(self, directory):
        self.current_desk = Desk(path=directory / "test.desk")
        self._widgets = {}
        self._handle = _FakeHandle()
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self._broker = HotReloadBroker()
        self._event_mediator = None
        self._custom_widget_definitions = {}
        self._custom_widget_sources = {}
        self._custom_widget_source_paths = {}
        self._custom_widget_content_hash = {}
        self.saved = []
        self.confirmed_messages = []
        self.info_messages = []

    def _confirm_fn(self, title, message):
        def confirm():
            self.confirmed_messages.append((title, message))
            return True

        return confirm

    def _info(self, title, message):
        self.info_messages.append((title, message))

    def save_current_desk(self):
        self.saved.append(True)


_FakeWindow._register_custom_widget = DeskWindow._register_custom_widget
_FakeWindow._refresh_stale_indicators_for = DeskWindow._refresh_stale_indicators_for
_FakeWindow._on_tempui_promote_requested = DeskWindow._on_tempui_promote_requested
_FakeWindow._relocate_promoted_widget_source = DeskWindow._relocate_promoted_widget_source
_FakeWindow._sync_tempui_doc = DeskWindow._sync_tempui_doc
_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator


def _promote(win, keyword, tempui_path):
    definition = win._custom_widget_definitions[keyword]
    frame = win._place_widget(keyword, win._widgets[keyword], (0, 0), (400, 300), instance_id="abc12345")
    win._custom_widget_source_paths[keyword] = tempui_path
    win._on_tempui_promote_requested(frame)
    return definition


def test_source_directory_moved_on_promotion():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(), source="tempui")

        source_dir = directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / "KanbanBoard"
        source_dir.mkdir(parents=True)
        (source_dir / "widget.json").write_text("{}")
        (source_dir / "KanbanBoard.ts").write_text("// source")

        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        _promote(win, "KanbanBoard", tempui_path)

        destination_dir = directory / PROMOTED_WIDGET_SRC_DIRNAME / "KanbanBoard"
        check("source directory moved to desk_widgets/<keyword>/", destination_dir.is_dir())
        check("moved widget.json present", (destination_dir / "widget.json").is_file())
        check("moved .ts file present", (destination_dir / "KanbanBoard.ts").is_file())
        check("original .desk_temp/widgets/<keyword>/ is gone", not source_dir.exists())
        check("tempui invocation file removed", not tempui_path.exists())
        check("promotion still recorded in .desk file", any(cw.keyword == "KanbanBoard" for cw in win.current_desk.custom_widgets))


def test_no_source_directory_is_a_silent_noop():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(), source="tempui")
        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        _promote(win, "KanbanBoard", tempui_path)

        destination_dir = directory / PROMOTED_WIDGET_SRC_DIRNAME / "KanbanBoard"
        check("no source dir to move: no destination created", not destination_dir.exists())
        check("promotion still succeeded", any(cw.keyword == "KanbanBoard" for cw in win.current_desk.custom_widgets))


def test_preexisting_destination_is_not_clobbered():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(), source="tempui")

        source_dir = directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / "KanbanBoard"
        source_dir.mkdir(parents=True)
        (source_dir / "marker.txt").write_text("original source")

        destination_dir = directory / PROMOTED_WIDGET_SRC_DIRNAME / "KanbanBoard"
        destination_dir.mkdir(parents=True)
        (destination_dir / "marker.txt").write_text("pre-existing, unrelated content")

        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        _promote(win, "KanbanBoard", tempui_path)

        check("source dir left in place, not clobbered", source_dir.is_dir())
        check("pre-existing destination content untouched", (destination_dir / "marker.txt").read_text() == "pre-existing, unrelated content")
        check("promotion (the .desk file part) still succeeded despite the move being skipped", any(cw.keyword == "KanbanBoard" for cw in win.current_desk.custom_widgets))


def test_doc_content():
    check("TEMPUI_DOC_VERSION bumped to 14", TEMPUI_DOC_VERSION == 14)
    doc = SPLIT_DOC_CONTENT[CUSTOM_WIDGETS_DOC_FILENAME]
    check("doc recommends .desk_temp/widgets/<name>/", ".desk_temp/widgets/<name>/" in doc)
    check("custom_widget_src no longer mentioned", "custom_widget_src" not in doc)
    check("doc mentions desk_widgets/<name>/ post-promotion", "desk_widgets/<name>/" in doc)


def test_build_widget_script_docstring_updated():
    text = Path("/Users/mphair/inadvisable-adventures/desk/scripts/build_widget.py").read_text()
    check("build_widget.py docstring no longer hardcodes custom_widget_src", "custom_widget_src" not in text)
    check("build_widget.py docstring mentions .desk_temp/widgets", ".desk_temp/widgets/<name>" in text)
    check("build_widget.py docstring mentions desk_widgets", "desk_widgets/<name>" in text)


test_source_directory_moved_on_promotion()
test_no_source_directory_is_a_silent_noop()
test_preexisting_destination_is_not_clobbered()
test_doc_content()
test_build_widget_script_docstring_updated()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
