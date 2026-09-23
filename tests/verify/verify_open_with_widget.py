# TODO 3b6de01: the generic OpenWithWidget<TAB>widget_id<TAB>path tempui
# keyword places any widget kind with a file pre-loaded -- set_file for
# kind:"python" (e.g. Sheet, TODO 5928ae6), self.getOpenedFile for
# kind:"html" (TODO 83427f4). Covers both fresh placement
# (_activate_temp_ui) and Desk-reload restore (_bind_temp_ui_widget),
# since the two use genuinely different code paths for a kind:"html"
# instance (open_widget_content's own path= vs. a new dedicated branch).
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
from desk.temp_ui import (  # noqa: E402
    CustomWidgetDefinition,
    OPEN_WITH_WIDGET_KEYWORD,
    RESERVED_TEMPUI_KEYWORDS,
    detect_temp_ui_kind,
    parse_open_with_widget,
)
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


def _custom_definition(keyword="PdfViewer", label="PDF Viewer"):
    return CustomWidgetDefinition(keyword=keyword, label=label, html_b64=SAMPLE_HTML_B64, default_size=(600, 400))


def _python_widget_info(directory, widget_id="ordinary_python"):
    return WidgetInfo(
        id=widget_id, path=directory, kind="python", name="Ordinary",
        entry="widget.py", capabilities=[], default_size=(400, 300),
    )


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
_FakeWindow.get_opened_file_for_instance = DeskWindow.get_opened_file_for_instance
_FakeWindow._temp_ui_widget_id_for = DeskWindow._temp_ui_widget_id_for
_FakeWindow._activate_temp_ui = DeskWindow._activate_temp_ui
_FakeWindow._bind_temp_ui_widget = DeskWindow._bind_temp_ui_widget
_FakeWindow._bind_temp_ui_content = DeskWindow._bind_temp_ui_content
_FakeWindow._resolve_open_with_widget_target = staticmethod(DeskWindow._resolve_open_with_widget_target)


def _write_open_with_widget_file(directory, uuid_str, widget_id, raw_path):
    tempui_dir = directory / ".desk_temp"
    tempui_dir.mkdir(parents=True, exist_ok=True)
    path = tempui_dir / uuid_str
    path.write_text(f"{OPEN_WITH_WIDGET_KEYWORD}\t{widget_id}\t{raw_path}\n")
    return path


# ---------- pure parsing/detection --------------------------------------


def test_parse_round_trips_widget_id_and_path():
    check("parses widget_id and path", parse_open_with_widget("OpenWithWidget\tsheet\t./a.tsv\n") == ("sheet", "./a.tsv"))


def test_parse_tolerates_spaces_in_the_path():
    check("a path containing spaces needs no escaping (the whole point of tab-separation)", parse_open_with_widget("OpenWithWidget\tsheet\t./my results.tsv\n") == ("sheet", "./my results.tsv"))


def test_parse_returns_none_for_missing_fields_or_wrong_keyword():
    check("missing path field: None", parse_open_with_widget("OpenWithWidget\tsheet\n") is None)
    check("missing everything: None", parse_open_with_widget("OpenWithWidget\n") is None)
    check("blank widget_id field: None", parse_open_with_widget("OpenWithWidget\t\t./a.tsv\n") is None)
    check("wrong keyword entirely: None", parse_open_with_widget("Scratch\thello\n") is None)


def test_detect_temp_ui_kind_shapes():
    check("well-formed: open_with_widget:<id>", detect_temp_ui_kind("OpenWithWidget\tsheet\t./a.tsv\n") == "open_with_widget:sheet")
    check("missing path: falls back to question, same tolerance an unrecognized keyword gets", detect_temp_ui_kind("OpenWithWidget\tsheet\n") == "question")
    check("OpenWithWidget is a reserved keyword a DefineWidget can't reuse", OPEN_WITH_WIDGET_KEYWORD in RESERVED_TEMPUI_KEYWORDS)


# ---------- fresh placement (_activate_temp_ui) --------------------------


def test_fresh_placement_targets_a_python_widget():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        (directory / "widget.py").write_text(_SET_FILE_WIDGET_BODY)
        win._widgets["sheet_like"] = _python_widget_info(directory, "sheet_like")
        target = directory / "data.tsv"
        target.write_text("a\tb\n")
        uuid_str = "instance-py-1"
        tempui_path = _write_open_with_widget_file(directory, uuid_str, "sheet_like", str(target))

        win._activate_temp_ui(tempui_path)

        frame = win.find_frame_by_instance_id(uuid_str)
        check("a real frame was placed", frame is not None)
        check("set_file was called on the newly-built content with the resolved path", frame.content.current.set_file_calls == [str(target)])


def test_fresh_placement_targets_an_html_widget():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_custom_definition(), source="tempui")
        target = directory / "doc.pdf"
        uuid_str = "instance-html-1"
        tempui_path = _write_open_with_widget_file(directory, uuid_str, "PdfViewer", str(target))

        win._activate_temp_ui(tempui_path)

        frame = win.find_frame_by_instance_id(uuid_str)
        check("a real ChromiumWidget-backed frame was placed", frame is not None)
        check("the opened file was recorded for self.getOpenedFile()", win.get_opened_file_for_instance(uuid_str) == str(target))


def test_fresh_placement_relative_path_resolves_against_desk_directory():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        (directory / "widget.py").write_text(_SET_FILE_WIDGET_BODY)
        win._widgets["sheet_like"] = _python_widget_info(directory, "sheet_like")
        (directory / "sub").mkdir()
        (directory / "sub" / "data.tsv").write_text("x\n")
        uuid_str = "instance-rel-1"
        tempui_path = _write_open_with_widget_file(directory, uuid_str, "sheet_like", "sub/data.tsv")

        win._activate_temp_ui(tempui_path)

        frame = win.find_frame_by_instance_id(uuid_str)
        check("a relative path resolves against the current Desk's own directory", frame.content.current.set_file_calls == [str((directory / "sub" / "data.tsv").resolve())])


def test_fresh_placement_unknown_widget_id_is_a_silent_noop():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        uuid_str = "instance-unknown-1"
        tempui_path = _write_open_with_widget_file(directory, uuid_str, "totally_bogus_widget_id", "a.tsv")

        try:
            win._activate_temp_ui(tempui_path)
            check("an unknown widget_id doesn't raise", True)
        except Exception as e:  # noqa: BLE001
            check(f"an unknown widget_id doesn't raise (raised {e!r})", False)
        check("nothing was placed for an unknown widget_id", win.find_frame_by_instance_id(uuid_str) is None)


def test_repeat_click_just_centers_does_not_replace():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        (directory / "widget.py").write_text(_SET_FILE_WIDGET_BODY)
        win._widgets["sheet_like"] = _python_widget_info(directory, "sheet_like")
        uuid_str = "instance-repeat-1"
        tempui_path = _write_open_with_widget_file(directory, uuid_str, "sheet_like", "a.tsv")

        win._activate_temp_ui(tempui_path)
        first_frame = win.find_frame_by_instance_id(uuid_str)
        win._activate_temp_ui(tempui_path)
        second_frame = win.find_frame_by_instance_id(uuid_str)

        check("a repeat activation on the same file re-centers the same frame, doesn't replace it", first_frame is second_frame)


# ---------- restore (_bind_temp_ui_widget) --------------------------------


def test_restore_reapplies_for_a_python_widget():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        (directory / "widget.py").write_text(_SET_FILE_WIDGET_BODY)
        info = _python_widget_info(directory, "sheet_like")
        win._widgets["sheet_like"] = info
        target = directory / "data.tsv"
        uuid_str = "instance-restore-py"
        _write_open_with_widget_file(directory, uuid_str, "sheet_like", str(target))

        # Restore path: a frame placed fresh (no tempui content bound
        # yet, mirroring _load_desk_widgets' own two-step "place, then
        # bind" restore shape), then _bind_temp_ui_widget re-applies it.
        frame = win._place_widget("sheet_like", info, (0, 0), (400, 300), instance_id=uuid_str)
        check("sanity: nothing applied yet before the restore-binding step", frame.content.current.set_file_calls == [])

        win._bind_temp_ui_widget(frame, directory, uuid_str)

        check("restore re-applies set_file with the resolved path", frame.content.current.set_file_calls == [str(target)])


def test_restore_reapplies_for_an_html_widget():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_custom_definition(), source="tempui")
        target = directory / "doc.pdf"
        uuid_str = "instance-restore-html"
        _write_open_with_widget_file(directory, uuid_str, "PdfViewer", str(target))

        frame = win._place_widget("PdfViewer", win._widgets["PdfViewer"], (0, 0), (400, 300), instance_id=uuid_str)
        check("sanity: nothing recorded yet before the restore-binding step", win.get_opened_file_for_instance(uuid_str) is None)

        win._bind_temp_ui_widget(frame, directory, uuid_str)

        check("restore re-applies the opened file for a kind:'html' instance too", win.get_opened_file_for_instance(uuid_str) == str(target))


def test_restore_is_a_noop_for_other_kinds_html_content():
    # Regression: _bind_temp_ui_widget's new ChromiumWidget branch must
    # not do anything for every *other* tempui kind (they're all
    # Python-only) -- confirms it doesn't, say, crash or record garbage.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_custom_definition(), source="tempui")
        uuid_str = "instance-scratch-html"
        tempui_dir = directory / ".desk_temp"
        tempui_dir.mkdir(parents=True, exist_ok=True)
        (tempui_dir / uuid_str).write_text("Scratch\tsome label\nbody text\n")
        frame = win._place_widget("PdfViewer", win._widgets["PdfViewer"], (0, 0), (400, 300), instance_id=uuid_str)

        win._bind_temp_ui_widget(frame, directory, uuid_str)

        check("an unrelated (Python-only) kind leaves a kind:'html' instance's opened file untouched", win.get_opened_file_for_instance(uuid_str) is None)


# ---------- docs/changelog -------------------------------------------------


def test_changelog_and_doc_cover_this():
    from desk.temp_ui import CURRENT_TAGS, DOC_TEMPLATE, SPLIT_DOC_CONTENT, OPEN_WITH_WIDGET_DOC_FILENAME, _NEW_FEATURES

    tag = "OpenWithWidget places any widget with a file #051616"
    check("tag is in CURRENT_TAGS with a _NEW_FEATURES entry", tag in CURRENT_TAGS and tag in _NEW_FEATURES)
    check("desk-temporary-ui.md's own keyword list mentions OpenWithWidget", "OpenWithWidget" in DOC_TEMPLATE)
    check("a real split doc file exists for it", OPEN_WITH_WIDGET_DOC_FILENAME in SPLIT_DOC_CONTENT)
    check("the split doc documents the tab-separated shape", "OpenWithWidget<TAB>widget_id<TAB>path" in SPLIT_DOC_CONTENT[OPEN_WITH_WIDGET_DOC_FILENAME])


test_parse_round_trips_widget_id_and_path()
test_parse_tolerates_spaces_in_the_path()
test_parse_returns_none_for_missing_fields_or_wrong_keyword()
test_detect_temp_ui_kind_shapes()
test_fresh_placement_targets_a_python_widget()
test_fresh_placement_targets_an_html_widget()
test_fresh_placement_relative_path_resolves_against_desk_directory()
test_fresh_placement_unknown_widget_id_is_a_silent_noop()
test_repeat_click_just_centers_does_not_replace()
test_restore_reapplies_for_a_python_widget()
test_restore_reapplies_for_an_html_widget()
test_restore_is_a_noop_for_other_kinds_html_content()
test_changelog_and_doc_cover_this()

# Same os._exit() ending as verify_relocate_promoted_widget_source.py's
# own sibling scripts (see LEARNINGS.md's TODO a5f66cc entry): real
# ChromiumWidget instances (placed for the html-widget tests above) can
# segfault tearing down QWebEngine profiles/pages at normal interpreter
# shutdown, after every check here has already run and printed.
print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
