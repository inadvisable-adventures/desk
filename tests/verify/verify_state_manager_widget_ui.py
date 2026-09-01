import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/widgets/state_manager")

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.event_mediator import EventMediator  # noqa: E402
from desk.schema_registry import SCHEMA_CHANGED_EVENT  # noqa: E402
from desk.shell import current_context  # noqa: E402

import widget as state_manager_widget  # noqa: E402

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


def _reset_providers():
    current_context.set_state_overview_provider(None)
    current_context.set_state_history_provider(None)
    current_context.set_state_writer(None)
    current_context.set_schema_file_writer(None)
    current_context.set_schema_file_deleter(None)
    current_context.set_state_exporter(None)
    current_context.set_state_importer(None)
    current_context.set_popup_opener(None)


COUNTER_ENTRY = {
    "key": "counter",
    "value": 5,
    "edit": None,
    "type_expr": "number",
    "source": "builtin_widget",
    "source_kind": "widget",
    "permanent": True,
    "placed_instance_count": 0,
}
RAW_ENTRY = {
    "key": "raw",
    "value": "hi",
    "edit": None,
    "type_expr": None,
    "source": None,
    "source_kind": None,
    "permanent": None,
    "placed_instance_count": 0,
}


def test_tree_populates_from_overview_provider():
    _reset_providers()
    current_context.set_state_overview_provider(lambda: [COUNTER_ENTRY, RAW_ENTRY])
    current_context.set_state_history_provider(lambda key, limit: [])
    widget = state_manager_widget.build()
    check("both keys appear in the tree", widget._tree.topLevelItemCount() == 2)


def test_selecting_a_row_shows_schema_value_and_history():
    _reset_providers()
    current_context.set_state_overview_provider(lambda: [COUNTER_ENTRY])
    current_context.set_state_history_provider(lambda key, limit: [{"value": 4, "edit": "bumped"}])
    widget = state_manager_widget.build()
    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))

    check("detail panel shows the selected key", widget._detail_key_label.text() == "counter")
    check("value field shows the current value", widget._value_field.toPlainText() == json.dumps(5, indent=2))
    check("schema field shows the type expression", widget._schema_type_field.text() == "number")
    check(
        "a widget-sourced schema's fields are disabled (view-only)",
        not widget._schema_type_field.isEnabled() and not widget._schema_delete_button.isEnabled(),
    )
    check("history shows the one entry", widget._history_list.count() == 1)


def test_editing_a_value_calls_the_writer_hook_with_edited_json():
    _reset_providers()
    current_context.set_state_overview_provider(lambda: [COUNTER_ENTRY])
    current_context.set_state_history_provider(lambda key, limit: [])
    calls = []
    current_context.set_state_writer(lambda key, value, edit, instance_id, type_hint: calls.append(
        (key, value, edit, instance_id, type_hint)
    ) or None)
    widget = state_manager_widget.build()
    widget._instance_id = "inst-test"
    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))

    widget._value_field.setPlainText("42")
    widget._edit_note_field.setText("manual bump")
    widget._on_save_value_clicked()

    check("the writer hook was called exactly once", len(calls) == 1)
    check("the writer hook received the parsed JSON value", calls[0][1] == 42)
    check("the writer hook received the edit note", calls[0][2] == "manual bump")
    check("the writer hook received the widget's own instance id", calls[0][3] == "inst-test")
    check("a success status is shown", widget._status_label.text() == "Saved.")


def test_writer_hook_error_shows_inline_without_clearing_the_edit_box():
    _reset_providers()
    current_context.set_state_overview_provider(lambda: [COUNTER_ENTRY])
    current_context.set_state_history_provider(lambda key, limit: [])
    current_context.set_state_writer(lambda key, value, edit, instance_id, type_hint: "does not match schema")
    widget = state_manager_widget.build()
    widget._instance_id = "inst-test"
    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))

    widget._value_field.setPlainText('"not a number"')
    widget._on_save_value_clicked()

    check("the error message is shown inline", "does not match schema" in widget._status_label.text())
    check("the edit box is not cleared on failure", widget._value_field.toPlainText() == '"not a number"')


def test_invalid_json_in_the_value_box_is_caught_before_calling_the_writer():
    _reset_providers()
    current_context.set_state_overview_provider(lambda: [COUNTER_ENTRY])
    current_context.set_state_history_provider(lambda key, limit: [])
    calls = []
    current_context.set_state_writer(lambda *args: calls.append(args) or None)
    widget = state_manager_widget.build()
    widget._instance_id = "inst-test"
    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))

    widget._value_field.setPlainText("{not valid json")
    widget._on_save_value_clicked()

    check("the writer hook is never called for invalid JSON", len(calls) == 0)
    check("a JSON error is shown", "Not valid JSON" in widget._status_label.text())


def test_live_events_trigger_a_refresh():
    _reset_providers()
    overview = [COUNTER_ENTRY]
    current_context.set_state_overview_provider(lambda: list(overview))
    current_context.set_state_history_provider(lambda key, limit: [])
    widget = state_manager_widget.build()
    check("one row before the live update", widget._tree.topLevelItemCount() == 1)

    mediator = EventMediator()
    widget.bind_event_mediator("inst-widget", mediator)

    overview.append(RAW_ENTRY)
    mediator.publish("desk.state.changed", {"key": "raw", "value": "hi", "edit": None}, sender_instance_id="inst-other")

    deadline_iterations = 200
    for _ in range(deadline_iterations):
        app.processEvents()
        if widget._tree.topLevelItemCount() == 2:
            break
        import time

        time.sleep(0.01)
    check("desk.state.changed triggers a refresh that picks up the new key", widget._tree.topLevelItemCount() == 2)

    overview.append(
        {
            "key": "third",
            "value": None,
            "edit": None,
            "type_expr": "boolean",
            "source": "some_widget",
            "source_kind": "widget",
            "permanent": True,
            "placed_instance_count": 0,
        }
    )
    mediator.publish(SCHEMA_CHANGED_EVENT, None, sender_instance_id="desk")
    for _ in range(deadline_iterations):
        app.processEvents()
        if widget._tree.topLevelItemCount() == 3:
            break
        import time

        time.sleep(0.01)
    check("SCHEMA_CHANGED_EVENT also triggers a refresh", widget._tree.topLevelItemCount() == 3)


def test_alert_and_confirm_route_through_the_popup_opener_not_a_qmessagebox():
    # TODO 5242aeb: this widget used to call QMessageBox.warning/
    # .question directly, which renders as a detached macOS window
    # (the bug this item fixes) -- _alert/_confirm must route through
    # current_context.get_popup_opener() instead.
    _reset_providers()
    current_context.set_state_overview_provider(lambda: [])
    current_context.set_state_history_provider(lambda key, limit: [])
    calls = []
    current_context.set_popup_opener(lambda title, message, buttons, default: calls.append(
        (title, message, buttons, default)
    ) or "Yes")
    widget = state_manager_widget.build()

    widget._alert("New State Key", "A key name is required.")
    check("_alert calls the popup opener with a single OK button", calls[-1] == (
        "New State Key", "A key name is required.", ["OK"], "OK"
    ))

    result = widget._confirm("Load State", "Import foo.json?")
    check("_confirm calls the popup opener with Yes/No, No as default", calls[-1] == (
        "Load State", "Import foo.json?", ["Yes", "No"], "No"
    ))
    check("_confirm returns True when the popup opener returns 'Yes'", result is True)

    current_context.set_popup_opener(lambda title, message, buttons, default: "No")
    check("_confirm returns False for any other answer", widget._confirm("t", "m") is False)

    check("QMessageBox is no longer imported by this widget", not hasattr(state_manager_widget, "QMessageBox"))


def test_load_state_confirmation_gates_the_importer():
    from unittest.mock import patch

    _reset_providers()
    current_context.set_state_overview_provider(lambda: [])
    current_context.set_state_history_provider(lambda key, limit: [])
    import_calls = []
    current_context.set_state_importer(lambda path: import_calls.append(path) or None)
    widget = state_manager_widget.build()

    current_context.set_popup_opener(lambda title, message, buttons, default: "No")
    with patch("widget.QFileDialog.getOpenFileName", return_value=("/tmp/state.json", "")):
        widget._on_load_state_clicked()
    check("declining the confirmation does not call the importer", import_calls == [])

    current_context.set_popup_opener(lambda title, message, buttons, default: "Yes")
    with patch("widget.QFileDialog.getOpenFileName", return_value=("/tmp/state.json", "")):
        widget._on_load_state_clicked()
    check("confirming calls the importer with the chosen path", len(import_calls) == 1 and str(import_calls[0]) == "/tmp/state.json")


test_tree_populates_from_overview_provider()
test_selecting_a_row_shows_schema_value_and_history()
test_editing_a_value_calls_the_writer_hook_with_edited_json()
test_writer_hook_error_shows_inline_without_clearing_the_edit_box()
test_invalid_json_in_the_value_box_is_caught_before_calling_the_writer()
test_alert_and_confirm_route_through_the_popup_opener_not_a_qmessagebox()
test_load_state_confirmation_gates_the_importer()
# Runs last: constructs a real EventMediator + EventSubscription, whose
# eventual (delayed, GC-timing-dependent) teardown was observed to
# crash the process (SIGABRT, an uncaught exception escaping a Qt
# `destroyed` signal handler -- see LEARNINGS.md's "uncaught Python
# exception escaping a Qt-signal-invoked slot" entry) if further
# widget/mediator construction happened afterward in the same process.
test_live_events_trigger_a_refresh()

_reset_providers()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
