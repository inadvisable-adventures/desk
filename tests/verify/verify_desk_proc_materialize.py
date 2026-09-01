import base64
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.desk_proc import (  # noqa: E402
    PYTHON_DESK_PROC_ENTRY_FILENAME,
    SOURCE_VIEW_FILENAME,
    desk_proc_dir,
    materialize,
    materialize_script_body,
)
from desk.temp_ui import DeskProcDefinition  # noqa: E402

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


def test_materialize_writes_script_py():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d)
        definition = DeskProcDefinition(summary="hi", script_b64=_b64("print(1)"))
        result = materialize(desk_temp_dir, "proc-1", definition)
        check("returns the proc's own directory", result == desk_proc_dir(desk_temp_dir, "proc-1"))
        entry = result / PYTHON_DESK_PROC_ENTRY_FILENAME
        check("writes a real script.py", entry.is_file())
        check("content round-trips", entry.read_text() == "print(1)")


def test_materialize_malformed_base64_returns_none_no_crash():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d)
        definition = DeskProcDefinition(summary="hi", script_b64="not-valid-base64!!!")
        result = materialize(desk_temp_dir, "proc-2", definition)
        check("malformed base64 returns None, doesn't raise", result is None)
        check("no directory created for a failed materialize", not desk_proc_dir(desk_temp_dir, "proc-2").exists())


def test_materialize_creates_directories_as_needed():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d) / "does" / "not" / "exist" / "yet"
        definition = DeskProcDefinition(summary="hi", script_b64=_b64("print('x')"))
        result = materialize(desk_temp_dir, "proc-3", definition)
        check("nested desk_procs/ directory created as needed", result is not None and result.is_dir())


def test_materialize_script_body_writes_distinct_plain_text_view():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d)
        definition = DeskProcDefinition(summary="hi", script_b64=_b64("print('view me')"))
        result = materialize_script_body(desk_temp_dir, "proc-4", definition)
        check("returns a real file path, not a directory", result is not None and result.is_file())
        check(
            "named distinctly from the execution entry (never collides with script.py)",
            result.name == SOURCE_VIEW_FILENAME and result.name != PYTHON_DESK_PROC_ENTRY_FILENAME,
        )
        check("content round-trips", result.read_text() == "print('view me')")

        # materialize() (the execution-ready path) and materialize_script_body()
        # (the View Code path) can coexist in the same desk_proc_dir.
        materialize(desk_temp_dir, "proc-4", definition)
        check(
            "both the execution-ready script.py and the View Code copy exist side by side",
            (desk_proc_dir(desk_temp_dir, "proc-4") / PYTHON_DESK_PROC_ENTRY_FILENAME).is_file() and result.is_file(),
        )


def test_materialize_script_body_malformed_base64_returns_none():
    with tempfile.TemporaryDirectory() as d:
        desk_temp_dir = Path(d)
        definition = DeskProcDefinition(summary="hi", script_b64="not-valid-base64!!!")
        result = materialize_script_body(desk_temp_dir, "proc-5", definition)
        check("malformed base64 returns None, doesn't raise", result is None)


test_materialize_writes_script_py()
test_materialize_malformed_base64_returns_none_no_crash()
test_materialize_creates_directories_as_needed()
test_materialize_script_body_writes_distinct_plain_text_view()
test_materialize_script_body_malformed_base64_returns_none()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
