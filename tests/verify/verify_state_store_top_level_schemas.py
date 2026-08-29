import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

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


class _FakeView:
    def __init__(self):
        self.notifications = {}

    def notify_temp_ui(self, path, text, on_clicked):
        self.notifications[path] = (text, on_clicked)


class _FakeSchemaFileWatcher:
    """A no-op stand-in: this file tests _on_schema_file_changed and
    _provision_schema_files' own clearing logic directly (by calling
    them the same way the real SchemaFileWatcher.changed signal
    would), not the real directory-watching mechanics themselves --
    see verify_schema_file_watcher.py for those."""

    def provision(self, ephemeral_dir, project_root):
        pass


class _FakeWindow:
    def __init__(self):
        self._schema_registry = SchemaRegistry()
        self._known_schema_file_sources = set()
        self._schema_file_watcher = _FakeSchemaFileWatcher()
        self.view = _FakeView()


_FakeWindow._on_schema_file_changed = DeskWindow._on_schema_file_changed
_FakeWindow._notify_schema_file_error = DeskWindow._notify_schema_file_error
_FakeWindow._show_schema_conflict_popup = DeskWindow._show_schema_conflict_popup
_FakeWindow._provision_schema_files = DeskWindow._provision_schema_files


def test_schema_file_registers_a_permanent_key():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "one.json"
        path.write_text(json.dumps({"counter": "number"}))
        win = _FakeWindow()
        win._on_schema_file_changed(path)

        entry = win._schema_registry.get("counter")
        check("the key is registered", entry is not None)
        check("the schema is permanent", entry is not None and entry.permanent)
        check("the source is the file's own path", entry is not None and entry.source_widget_id == str(path))
        check("the source is tracked as a known schema-file source", str(path) in win._known_schema_file_sources)


def test_conflicting_file_is_refused_with_a_notification():
    with tempfile.TemporaryDirectory() as d:
        path1 = Path(d) / "one.json"
        path1.write_text(json.dumps({"counter": "number"}))
        path2 = Path(d) / "two.json"
        path2.write_text(json.dumps({"counter": "string"}))

        win = _FakeWindow()
        win._on_schema_file_changed(path1)
        win._on_schema_file_changed(path2)

        check("the original file's schema is unchanged", win._schema_registry.get("counter").type_expr == "number")
        check("the conflicting file's source was never tracked", str(path2) not in win._known_schema_file_sources)
        check("a notification fired for the conflicting file", path2 in win.view.notifications)


def test_malformed_file_is_a_loading_error_not_a_crash():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "bad.json"
        path.write_text("not valid json {")
        win = _FakeWindow()
        win._on_schema_file_changed(path)  # must not raise
        check("nothing gets registered from malformed JSON", win._schema_registry.get("counter") is None)
        check("a notification fired for the malformed file", path in win.view.notifications)

        path2 = Path(d) / "bad2.json"
        path2.write_text(json.dumps({"counter": 5}))
        win._on_schema_file_changed(path2)
        check(
            "a non-string type-expression value is also a loading error, not a crash",
            path2 in win.view.notifications and win._schema_registry.get("counter") is None,
        )


def test_editing_a_file_replaces_its_own_registration_cleanly():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "one.json"
        path.write_text(json.dumps({"counter": "number"}))
        win = _FakeWindow()
        win._on_schema_file_changed(path)
        check("initial schema registered", win._schema_registry.get("counter").type_expr == "number")

        path.write_text(json.dumps({"counter": "string"}))
        win._on_schema_file_changed(path)
        check("editing the file replaces its own schema", win._schema_registry.get("counter").type_expr == "string")
        check("the source is still tracked after the edit", str(path) in win._known_schema_file_sources)


def test_deleting_a_file_clears_its_registration_and_unblocks_others():
    with tempfile.TemporaryDirectory() as d:
        path1 = Path(d) / "one.json"
        path1.write_text(json.dumps({"counter": "number"}))
        path2 = Path(d) / "two.json"
        path2.write_text(json.dumps({"counter": "string"}))

        win = _FakeWindow()
        win._on_schema_file_changed(path1)
        win._on_schema_file_changed(path2)
        check("path2 is still blocked before path1 is deleted", win._schema_registry.get("counter").type_expr == "number")

        path1.unlink()
        win._on_schema_file_changed(path1)
        check("deleting path1 clears its registration", win._schema_registry.get("counter") is None)
        check("path1's source is no longer tracked", str(path1) not in win._known_schema_file_sources)

        win._on_schema_file_changed(path2)
        check("path2 can now register once path1 is gone", win._schema_registry.get("counter").type_expr == "string")


def test_desk_switch_isolation_clears_only_schema_file_sources():
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        path = Path(d1) / "one.json"
        path.write_text(json.dumps({"file_key": "number"}))
        win = _FakeWindow()
        win._on_schema_file_changed(path)
        # Simulates what _refresh_builtin_schemas would have registered
        # for a real built-in widget -- a completely separate source
        # namespace, never touched by _provision_schema_files.
        win._schema_registry.register_permanent("builtin_key", "string", "some_builtin_widget")

        check("file-sourced key registered before the switch", win._schema_registry.get("file_key") is not None)
        check("built-in-sourced key registered before the switch", win._schema_registry.get("builtin_key") is not None)

        win._provision_schema_files(Path(d2), None)

        check("the file-sourced key is cleared after switching desks", win._schema_registry.get("file_key") is None)
        check(
            "the built-in widget's own permanent schema survives the switch untouched",
            win._schema_registry.get("builtin_key") is not None
            and win._schema_registry.get("builtin_key").type_expr == "string",
        )
        check("the known-sources tracking set is cleared too", len(win._known_schema_file_sources) == 0)


test_schema_file_registers_a_permanent_key()
test_conflicting_file_is_refused_with_a_notification()
test_malformed_file_is_a_loading_error_not_a_crash()
test_editing_a_file_replaces_its_own_registration_cleanly()
test_deleting_a_file_clears_its_registration_and_unblocks_others()
test_desk_switch_isolation_clears_only_schema_file_sources()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
