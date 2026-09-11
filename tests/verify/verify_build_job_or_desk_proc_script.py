import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.temp_ui import (  # noqa: E402
    _BUILD_JOB_OR_DESK_PROC_SCRIPT,
    parse_desk_proc,
    parse_job,
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


def run(cwd, *args):
    """Runs the real generated script as a real subprocess -- exactly
    how a project would actually invoke it, not an in-process import
    (the generated script is deliberately self-contained, no `desk`
    package on its own sys.path, so a subprocess is the honest way to
    exercise it)."""
    return subprocess.run(
        [sys.executable, str(cwd / "build_job_or_desk_proc.py"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _setup(tmpdir: Path) -> None:
    (tmpdir / "build_job_or_desk_proc.py").write_text(_BUILD_JOB_OR_DESK_PROC_SCRIPT)


def test_desk_proc_round_trips_through_the_real_parser():
    with tempfile.TemporaryDirectory() as d:
        tmpdir = Path(d)
        _setup(tmpdir)
        script_path = tmpdir / "my_script.py"
        script_path.write_text("print('hello from a real script')")

        result = run(tmpdir, "desk-proc", "A real test", "my_script.py")
        check("exits 0", result.returncode == 0)
        printed_path = tmpdir / result.stdout.strip()
        check("prints the path it wrote", printed_path.is_file())

        text = printed_path.read_text()
        definition = parse_desk_proc(text)
        check("the real parser accepts the generated file", definition is not None)
        check("summary round-trips", definition.summary == "A real test")
        decoded = base64.b64decode(definition.script_b64).decode("utf-8")
        check("script content round-trips exactly", decoded == "print('hello from a real script')")


def test_job_python_round_trips_through_the_real_parser():
    with tempfile.TemporaryDirectory() as d:
        tmpdir = Path(d)
        _setup(tmpdir)
        script_path = tmpdir / "my_script.py"
        script_path.write_text("print(1)")

        result = run(tmpdir, "job", "python", "A python job", "my_script.py")
        check("exits 0", result.returncode == 0)
        printed_path = tmpdir / result.stdout.strip()
        definition = parse_job(printed_path.read_text())
        check("the real parser accepts the generated file", definition is not None)
        check("kind round-trips", definition.kind == "python")
        check("summary round-trips", definition.summary == "A python job")
        check("no capabilities were added", definition.capabilities == [])
        decoded = base64.b64decode(definition.script_b64).decode("utf-8")
        check("script content round-trips exactly", decoded == "print(1)")


def test_job_html_with_capabilities_round_trips_through_the_real_parser():
    with tempfile.TemporaryDirectory() as d:
        tmpdir = Path(d)
        _setup(tmpdir)
        html_path = tmpdir / "widget.html"
        html_path.write_text("<html><body>hi</body></html>")

        result = run(
            tmpdir,
            "job",
            "html",
            "An html job",
            "widget.html",
            "--capability",
            "workspace",
            "--capability",
            "fs",
        )
        check("exits 0", result.returncode == 0)
        printed_path = tmpdir / result.stdout.strip()
        definition = parse_job(printed_path.read_text())
        check("kind round-trips", definition.kind == "html")
        check("both capabilities collected in order", definition.capabilities == ["workspace", "fs"])
        decoded = base64.b64decode(definition.script_b64).decode("utf-8")
        check("html content round-trips exactly", decoded == "<html><body>hi</body></html>")


def test_multi_chunk_script_round_trips():
    with tempfile.TemporaryDirectory() as d:
        tmpdir = Path(d)
        _setup(tmpdir)
        big_script = "x = 1\n" * 2000  # long enough to force multiple Script lines
        script_path = tmpdir / "big.py"
        script_path.write_text(big_script)

        result = run(tmpdir, "desk-proc", "A big script", "big.py")
        check("exits 0", result.returncode == 0)
        printed_path = tmpdir / result.stdout.strip()
        text = printed_path.read_text()
        check("really did chunk across multiple Script lines", text.count("Script\t") > 1)
        definition = parse_desk_proc(text)
        decoded = base64.b64decode(definition.script_b64).decode("utf-8")
        check("multi-chunk content still round-trips exactly", decoded == big_script)


def test_tab_in_summary_is_a_clear_build_error_not_corrupted_output():
    with tempfile.TemporaryDirectory() as d:
        tmpdir = Path(d)
        _setup(tmpdir)
        script_path = tmpdir / "my_script.py"
        script_path.write_text("pass")

        result = run(tmpdir, "desk-proc", "bad\ttab", "my_script.py")
        check("exits non-zero", result.returncode != 0)
        check("a clear error message, not a raw traceback", "error:" in result.stderr and "Traceback" not in result.stderr)
        check("no tempui file was written", not (tmpdir / ".desk_temp").exists() or not list((tmpdir / ".desk_temp").iterdir()))


def test_newline_in_capability_is_a_clear_build_error():
    with tempfile.TemporaryDirectory() as d:
        tmpdir = Path(d)
        _setup(tmpdir)
        script_path = tmpdir / "widget.html"
        script_path.write_text("<html></html>")

        result = run(tmpdir, "job", "html", "fine", "widget.html", "--capability", "bad\ncapability")
        check("exits non-zero", result.returncode != 0)
        check("a clear error message naming the real cause", "capability name" in result.stderr)


def test_missing_script_file_is_a_clear_error_not_a_crash():
    with tempfile.TemporaryDirectory() as d:
        tmpdir = Path(d)
        _setup(tmpdir)

        result = run(tmpdir, "desk-proc", "fine", "no_such_file.py")
        check("exits non-zero", result.returncode != 0)
        check("a clear error message, not a raw traceback", "not found" in result.stderr and "Traceback" not in result.stderr)


def test_invalid_job_kind_is_rejected_by_argparse():
    with tempfile.TemporaryDirectory() as d:
        tmpdir = Path(d)
        _setup(tmpdir)
        script_path = tmpdir / "my_script.py"
        script_path.write_text("pass")

        result = run(tmpdir, "job", "javascript", "fine", "my_script.py")
        check("exits non-zero for an invalid kind", result.returncode != 0)


test_desk_proc_round_trips_through_the_real_parser()
test_job_python_round_trips_through_the_real_parser()
test_job_html_with_capabilities_round_trips_through_the_real_parser()
test_multi_chunk_script_round_trips()
test_tab_in_summary_is_a_clear_build_error_not_corrupted_output()
test_newline_in_capability_is_a_clear_build_error()
test_missing_script_file_is_a_clear_error_not_a_crash()
test_invalid_job_kind_is_rejected_by_argparse()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
