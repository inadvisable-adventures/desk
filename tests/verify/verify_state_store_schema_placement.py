import base64
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

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
from desk.temp_ui import CustomWidgetDefinition  # noqa: E402

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


SAMPLE_HTML_B64 = base64.b64encode(b"<html><body>hi</body></html>").decode()


def _definition(keyword, schema):
    return CustomWidgetDefinition(
        keyword=keyword, label=keyword, html_b64=SAMPLE_HTML_B64, default_size=(400, 300),
        capabilities=["state"], state_schema=schema,
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
        self._schema_registry = SchemaRegistry()


_FakeWindow._register_custom_widget = DeskWindow._register_custom_widget
_FakeWindow._refresh_stale_indicators_for = DeskWindow._refresh_stale_indicators_for
_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_error_indicator = DeskWindow._bind_error_indicator
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._chromium_profile_dir = DeskWindow._chromium_profile_dir
_FakeWindow._check_schema_conflict = DeskWindow._check_schema_conflict
_FakeWindow._is_instance_currently_placed = DeskWindow._is_instance_currently_placed
_FakeWindow._notify_schema_conflict = DeskWindow._notify_schema_conflict
_FakeWindow._show_schema_conflict_popup = DeskWindow._show_schema_conflict_popup
_FakeWindow._ensure_state_manager_placed = DeskWindow._ensure_state_manager_placed
_FakeWindow._find_frame_by_widget_id = DeskWindow._find_frame_by_widget_id
_FakeWindow.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id


def test_conflicting_tempui_schemas_block_placement_and_dormancy_works():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        kind_a = _definition("KindA", {"shared_key": "number"})
        kind_b = _definition("KindB", {"shared_key": "string"})
        check("KindA registers", win._register_custom_widget(kind_a, source="tempui") is True)
        check("KindB registers", win._register_custom_widget(kind_b, source="tempui") is True)

        widget_a = win._widgets["KindA"]
        widget_b = win._widgets["KindB"]

        frame_a1 = win._place_widget("KindA", widget_a, (0, 0), None, instance_id="inst-a1")
        check("first placement of KindA (fresh schema registration) succeeds", frame_a1 is not None)

        frame_b1 = win._place_widget("KindB", widget_b, (100, 0), None, instance_id="inst-b1")
        check("KindB is refused: its schema conflicts with KindA's still-active one", frame_b1 is None)
        check(
            "KindB's WidgetInfo gets a desk_widget_loading_errors entry",
            len(widget_b.desk_widget_loading_errors) == 1 and "shared_key" in widget_b.desk_widget_loading_errors[0],
        )
        conflict_path = Path("schema-conflict:KindB")
        check(
            "a notification banner fires for the refused widget",
            conflict_path in win.view.temp_ui_notifications._banners,
        )

        win.view.remove_widget(frame_a1)
        check("closing KindA's only instance removes it from the canvas", win.find_frame_by_instance_id("inst-a1") is None)

        frame_a2 = win._place_widget("KindA", widget_a, (0, 0), None, instance_id="inst-a2")
        check("re-placing KindA with the same schema reactivates the now-dormant entry", frame_a2 is not None)

        frame_b2 = win._place_widget("KindB", widget_b, (100, 0), None, instance_id="inst-b2")
        check("KindB still conflicts while KindA's reactivated instance is placed", frame_b2 is None)

        win.view.remove_widget(frame_a2)
        check("closing KindA's reactivated instance too leaves the schema dormant again", win.find_frame_by_instance_id("inst-a2") is None)

        frame_b3 = win._place_widget("KindB", widget_b, (100, 0), None, instance_id="inst-b3")
        check("KindB can now replace the dormant schema with its own, different one", frame_b3 is not None)

        frame_a3 = win._place_widget("KindA", widget_a, (0, 0), None, instance_id="inst-a3")
        check("KindA now conflicts with KindB's freshly-active, different schema", frame_a3 is None)


test_conflicting_tempui_schemas_block_placement_and_dormancy_works()

print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
# See LEARNINGS.md's ChromiumWidget/QWebEngineProfile entry: this
# script places several real kind:"html" widgets (each its own
# QWebEngineProfile) without ever entering a real app.exec() loop,
# which races Qt/Chromium's internal per-profile teardown against
# interpreter shutdown -- os._exit skips that teardown race entirely,
# after every real check above has already run and passed/failed.
os._exit(1 if failed else 0)
