import base64
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.jobs import (  # noqa: E402
    HTML_JOB_ENTRY_FILENAME,
    PYTHON_JOB_ENTRY_FILENAME,
    SOURCE_VIEW_FILENAMES,
    job_dir,
    materialize,
    materialize_script_body,
)
from desk.temp_ui import JobDefinition  # noqa: E402

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


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_materialize_html_writes_index_html():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d)
        definition = JobDefinition(kind="html", summary="hi", script_b64=_b64("<html>content</html>"))
        result = materialize(desk_temp_dir, "job-1", definition)
        check("returns the job's own directory", result == job_dir(desk_temp_dir, "job-1"))
        entry = result / HTML_JOB_ENTRY_FILENAME
        check("writes a real index.html", entry.is_file())
        check("content round-trips", entry.read_text() == "<html>content</html>")


def test_materialize_python_writes_script_py():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d)
        definition = JobDefinition(kind="python", summary="hi", script_b64=_b64("print(1)"))
        result = materialize(desk_temp_dir, "job-2", definition)
        entry = result / PYTHON_JOB_ENTRY_FILENAME
        check("writes a real script.py", entry.is_file())
        check("content round-trips", entry.read_text() == "print(1)")


def test_materialize_malformed_base64_returns_none_no_crash():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d)
        definition = JobDefinition(kind="python", summary="hi", script_b64="not-valid-base64!!!")
        result = materialize(desk_temp_dir, "job-3", definition)
        check("malformed base64 returns None, doesn't raise", result is None)
        check("no directory created for a failed materialize", not job_dir(desk_temp_dir, "job-3").exists())


def test_materialize_creates_directories_as_needed():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d) / "does" / "not" / "exist" / "yet"
        definition = JobDefinition(kind="html", summary="hi", script_b64=_b64("<html></html>"))
        result = materialize(desk_temp_dir, "job-4", definition)
        check("nested jobs/ directory created as needed", result is not None and result.is_dir())


def test_materialize_script_body_writes_plain_text_view():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d)
        definition = JobDefinition(kind="python", summary="hi", script_b64=_b64("print('view me')"))
        result = materialize_script_body(desk_temp_dir, "job-5", definition)
        check("returns a real file path, not a directory", result is not None and result.is_file())
        check(
            "named distinctly from the html-kind execution entry (never collides with index.html)",
            result.name == SOURCE_VIEW_FILENAMES["python"] and result.name != HTML_JOB_ENTRY_FILENAME,
        )
        check("content round-trips", result.read_text() == "print('view me')")


def test_materialize_script_body_html_kind_uses_distinct_filename():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d)
        definition = JobDefinition(kind="html", summary="hi", script_b64=_b64("<html>src</html>"))
        result = materialize_script_body(desk_temp_dir, "job-6", definition)
        check("html-kind View Code file is separate from index.html", result.name == SOURCE_VIEW_FILENAMES["html"])
        # materialize() (the execution-ready path) and materialize_script_body()
        # (the View Code path) can coexist in the same job_dir without clobbering.
        materialize(desk_temp_dir, "job-6", definition)
        check(
            "both the execution-ready index.html and the View Code copy exist side by side",
            (job_dir(desk_temp_dir, "job-6") / HTML_JOB_ENTRY_FILENAME).is_file() and result.is_file(),
        )


def test_materialize_script_body_malformed_base64_returns_none():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d)
        definition = JobDefinition(kind="python", summary="hi", script_b64="not-valid-base64!!!")
        result = materialize_script_body(desk_temp_dir, "job-7", definition)
        check("malformed base64 returns None, doesn't raise", result is None)


test_materialize_html_writes_index_html()
test_materialize_python_writes_script_py()
test_materialize_malformed_base64_returns_none_no_crash()
test_materialize_creates_directories_as_needed()
test_materialize_script_body_writes_plain_text_view()
test_materialize_script_body_html_kind_uses_distinct_filename()
test_materialize_script_body_malformed_base64_returns_none()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
