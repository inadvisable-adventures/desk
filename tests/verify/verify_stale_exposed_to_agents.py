# TODO f0da2e9: desk_list_widget_instances/desk.workspace.getState()
# expose each placed instance's stale bit -- the exact live signal the
# titlebar [STALE] badge reads (WidgetFrame.is_stale()), not an
# independently recomputed hash diff, and never persisted to the .desk
# file. Scaffold mirrors verify_custom_widget_content_hash.py (the
# _FakeWindow with a real _capture_desk_state/get_state_dict) and
# verify_stale_marker_click_dialog.py (_make_stale_frame's established
# way to get a genuinely stale instance).
import base64
import os
import sys
import tempfile
import uuid as uuid_mod
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk, WidgetState, desk_state_dict  # noqa: E402
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


SAMPLE_HTML = "<html><body><h1>Kanban</h1></body></html>"
SAMPLE_HTML_B64 = base64.b64encode(SAMPLE_HTML.encode()).decode()
SAMPLE_HTML_2_B64 = base64.b64encode((SAMPLE_HTML + "<p>v2</p>").encode()).decode()


def _definition(html_b64=SAMPLE_HTML_B64, keyword="KanbanBoard", label="Kanban Board"):
    return CustomWidgetDefinition(keyword=keyword, label=label, html_b64=html_b64, default_size=(600, 400))


def _python_widget_info(directory):
    return WidgetInfo(
        id="ordinary_python", path=directory, kind="python", name="Ordinary",
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
        self._schema_registry = SchemaRegistry()


_FakeWindow._register_custom_widget = DeskWindow._register_custom_widget
_FakeWindow._refresh_stale_indicators_for = DeskWindow._refresh_stale_indicators_for
_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._scratch_backing_file = DeskWindow._scratch_backing_file
_FakeWindow._bind_scratch_backing_file = DeskWindow._bind_scratch_backing_file
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
_FakeWindow._bind_widget_local_storage = DeskWindow._bind_widget_local_storage
_FakeWindow._capture_desk_state = DeskWindow._capture_desk_state
_FakeWindow._flush_scratch_backing_files = DeskWindow._flush_scratch_backing_files
_FakeWindow._get_widget_local_storage = DeskWindow._get_widget_local_storage
_FakeWindow.get_state_dict = DeskWindow.get_state_dict
_FakeWindow._on_promoted_widget_source_changed = DeskWindow._on_promoted_widget_source_changed


def _make_stale_frame(win, html_b64=SAMPLE_HTML_2_B64):
    """A genuinely stale instance via a real hash mismatch -- the same
    way verify_stale_marker_click_dialog.py's own helper does: place
    one, then live-redefine the keyword with different content."""
    win._register_custom_widget(_definition(), source="tempui")
    widget = win._widgets["KanbanBoard"]
    frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
    win._register_custom_widget(_definition(html_b64=html_b64), source="tempui")
    win._refresh_stale_indicators_for("KanbanBoard")
    return frame


def _widget_dict(state, instance_id):
    return next(w for w in state["widgets"] if w["instance_id"] == instance_id)


# ---------- WidgetFrame.is_stale() -----------------------------------


def test_widget_frame_is_stale_reflects_set_stale():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(), source="tempui")
        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        check("a freshly placed instance is not stale", frame.is_stale() is False)
        frame.set_stale(True)
        check("is_stale() reflects set_stale(True)", frame.is_stale() is True)
        frame.set_stale(False)
        check("is_stale() reflects set_stale(False)", frame.is_stale() is False)


# ---------- desk_state_dict's optional stale_by_instance_id -----------


def test_desk_state_dict_omits_stale_by_default():
    desk = Desk(
        path=Path("/tmp/x.desk"),
        widgets=[WidgetState(widget_id="editor", x=0, y=0, width=100, height=100, instance_id="inst1")],
    )
    state = desk_state_dict(desk)
    check("no stale_by_instance_id given: no 'stale' key at all (save_desk's own exact shape)", "stale" not in state["widgets"][0])


def test_desk_state_dict_adds_stale_when_given():
    desk = Desk(
        path=Path("/tmp/x.desk"),
        widgets=[
            WidgetState(widget_id="editor", x=0, y=0, width=100, height=100, instance_id="inst1"),
            WidgetState(widget_id="editor", x=0, y=0, width=100, height=100, instance_id="inst2"),
        ],
    )
    state = desk_state_dict(desk, {"inst1": True})
    check("an instance present in the map gets its own value", _widget_dict(state, "inst1")["stale"] is True)
    check("an instance missing from the map defaults to False, not omitted/None", _widget_dict(state, "inst2")["stale"] is False)


def test_save_desk_persists_the_unchanged_shape():
    from desk.desks import save_desk, load_desk
    import json

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        path = Path(d) / "test.desk"
        desk = Desk(path=path, widgets=[WidgetState(widget_id="editor", x=0, y=0, width=100, height=100, instance_id="inst1")])
        save_desk(desk)
        on_disk = json.loads(path.read_text())
        check("save_desk never writes a 'stale' key to the .desk file", "stale" not in on_disk["widgets"][0])
        check("save_desk's own file still loads back fine", load_desk(path).widgets[0].instance_id == "inst1")


# ---------- DeskWindow.get_state_dict() -> both real MCP/Bridge surfaces ---


def test_get_state_dict_reports_stale_true_for_a_genuinely_stale_instance():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        frame = _make_stale_frame(win)
        check("sanity: the instance really is showing [STALE]", frame.is_stale() is True)

        state = win.get_state_dict()
        entry = _widget_dict(state, frame.instance_id)
        check("get_state_dict() reports stale: true for it", entry["stale"] is True)
        check("placed_content_hash is still present alongside it, unchanged", "placed_content_hash" in entry)


def test_get_state_dict_reports_stale_false_for_a_fresh_instance():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(), source="tempui")
        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])

        entry = _widget_dict(win.get_state_dict(), frame.instance_id)
        check("a freshly placed, never-edited-since instance reports stale: false", entry["stale"] is False)


def test_get_state_dict_reports_stale_true_from_the_force_true_path():
    # TODO f0da2e9's own explicit reasoning: the fix must read the
    # frame's live bit, not recompute a hash diff -- this is exactly
    # the case an independent hash diff would miss (source changed on
    # disk, no fresh hash exists yet to compare against).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(), source="tempui")
        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        check("sanity: not stale before the source-changed signal", frame.is_stale() is False)

        win._on_promoted_widget_source_changed("KanbanBoard")

        check("sanity: force-marked stale with no fresh hash to diff", frame.is_stale() is True)
        entry = _widget_dict(win.get_state_dict(), frame.instance_id)
        check("get_state_dict() reports stale: true for the force-True path too", entry["stale"] is True)


def test_ordinary_python_widget_reports_stale_false():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        (directory / "widget.py").write_text("from PyQt6.QtWidgets import QLabel\ndef build():\n    return QLabel('hi')\n")
        win = _FakeWindow(directory)
        info = _python_widget_info(directory)
        frame = win._place_widget("ordinary_python", info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])

        entry = _widget_dict(win.get_state_dict(), frame.instance_id)
        check("an ordinary widget kind with no staleness concept at all reports stale: false", entry["stale"] is False)


def test_mcp_tool_and_bridge_route_share_one_implementation():
    # desk_list_widget_instances (desk_mcp_server.py:
    # `await window.get_state_dict()`, returns `state["widgets"]`) and
    # desk.workspace.getState() (server/app.py's own getState route:
    # `await run_on_gui(lambda: gui_bridge.window.get_state_dict())`)
    # are both literally this one DeskWindow method -- confirmed by
    # reading both call sites, not assumed. No separate HTTP/MCP
    # plumbing to stand up here: this documents that fact and confirms
    # the shape each of them relays (state["widgets"]) actually carries
    # stale end to end for a real stale instance.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        frame = _make_stale_frame(win)

        widgets = win.get_state_dict()["widgets"]  # what both _list_widget_instances and the getState route relay as-is
        check("the relayed widgets list carries stale through for a real stale instance", _widget_dict({"widgets": widgets}, frame.instance_id)["stale"] is True)


# ---------- docs/changelog --------------------------------------------


def test_changelog_and_doc_cover_this():
    from desk.temp_ui import CURRENT_TAGS, _CUSTOM_WIDGETS_DOC, _DESK_PROC_DOC, _NEW_FEATURES

    tag = "workspace getState exposes per-instance stale flag #157810"
    check("tag is in CURRENT_TAGS with a _NEW_FEATURES entry", tag in CURRENT_TAGS and tag in _NEW_FEATURES)
    check("tempui-custom-widgets.md documents stale on getState()", "`stale`" in _CUSTOM_WIDGETS_DOC and "[STALE]" in _CUSTOM_WIDGETS_DOC)
    check("tempui-desk-proc.md documents stale on list_widget_instances()", "`stale`" in _DESK_PROC_DOC)


test_widget_frame_is_stale_reflects_set_stale()
test_desk_state_dict_omits_stale_by_default()
test_desk_state_dict_adds_stale_when_given()
test_save_desk_persists_the_unchanged_shape()
test_get_state_dict_reports_stale_true_for_a_genuinely_stale_instance()
test_get_state_dict_reports_stale_false_for_a_fresh_instance()
test_get_state_dict_reports_stale_true_from_the_force_true_path()
test_ordinary_python_widget_reports_stale_false()
test_mcp_tool_and_bridge_route_share_one_implementation()
test_changelog_and_doc_cover_this()

# Same os._exit() ending as verify_relocate_promoted_widget_source.py's
# own sibling scripts (see LEARNINGS.md's TODO a5f66cc entry): several
# real ChromiumWidget instances (placed via _place_widget for the
# custom-widget tests above) can segfault tearing down QWebEngine
# profiles/pages at normal interpreter shutdown, unrelated to anything
# checked above -- every check has already run and printed by this
# point.
print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
