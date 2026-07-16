import base64
import hashlib
import os
import sys
import tempfile
import uuid as uuid_mod
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk, WidgetState, desk_state_dict, load_desk, save_desk  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.server.app import _widget_info_dict  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
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
        self._html_widget_local_storage = {}


_FakeWindow._register_custom_widget = DeskWindow._register_custom_widget
_FakeWindow._refresh_stale_indicators_for = DeskWindow._refresh_stale_indicators_for
_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._load_desk_widgets = DeskWindow._load_desk_widgets
_FakeWindow._seed_new_desk_widgets = DeskWindow._seed_new_desk_widgets
_FakeWindow._bind_temp_ui_widget = DeskWindow._bind_temp_ui_widget
_FakeWindow._bind_crash_log_widget = DeskWindow._bind_crash_log_widget
_FakeWindow._bind_widget_local_storage = DeskWindow._bind_widget_local_storage
_FakeWindow._capture_desk_state = DeskWindow._capture_desk_state
_FakeWindow._get_widget_local_storage = DeskWindow._get_widget_local_storage


# ---------- registration computes + stores + exposes the hash ----------


def test_registration_computes_content_hash():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(), source="tempui")
        expected = hashlib.md5(SAMPLE_HTML_B64.encode("ascii")).hexdigest()[:12]
        check("content hash stored in lookup dict", win._custom_widget_content_hash["KanbanBoard"] == expected)
        check("content hash set on WidgetInfo", win._widgets["KanbanBoard"].content_hash == expected)


def test_ordinary_widget_info_has_no_content_hash():
    info = WidgetInfo(
        id="editor", path=Path("."), kind="html", name="Editor", entry="index.html",
        capabilities=[], default_size=None,
    )
    check("ordinary WidgetInfo.content_hash defaults to None", info.content_hash is None)


def test_get_manifest_dict_exposes_content_hash():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(), source="tempui")
        manifest = _widget_info_dict(win._widgets["KanbanBoard"])
        check("getManifest dict includes content_hash", manifest["content_hash"] == win._widgets["KanbanBoard"].content_hash)
        ordinary = _widget_info_dict(
            WidgetInfo(id="editor", path=Path("."), kind="html", name="Editor", entry="index.html",
                       capabilities=[], default_size=None)
        )
        check("getManifest dict is None for an ordinary widget", ordinary["content_hash"] is None)


def test_redefinition_changes_hash():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(), source="tempui")
        first_hash = win._custom_widget_content_hash["KanbanBoard"]
        win._register_custom_widget(_definition(html_b64=SAMPLE_HTML_2_B64), source="tempui")
        second_hash = win._custom_widget_content_hash["KanbanBoard"]
        check("re-registration with different content changes the hash", first_hash != second_hash)


# ---------- fresh placement is never stale ----------


def test_fresh_placement_is_never_stale():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(), source="tempui")
        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        check("fresh placement's placed_content_hash is set", frame.placed_content_hash == win._custom_widget_content_hash["KanbanBoard"])
        check("fresh placement's stale button is not visible", not frame._titlebar.stale_button.isVisible())


# ---------- live edit while placed marks it stale immediately ----------


def test_live_redefinition_marks_placed_instance_stale():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(), source="tempui")
        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        check("not stale right after placement", not frame._titlebar.stale_button.isVisible())

        # Live-edit the definition (same source, different content) --
        # the already-placed frame's own placed_content_hash still
        # holds the old hash, so it should now read as stale.
        win._register_custom_widget(_definition(html_b64=SAMPLE_HTML_2_B64), source="tempui")
        check("placed instance's stale button now visible after live redefinition", frame._titlebar.stale_button.isVisible())
        check("stale button has an explanatory tooltip", "click for details" in frame._titlebar.stale_button.toolTip())

        # A second, brand-new instance placed *after* the redefinition
        # should not be stale -- it's current by construction.
        widget = win._widgets["KanbanBoard"]
        fresh_frame = win._place_widget("KanbanBoard", widget, (450, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        check("a newly-placed instance after the edit is not stale", not fresh_frame._titlebar.stale_button.isVisible())


# ---------- restore compares saved hash against the live one ----------


def test_restore_with_matching_hash_is_not_stale():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(), source="tempui")
        current_hash = win._custom_widget_content_hash["KanbanBoard"]
        desk = Desk(
            path=directory / "test.desk",
            widgets=[
                WidgetState(
                    widget_id="KanbanBoard", x=0, y=0, width=400, height=300,
                    instance_id="abc12345", placed_content_hash=current_hash,
                )
            ],
        )
        win._load_desk_widgets(desk)
        frame = win.view._frames[0]
        check("restore with matching hash is not stale", not frame._titlebar.stale_button.isVisible())


def test_restore_with_stale_hash_is_marked_stale():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(), source="tempui")
        desk = Desk(
            path=directory / "test.desk",
            widgets=[
                WidgetState(
                    widget_id="KanbanBoard", x=0, y=0, width=400, height=300,
                    instance_id="abc12345", placed_content_hash="deadbeefcafe",
                )
            ],
        )
        win._load_desk_widgets(desk)
        frame = win.view._frames[0]
        check("restore with mismatched hash shows the stale button", frame._titlebar.stale_button.isVisible())


# ---------- WidgetState/desk_state_dict round-trip ----------


def test_widget_state_round_trips_placed_content_hash():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        desk = Desk(
            path=directory / "test.desk",
            widgets=[
                WidgetState(
                    widget_id="KanbanBoard", x=1, y=2, width=3, height=4,
                    instance_id="abc12345", placed_content_hash="abc123def456",
                )
            ],
        )
        save_desk(desk)
        reloaded = load_desk(desk.path)
        check("placed_content_hash round-trips through save/load", reloaded.widgets[0].placed_content_hash == "abc123def456")

        state_dict = desk_state_dict(desk)
        check("desk_state_dict includes placed_content_hash", state_dict["widgets"][0]["placed_content_hash"] == "abc123def456")


def test_old_desk_file_without_field_defaults_to_none():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        path = directory / "old.desk"
        path.write_text(
            '{"widgets": [{"widget_id": "editor", "x": 0, "y": 0, "width": 1, "height": 1, '
            '"instance_id": "abc12345"}]}'
        )
        desk = load_desk(path)
        check("old .desk file with no placed_content_hash key defaults to None", desk.widgets[0].placed_content_hash is None)


test_registration_computes_content_hash()
test_ordinary_widget_info_has_no_content_hash()
test_get_manifest_dict_exposes_content_hash()
test_redefinition_changes_hash()
test_fresh_placement_is_never_stale()
test_live_redefinition_marks_placed_instance_stale()
test_restore_with_matching_hash_is_not_stale()
test_restore_with_stale_hash_is_marked_stale()
test_widget_state_round_trips_placed_content_hash()
test_old_desk_file_without_field_defaults_to_none()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
