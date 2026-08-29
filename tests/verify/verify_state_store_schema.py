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

from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.schema_registry import SchemaRegistry  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402

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


class _FakeDesk:
    def __init__(self, directory):
        self.directory = directory
        self.state = {}


class _FakeGuiWindow:
    """Reuses the real DeskWindow.get_state/set_state/get_state_history
    implementations (unbound, called against this lightweight stand-in)
    rather than re-typing their logic a third time -- these three
    methods only ever touch self.current_desk/._schema_registry/
    ._event_mediator, all provided here, so this is real coverage of
    the actual production code, not a rewritten copy of it."""

    def __init__(self, directory, mediator):
        self.current_desk = _FakeDesk(directory)
        self._schema_registry = SchemaRegistry()
        self._event_mediator = mediator
        self._widget_capabilities = {}

    def get_widget_info(self, widget_id):
        from desk.widgets import WidgetInfo

        capabilities = self._widget_capabilities.get(widget_id, ["state"])
        return WidgetInfo(
            id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
            capabilities=capabilities, default_size=None,
        )

    get_state = DeskWindow.get_state
    set_state = DeskWindow.set_state
    get_state_history = DeskWindow.get_state_history


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


def _request_expect_status(url, token, widget_id, instance_id, method="GET", body=None):
    try:
        _request(url, token, widget_id, instance_id, method=method, body=body)
        return None
    except RuntimeError as e:
        return int(str(e).split(":")[0].split(" ")[1])


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


def test_bridge_api_schema_aware_state():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            fake_window = _FakeGuiWindow(desk_dir, handle.event_mediator)
            handle.gui_bridge.attach(fake_window)
            base = f"http://{handle.host}:{handle.port}"
            result = {}

            def run_requests():
                # non-validated key: no typeHint given preserves f68383f's exact prior behavior
                result["plain_set"] = _request(
                    f"{base}/api/bridge/state/set", handle.token, "widget_a", "inst-a",
                    method="POST", body={"key": "raw", "value": "5"},
                )
                result["plain_get"] = _request(
                    f"{base}/api/bridge/state/get?key=raw", handle.token, "widget_a", "inst-a"
                )

                # non-validated key: typeHint coerces on both set and get
                _request(
                    f"{base}/api/bridge/state/set", handle.token, "widget_a", "inst-a",
                    method="POST", body={"key": "coerced", "value": "5", "type_hint": "number"},
                )
                result["coerced_get"] = _request(
                    f"{base}/api/bridge/state/get?key=coerced", handle.token, "widget_a", "inst-a"
                )
                result["coerced_get_with_hint"] = _request(
                    f"{base}/api/bridge/state/get?key=raw&type_hint=number", handle.token, "widget_a", "inst-a"
                )

                # invalid typeHint syntax is a 400
                result["bad_type_hint_status"] = _request_expect_status(
                    f"{base}/api/bridge/state/set", handle.token, "widget_a", "inst-a",
                    method="POST", body={"key": "raw", "value": "5", "type_hint": "not a type }"},
                )

                # validated key: register a schema directly on the fake window's own registry
                fake_window._schema_registry.register_permanent("counter", "number", "builtin_widget")
                result["valid_set"] = _request(
                    f"{base}/api/bridge/state/set", handle.token, "widget_a", "inst-a",
                    method="POST", body={"key": "counter", "value": 5},
                )
                result["valid_get"] = _request(
                    f"{base}/api/bridge/state/get?key=counter", handle.token, "widget_a", "inst-a"
                )
                result["mismatch_status"] = _request_expect_status(
                    f"{base}/api/bridge/state/set", handle.token, "widget_a", "inst-a",
                    method="POST", body={"key": "counter", "value": "not a number"},
                )
                # a mismatched set must not have stored anything
                result["get_after_mismatch"] = _request(
                    f"{base}/api/bridge/state/get?key=counter", handle.token, "widget_a", "inst-a"
                )
                # typeHint is ignored for a validated key -- the raw stored value comes back
                result["get_with_hint_on_validated_key"] = _request(
                    f"{base}/api/bridge/state/get?key=counter&type_hint=string",
                    handle.token, "widget_a", "inst-a",
                )

            _run_with_pumped_event_loop(run_requests)

            check("plain set with no typeHint stores the value as-is", result["plain_get"] == {"value": "5", "edit": None})
            check("(regression) plain set unaffected by this TODO's changes", result["plain_set"] == {"ok": True})
            check("a typeHint on set coerces before storing", result["coerced_get"] == {"value": 5.0, "edit": None})
            check(
                "a typeHint on get coerces only the returned value, not storage",
                result["coerced_get_with_hint"] == {"value": 5.0, "edit": None},
            )
            check("an invalid typeHint is a 400", result["bad_type_hint_status"] == 400)
            check("a value matching an active schema is stored", result["valid_set"] == {"ok": True})
            check("get on a validated key returns the stored value", result["valid_get"] == {"value": 5, "edit": None})
            check("a value violating the active schema is a 400", result["mismatch_status"] == 400)
            check("a rejected set does not overwrite the previously-stored value", result["get_after_mismatch"] == {"value": 5, "edit": None})
            check("typeHint is ignored entirely for a validated key", result["get_with_hint_on_validated_key"] == {"value": 5, "edit": None})
        finally:
            handle.stop()


def test_self_get_manifest_reflects_live_widget_info():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            fake_window = _FakeGuiWindow(desk_dir, handle.event_mediator)
            handle.gui_bridge.attach(fake_window)
            base = f"http://{handle.host}:{handle.port}"
            result = {}

            def run_requests():
                live_widget = fake_window.get_widget_info("widget_a")
                live_widget.state_schema = {"counter": "number"}
                live_widget.desk_widget_loading_errors.append("Schema conflict: something went wrong")
                fake_window.get_widget_info = lambda widget_id, _cached=live_widget: _cached
                result["manifest"] = _request(
                    f"{base}/api/bridge/self/getManifest", handle.token, "widget_a", "inst-a"
                )

            _run_with_pumped_event_loop(run_requests)

            manifest = result["manifest"]
            check("self.getManifest() reflects the live state_schema", manifest["state_schema"] == {"counter": "number"})
            check(
                "self.getManifest() reflects live desk_widget_loading_errors, not a stale empty scan",
                manifest["desk_widget_loading_errors"] == ["Schema conflict: something went wrong"],
            )
        finally:
            handle.stop()


def test_bridge_client_has_type_hint_support():
    from desk.server.bridge_client import BRIDGE_CLIENT_TEMPLATE

    check("bridge client's state.get supports typeHint", "type_hint=" in BRIDGE_CLIENT_TEMPLATE)
    check("bridge client's state.set supports typeHint", "type_hint: typeHint" in BRIDGE_CLIENT_TEMPLATE)


test_bridge_api_schema_aware_state()
test_self_get_manifest_reflects_live_widget_info()
test_bridge_client_has_type_hint_support()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
