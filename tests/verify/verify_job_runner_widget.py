import base64
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.shell import current_context  # noqa: E402

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")

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


def load_job_runner_module():
    spec = importlib.util.spec_from_file_location(
        "job_runner_verify_mod", REPO_ROOT / "widgets" / "job_runner" / "widget.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


job_runner = load_job_runner_module()


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _write_job_file(desk_temp_dir, job_id, kind, summary, script, capabilities=()):
    lines = [f"Job\t{kind}\t{summary}"]
    lines.extend(f"Capability\t{c}" for c in capabilities)
    lines.append(f"Script\t{_b64(script)}")
    (desk_temp_dir / job_id).write_text("\n".join(lines) + "\n")
    return desk_temp_dir / job_id


def test_set_source_file_updates_summary_display():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        job_path = _write_job_file(temp_dir, "job-a", "python", "Clean up scratch files", "pass")

        widget = job_runner.build()
        widget.set_source_file(job_path)
        check(
            "summary label shows the declared kind and summary",
            widget._summary_label.text() == "Job (python): Clean up scratch files",
        )
        check("has_unsaved_local_edits is False before Start", widget.has_unsaved_local_edits() is False)


def test_set_source_file_handles_malformed_job_gracefully():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        bad_path = temp_dir / "bad-job"
        bad_path.write_text("not a job file at all\n")

        widget = job_runner.build()
        widget.set_source_file(bad_path)
        check("a malformed Job file shows a clear placeholder, not a crash", widget._summary_label.text() == "(malformed Job file)")


def test_python_job_runs_and_reaches_done_with_captured_stdout():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        job_path = _write_job_file(temp_dir, "job-b", "python", "Say hi", "print('hi from job')")

        widget = job_runner.build()
        widget.set_source_file(job_path)
        widget._on_start_clicked()
        pump(until=lambda: widget._status in ("done", "errored"))
        check("status reaches done", widget._status == "done")
        check("stdout was captured into the detail view", widget._detail == "hi from job\n")
        check("Start is disabled once finished", widget._start_button.isEnabled() is False)
        check("has_unsaved_local_edits is True once started", widget.has_unsaved_local_edits() is True)


def test_python_job_that_raises_reaches_errored_with_traceback():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        job_path = _write_job_file(temp_dir, "job-c", "python", "Boom", "raise ValueError('boom')")

        widget = job_runner.build()
        widget.set_source_file(job_path)
        widget._on_start_clicked()
        pump(until=lambda: widget._status in ("done", "errored"))
        check("status reaches errored", widget._status == "errored")
        check("a real traceback was captured", "ValueError: boom" in widget._detail)


def test_persisted_status_round_trips_and_disables_start():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        job_path = _write_job_file(temp_dir, "job-d", "python", "Already ran", "pass")

        widget = job_runner.build()
        widget.set_source_file(job_path)
        widget.set_widget_local_storage({"status": "done", "detail": "already ran output"})
        check("restored done status shows the persisted detail", widget._detail == "already ran output")
        check("Start stays disabled for a restored done status", widget._start_button.isEnabled() is False)

        stored = widget.get_widget_local_storage()
        check("get_widget_local_storage returns exactly what was restored", stored == {"status": "done", "detail": "already ran output"})


def test_restored_executing_status_is_shown_as_interrupted_with_start_re_enabled():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        job_path = _write_job_file(temp_dir, "job-e", "python", "Interrupted mid-run", "pass")

        widget = job_runner.build()
        widget.set_source_file(job_path)
        widget.set_widget_local_storage({"status": "executing", "detail": ""})
        check("a restored 'executing' status is shown as interrupted, not stuck", widget._status == "interrupted")
        check("Start is re-enabled for an interrupted job", widget._start_button.isEnabled() is True)
        check("has_unsaved_local_edits is False for an interrupted job (a fresh Start is allowed)", widget.has_unsaved_local_edits() is False)


def test_view_code_materializes_and_calls_the_editor_opener():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        job_path = _write_job_file(temp_dir, "job-f", "python", "Viewable", "print('view me')")

        opened = []
        current_context.set_editor_or_scrap_opener(lambda p: opened.append(p))
        widget = job_runner.build()
        widget.set_source_file(job_path)
        widget._on_view_code_clicked()

        check("the editor-or-scrap opener was called with a real, materialized file", len(opened) == 1 and opened[0].is_file())
        check("the materialized file's content matches the job's own script", opened[0].read_text() == "print('view me')")
        current_context.set_editor_or_scrap_opener(None)


def test_view_code_is_a_noop_with_no_opener_registered():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        job_path = _write_job_file(temp_dir, "job-g", "python", "No opener", "pass")

        current_context.set_editor_or_scrap_opener(None)
        widget = job_runner.build()
        widget.set_source_file(job_path)
        try:
            widget._on_view_code_clicked()
            check("no opener registered -> silent no-op, no crash", True)
        except Exception as e:  # noqa: BLE001
            check(f"no opener registered -> silent no-op, no crash (raised {e!r})", False)


def test_html_job_dispatches_through_the_html_job_starter_hook():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        job_path = _write_job_file(
            temp_dir, "job-h", "html", "Talk to the Bridge API", "<html></html>", capabilities=["workspace"]
        )

        calls = []

        def fake_starter(job_id, definition, on_status):
            calls.append((job_id, definition.kind, definition.capabilities))
            on_status("executing", "")
            on_status("done", "")

        current_context.set_html_job_starter(fake_starter)
        widget = job_runner.build()
        widget.set_source_file(job_path)
        widget._on_start_clicked()

        check("the html job starter hook was called with this job's id and definition", calls == [("job-h", "html", ["workspace"])])
        check("status reflects the starter's own on_status callback", widget._status == "done")
        current_context.set_html_job_starter(None)


def test_html_job_with_no_starter_registered_reports_errored():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        job_path = _write_job_file(temp_dir, "job-i", "html", "No starter available", "<html></html>")

        current_context.set_html_job_starter(None)
        widget = job_runner.build()
        widget.set_source_file(job_path)
        widget._on_start_clicked()
        check("no html job starter registered -> errored, not a crash or a silent hang", widget._status == "errored")


test_set_source_file_updates_summary_display()
test_set_source_file_handles_malformed_job_gracefully()
test_python_job_runs_and_reaches_done_with_captured_stdout()
test_python_job_that_raises_reaches_errored_with_traceback()
test_persisted_status_round_trips_and_disables_start()
test_restored_executing_status_is_shown_as_interrupted_with_start_re_enabled()
test_view_code_materializes_and_calls_the_editor_opener()
test_view_code_is_a_noop_with_no_opener_registered()
test_html_job_dispatches_through_the_html_job_starter_hook()
test_html_job_with_no_starter_registered_reports_errored()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
