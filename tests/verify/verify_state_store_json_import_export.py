import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.schema_registry import SchemaRegistry  # noqa: E402
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


class _FakeWindow:
    def __init__(self, directory):
        self.current_desk = Desk(path=directory / "test.desk")
        self._event_mediator = EventMediator()
        self._schema_registry = SchemaRegistry(self._event_mediator)


for name in ("get_state", "set_state", "get_state_history", "export_state_json", "import_state_json"):
    setattr(_FakeWindow, name, getattr(DeskWindow, name))


def test_export_import_round_trips_value_edit_and_history():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win.set_state("counter", 1, "first", "inst-a")
        win.set_state("counter", 2, "second", "inst-a")
        win.set_state("raw", "hello", None, "inst-a")

        export_path = directory / "export.json"
        error = win.export_state_json(export_path)
        check("export succeeds", error is None)
        check("a real file is written", export_path.is_file())

        win2 = _FakeWindow(directory)
        error = win2.import_state_json(export_path)
        check("import succeeds", error is None)
        check("counter's current value round-trips", win2.get_state("counter") == {"value": 2, "edit": "second"})
        check("raw's current value round-trips", win2.get_state("raw") == {"value": "hello", "edit": None})
        check(
            "counter's history round-trips latest-first",
            win2.get_state_history("counter", 50) == [{"value": 2, "edit": "second"}, {"value": 1, "edit": "first"}],
        )


def test_schema_violating_key_refuses_the_whole_import():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        source = _FakeWindow(directory)
        source.set_state("counter", "not a number", None, "inst-a")
        source.set_state("raw", "fine", None, "inst-a")
        export_path = directory / "export.json"
        source.export_state_json(export_path)

        target = _FakeWindow(directory)
        target._schema_registry.register_permanent("counter", "number", "builtin_widget")
        error = target.import_state_json(export_path)
        check("a schema-violating key refuses the whole import", error is not None and "counter" in error)
        check("the otherwise-valid key was not applied either (all-or-nothing)", target.get_state("raw")["value"] is None)


def test_non_validated_key_imports_unchanged():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        source = _FakeWindow(directory)
        source.set_state("raw", {"nested": [1, 2, 3]}, None, "inst-a")
        export_path = directory / "export.json"
        source.export_state_json(export_path)

        target = _FakeWindow(directory)
        error = target.import_state_json(export_path)
        check("a key with no active schema imports without error", error is None)
        check("its value is exactly preserved", target.get_state("raw")["value"] == {"nested": [1, 2, 3]})


def test_key_absent_from_file_survives_untouched():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        source = _FakeWindow(directory)
        source.set_state("only_in_file", "x", None, "inst-a")
        export_path = directory / "export.json"
        source.export_state_json(export_path)

        target = _FakeWindow(directory)
        target.set_state("only_in_target", "y", None, "inst-a")
        target.import_state_json(export_path)
        check("a key already in the target but absent from the file survives", target.get_state("only_in_target")["value"] == "y")
        check("a key from the file is applied too", target.get_state("only_in_file")["value"] == "x")


def test_import_publishes_desk_state_changed_per_changed_key():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        source = _FakeWindow(directory)
        source.set_state("a", 1, None, "inst-a")
        source.set_state("b", 2, None, "inst-a")
        export_path = directory / "export.json"
        source.export_state_json(export_path)

        target = _FakeWindow(directory)
        target._event_mediator.subscribe("listener", "desk.state.changed")

        error = target.import_state_json(export_path)
        check("import succeeds", error is None)

        received = []
        for _ in range(2):
            event = target._event_mediator.poll("listener", timeout=2)
            if event is not None:
                received.append(event)
        keys = {event.payload["key"] for event in received}
        check("desk.state.changed is published for each imported key", keys == {"a", "b"})


def test_malformed_and_non_dict_json_are_real_errors_not_crashes():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)

        bad_path = directory / "bad.json"
        bad_path.write_text("not valid json {")
        error = win.import_state_json(bad_path)
        check("malformed JSON is a real error, not a crash", error is not None)

        list_path = directory / "list.json"
        list_path.write_text(json.dumps([1, 2, 3]))
        error = win.import_state_json(list_path)
        check("a non-dict top level is a real error, not a crash", error is not None)


test_export_import_round_trips_value_edit_and_history()
test_schema_violating_key_refuses_the_whole_import()
test_non_validated_key_imports_unchanged()
test_key_absent_from_file_survives_untouched()
test_import_publishes_desk_state_changed_per_changed_key()
test_malformed_and_non_dict_json_are_real_errors_not_crashes()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
