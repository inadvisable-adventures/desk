# TODO 83427f4: a kind:"html" widget learns which file it was opened
# for, via desk.self.getOpenedFile() (backed by DeskWindow
# ._html_widget_opened_file, set by open_widget_content's new path=
# parameter) -- the same information a built-in kind:"python" viewer
# already gets via its own set_file(path) Python method, which a
# ChromiumWidget has no equivalent of.
import base64
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.schema_registry import SchemaRegistry  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.shell.promoted_widget_source_watcher import PromotedWidgetSourceWatcher  # noqa: E402
from desk.temp_ui import CustomWidgetDefinition  # noqa: E402
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


SAMPLE_HTML_B64 = base64.b64encode(b"<html><body>Hi</body></html>").decode()


def _definition(keyword="PdfViewer", label="PDF Viewer"):
    return CustomWidgetDefinition(keyword=keyword, label=label, html_b64=SAMPLE_HTML_B64, default_size=(600, 400))


def _python_widget_info(directory, widget_id="ordinary_python"):
    return WidgetInfo(
        id=widget_id, path=directory, kind="python", name="Ordinary",
        entry="widget.py", capabilities=[], default_size=None,
    )


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
        self._promoted_widget_source_watcher = PromotedWidgetSourceWatcher()
        self._promoted_widget_source_dirty = set()
        self._html_widget_local_storage = {}
        self._html_widget_opened_file = {}
        self._schema_registry = SchemaRegistry()


_FakeWindow._register_custom_widget = DeskWindow._register_custom_widget
_FakeWindow._refresh_stale_indicators_for = DeskWindow._refresh_stale_indicators_for
_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._check_schema_conflict = DeskWindow._check_schema_conflict
_FakeWindow._is_instance_currently_placed = DeskWindow._is_instance_currently_placed
_FakeWindow._notify_schema_conflict = DeskWindow._notify_schema_conflict
_FakeWindow._show_schema_conflict_popup = DeskWindow._show_schema_conflict_popup
_FakeWindow.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id
_FakeWindow._chromium_profile_dir = DeskWindow._chromium_profile_dir
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._bind_error_indicator = DeskWindow._bind_error_indicator
_FakeWindow.open_widget = DeskWindow.open_widget
_FakeWindow.open_widget_content = DeskWindow.open_widget_content
_FakeWindow.open_widget_content_centered = DeskWindow.open_widget_content_centered
_FakeWindow.get_opened_file_for_instance = DeskWindow.get_opened_file_for_instance


def test_html_widget_records_opened_file():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(), source="tempui")
        path = Path(d) / "doc.pdf"

        content = win.open_widget_content("PdfViewer", pos=(0, 0), path=path)

        check("open_widget_content still returns None for a kind:'html' widget (unchanged contract)", content is None)
        frame = next(iter(win.view._frames))
        check("the placed instance's opened file was recorded", win.get_opened_file_for_instance(frame.instance_id) == str(path))


def test_html_widget_via_centered_variant():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(), source="tempui")
        path = Path(d) / "doc.pdf"

        win.open_widget_content_centered("PdfViewer", path=path)

        frame = next(iter(win.view._frames))
        check("open_widget_content_centered's own path= reaches the same place", win.get_opened_file_for_instance(frame.instance_id) == str(path))


def test_no_path_given_records_nothing():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(), source="tempui")

        win.open_widget_content("PdfViewer", pos=(0, 0))

        frame = next(iter(win.view._frames))
        check("no path given: opened file is not set at all", win.get_opened_file_for_instance(frame.instance_id) is None)


def test_unknown_instance_returns_none():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        check("an instance that was never opened for a file returns None, not KeyError", win.get_opened_file_for_instance("no-such-instance") is None)


_SET_FILE_WIDGET_BODY = """
from PyQt6.QtWidgets import QLabel

class _Widget(QLabel):
    def __init__(self):
        super().__init__("hi")
        self.set_file_calls = []

    def set_file(self, path):
        self.set_file_calls.append(str(path))

def build():
    return _Widget()
"""

_BROKEN_SET_FILE_WIDGET_BODY = """
from PyQt6.QtWidgets import QLabel

class _Widget(QLabel):
    def set_file(self, path):
        raise RuntimeError("boom")

def build():
    return _Widget()
"""

_NO_SET_FILE_WIDGET_BODY = """
from PyQt6.QtWidgets import QLabel

def build():
    return QLabel("no set_file here")
"""


def _place_real_python_widget(win, directory, body, widget_id="ordinary_python"):
    """Real widget.py content built by PythonWidgetHost itself (the
    same file-on-disk shape verify_desk_proc_screenshot.py's own
    _write_widget_py uses) -- open_widget_content's own path= handling
    for a kind:'python' widget needs a genuinely-built content object
    to call set_file on, not a fake swapped in after the fact (calling
    open_widget_content a second time against an already-placed
    instance_id would place a second, conflicting frame instead of
    reusing the first)."""
    (directory / "widget.py").write_text(body)
    info = _python_widget_info(directory, widget_id)
    win._widgets[widget_id] = info
    return win.open_widget_content(widget_id, pos=(0, 0), path=directory / "doc.txt")


def test_python_widget_still_calls_set_file():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        path = directory / "doc.txt"
        content = _place_real_python_widget(win, directory, _SET_FILE_WIDGET_BODY)

        check("kind:'python' widget: open_widget_content still returns the built content object", content is not None)
        check("kind:'python' widget: set_file was called with the given path (unchanged from before this TODO)", content.set_file_calls == [str(path)])
        frame = next(iter(win.view._frames))
        check("kind:'python' widget: nothing recorded in the html-only opened-file dict", win.get_opened_file_for_instance(frame.instance_id) is None)


def test_broken_set_file_does_not_propagate():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        try:
            _place_real_python_widget(win, directory, _BROKEN_SET_FILE_WIDGET_BODY)
            check("a broken set_file() does not propagate out of open_widget_content", True)
        except Exception as e:  # noqa: BLE001
            check(f"a broken set_file() does not propagate out of open_widget_content (raised {e!r})", False)


def test_python_widget_with_no_set_file_is_a_noop():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        content = _place_real_python_widget(win, directory, _NO_SET_FILE_WIDGET_BODY)
        check("a python widget with no set_file at all: no crash, content still returned", content is not None)


def test_omitting_path_reproduces_existing_callers_unchanged():
    # Regression: every existing open_widget_content/_centered call site
    # (README seeding, drag-and-drop, tempui binding) never passes path
    # at all -- confirms the new parameter is purely additive.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(), source="tempui")
        result_no_kw = win.open_widget_content("PdfViewer", pos=(10, 10))
        frame1 = next(f for f in win.view._frames if f.content.widget_id == "PdfViewer")
        check("omitting path entirely: still places the widget, returns None for html (unchanged)", result_no_kw is None)
        check("omitting path entirely: nothing recorded", win.get_opened_file_for_instance(frame1.instance_id) is None)


test_html_widget_records_opened_file()
test_html_widget_via_centered_variant()
test_no_path_given_records_nothing()
test_unknown_instance_returns_none()
test_python_widget_still_calls_set_file()
test_broken_set_file_does_not_propagate()
test_python_widget_with_no_set_file_is_a_noop()
test_omitting_path_reproduces_existing_callers_unchanged()


def test_changelog_and_doc_cover_this():
    from desk.temp_ui import CURRENT_TAGS, _CUSTOM_WIDGETS_DOC, _NEW_FEATURES

    tag = "self.getOpenedFile for html widgets #003325"
    check("tag is in CURRENT_TAGS with a _NEW_FEATURES entry", tag in CURRENT_TAGS and tag in _NEW_FEATURES)
    check("tempui-custom-widgets.md documents self.getOpenedFile", "desk.self.getOpenedFile()" in _CUSTOM_WIDGETS_DOC)


test_changelog_and_doc_cover_this()

# Same os._exit() ending as verify_relocate_promoted_widget_source.py's
# own sibling scripts (see LEARNINGS.md's TODO a5f66cc entry): real
# ChromiumWidget instances (placed for the html-widget tests above) can
# segfault tearing down QWebEngine profiles/pages at normal interpreter
# shutdown, after every check here has already run and printed.
print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
