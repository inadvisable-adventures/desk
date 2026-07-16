import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.event_mediator import MediatedEvent  # noqa: E402
from desk.shell import current_context  # noqa: E402


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


event_viewer_widget = load_widget_module(
    "event_viewer_verify_mod", "/Users/mphair/inadvisable-adventures/desk/widgets/event_viewer/widget.py"
)

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


# ---------- EventViewerWidget ----------


def test_placeholder_shown_with_no_event():
    widget = event_viewer_widget.build()
    check("placeholder shown initially", widget._payload_view.toPlainText() == event_viewer_widget.PLACEHOLDER_TEXT)
    check("timestamp label shows no-value placeholder", widget._timestamp_label.text() == "—")


def test_set_event_populates_fields():
    widget = event_viewer_widget.build()
    event = MediatedEvent(
        timestamp="2026-07-16T10:00:00", name="todo.item_added",
        sender_instance_id="abc12345", payload={"id": "x", "nested": [1, 2, 3]},
    )
    widget.set_event(event)
    check("timestamp populated", widget._timestamp_label.text() == "2026-07-16T10:00:00")
    check("name populated", widget._name_label.text() == "todo.item_added")
    check("sender populated", widget._sender_label.text() == "abc12345")
    payload_text = widget._payload_view.toPlainText()
    check("payload is pretty-printed (multi-line)", "\n" in payload_text)
    check("payload content correct", '"nested"' in payload_text and '"id": "x"' in payload_text)


def test_set_event_with_none_payload():
    widget = event_viewer_widget.build()
    event = MediatedEvent(timestamp="t", name="n", sender_instance_id="s", payload=None)
    widget.set_event(event)
    check("None payload shows as empty string", widget._payload_view.toPlainText() == "")


# ---------- EventLogWidget double-click -> Event Viewer ----------


def test_double_click_opens_event_viewer_with_correct_event():
    event_log_widget = load_widget_module(
        "event_log_verify_mod", "/Users/mphair/inadvisable-adventures/desk/widgets/event_log/widget.py"
    )

    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        log_path = temp_dir / "MEDIATED-EVENT-LOG.tsv"
        log_path.write_text(
            "timestamp\tevent_name\tsender_instance_id\tpayload\n"
            '2026-07-16T10:00:00\ttodo.item_added\tabc12345\t{"id": "x"}\n'
        )
        current_context.set_current_desk_directory(directory)
        try:
            opened = {}

            def fake_opener(widget_id):
                opened["widget_id"] = widget_id
                return opened.setdefault("viewer", event_viewer_widget.build())

            current_context.set_widget_opener(fake_opener)
            try:
                log_widget = event_log_widget.build()
                check("log table has one row", log_widget._table.rowCount() == 1)
                item = log_widget._table.item(0, 0)
                log_widget._open_event_viewer(item)
                check("opener called with event_viewer", opened.get("widget_id") == "event_viewer")
                viewer = opened["viewer"]
                check("viewer's timestamp set from the double-clicked row", viewer._timestamp_label.text() == "2026-07-16T10:00:00")
                check("viewer's name set from the double-clicked row", viewer._name_label.text() == "todo.item_added")
                check("viewer's sender set from the double-clicked row", viewer._sender_label.text() == "abc12345")
            finally:
                current_context.set_widget_opener(None)
        finally:
            current_context.set_current_desk_directory(None)


def test_broken_opener_or_missing_set_event_does_not_raise():
    event_log_widget = load_widget_module(
        "event_log_verify_mod", "/Users/mphair/inadvisable-adventures/desk/widgets/event_log/widget.py"
    )

    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        log_path = temp_dir / "MEDIATED-EVENT-LOG.tsv"
        log_path.write_text(
            "timestamp\tevent_name\tsender_instance_id\tpayload\n"
            "2026-07-16T10:00:00\ttodo.item_added\tabc12345\tnull\n"
        )
        current_context.set_current_desk_directory(directory)
        try:
            # Case 1: no opener registered at all.
            current_context.set_widget_opener(None)
            log_widget = event_log_widget.build()
            try:
                log_widget._open_event_viewer(log_widget._table.item(0, 0))
                check("no opener registered: no raise", True)
            except Exception as e:  # noqa: BLE001
                check(f"no opener registered: no raise (raised {e!r})", False)

            # Case 2: opener returns something with no set_event method.
            class _NoSetEvent:
                pass

            current_context.set_widget_opener(lambda widget_id: _NoSetEvent())
            try:
                log_widget._open_event_viewer(log_widget._table.item(0, 0))
                check("opener returns object without set_event: no raise", True)
            except Exception as e:  # noqa: BLE001
                check(f"opener returns object without set_event: no raise (raised {e!r})", False)

            # Case 3: set_event itself raises.
            class _BrokenViewer:
                def set_event(self, event):
                    raise RuntimeError("boom")

            current_context.set_widget_opener(lambda widget_id: _BrokenViewer())
            try:
                log_widget._open_event_viewer(log_widget._table.item(0, 0))
                check("broken set_event: exception caught, no raise", True)
            except Exception as e:  # noqa: BLE001
                check(f"broken set_event: exception caught, no raise (raised {e!r})", False)
        finally:
            current_context.set_widget_opener(None)
            current_context.set_current_desk_directory(None)


test_placeholder_shown_with_no_event()
test_set_event_populates_fields()
test_set_event_with_none_payload()
test_double_click_opens_event_viewer_with_correct_event()
test_broken_opener_or_missing_set_event_does_not_raise()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
