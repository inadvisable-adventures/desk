import base64
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.shell import current_context  # noqa: E402

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


def pump(seconds=5.0, until=None):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        if until is not None and until():
            return
        time.sleep(0.02)


def load_desk_proc_runner_module():
    spec = importlib.util.spec_from_file_location(
        "desk_proc_runner_verify_mod", REPO_ROOT / "widgets" / "desk_proc_runner" / "widget.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


desk_proc_runner = load_desk_proc_runner_module()


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _write_desk_proc_file(desk_temp_dir, proc_id, summary, script):
    lines = [f"DeskProc\t{summary}", f"Script\t{_b64(script)}"]
    (desk_temp_dir / proc_id).write_text("\n".join(lines) + "\n")
    return desk_temp_dir / proc_id


def test_set_source_file_updates_summary_display():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        proc_path = _write_desk_proc_file(temp_dir, "proc-a", "Clean up scratch files", "pass")

        widget = desk_proc_runner.build()
        widget.set_source_file(proc_path)
        check(
            "summary label shows the declared summary",
            widget._summary_label.text() == "Desk Proc: Clean up scratch files",
        )
        check("has_unsaved_local_edits is False before Start", widget.has_unsaved_local_edits() is False)


def test_set_source_file_handles_malformed_desk_proc_gracefully():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        bad_path = temp_dir / "bad-proc"
        bad_path.write_text("not a desk proc file at all\n")

        widget = desk_proc_runner.build()
        widget.set_source_file(bad_path)
        check(
            "a malformed Desk Proc file shows a clear placeholder, not a crash",
            widget._summary_label.text() == "(malformed Desk Proc file)",
        )


def test_desk_proc_runs_and_reaches_done_with_captured_stdout():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        proc_path = _write_desk_proc_file(temp_dir, "proc-b", "Say hi", "print('hi from proc')")

        widget = desk_proc_runner.build()
        widget.set_source_file(proc_path)
        widget._on_start_clicked()
        pump(until=lambda: widget._status in ("done", "errored"))
        check("status reaches done", widget._status == "done")
        check("stdout was captured into the detail view", widget._detail == "hi from proc\n")
        check("Start is disabled once finished", widget._start_button.isEnabled() is False)
        check("has_unsaved_local_edits is True once started", widget.has_unsaved_local_edits() is True)


def test_desk_proc_that_raises_reaches_errored_with_traceback():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        proc_path = _write_desk_proc_file(temp_dir, "proc-c", "Boom", "raise ValueError('boom')")

        widget = desk_proc_runner.build()
        widget.set_source_file(proc_path)
        widget._on_start_clicked()
        pump(until=lambda: widget._status in ("done", "errored"))
        check("status reaches errored", widget._status == "errored")
        check("a real traceback was captured", "ValueError: boom" in widget._detail)


def test_deskproc_global_is_injected_and_reachable_in_the_script_namespace():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        script = "print(type(deskproc).__name__)\nprint(deskproc.reveal_widget('nope'))\n"
        proc_path = _write_desk_proc_file(temp_dir, "proc-d", "Uses deskproc", script)

        current_context.set_main_window(None)
        widget = desk_proc_runner.build()
        widget.set_source_file(proc_path)
        widget._on_start_clicked()
        pump(until=lambda: widget._status in ("done", "errored"))
        check("status reaches done", widget._status == "done")
        check("deskproc is a real DeskProcApi instance in the script's own namespace", "DeskProcApi" in widget._detail)
        check(
            "reveal_widget with no main window registered returns False, not a crash",
            "False" in widget._detail,
        )


def test_deskproc_methods_route_through_the_gui_thread_caller_hook():
    """Doesn't need a real Qt canvas -- proves the wiring (that
    deskproc.* calls current_context.get_gui_thread_caller(), which in
    turn calls the real DeskWindow method) with a fake main window and
    a fake caller that just runs fn() synchronously and records it."""
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()

        calls = []

        class _FakeMainWindow:
            def zoom_to_widget_by_instance_id(self, instance_id):
                calls.append(("zoom", instance_id))
                return True

            def screenshot_widget_instance(self, instance_id, path):
                calls.append(("screenshot_widget", instance_id, path))
                return True

            def screenshot_desk(self, path):
                calls.append(("screenshot_desk", path))
                return True

            def get_state_dict(self):
                calls.append(("list",))
                return {"widgets": [{"instance_id": "abc"}]}

        current_context.set_main_window(_FakeMainWindow())
        current_context.set_gui_thread_caller(lambda fn: fn())

        script = (
            "print(deskproc.reveal_widget('abc'))\n"
            "print(deskproc.screenshot_widget('abc', 'shot.png'))\n"
            "print(deskproc.screenshot_desk('desk.png'))\n"
            "print(deskproc.list_widget_instances())\n"
        )
        proc_path = _write_desk_proc_file(temp_dir, "proc-e", "Exercises all four methods", script)

        widget = desk_proc_runner.build()
        widget.set_source_file(proc_path)
        widget._on_start_clicked()
        pump(until=lambda: widget._status in ("done", "errored"))
        check("status reaches done", widget._status == "done")
        check(
            "all four deskproc methods actually reached the fake main window via the GUI thread caller",
            calls
            == [
                ("zoom", "abc"),
                ("screenshot_widget", "abc", "shot.png"),
                ("screenshot_desk", "desk.png"),
                ("list",),
            ],
        )
        check(
            "return values round-trip back into the script's own printed output",
            "True" in widget._detail and "[{'instance_id': 'abc'}]" in widget._detail,
        )
        current_context.set_main_window(None)
        current_context.set_gui_thread_caller(None)


def test_deskproc_call_with_no_gui_thread_caller_raises_a_clear_error():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()

        class _FakeMainWindow:
            def zoom_to_widget_by_instance_id(self, instance_id):
                return True

        current_context.set_main_window(_FakeMainWindow())
        current_context.set_gui_thread_caller(None)

        proc_path = _write_desk_proc_file(temp_dir, "proc-f", "No caller registered", "deskproc.reveal_widget('x')")
        widget = desk_proc_runner.build()
        widget.set_source_file(proc_path)
        widget._on_start_clicked()
        pump(until=lambda: widget._status in ("done", "errored"))
        check("status reaches errored (no GUI thread caller registered)", widget._status == "errored")
        check("the error message names the real cause", "no GUI thread caller registered" in widget._detail)
        current_context.set_main_window(None)


def test_persisted_status_round_trips_and_disables_start():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        proc_path = _write_desk_proc_file(temp_dir, "proc-g", "Already ran", "pass")

        widget = desk_proc_runner.build()
        widget.set_source_file(proc_path)
        widget.set_widget_local_storage({"status": "done", "detail": "already ran output"})
        check("restored done status shows the persisted detail", widget._detail == "already ran output")
        check("Start stays disabled for a restored done status", widget._start_button.isEnabled() is False)

        stored = widget.get_widget_local_storage()
        check(
            "get_widget_local_storage returns exactly what was restored",
            stored == {"status": "done", "detail": "already ran output"},
        )


def test_restored_executing_status_is_shown_as_interrupted_with_start_re_enabled():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        proc_path = _write_desk_proc_file(temp_dir, "proc-h", "Interrupted mid-run", "pass")

        widget = desk_proc_runner.build()
        widget.set_source_file(proc_path)
        widget.set_widget_local_storage({"status": "executing", "detail": ""})
        check("a restored 'executing' status is shown as interrupted, not stuck", widget._status == "interrupted")
        check("Start is re-enabled for an interrupted proc", widget._start_button.isEnabled() is True)
        check(
            "has_unsaved_local_edits is False for an interrupted proc (a fresh Start is allowed)",
            widget.has_unsaved_local_edits() is False,
        )


def test_view_code_materializes_and_calls_the_editor_opener():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        proc_path = _write_desk_proc_file(temp_dir, "proc-i", "Viewable", "print('view me')")

        opened = []
        current_context.set_editor_or_scrap_opener(lambda p: opened.append(p))
        widget = desk_proc_runner.build()
        widget.set_source_file(proc_path)
        widget._on_view_code_clicked()

        check("the editor-or-scrap opener was called with a real, materialized file", len(opened) == 1 and opened[0].is_file())
        check("the materialized file's content matches the proc's own script", opened[0].read_text() == "print('view me')")
        current_context.set_editor_or_scrap_opener(None)


test_set_source_file_updates_summary_display()
test_set_source_file_handles_malformed_desk_proc_gracefully()
test_desk_proc_runs_and_reaches_done_with_captured_stdout()
test_desk_proc_that_raises_reaches_errored_with_traceback()
test_deskproc_global_is_injected_and_reachable_in_the_script_namespace()
test_deskproc_methods_route_through_the_gui_thread_caller_hook()
test_deskproc_call_with_no_gui_thread_caller_raises_a_clear_error()
test_persisted_status_round_trips_and_disables_start()
test_restored_executing_status_is_shown_as_interrupted_with_start_re_enabled()
test_view_code_materializes_and_calls_the_editor_opener()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
