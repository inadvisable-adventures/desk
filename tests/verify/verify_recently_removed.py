"""Verifies TODO `454d718`: tombstones in the .desk file, tombstoning on both
close paths, revive/clear, change events, and the Recently Removed widget."""

import json
import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication(sys.argv)

from desk.desks import Desk, RemovedWidget, load_desk, save_desk  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.recently_removed import RECENTLY_REMOVED_CHANGED_EVENT, RECENTLY_REMOVED_MAX  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402

DeskWindow = desk.shell.window.DeskWindow
_KEEP_ALIVE = []


def _keep(mediator):
    """An EventSubscription's destroyed-callback calls mediator.unsubscribe_all
    when the widget is garbage collected; if the mediator was collected first
    (interpreter shutdown order is arbitrary) that raises and aborts the
    process. Keep every test mediator alive for the whole run."""
    _KEEP_ALIVE.append(mediator)
    return mediator


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


def _module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("rr_check", REPO_ROOT / "widgets" / "recently_removed" / "widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _module()


def tomb(i, **kw):
    base = dict(widget_id="editor", kind="python", label=f"Editor ({i})", instance_id=f"id{i}", state={"n": i}, width=400.0, height=300.0, removed_at=1000.0 + i)
    base.update(kw)
    return RemovedWidget(**base)


# -- desk file -----------------------------------------------------------------------


def test_desk_round_trip_and_old_files():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "t.desk"
        desk = Desk(path=path, recently_removed=[tomb(1), tomb(2)])
        save_desk(desk)
        loaded = load_desk(path)
        check("tombstones round-trip through the .desk file", loaded.recently_removed == [tomb(1), tomb(2)])
        data = json.loads(path.read_text())
        del data["recently_removed"]
        path.write_text(json.dumps(data))
        check("an old file with no key still loads, as an empty list", load_desk(path).recently_removed == [])


# -- window ------------------------------------------------------------------------------------


class _Stub:
    def __init__(self, directory):
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.current_desk = Desk(path=directory / "t.desk")
        self._widgets = {
            "editor": types.SimpleNamespace(kind="python", default_size=(480, 360)),
            "html1": types.SimpleNamespace(kind="html", default_size=(480, 360)),
        }
        self._event_mediator = _keep(EventMediator())
        self._event_mediator.subscribe("listener", RECENTLY_REMOVED_CHANGED_EVENT)
        self.local_storage = {}
        self.saves = 0
        self.placed = []
        self.bound = []
        self._counter = 0

    def add(self, widget_id="editor", size=(400, 300)):
        self._counter += 1
        iid = f"inst{self._counter}"
        content = QLabel(iid)
        content.widget_id = widget_id
        proxy = self.view.add_widget(content, title=iid, size=size, instance_id=iid)
        self.local_storage[iid] = {"saved": iid}
        return proxy.widget()

    def _display_name_for_instance(self, iid):
        return f"label-{iid}"

    def _get_widget_local_storage(self, frame):
        return self.local_storage.get(frame.instance_id, {})

    def save_current_desk(self):
        self.saves += 1

    def _place_widget(self, widget_id, widget, pos, size, local_storage_data=None, **kw):
        self.placed.append((widget_id, size, local_storage_data))
        return types.SimpleNamespace(instance_id=f"new{len(self.placed)}")

    def _bind_widget_local_storage(self, frame, data):
        self.bound.append((frame.instance_id, data))

    def events(self):
        return [e.payload for e in self._event_mediator.drain("listener")]


for name in ("_tombstone_widget", "get_recently_removed", "_publish_recently_removed", "revive_removed_widget", "clear_recently_removed", "close_widget_by_instance_id", "close_widget"):
    setattr(_Stub, name, getattr(DeskWindow, name))
_Stub.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id
_Stub._schedule_chromium_profile_cleanup = lambda self, iid: None
_Stub._confirm_fn = lambda self, t, m: (lambda: True)


def test_tombstone_on_both_close_paths():
    with tempfile.TemporaryDirectory() as d:
        win = _Stub(Path(d))
        a, b = win.add(size=(410, 310)), win.add("html1")
        win.close_widget(a)
        (entry,) = win.current_desk.recently_removed
        check("close button path tombstones id, kind, label, size and state", (entry.instance_id, entry.widget_id, entry.kind, entry.label, entry.state) == ("inst1", "editor", "python", "label-inst1", {"saved": "inst1"}) and (entry.width, entry.height) == (410, 310))
        check("with a removal time", entry.removed_at > 0)
        check("the desk was saved after the tombstone existed", win.saves == 1)
        win.close_widget_by_instance_id("inst2")
        check("the API path tombstones too, newest first", [r.instance_id for r in win.current_desk.recently_removed] == ["inst2", "inst1"] and win.current_desk.recently_removed[0].kind == "html")
        events = win.events()
        check("each removal publishes the entries without state", len(events) == 2 and "state" not in events[-1]["entries"][0] and [e["instance_id"] for e in events[-1]["entries"]] == ["inst2", "inst1"])


def test_cap_and_skipped_kinds():
    with tempfile.TemporaryDirectory() as d:
        win = _Stub(Path(d))
        for _ in range(RECENTLY_REMOVED_MAX + 5):
            win.close_widget_by_instance_id(win.add().instance_id)
        ids = [r.instance_id for r in win.current_desk.recently_removed]
        check("the list is capped, oldest dropped", len(ids) == RECENTLY_REMOVED_MAX and ids[0] == f"inst{RECENTLY_REMOVED_MAX + 5}" and "inst1" not in ids)
        win2 = _Stub(Path(d))
        for skipped in sorted(desk.shell.window.TEMP_UI_WIDGET_IDS) + [desk.shell.window.CRASH_LOG_WIDGET_ID]:
            win2.close_widget_by_instance_id(win2.add(skipped).instance_id)
        check("tempui-backed and crash-log widgets are never tombstoned", win2.current_desk.recently_removed == [])


def test_revive():
    with tempfile.TemporaryDirectory() as d:
        win = _Stub(Path(d))
        win.current_desk.recently_removed = [tomb(1, state={"k": "v"}, width=555.0, height=333.0), tomb(2, widget_id="gone")]
        win.events()
        new_id = win.revive_removed_widget("id1")
        check("a brand-new instance is placed with the saved state and size", new_id == "new1" and win.placed == [("editor", (555, 333), {"k": "v"})])
        check("its local storage is seeded synchronously after placement", win.bound == [("new1", {"k": "v"})])
        check("the tombstone is removed, the desk saved, an event published", [r.instance_id for r in win.current_desk.recently_removed] == ["id2"] and win.saves == 1 and len(win.events()) == 1)
        check("a kind that no longer exists can't be revived, and its tombstone stays", win.revive_removed_widget("id2") is None and len(win.current_desk.recently_removed) == 1)
        check("an unknown id returns None", win.revive_removed_widget("nope") is None)
        win.current_desk.recently_removed = [tomb(3, width=0.0, height=0.0)]
        win.revive_removed_widget("id3")
        check("a tombstone with no recorded size falls back to the widget's default", win.placed[-1][1] == (480, 360))


def test_clear():
    with tempfile.TemporaryDirectory() as d:
        win = _Stub(Path(d))
        win.current_desk.recently_removed = [tomb(1), tomb(2)]
        win.events()
        win.clear_recently_removed()
        check("clearing empties the list, saves and publishes an empty event", win.current_desk.recently_removed == [] and win.saves == 1 and win.events() == [{"entries": []}])


# -- widget ----------------------------------------------------------------------------------------


class _WindowFor:
    def __init__(self, entries):
        self.entries = entries
        self.calls = []

    def get_recently_removed(self):
        return self.entries

    def revive_removed_widget(self, iid):
        self.calls.append(("revive", iid))

    def clear_recently_removed(self):
        self.calls.append(("clear",))


def entries(*specs):
    return [{"instance_id": i, "widget_id": "editor", "kind": "python", "label": l, "removed_at": 0.0} for i, l in specs]


def test_relative_time():
    r = module.relative_time
    check("relative times", [r(0, 30), r(0, 120), r(0, 7300), r(0, 200000)] == ["just now", "2 min ago", "2 h ago", "2 d ago"])


def test_widget():
    window = _WindowFor(entries(("a", "Editor (a)"), ("b", "Todo (b)")))
    previous = current_context.get_main_window()
    current_context.set_main_window(window)
    try:
        widget = module.build()
        check("a row per tombstone with label and kind", widget._list.count() == 2 and "Editor (a) (python)" in widget._list.itemWidget(widget._list.item(0)).label.text())
        check("the summary counts them", widget._status_label.text() == "2 recently removed.")
        widget._list.itemWidget(widget._list.item(1)).revive_button.click()
        check("Revive asks the window to revive that instance", window.calls == [("revive", "b")])

        widget._confirm_clear = lambda: False
        widget._clear_button.click()
        check("declining the confirmation clears nothing", window.calls == [("revive", "b")])
        widget._confirm_clear = lambda: True
        widget._clear_button.click()
        check("confirming clears", window.calls[-1] == ("clear",))

        mediator = _keep(EventMediator())
        widget.bind_event_mediator("rr-1", mediator)
        mediator.publish(RECENTLY_REMOVED_CHANGED_EVENT, {"entries": entries(("z", "Z"))}, "desk")
        widget._subscription._poll()
        check("an event replaces the list", widget._list.count() == 1)
        mediator.publish(RECENTLY_REMOVED_CHANGED_EVENT, {"entries": []}, "desk")
        widget._subscription._poll()
        check("empty shows the empty message and disables Clear", widget._status_label.text() == module.EMPTY_STATUS and not widget._clear_button.isEnabled())
        widget._on_mediated_event("other", {"entries": entries(("q", "Q"))}, "x")
        check("unrelated events are ignored", widget._list.count() == 0)
    finally:
        if previous is not None:
            current_context.set_main_window(previous)


def test_confirm_uses_the_popups_service():
    widget = module.build()
    previous = current_context.get_popup_opener()
    seen = []
    current_context.set_popup_opener(lambda title, text, buttons, default: seen.append((title, buttons, default)) or "Yes")
    try:
        check("confirming goes through the desk-internal popups service", widget._confirm_clear() is True and seen[0][1:] == (["Yes", "No"], "No"))
    finally:
        if previous is not None:
            current_context.set_popup_opener(previous)


test_desk_round_trip_and_old_files()
test_tombstone_on_both_close_paths()
test_cap_and_skipped_kinds()
test_revive()
test_clear()
test_relative_time()
test_widget()
test_confirm_uses_the_popups_service()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
