import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
# TODO 78bfa41: canvas.py's own QWebEngineView import (previously used
# by the now-removed _scrollable_at) was the thing actually satisfying
# the "import WebEngine before QApplication" ordering requirement above
# -- import it explicitly instead of depending on that as an incidental
# side effect of an unrelated module.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    CUSTOM_WIDGETS_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
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


SAMPLE_HTML = "<html><body><h1>Kanban</h1></body></html>"
import base64  # noqa: E402

SAMPLE_HTML_B64 = base64.b64encode(SAMPLE_HTML.encode()).decode()


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


_FakeWindow._register_custom_widget = DeskWindow._register_custom_widget
_FakeWindow._refresh_stale_indicators_for = DeskWindow._refresh_stale_indicators_for
_FakeWindow._register_custom_widgets_from_desk_temp = DeskWindow._register_custom_widgets_from_desk_temp
_FakeWindow._handle_define_widget_file = DeskWindow._handle_define_widget_file
_FakeWindow._sync_tempui_doc = DeskWindow._sync_tempui_doc
_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator


def _write_define_widget_file(directory, keyword="KanbanBoard", label="Kanban Board"):
    import uuid as uuid_mod

    path = directory / str(uuid_mod.uuid4())
    path.write_text(f"DefineWidget\t{keyword}\t{label}\nSize\t600\t400\nHtml\t{SAMPLE_HTML_B64}\n")
    return path


def test_live_added_brand_new_keyword_places_nothing():
    # TODO dafbaab: reverts TODO 5ff02d2's auto-place-one-instance
    # behavior -- a brand-new keyword registered via the live-added
    # path now places zero instances, same as every other case below.
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        path = _write_define_widget_file(directory)
        handled = win._handle_define_widget_file(path)
        check("returns True for a DefineWidget file", handled is True)
        check("keyword registered", "KanbanBoard" in win._widgets)
        check("no instance auto-placed", len(win.view._frames) == 0)


def test_edit_of_already_known_keyword_places_nothing_new():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        path = _write_define_widget_file(directory)
        win._handle_define_widget_file(path)
        check("zero instances after initial add", len(win.view._frames) == 0)
        # Re-save (edit) the same file.
        path.write_text(f"DefineWidget\tKanbanBoard\tKanban Board (v2)\nSize\t600\t400\nHtml\t{SAMPLE_HTML_B64}\n")
        win._handle_define_widget_file(path)
        check("relabel took effect", win._widgets["KanbanBoard"].name == "Kanban Board (v2)")
        check("still no instance placed on edit", len(win.view._frames) == 0)


def test_startup_bulk_rescan_places_nothing():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        _write_define_widget_file(temp_dir)
        win._register_custom_widgets_from_desk_temp(directory)
        check("keyword registered by bulk rescan", "KanbanBoard" in win._widgets)
        check("bulk rescan places no instance at all", len(win.view._frames) == 0)


def test_failed_registration_places_nothing():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        # "Scratch" collides with a reserved built-in DSL keyword, so
        # _register_custom_widget refuses it.
        path = _write_define_widget_file(directory, keyword="Scratch", label="Sneaky")
        handled = win._handle_define_widget_file(path)
        check("still recognized as a DefineWidget file", handled is True)
        check("reserved keyword refused", "Scratch" not in win._widgets)
        check("nothing placed for a refused registration", len(win.view._frames) == 0)


def test_doc_callout_and_version():
    check("TEMPUI_DOC_VERSION bumped to at least 18", TEMPUI_DOC_VERSION >= 18)
    doc = SPLIT_DOC_CONTENT[CUSTOM_WIDGETS_DOC_FILENAME]
    check(
        "doc has the loud no-instance-placed callout",
        "only registers the new widget" in doc and "place an instance of it on the canvas" in doc,
    )
    check("doc no longer mentions auto-placing", "auto-places" not in doc and "auto -places" not in doc)


test_live_added_brand_new_keyword_places_nothing()
test_edit_of_already_known_keyword_places_nothing_new()
test_startup_bulk_rescan_places_nothing()
test_failed_registration_places_nothing()
test_doc_callout_and_version()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
