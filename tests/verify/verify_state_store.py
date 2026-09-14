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
# A hardcoded absolute path here would silently test a *different*
# checkout's code if one happens to exist alongside this one -- see
# LEARNINGS.md's "Some tests/verify/ scripts hardcode a sibling
# checkout's absolute path" entry. This is the one script directly
# gating TODO 224fbc9's own verification, so fixed here; the ~28 other
# affected scripts remain tracked separately in PARKINGLOT.md.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk, StateEntry, StateHistoryEntry, desk_state_dict, load_desk, save_desk  # noqa: E402
from desk.schema_registry import SchemaRegistry  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402

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


# ---------- TODO 224fbc9: _capture_desk_state (and friends) must not
# drop Desk.state -- see
# ../FEEDBACK/FEEDBACK-DESK-state-store-wiped-by-capture-desk-state-2026-09-12-2100.md
# ----------


class _FakeProxy:
    def pos(self):
        p = type("P", (), {})()
        p.x = lambda: 0.0
        p.y = lambda: 0.0
        return p

    def size(self):
        s = type("S", (), {})()
        s.width = lambda: 100.0
        s.height = lambda: 100.0
        return s


class _FakeContent:
    widget_id = "editor"


class _FakeFrame:
    def __init__(self, instance_id):
        self.instance_id = instance_id
        self.content = _FakeContent()
        self.locked = False
        self.placed_content_hash = None

    def graphicsProxyWidget(self):
        return _FakeProxy()


class _FakeView:
    def __init__(self, frames):
        self._frames = frames

    def get_view_state(self):
        return 0.0, 0.0, 1.0


class _FakeCaptureWindow:
    def __init__(self, current_desk, frames=()):
        self.view = _FakeView(list(frames))
        self.current_desk = current_desk

    def _get_widget_local_storage(self, frame):
        return {}


_FakeCaptureWindow._capture_desk_state = DeskWindow._capture_desk_state
_FakeCaptureWindow.get_state_dict = DeskWindow.get_state_dict


def _desk_with_everything(**overrides):
    from desk.file_type_registry import FileTypeRegistryEntry
    from desk.installed_jobs import InstalledJobDefinition
    from desk.temp_ui import CustomWidgetDefinition

    kwargs = dict(
        path=Path("/tmp/everything.desk"),
        state={"raycaster.camera.camera-1": StateEntry(value={"x": 1}, edit=None)},
        custom_widgets=[CustomWidgetDefinition(keyword="marker", label="Marker", html_b64="")],
        file_type_registry=[FileTypeRegistryEntry(extensions=[".marker"])],
        installed_jobs=[InstalledJobDefinition(name="marker", version_hash="abc123", installed_at="2026-01-01T00:00:00")],
    )
    kwargs.update(overrides)
    return Desk(**kwargs)


def test_capture_desk_state_carries_over_state():
    win = _FakeCaptureWindow(_desk_with_everything())
    captured = win._capture_desk_state()
    check("_capture_desk_state carries over state", captured.state == win.current_desk.state)
    check("_capture_desk_state still carries over custom_widgets", captured.custom_widgets == win.current_desk.custom_widgets)
    check("_capture_desk_state still carries over file_type_registry", captured.file_type_registry == win.current_desk.file_type_registry)
    check("_capture_desk_state still carries over installed_jobs", captured.installed_jobs == win.current_desk.installed_jobs)


def test_get_state_dict_reflects_live_state():
    win = _FakeCaptureWindow(_desk_with_everything())
    result = win.get_state_dict()
    check("get_state_dict (workspace.getState) reports the real, non-empty state", result["state"] != {})
    check(
        "get_state_dict's reported state matches the live store",
        set(result["state"]) == {"raycaster.camera.camera-1"},
    )


def test_close_widget_does_not_wipe_state():
    """Reproduces the reported incident: a Desk with two placed widgets
    and non-empty state, one widget closed (removed from view._frames,
    matching what close_widget/close_widget_by_instance_id do before
    calling save_current_desk), then a save -- state must survive."""
    frame_a = _FakeFrame("instance-a")
    frame_b = _FakeFrame("instance-b")
    desk = _desk_with_everything()
    win = _FakeCaptureWindow(desk, frames=[frame_a, frame_b])

    before = win._capture_desk_state()
    check("state present before any widget is closed", before.state != {})

    # Simulate closing frame_b, then the save that follows (the real
    # save_current_desk does exactly this: recapture, then replace
    # self.current_desk with the freshly-captured Desk).
    win.view._frames.remove(frame_b)
    win.current_desk = win._capture_desk_state()

    check("closing a widget does not wipe the live state store", win.current_desk.state != {})
    check("state value itself is unchanged", win.current_desk.state["raycaster.camera.camera-1"].value == {"x": 1})
    check("the closed widget is actually gone from the captured widgets", len(win.current_desk.widgets) == 1)


class _FakeDeskOpsWindow:
    """Exercises change_current_desk_directory/rename_current_desk's
    own carry-over behavior directly -- save_current_desk/
    _refresh_picker/_provision_temp_ui/_warn are stubbed no-ops (real
    add_to_mru/GUI refresh are irrelevant to what's being checked here
    and add_to_mru writes to the real ~/.desk/recent_desks.json, which
    a verify script must not touch as a side effect)."""

    def __init__(self, current_desk):
        self.current_desk = current_desk

    def save_current_desk(self):
        pass

    def _refresh_picker(self):
        pass

    def _provision_temp_ui(self, provisioning=None):
        pass

    def _warn(self, title, message):
        pass


_FakeDeskOpsWindow.change_current_desk_directory = DeskWindow.change_current_desk_directory
_FakeDeskOpsWindow.rename_current_desk = DeskWindow.rename_current_desk


def test_change_directory_carries_over_state_and_other_fields():
    with tempfile.TemporaryDirectory() as d:
        old_dir = Path(d) / "old"
        new_dir = Path(d) / "new"
        old_dir.mkdir()
        new_dir.mkdir()
        desk = _desk_with_everything(path=old_dir / "everything.desk")
        win = _FakeDeskOpsWindow(desk)
        win.change_current_desk_directory(new_dir, confirm=lambda: True)
        check("change_current_desk_directory updates path", win.current_desk.path == new_dir / "everything.desk")
        check("change_current_desk_directory carries over state", win.current_desk.state == desk.state)
        check("change_current_desk_directory carries over custom_widgets", win.current_desk.custom_widgets == desk.custom_widgets)
        check("change_current_desk_directory carries over file_type_registry", win.current_desk.file_type_registry == desk.file_type_registry)
        check("change_current_desk_directory carries over installed_jobs", win.current_desk.installed_jobs == desk.installed_jobs)


def test_rename_carries_over_state_and_other_fields():
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        old_path = directory / "old-name.desk"
        old_path.write_text("{}")
        desk = _desk_with_everything(path=old_path)
        win = _FakeDeskOpsWindow(desk)
        with patch("desk.shell.window.add_to_mru"):
            win.rename_current_desk("new-name")
        check("rename_current_desk updates path", win.current_desk.path == directory / "new-name.desk")
        check("rename_current_desk actually renamed the file on disk", win.current_desk.path.is_file())
        check("rename_current_desk carries over state", win.current_desk.state == desk.state)
        check("rename_current_desk carries over custom_widgets", win.current_desk.custom_widgets == desk.custom_widgets)
        check("rename_current_desk carries over file_type_registry", win.current_desk.file_type_registry == desk.file_type_registry)
        check("rename_current_desk carries over installed_jobs", win.current_desk.installed_jobs == desk.installed_jobs)


def test_capture_then_save_then_reload_round_trips_state():
    """The feedback's 'structural finding': every .desk file's state was
    always {} on disk, precisely because _capture_desk_state wiped it
    before save_desk ever saw it. Proves the fix closes that too."""
    with tempfile.TemporaryDirectory() as d:
        desk = _desk_with_everything(path=Path(d) / "roundtrip.desk")
        win = _FakeCaptureWindow(desk)
        captured = win._capture_desk_state()
        save_desk(captured)
        reloaded = load_desk(captured.path)
        check("a real save/reload round-trip no longer loses state", reloaded.state != {})
        check(
            "round-tripped state value matches what was live",
            reloaded.state["raycaster.camera.camera-1"].value == {"x": 1},
        )


test_capture_desk_state_carries_over_state()
test_get_state_dict_reflects_live_state()
test_close_widget_does_not_wipe_state()
test_change_directory_carries_over_state_and_other_fields()
test_rename_carries_over_state_and_other_fields()
test_capture_then_save_then_reload_round_trips_state()


# ---------- Bridge API, over real HTTP ----------


class _FakeDesk:
    def __init__(self, directory):
        self.directory = directory
        self.state = {}


class _FakeGuiWindow:
    """get_state/set_state/get_state_history are the real
    DeskWindow methods (unbound, called against this lightweight stand
    -in) rather than a hand-rolled copy -- TODO af7898b added a
    `type_hint` parameter and a `self._schema_registry` reference to
    both, so a duplicate copy here would have silently drifted out of
    sync with the real signature (as it briefly did, causing every
    request in this file to 500 until fixed)."""

    def __init__(self, directory):
        self.current_desk = _FakeDesk(directory)
        self._schema_registry = SchemaRegistry()

    def get_widget_info(self, widget_id):
        from desk.widgets import WidgetInfo

        capabilities = [] if widget_id == "no_capability_widget" else ["state"]
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


def test_bridge_api_state_get_set_history_and_events():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        desk_dir = Path(d) / "my-project"
        desk_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            fake_window = _FakeGuiWindow(desk_dir)
            fake_window._event_mediator = handle.event_mediator
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
