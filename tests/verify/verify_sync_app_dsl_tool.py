import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.temp_ui import APP_DSL_DIRNAME, _repo_app_dsl_dir, sync_app_dsl_tool  # noqa: E402

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


def test_repo_app_dsl_dir_exists_and_is_real():
    source = _repo_app_dsl_dir()
    check("this repo's own app_dsl/ directory resolves and exists", source.is_dir())
    check("it contains the real build.py entry point", (source / "build.py").is_file())
    check("it contains schema.py/parse.py/codegen.py", all((source / f).is_file() for f in ("schema.py", "parse.py", "codegen.py")))
    check("it contains README.md", (source / "README.md").is_file())


def test_sync_mirrors_a_fresh_copy():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        sync_app_dsl_tool(temp_dir)
        destination = temp_dir / APP_DSL_DIRNAME
        check("app_dsl/ was mirrored into the target directory", destination.is_dir())
        check("build.py was mirrored", (destination / "build.py").is_file())
        source_text = (_repo_app_dsl_dir() / "build.py").read_text()
        mirrored_text = (destination / "build.py").read_text()
        check("mirrored content matches the real source exactly", source_text == mirrored_text)


def test_sync_excludes_pycache():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        # A real __pycache__ from actually running this repo's own
        # scripts -- confirms sync_app_dsl_tool's ignore_patterns
        # really excludes it, not just that none happens to exist.
        pycache = _repo_app_dsl_dir() / "__pycache__"
        created_it = not pycache.exists()
        if created_it:
            pycache.mkdir()
            (pycache / "schema.cpython-313.pyc").write_bytes(b"fake bytecode")
        try:
            sync_app_dsl_tool(temp_dir)
            destination = temp_dir / APP_DSL_DIRNAME
            check("__pycache__ is not mirrored into .desk_temp", not (destination / "__pycache__").exists())
        finally:
            if created_it:
                import shutil

                shutil.rmtree(pycache)


def test_sync_is_always_fresh_not_gated_by_already_exists():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        destination = temp_dir / APP_DSL_DIRNAME
        destination.mkdir(parents=True)
        (destination / "build.py").write_text("# a stale, pre-sync placeholder\n")
        sync_app_dsl_tool(temp_dir)
        check(
            "a stale pre-existing app_dsl/ is fully replaced, not left alone",
            (destination / "build.py").read_text() == (_repo_app_dsl_dir() / "build.py").read_text(),
        )


test_repo_app_dsl_dir_exists_and_is_real()
test_sync_mirrors_a_fresh_copy()
test_sync_excludes_pycache()
test_sync_is_always_fresh_not_gated_by_already_exists()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
