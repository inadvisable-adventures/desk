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

from desk.desks import Desk, StateEntry, StateHistoryEntry, desk_state_dict, load_desk, save_desk  # noqa: E402
from desk.server.runner import start_server  # noqa: E402

passed = 0
failed = 0

STATE_HISTORY_MAX_ENTRIES = 50


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


# ---------- data model round-trip ----------


def test_desk_persists_state():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        entry = StateEntry(
            value={"count": 2}, edit="incremented",
            history=[StateHistoryEntry(value={"count": 1}, edit=None), StateHistoryEntry(value={"count": 2}, edit="incremented")],
        )
        desk = Desk(path=directory / "test.desk", state={"counter": entry})
        save_desk(desk)
        reloaded = load_desk(desk.path)
        restored = reloaded.state["counter"]
        check("value round-trips through save/load", restored.value == {"count": 2})
        check("edit round-trips through save/load", restored.edit == "incremented")
        check("history round-trips through save/load", [(h.value, h.edit) for h in restored.history] == [({"count": 1}, None), ({"count": 2}, "incremented")])

        state_dict = desk_state_dict(desk)
        check("desk_state_dict includes state", state_dict["state"]["counter"]["value"] == {"count": 2})


def test_old_desk_file_without_state_defaults_to_empty():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "old.desk"
        path.write_text('{"widgets": []}')
        desk = load_desk(path)
        check("old .desk file with no state key defaults to {}", desk.state == {})


# ---------- Bridge API, over real HTTP ----------


class _FakeDesk:
    def __init__(self, directory):
        self.directory = directory
        self.state = {}


class _FakeGuiWindow:
    def __init__(self, directory):
        self.current_desk = _FakeDesk(directory)

    def get_widget_info(self, widget_id):
        from desk.widgets import WidgetInfo

        capabilities = [] if widget_id == "no_capability_widget" else ["state"]
        return WidgetInfo(
            id=widget_id, path=Path("."), kind="html", name=widget_id, entry="index.html",
            capabilities=capabilities, default_size=None,
        )

    def get_state(self, key):
        entry = self.current_desk.state.get(key)
        if entry is None:
            return {"value": None, "edit": None}
        return {"value": entry.value, "edit": entry.edit}

    def set_state(self, key, value, edit, instance_id):
        entry = self.current_desk.state.get(key)
        if entry is None:
            entry = StateEntry(value=value, edit=edit)
            self.current_desk.state[key] = entry
        else:
            entry.value = value
            entry.edit = edit
        entry.history.append(StateHistoryEntry(value=value, edit=edit))
        del entry.history[:-STATE_HISTORY_MAX_ENTRIES]
        self._mediator.publish("desk.state.changed", {"key": key, "value": value, "edit": edit}, sender_instance_id=instance_id)

    def get_state_history(self, key, limit):
        entry = self.current_desk.state.get(key)
        if entry is None:
            return []
        recent = entry.history[-limit:] if limit > 0 else []
        return [{"value": h.value, "edit": h.edit} for h in reversed(recent)]


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


def test_bridge_api_state_get_set_history_and_events():
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
                # get on a never-set key
                result["unset_get"] = _request(
                    f"{base}/api/bridge/state/get?key=counter", handle.token, "widget_a", "inst-a"
                )

                # set with no edit given
                result["set_no_edit"] = _request(
                    f"{base}/api/bridge/state/set", handle.token, "widget_a", "inst-a",
                    method="POST", body={"key": "counter", "value": 1},
                )
                result["get_after_no_edit_set"] = _request(
                    f"{base}/api/bridge/state/get?key=counter", handle.token, "widget_a", "inst-a"
                )

                # subscribe a second instance, then set from the first, with an edit
                handle.event_mediator.subscribe("inst-listener", "desk.state.changed")
                result["set_with_edit"] = _request(
                    f"{base}/api/bridge/state/set", handle.token, "widget_a", "inst-a",
                    method="POST", body={"key": "counter", "value": 2, "edit": "incremented"},
                )
                result["get_after_edit_set"] = _request(
                    f"{base}/api/bridge/state/get?key=counter", handle.token, "widget_a", "inst-a"
                )
                result["change_event"] = handle.event_mediator.poll("inst-listener", timeout=5)

                # the setting instance itself doesn't get the change echoed back
                handle.event_mediator.subscribe("inst-a", "desk.state.changed")
                result["own_echo"] = handle.event_mediator.poll("inst-a", timeout=1)

                # history: write past STATE_HISTORY_MAX_ENTRIES total writes to one key
                for i in range(3, STATE_HISTORY_MAX_ENTRIES + 5):
                    _request(
                        f"{base}/api/bridge/state/set", handle.token, "widget_a", "inst-a",
                        method="POST", body={"key": "counter", "value": i},
                    )
                result["full_history"] = _request(
                    f"{base}/api/bridge/state/getHistory?key=counter", handle.token, "widget_a", "inst-a"
                )
                result["limited_history"] = _request(
                    f"{base}/api/bridge/state/getHistory?key=counter&limit=3", handle.token, "widget_a", "inst-a"
                )
                result["oversized_limit_history"] = _request(
                    f"{base}/api/bridge/state/getHistory?key=counter&limit=99999", handle.token, "widget_a", "inst-a"
                )

                # missing capability
                result["no_cap_get_status"] = _request_expect_status(
                    f"{base}/api/bridge/state/get?key=counter", handle.token, "no_capability_widget", "inst-b"
                )
                result["no_cap_set_status"] = _request_expect_status(
                    f"{base}/api/bridge/state/set", handle.token, "no_capability_widget", "inst-b",
                    method="POST", body={"key": "counter", "value": 1},
                )

            _run_with_pumped_event_loop(run_requests)

            check("get on unset key returns {value: None, edit: None}", result["unset_get"] == {"value": None, "edit": None})
            check("set returns ok", result["set_no_edit"] == {"ok": True})
            check("set with no edit given defaults it to None", result["get_after_no_edit_set"] == {"value": 1, "edit": None})
            check("set with an edit round-trips through get", result["get_after_edit_set"] == {"value": 2, "edit": "incremented"})

            event = result["change_event"]
            check("desk.state.changed delivered to a subscribed other instance", event is not None and event.name == "desk.state.changed")
            check("event payload carries key/value/edit", event.payload == {"key": "counter", "value": 2, "edit": "incremented"})
            check("event sender is the writing instance", event.sender_instance_id == "inst-a")
            check("the writing instance does not receive its own change", result["own_echo"] is None)

            full_history = result["full_history"]["history"]
            check(f"history is bounded to {STATE_HISTORY_MAX_ENTRIES} entries", len(full_history) == STATE_HISTORY_MAX_ENTRIES)
            check("history is returned latest-first", full_history[0]["value"] == STATE_HISTORY_MAX_ENTRIES + 4)
            check("oldest entries are evicted", full_history[-1]["value"] == 5)

            limited_history = result["limited_history"]["history"]
            check("a limit smaller than the full history is honored", [h["value"] for h in limited_history] == [STATE_HISTORY_MAX_ENTRIES + 4, STATE_HISTORY_MAX_ENTRIES + 3, STATE_HISTORY_MAX_ENTRIES + 2])

            oversized_history = result["oversized_limit_history"]["history"]
            check("a limit larger than what exists returns everything without error", len(oversized_history) == STATE_HISTORY_MAX_ENTRIES)

            check("get without the state capability is a 403", result["no_cap_get_status"] == 403)
            check("set without the state capability is a 403", result["no_cap_set_status"] == 403)
        finally:
            handle.stop()


def test_bridge_client_has_state_namespace():
    from desk.server.bridge_client import BRIDGE_CLIENT_TEMPLATE

    check("bridge client declares state.get", "/api/bridge/state/get?key=" in BRIDGE_CLIENT_TEMPLATE)
    check("bridge client declares state.set", '"/api/bridge/state/set"' in BRIDGE_CLIENT_TEMPLATE)
    check("bridge client declares state.getHistory", "/api/bridge/state/getHistory?key=" in BRIDGE_CLIENT_TEMPLATE)


test_desk_persists_state()
test_old_desk_file_without_state_defaults_to_empty()
test_bridge_api_state_get_set_history_and_events()
test_bridge_client_has_state_namespace()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
