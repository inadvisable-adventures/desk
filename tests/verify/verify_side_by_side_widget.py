import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")

from desk.shell import current_context  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.widgets import discover_widgets  # noqa: E402
from desk.shell.event_broker import EventSubscription  # noqa: E402

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


catalog = discover_widgets(REPO_ROOT / "widgets")
mediator = EventMediator()
broker = HotReloadBroker()

current_context.set_event_mediator(mediator)
current_context.set_hot_reload_broker(broker)
current_context.set_widget_catalog_provider(
    lambda: [
        {"id": wid, "name": info.name, "path": str(info.path), "entry": info.entry}
        for wid, info in catalog.items()
        if info.kind == "python"
    ]
)

spec = importlib.util.spec_from_file_location("side_by_side_check", REPO_ROOT / "widgets/side_by_side/widget.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# ---------- current_context wiring ----------

check("widget catalog provider returns only python-kind entries", all(
    catalog[e["id"]].kind == "python" for e in current_context.get_widget_catalog_provider()()
))
check("widget catalog includes editor", any(e["id"] == "editor" for e in current_context.get_widget_catalog_provider()()))
check("hot reload broker retrievable", current_context.get_hot_reload_broker() is broker)


# ---------- choosing widgets for both slots ----------

def test_choose_widgets_and_bind_mediator():
    widget = mod.SideBySideWidget()
    check("splitter starts with 2 placeholders", widget._splitter.count() == 2)

    widget._choose_widget(0, "event_poster")
    widget._choose_widget(1, "event_poster")

    check("slot 0 built a real host", widget._slots[0].host is not None)
    check("slot 1 built a real host", widget._slots[1].host is not None)
    check("slot 0 content is an EventPosterWidget", type(widget._slots[0].host.current).__name__ == "EventPosterWidget")

    id0 = widget._slots[0].instance_id
    id1 = widget._slots[1].instance_id
    check("slots got distinct instance ids", id0 != id1 and id0 is not None and id1 is not None)

    # event_poster only ever publishes (never subscribes -- see its own
    # bind_event_mediator docstring), so list_subscriptions() has
    # nothing to show for it; the real proof the container's slots are
    # on the shared bus is that a publish from slot 0's own bound
    # instance id is genuinely delivered to a third, independent
    # subscriber below.
    import time

    third = EventSubscription(mediator, "third-observer", names=["ping"])
    received = []
    third.message_received.connect(lambda name, payload, sender: received.append((name, payload, sender)))

    poster0 = widget._slots[0].host.current
    poster0._name_field.setText("ping")
    poster0._payload_field.setPlainText('"hello"')
    poster0._publish()

    deadline = time.monotonic() + 3.0
    while not received and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    check("third-party subscriber received the publish from slot 0", len(received) == 1)
    if received:
        check("received event carries slot 0's own instance id as sender", received[0][2] == id0)

    widget.deleteLater()
    return widget


test_choose_widgets_and_bind_mediator()


def test_repick_unsubscribes_old_instance():
    widget = mod.SideBySideWidget()
    widget._choose_widget(0, "project_files")
    old_id = widget._slots[0].instance_id
    check("old instance subscribed", old_id in mediator.list_subscriptions())

    widget._choose_widget(0, "editor")
    new_id = widget._slots[0].instance_id
    check("re-picking mints a new instance id", new_id != old_id)
    check("old instance id fully unsubscribed", mediator.list_subscriptions().get(old_id, set()) == set() or old_id not in mediator.list_subscriptions())
    check("slot now hosts an editor", type(widget._slots[0].host.current).__name__ == "EditorWidget")
    widget.deleteLater()


test_repick_unsubscribes_old_instance()


def test_swap_preserves_instance_identity():
    widget = mod.SideBySideWidget()
    widget._choose_widget(0, "event_poster")
    widget._choose_widget(1, "editor")
    id0_before = widget._slots[0].instance_id
    id1_before = widget._slots[1].instance_id
    host0_before = widget._slots[0].host
    host1_before = widget._slots[1].host

    check("initial order is [0, 1]", widget._order == [0, 1])
    check("position 0 shows slot 0's host", widget._splitter.widget(0) is host0_before)
    check("position 1 shows slot 1's host", widget._splitter.widget(1) is host1_before)

    widget._swap()

    check("order reversed after swap", widget._order == [1, 0])
    check("position 0 now shows slot 1's host", widget._splitter.widget(0) is host1_before)
    check("position 1 now shows slot 0's host", widget._splitter.widget(1) is host0_before)
    check("slot 0's instance id unchanged by swap", widget._slots[0].instance_id == id0_before)
    check("slot 1's instance id unchanged by swap", widget._slots[1].instance_id == id1_before)
    check("swap did not rebuild either host", widget._slots[0].host is host0_before and widget._slots[1].host is host1_before)
    widget.deleteLater()


test_swap_preserves_instance_identity()


def test_orientation_toggle():
    widget = mod.SideBySideWidget()
    from PyQt6.QtCore import Qt
    check("starts horizontal", widget._splitter.orientation() == Qt.Orientation.Horizontal)
    widget._toggle_orientation()
    check("toggled to vertical", widget._splitter.orientation() == Qt.Orientation.Vertical)
    widget._toggle_orientation()
    check("toggled back to horizontal", widget._splitter.orientation() == Qt.Orientation.Horizontal)
    widget.deleteLater()


test_orientation_toggle()


# ---------- persistence round-trip, including a nested child's own local storage ----------

def test_persistence_roundtrip_with_nested_child_storage():
    widget = mod.SideBySideWidget()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "file.txt"
        path.write_text("hello from side by side test\n")

        widget._choose_widget(0, "editor")
        editor = widget._slots[0].host.current
        editor.set_file(path)

        widget._choose_widget(1, "event_poster")
        widget._swap()

        saved = widget.get_widget_local_storage()
        check("saved payload has orientation/order/slots", set(saved.keys()) == {"orientation", "order", "slots"})
        check("saved order reflects the swap", saved["order"] == [1, 0])
        check("slot 0's nested editor local storage captured", "path" in saved["slots"][0]["local_storage"])
        check(
            "captured path matches the opened file",
            saved["slots"][0]["local_storage"]["path"] == str(path),
        )
        widget.deleteLater()

        # A totally fresh instance restoring this payload should
        # reconstruct both slots, including the nested editor's own file.
        widget2 = mod.SideBySideWidget()
        widget2.set_widget_local_storage(saved)
        check("restored order matches", widget2._order == [1, 0])
        check("restored slot 0 has the editor widget id", widget2._slots[0].widget_id == "editor")
        check("restored slot 0 instance id matches the original", widget2._slots[0].instance_id == saved["slots"][0]["instance_id"])
        restored_editor = widget2._slots[0].host.current
        check(
            "restored editor's own file re-opened via nested local storage",
            str(getattr(restored_editor, "_current_path", None)) == str(path),
        )
        widget2.deleteLater()


test_persistence_roundtrip_with_nested_child_storage()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
