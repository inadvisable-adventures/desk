import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk, desk_state_dict, load_desk, save_desk  # noqa: E402
from desk.file_type_registry import (  # noqa: E402
    FILE_TYPE_REGISTRY_UPDATED_EVENT,
    FileTypeHandler,
    FileTypeRegistryEntry,
    entry_from_dict,
    entry_to_dict,
)
from desk.server.runner import start_server  # noqa: E402
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


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------- data model round-trip ----------


def test_entry_round_trips_through_dict():
    entry = FileTypeRegistryEntry(
        extensions=[".svg"], mime_types=["image/svg+xml"],
        handlers=[FileTypeHandler(widget_id="svg_viewer", role="view")],
    )
    data = entry_to_dict(entry)
    restored = entry_from_dict(data)
    check("extensions round-trip", restored.extensions == [".svg"])
    check("mime_types round-trip", restored.mime_types == ["image/svg+xml"])
    check("handlers round-trip", restored.handlers == [FileTypeHandler(widget_id="svg_viewer", role="view")])


def test_desk_persists_file_type_registry():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        entry = FileTypeRegistryEntry(
            extensions=[".md"], mime_types=[],
            handlers=[FileTypeHandler(widget_id="markdown", role="view"), FileTypeHandler(widget_id="editor", role="edit")],
        )
        desk = Desk(path=directory / "test.desk", file_type_registry=[entry])
        save_desk(desk)
        reloaded = load_desk(desk.path)
        check("file_type_registry round-trips through save/load", reloaded.file_type_registry == [entry])

        state_dict = desk_state_dict(desk)
        check("desk_state_dict includes file_type_registry", state_dict["file_type_registry"] == [entry_to_dict(entry)])


def test_old_desk_file_without_registry_defaults_to_empty():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "old.desk"
        path.write_text('{"widgets": []}')
        desk = load_desk(path)
        check("old .desk file with no file_type_registry key defaults to []", desk.file_type_registry == [])


# ---------- widget discovery ----------


def test_filetype_registry_editor_widget_discovered():
    widgets = discover_widgets(Path("/Users/mphair/inadvisable-adventures/desk/widgets"))
    info = widgets.get("filetype_registry_editor")
    check("widget discovered", info is not None)
    check("kind is html", info.kind == "html")
    check("declares filetypes capability", "filetypes" in info.capabilities)


# ---------- current_context provider hook ----------


def test_current_context_file_type_registry_provider():
    from desk.shell import current_context

    try:
        current_context.set_file_type_registry_provider(lambda: [{"extensions": [".foo"]}])
        provider = current_context.get_file_type_registry_provider()
        check("provider returns the registered value", provider() == [{"extensions": [".foo"]}])
    finally:
        current_context.set_file_type_registry_provider(lambda: [])


# ---------- File Explorer's own consumption ----------


def test_file_explorer_reads_initial_registry_and_updates_on_event():
    from desk.shell import current_context
    from desk.event_mediator import EventMediator

    file_explorer_mod = load_widget_module(
        "file_explorer_verify_mod", "/Users/mphair/inadvisable-adventures/desk/widgets/project_files/widget.py"
    )
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        current_context.set_file_type_registry_provider(lambda: [{"extensions": [".svg"], "mime_types": [], "handlers": []}])
        try:
            widget = file_explorer_mod.build()
            check("initial registry read via current_context provider", widget._file_type_registry == [{"extensions": [".svg"], "mime_types": [], "handlers": []}])

            mediator = EventMediator()
            widget.bind_event_mediator("inst-1", mediator)
            mediator.publish(
                FILE_TYPE_REGISTRY_UPDATED_EVENT,
                {"entries": [{"extensions": [".png"], "mime_types": [], "handlers": []}]},
                sender_instance_id="inst-2",
            )
            deadline = time.time() + 5
            while widget._file_type_registry[0]["extensions"] != [".png"] and time.time() < deadline:
                app.processEvents()
                time.sleep(0.01)
            check("local copy updated from the published event's own payload", widget._file_type_registry == [{"extensions": [".png"], "mime_types": [], "handlers": []}])
        finally:
            current_context.set_current_desk_directory(None)
            current_context.set_file_type_registry_provider(lambda: [])


# ---------- Bridge API, over real HTTP ----------


class _FakeDesk:
    def __init__(self, directory):
        self.directory = directory
        self.file_type_registry = []


class _FakeGuiWindow:
    def __init__(self, directory):
        self.current_desk = _FakeDesk(directory)

    def get_widget_info(self, widget_id):
        from desk.widgets import WidgetInfo

        return WidgetInfo(
            id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
            capabilities=["filetypes"], default_size=None,
        )

    def get_file_type_registry_dicts(self):
        return [entry_to_dict(e) if not isinstance(e, dict) else e for e in self.current_desk.file_type_registry]

    def set_file_type_registry(self, entries, sender_instance_id):
        self.current_desk.file_type_registry = entries
        self._mediator.publish(FILE_TYPE_REGISTRY_UPDATED_EVENT, {"entries": entries}, sender_instance_id)


def _request(url, token, widget_id, instance_id, method="GET", body=None):
    headers = {"X-Desk-Token": token, "X-Desk-Widget-Id": widget_id, "X-Desk-Instance-Id": instance_id}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8')}") from e


def _run_with_pumped_event_loop(fn, timeout=10):
    outcome = {}

    def run():
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            outcome["error"] = e
        finally:
            outcome["done"] = True

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.time() + timeout
    while not outcome.get("done") and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    thread.join(timeout=1)
    assert outcome.get("done"), "background requests never finished"
    if "error" in outcome:
        raise outcome["error"]


def test_bridge_api_get_reads_and_subscribes_set_persists_and_publishes():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            fake_window = _FakeGuiWindow(desk_dir)
            fake_window._mediator = handle.event_mediator
            handle.gui_bridge.attach(fake_window)
            base = f"http://{handle.host}:{handle.port}"
            result = {}

            def run_requests():
                get_result = _request(f"{base}/api/bridge/filetypes/get", handle.token, "editor_widget", "inst-caller")
                result["get"] = get_result
                subs = handle.event_mediator.list_subscriptions()
                result["subscribed"] = "inst-caller" in subs and FILE_TYPE_REGISTRY_UPDATED_EVENT in subs["inst-caller"]

                handle.event_mediator.subscribe("inst-listener", FILE_TYPE_REGISTRY_UPDATED_EVENT)

                set_result = _request(
                    f"{base}/api/bridge/filetypes/set", handle.token, "editor_widget", "inst-caller",
                    method="POST", body={"entries": [{"extensions": [".svg"], "mime_types": [], "handlers": []}]},
                )
                result["set"] = set_result
                event = handle.event_mediator.poll("inst-listener", timeout=5)
                result["published_event"] = event

            _run_with_pumped_event_loop(run_requests)

            check("GET returns entries key", result["get"] == {"entries": []})
            check("GET subscribed the caller to future edits", result["subscribed"] is True)
            check("POST returns ok", result["set"] == {"ok": True})
            check("fake window's registry was updated", fake_window.current_desk.file_type_registry == [{"extensions": [".svg"], "mime_types": [], "handlers": []}])
            event = result["published_event"]
            check("update event published to another subscriber", event is not None and event.name == FILE_TYPE_REGISTRY_UPDATED_EVENT)
            check("event payload carries the new entries", event.payload == {"entries": [{"extensions": [".svg"], "mime_types": [], "handlers": []}]})
            check("event sender is the editing widget's instance id", event.sender_instance_id == "inst-caller")
        finally:
            handle.stop()


def test_bridge_client_has_filetypes_namespace():
    from desk.server.bridge_client import BRIDGE_CLIENT_TEMPLATE

    check("bridge client declares filetypes.get", '"/api/bridge/filetypes/get"' in BRIDGE_CLIENT_TEMPLATE)
    check("bridge client declares filetypes.set", '"/api/bridge/filetypes/set"' in BRIDGE_CLIENT_TEMPLATE)


test_entry_round_trips_through_dict()
test_desk_persists_file_type_registry()
test_old_desk_file_without_registry_defaults_to_empty()
test_filetype_registry_editor_widget_discovered()
test_current_context_file_type_registry_provider()
test_file_explorer_reads_initial_registry_and_updates_on_event()
test_bridge_api_get_reads_and_subscribes_set_persists_and_publishes()
test_bridge_client_has_filetypes_namespace()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
