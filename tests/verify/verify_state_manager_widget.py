import json
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
from desk.event_mediator import EventMediator  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.schema_registry import SchemaRegistry  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import STATE_MANAGER_WIDGET_ID, DeskWindow  # noqa: E402
from desk.widgets import discover_widgets  # noqa: E402

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


REAL_WIDGETS = discover_widgets(REPO_ROOT / "widgets")
STATE_MANAGER_INFO = REAL_WIDGETS["state_manager"]


class _FakeHandle:
    def widget_url(self, widget_id):
        return f"http://fake/{widget_id}"

    token = "tok"


class _FakeSchemaFileWatcher:
    def provision(self, ephemeral_dir, project_root):
        pass


class _FakeWindow:
    def __init__(self, directory):
        self.current_desk = Desk(path=directory / "test.desk")
        self._widgets = {STATE_MANAGER_WIDGET_ID: STATE_MANAGER_INFO}
        self._handle = _FakeHandle()
        self._broker = HotReloadBroker()
        self._event_mediator = EventMediator()
        self._schema_registry = SchemaRegistry(self._event_mediator)
        self._known_schema_file_sources = set()
        self._schema_file_watcher = _FakeSchemaFileWatcher()
        self._custom_widget_sources = {}
        self._custom_widget_content_hash = {}
        # _ensure_state_manager_placed (called automatically whenever a
        # schema registers) needs a real WorkspaceView, not a bare
        # stand-in -- it can genuinely place a real state_manager
        # instance (a real PythonWidgetHost building the real
        # widgets/state_manager/widget.py), matching every other
        # DeskWindow-adjacent verify script's own "real view" pattern.
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()


for name in (
    "_place_widget",
    "_chromium_profile_dir",
    "_bind_claude_widget",
    "_bind_external_indicator",
    "_bind_error_indicator",
    "_bind_event_mediator",
    "_check_schema_conflict",
    "_is_instance_currently_placed",
    "_notify_schema_conflict",
    "_show_schema_conflict_popup",
    "_notify_schema_file_error",
    "_on_schema_file_changed",
    "_ensure_state_manager_placed",
    "_find_frame_by_widget_id",
    "find_frame_by_instance_id",
    "get_state",
    "set_state",
    "get_state_history",
    "get_state_overview",
    "try_set_state",
    "write_schema_file",
    "delete_schema_key",
):
    setattr(_FakeWindow, name, getattr(DeskWindow, name))


def test_get_state_overview_reflects_validated_and_non_validated_keys():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        win._schema_registry.register_permanent("counter", "number", "builtin_widget", source_kind="widget")
        win.set_state("counter", 5, None, "inst-a")
        win.set_state("raw", "hi", None, "inst-a")

        overview = {entry["key"]: entry for entry in win.get_state_overview()}
        check("both keys appear", set(overview.keys()) == {"counter", "raw"})
        check("validated key carries its schema info", overview["counter"]["type_expr"] == "number")
        check("validated key's source_kind is 'widget'", overview["counter"]["source_kind"] == "widget")
        check("validated key is marked permanent", overview["counter"]["permanent"] is True)
        check("non-validated key has no schema info", overview["raw"]["type_expr"] is None)
        check("non-validated key's value is still shown", overview["raw"]["value"] == "hi")


def test_write_schema_file_creates_a_real_file_and_registers():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / ".desk_temp").mkdir()
        win = _FakeWindow(directory)

        error = win.write_schema_file("ephemeral", "counter", "number")
        check("write_schema_file to the ephemeral location succeeds", error is None)
        path = directory / ".desk_temp" / "schemas" / "counter.json"
        check("a real file is created", path.is_file())
        check("the file's content matches", json.loads(path.read_text()) == {"counter": "number"})
        check("the key is actually registered", win._schema_registry.get("counter") is not None)
        check("the registered source_kind is 'file'", win._schema_registry.get("counter").source_kind == "file")


def test_write_schema_file_git_tracked_creates_the_directory_on_demand():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        check("./desk-schemas/ does not exist yet", not (directory / "desk-schemas").is_dir())

        error = win.write_schema_file("git_tracked", "doc", "string")
        check("write_schema_file to the git-tracked location succeeds", error is None)
        check("./desk-schemas/ was created on demand", (directory / "desk-schemas").is_dir())
        check("the key is registered", win._schema_registry.get("doc") is not None)


def test_write_schema_file_reports_a_real_conflict():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._schema_registry.register_permanent("counter", "number", "builtin_widget", source_kind="widget")

        error = win.write_schema_file("ephemeral", "counter", "string")
        check("a real conflict against an active schema is reported", error is not None and "counter" in error)
        check(
            "the conflicting write did not overwrite the active schema",
            win._schema_registry.get("counter").type_expr == "number",
        )


def test_delete_schema_key_refuses_widget_sourced():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        win._schema_registry.register_permanent("counter", "number", "builtin_widget", source_kind="widget")
        error = win.delete_schema_key("counter")
        check("deleting a widget-sourced schema is refused", error is not None and "builtin_widget" in error)
        check("the schema is untouched", win._schema_registry.get("counter") is not None)


def test_delete_schema_key_removes_a_file_sourced_one():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win.write_schema_file("ephemeral", "counter", "number")
        path = directory / ".desk_temp" / "schemas" / "counter.json"
        check("file exists before delete", path.is_file())

        error = win.delete_schema_key("counter")
        check("deleting a file-sourced schema succeeds", error is None)
        check("the file is removed (it was the only key)", not path.is_file())
        check("the key is no longer registered", win._schema_registry.get("counter") is None)


def test_try_set_state_never_raises():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        win._schema_registry.register_permanent("counter", "number", "builtin_widget", source_kind="widget")
        error = win.try_set_state("counter", "not a number", None, "inst-a")
        check("a schema mismatch is returned as a message, not raised", error is not None)
        error = win.try_set_state("counter", 5, None, "inst-a")
        check("a valid write succeeds", error is None)
        check("the value actually persisted", win.get_state("counter")["value"] == 5)


def test_ensure_state_manager_placed_guarantee():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / ".desk_temp").mkdir()
        win = _FakeWindow(directory)

        check("no instance placed yet", win._find_frame_by_widget_id(STATE_MANAGER_WIDGET_ID) is None)
        win.write_schema_file("ephemeral", "counter", "number")
        frame = win._find_frame_by_widget_id(STATE_MANAGER_WIDGET_ID)
        check("an instance is auto-placed once a schema registers", frame is not None)

        win.write_schema_file("ephemeral", "other", "string")
        check(
            "a second registration does not place a second instance",
            len([f for f in win.view._frames if getattr(f.content, "widget_id", None) == STATE_MANAGER_WIDGET_ID]) == 1,
        )

        win.view.remove_widget(frame)
        check("closing the only instance leaves none placed", win._find_frame_by_widget_id(STATE_MANAGER_WIDGET_ID) is None)
        win.write_schema_file("ephemeral", "third", "boolean")
        check(
            "a later registration re-places an instance after the sole one was closed",
            win._find_frame_by_widget_id(STATE_MANAGER_WIDGET_ID) is not None,
        )


test_get_state_overview_reflects_validated_and_non_validated_keys()
test_write_schema_file_creates_a_real_file_and_registers()
test_write_schema_file_git_tracked_creates_the_directory_on_demand()
test_write_schema_file_reports_a_real_conflict()
test_delete_schema_key_refuses_widget_sourced()
test_delete_schema_key_removes_a_file_sourced_one()
test_try_set_state_never_raises()
test_ensure_state_manager_placed_guarantee()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
