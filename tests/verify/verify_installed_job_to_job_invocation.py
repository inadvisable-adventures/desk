# TODO 0959ff1: fast, always-run coverage for RUN_INSTALLED_JOB (a
# python-kind job invoking another Installed Job, python or rust). The
# rust-kind case here uses a dependency-free Cargo project (no
# crates.io fetch), same reasoning as verify_installed_jobs_rust.py's
# own header comment, so this stays in the normal sweep.
#
# The single most important thing this file checks is that a
# python-kind job invoking another python-kind job does NOT deadlock:
# reasoned through in plans/installed-job-to-job-invocation.md before
# writing any code (a plain threading.Lock, reentered on the same
# thread, would hang forever) -- confirmed here with a real, timed
# wait rather than trusted on inspection alone.
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk  # noqa: E402
from desk.installed_jobs import InstalledJobDefinition, compute_version_hash, installed_job_dir  # noqa: E402
from desk.shell import current_context  # noqa: E402
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


class _FakeWindowForRun:
    def __init__(self, directory: Path, installed_jobs: list) -> None:
        self.current_desk = Desk(path=directory / "default.desk", installed_jobs=installed_jobs)
        self._schema_registry = type("S", (), {"get": lambda self, k: None})()

    get_installed_job = DeskWindow.get_installed_job
    get_installed_job_for_run = DeskWindow.get_installed_job_for_run
    run_installed_job = DeskWindow.run_installed_job
    get_state = DeskWindow.get_state
    _resolve_job_needs = DeskWindow._resolve_job_needs
    _prepare_installed_job_run = DeskWindow._prepare_installed_job_run
    _make_run_installed_job_callable = DeskWindow._make_run_installed_job_callable


def _wait(predicate, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _install(directory: Path, name: str) -> InstalledJobDefinition:
    job_dir = installed_job_dir(directory, name)
    real_hash = compute_version_hash(job_dir)
    return InstalledJobDefinition(name=name, version_hash=real_hash, installed_at="2026-01-01T00:00:00")


def _write_python_job(directory: Path, name: str, main_py: str, extra_files: dict | None = None) -> None:
    job_dir = installed_job_dir(directory, name)
    job_dir.mkdir(parents=True)
    (job_dir / "main.py").write_text(main_py)
    for filename, content in (extra_files or {}).items():
        (job_dir / filename).write_text(content)


_RUST_CARGO_TOML = """[package]
name = "leaf_rust"
version = "0.1.0"
edition = "2021"
"""
_RUST_MAIN_RS = """fn main() { println!("hello from rust leaf"); }
"""


def _write_rust_job(directory: Path, name: str) -> None:
    job_dir = installed_job_dir(directory, name)
    (job_dir / "src").mkdir(parents=True)
    (job_dir / "Cargo.toml").write_text(_RUST_CARGO_TOML)
    (job_dir / "src" / "main.rs").write_text(_RUST_MAIN_RS)


def _run_sync(window: _FakeWindowForRun, name: str, config_path: str | None = None) -> dict:
    results = []
    window.run_installed_job(name, config_path, lambda ok, out, err, tb: results.append((ok, out, err, tb)))
    ok = _wait(lambda: results, timeout=120.0)
    if not ok:
        return {"ok": False, "stdout": "", "stderr": "TIMED OUT", "traceback": ""}
    run_ok, stdout, stderr, tb = results[0]
    return {"ok": run_ok, "stdout": stdout, "stderr": stderr, "traceback": tb}


def test_python_invokes_python_no_deadlock():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _write_python_job(directory, "b_job", "print('hello from B')\n")
        _write_python_job(
            directory,
            "a_job",
            "import helper_a\n"
            "before = helper_a.VALUE\n"
            "result = RUN_INSTALLED_JOB('b_job')\n"
            "import helper_a as helper_a_again\n"
            "after = helper_a_again.VALUE\n"
            "print('before=' + before)\n"
            "print('after=' + after)\n"
            "print('nested_ok=' + str(result['ok']))\n"
            "print('nested_stdout=' + result['stdout'].strip())\n",
            extra_files={"helper_a.py": "VALUE = 'helper-a-loaded'\n"},
        )
        window = _FakeWindowForRun(directory, [_install(directory, "a_job"), _install(directory, "b_job")])
        current_context.set_main_window(window)
        current_context.set_gui_thread_caller(lambda fn: fn())
        try:
            result = _run_sync(window, "a_job")
        finally:
            current_context.set_gui_thread_caller(None)
            current_context.set_main_window(None)
        check("A invoking B does not deadlock/time out", result["stderr"] != "TIMED OUT")
        check("A's own run succeeded", result["ok"])
        check("A's own sibling import still resolves before the nested call", "before=helper-a-loaded" in result["stdout"])
        check(
            "A's own sibling import still resolves AFTER the nested call (sys.path composed correctly)",
            "after=helper-a-loaded" in result["stdout"],
        )
        check("the nested call itself succeeded", "nested_ok=True" in result["stdout"])
        check("the nested call's stdout reached A", "nested_stdout=hello from B" in result["stdout"])


def test_python_invokes_rust():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _write_rust_job(directory, "rust_leaf")
        _write_python_job(
            directory,
            "a_job",
            "result = RUN_INSTALLED_JOB('rust_leaf')\n"
            "print('nested_ok=' + str(result['ok']))\n"
            "print('nested_stdout=' + result['stdout'].strip())\n",
        )
        window = _FakeWindowForRun(directory, [_install(directory, "a_job"), _install(directory, "rust_leaf")])
        current_context.set_main_window(window)
        current_context.set_gui_thread_caller(lambda fn: fn())
        try:
            result = _run_sync(window, "a_job")
        finally:
            current_context.set_gui_thread_caller(None)
            current_context.set_main_window(None)
        check("A invoking a rust job succeeded", result["ok"])
        check(
            "the calling job's own code is identical regardless of target kind (uniform interface)",
            "nested_ok=True" in result["stdout"],
        )
        check("the rust job's real stdout reached A", "nested_stdout=hello from rust leaf" in result["stdout"])


def test_invoking_not_installed_returns_ok_false_not_raised():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _write_python_job(
            directory,
            "a_job",
            "result = RUN_INSTALLED_JOB('ghost')\n"
            "print('nested_ok=' + str(result['ok']))\n"
            "print('nested_stderr=' + result['stderr'])\n",
        )
        window = _FakeWindowForRun(directory, [_install(directory, "a_job")])
        current_context.set_main_window(window)
        current_context.set_gui_thread_caller(lambda fn: fn())
        try:
            result = _run_sync(window, "a_job")
        finally:
            current_context.set_gui_thread_caller(None)
            current_context.set_main_window(None)
        check("A's own run still succeeds even though the nested call failed", result["ok"])
        check("the nested call reports ok=False, not a raised exception into A's own script", "nested_ok=False" in result["stdout"])
        check("the nested call's stderr explains why", "is not installed" in result["stdout"])


def test_invoking_stale_source_returns_ok_false():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _write_python_job(directory, "b_job", "print('v1')\n")
        stale_entry = _install(directory, "b_job")
        (installed_job_dir(directory, "b_job") / "main.py").write_text("print('v2 -- changed after install')\n")
        _write_python_job(
            directory,
            "a_job",
            "result = RUN_INSTALLED_JOB('b_job')\n"
            "print('nested_ok=' + str(result['ok']))\n"
            "print('nested_stderr=' + result['stderr'])\n",
        )
        window = _FakeWindowForRun(directory, [_install(directory, "a_job"), stale_entry])
        current_context.set_main_window(window)
        current_context.set_gui_thread_caller(lambda fn: fn())
        try:
            result = _run_sync(window, "a_job")
        finally:
            current_context.set_gui_thread_caller(None)
            current_context.set_main_window(None)
        check("nested call on stale source reports ok=False", "nested_ok=False" in result["stdout"])
        check("the stderr names the stale-source refusal", "no longer matches" in result["stdout"])


def test_config_path_passes_through_nested_call():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _write_python_job(directory, "b_job", "print('config=' + str(CONFIG_PATH))\n")
        cfg = directory / "cfg.json"
        cfg.write_text("{}")
        _write_python_job(
            directory,
            "a_job",
            f"result = RUN_INSTALLED_JOB('b_job', {str(cfg)!r})\n"
            "print('nested_stdout=' + result['stdout'].strip())\n",
        )
        window = _FakeWindowForRun(directory, [_install(directory, "a_job"), _install(directory, "b_job")])
        current_context.set_main_window(window)
        current_context.set_gui_thread_caller(lambda fn: fn())
        try:
            result = _run_sync(window, "a_job")
        finally:
            current_context.set_gui_thread_caller(None)
            current_context.set_main_window(None)
        check("config_path reaches the nested job", f"config={cfg}" in result["stdout"])


def test_three_level_nesting():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _write_python_job(directory, "c_job", "print('hello from C')\n")
        _write_python_job(
            directory,
            "b_job",
            "r = RUN_INSTALLED_JOB('c_job')\n"
            "print('B saw: ' + r['stdout'].strip())\n",
        )
        _write_python_job(
            directory,
            "a_job",
            "r = RUN_INSTALLED_JOB('b_job')\n"
            "print('A saw: ' + r['stdout'].strip())\n",
        )
        window = _FakeWindowForRun(
            directory,
            [_install(directory, "a_job"), _install(directory, "b_job"), _install(directory, "c_job")],
        )
        current_context.set_main_window(window)
        current_context.set_gui_thread_caller(lambda fn: fn())
        try:
            result = _run_sync(window, "a_job")
        finally:
            current_context.set_gui_thread_caller(None)
            current_context.set_main_window(None)
        check("three levels of python-to-python nesting succeed", result["ok"])
        check(
            "C's own output survived being relayed through B and then A (real recursion, depth > 1)",
            "A saw: B saw: hello from C" in result["stdout"],
        )


def test_no_gui_thread_caller_registered_degrades_gracefully():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _write_python_job(directory, "b_job", "print('hello from B')\n")
        _write_python_job(
            directory,
            "a_job",
            "result = RUN_INSTALLED_JOB('b_job')\n"
            "print('nested_ok=' + str(result['ok']))\n"
            "print('nested_stderr=' + result['stderr'])\n",
        )
        window = _FakeWindowForRun(directory, [_install(directory, "a_job"), _install(directory, "b_job")])
        current_context.set_main_window(None)
        current_context.set_gui_thread_caller(None)  # deliberately not registered
        result = _run_sync(window, "a_job")
        check("A's own run still succeeds even with no GUI thread caller registered", result["ok"])
        check("the nested call reports ok=False rather than crashing", "nested_ok=False" in result["stdout"])
        check("the nested call's stderr explains the GUI thread is unreachable", "GUI thread is not reachable" in result["stdout"])


test_python_invokes_python_no_deadlock()
test_python_invokes_rust()
test_invoking_not_installed_returns_ok_false_not_raised()
test_invoking_stale_source_returns_ok_false()
test_config_path_passes_through_nested_call()
test_three_level_nesting()
test_no_gui_thread_caller_registered_degrades_gracefully()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
