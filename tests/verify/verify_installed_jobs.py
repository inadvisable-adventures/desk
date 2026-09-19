import json
import os
import sys
import tempfile
import threading
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

from desk.desks import Desk, desk_state_dict, load_desk, save_desk  # noqa: E402
from desk.installed_jobs import (  # noqa: E402
    InstalledJobDefinition,
    compute_version_hash,
    installed_job_dir,
    resolve_config_path,
)
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


def _write(directory: Path, name: str, files: dict[str, str]) -> Path:
    job_dir = installed_job_dir(directory, name)
    job_dir.mkdir(parents=True, exist_ok=True)
    for relative_path, content in files.items():
        path = job_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return job_dir


def test_hash_is_deterministic_and_reasonably_sized():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        job_dir = _write(directory, "greet", {"main.py": "print('hi')\n"})
        h1 = compute_version_hash(job_dir)
        h2 = compute_version_hash(job_dir)
        check("hash is deterministic across calls", h1 == h2)
        check("hash is 12 hex chars (reasonable-sized, matching the custom-widget precedent)", len(h1) == 12)
        check("hash is valid hex", all(c in "0123456789abcdef" for c in h1))


def test_hash_changes_with_content_and_with_filenames():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        job_dir = _write(directory, "greet", {"main.py": "print('hi')\n"})
        original = compute_version_hash(job_dir)

        (job_dir / "main.py").write_text("print('bye')\n")
        check("hash changes when a file's content changes", compute_version_hash(job_dir) != original)

        (job_dir / "main.py").write_text("print('hi')\n")
        check("hash is back to original once content matches again", compute_version_hash(job_dir) == original)

        (job_dir / "helper.py").write_text("VALUE = 1\n")
        check("hash changes when a file is added", compute_version_hash(job_dir) != original)


def test_hash_covers_multiple_files_deterministically_by_path():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        job_dir = _write(directory, "multi", {"main.py": "import helper\n", "helper.py": "X = 1\n"})
        h1 = compute_version_hash(job_dir)

        # Rewriting in a different order shouldn't matter -- rglob is sorted.
        (job_dir / "helper.py").write_text("X = 1\n")
        (job_dir / "main.py").write_text("import helper\n")
        h2 = compute_version_hash(job_dir)
        check("multi-file hash is stable regardless of write order", h1 == h2)


def test_desk_file_round_trips_installed_jobs():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        desk_path = directory / "default.desk"
        built_desk = Desk(
            path=desk_path,
            installed_jobs=[
                InstalledJobDefinition(name="greet", version_hash="abc123def456", installed_at="2026-01-01T00:00:00")
            ],
        )
        save_desk(built_desk)

        raw = json.loads(desk_path.read_text())
        check("installed_jobs section is present in the raw .desk JSON", "installed_jobs" in raw)
        check(
            "raw installed_jobs entry has the right shape",
            raw["installed_jobs"] == [
                {"name": "greet", "version_hash": "abc123def456", "installed_at": "2026-01-01T00:00:00"}
            ],
        )

        reloaded = load_desk(desk_path)
        check("load_desk reconstructs installed_jobs", len(reloaded.installed_jobs) == 1)
        check("reloaded entry has the right name/hash", reloaded.installed_jobs[0].name == "greet")
        check("reloaded entry has the right version_hash", reloaded.installed_jobs[0].version_hash == "abc123def456")

        state = desk_state_dict(reloaded)
        check("desk_state_dict includes installed_jobs too (Bridge API parity)", "installed_jobs" in state)


def test_load_desk_defaults_installed_jobs_for_an_old_file_missing_the_key():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        desk_path = directory / "default.desk"
        desk_path.write_text(json.dumps({"widgets": []}))
        reloaded = load_desk(desk_path)
        check("an old .desk file with no installed_jobs key loads with an empty list", reloaded.installed_jobs == [])


def test_resolve_config_path():
    directory = Path("/some/desk/dir")
    check("None stays None", resolve_config_path(directory, None) is None)
    check("empty string becomes None", resolve_config_path(directory, "") is None)
    check(
        "a relative path resolves against the given directory",
        resolve_config_path(directory, "cfg.json") == str(directory / "cfg.json"),
    )
    check(
        "an already-absolute path is used as-is",
        resolve_config_path(directory, "/elsewhere/cfg.json") == "/elsewhere/cfg.json",
    )


class _FakeWindowForRun:
    """A minimal duck-typed stand-in for DeskWindow -- only
    .current_desk is real state; get_installed_job_for_run/
    run_installed_job are grabbed directly off the real DeskWindow
    class below and called with this as `self`, so this test exercises
    the actual production logic (including the real background thread
    + desk.installed_jobs.run_script), not a reimplementation of it --
    mirrors verify_lock_persistence.py's own
    `_FakeWindow._capture_desk_state = DeskWindow._capture_desk_state`
    technique."""

    def __init__(self, directory: Path, installed_jobs: list[InstalledJobDefinition]) -> None:
        self.current_desk = Desk(path=directory / "default.desk", installed_jobs=installed_jobs)

    get_installed_job = DeskWindow.get_installed_job
    get_installed_job_for_run = DeskWindow.get_installed_job_for_run
    run_installed_job = DeskWindow.run_installed_job
    # TODO 94a2fa2: run_installed_job now also calls this -- pulled in
    # the same real-production-logic-not-reimplemented way as the three
    # methods above. Never touches self.get_state/self._schema_registry
    # in this file's tests (none of them write a job.json), so no
    # further fake attributes are needed for it here.
    _resolve_job_needs = DeskWindow._resolve_job_needs
    # TODO 0959ff1: run_installed_job now goes through these two
    # instead of its own inline logic -- same pull-the-real-method
    # technique. _make_run_installed_job_callable's own closure is
    # built by every run_installed_job call now, but this file's own
    # jobs never actually call RUN_INSTALLED_JOB, so it's never
    # invoked -- no current_context.get_gui_thread_caller() setup
    # needed here (see verify_installed_job_to_job_invocation.py for
    # that).
    _prepare_installed_job_run = DeskWindow._prepare_installed_job_run
    _make_run_installed_job_callable = DeskWindow._make_run_installed_job_callable


def test_get_installed_job_for_run_raises_for_not_installed_and_stale_hash():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        job_dir = installed_job_dir(directory, "greet")
        job_dir.mkdir(parents=True)
        (job_dir / "main.py").write_text("print('v1')\n")
        real_hash = compute_version_hash(job_dir)

        window = _FakeWindowForRun(
            directory, [InstalledJobDefinition(name="greet", version_hash=real_hash, installed_at="2026-01-01T00:00:00")]
        )
        check("a matching hash returns the job, no error", window.get_installed_job_for_run("greet").name == "greet")

        try:
            window.get_installed_job_for_run("ghost")
            check("not-installed raises ValueError", False)
        except ValueError as e:
            check("not-installed raises ValueError", "is not installed" in str(e))

        (job_dir / "main.py").write_text("print('v2 -- changed after install')\n")
        try:
            window.get_installed_job_for_run("greet")
            check("stale hash raises ValueError", False)
        except ValueError as e:
            check("stale hash raises ValueError", "no longer matches" in str(e) and "desk_install_job" in str(e))


def test_run_installed_job_is_non_blocking_and_reports_a_real_result():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        job_dir = installed_job_dir(directory, "greet")
        job_dir.mkdir(parents=True)
        (job_dir / "main.py").write_text("import time\ntime.sleep(0.2)\nprint('done', CONFIG_PATH)\n")
        real_hash = compute_version_hash(job_dir)
        window = _FakeWindowForRun(
            directory, [InstalledJobDefinition(name="greet", version_hash=real_hash, installed_at="2026-01-01T00:00:00")]
        )

        results = []
        event = threading.Event()

        def on_result(ok, stdout, stderr, tb):
            results.append((ok, stdout, stderr, tb))
            event.set()

        # Note: no check() (it print()s) until after event.wait() below
        # -- run_script's contextlib.redirect_stdout swaps sys.stdout
        # process-wide for as long as the job's own 0.2s sleep runs,
        # not just for this background thread, so a print() from any
        # other thread during that window is silently captured into
        # the job's own stdout buffer instead of reaching the real
        # terminal (see LEARNINGS.md). Capture every condition into a
        # plain variable first; print results only once the job has
        # actually finished and swapped stdout back.
        started = time.monotonic()
        window.run_installed_job("greet", "cfg.json", on_result)
        returned_immediately = (time.monotonic() - started) < 0.1
        result_not_yet_set = results == []
        eventually_fired = event.wait(timeout=5)

        check("run_installed_job returns immediately, not after the job's own 0.2s sleep", returned_immediately)
        check("on_result hasn't fired yet immediately after returning", result_not_yet_set)
        check("on_result eventually fires from the background thread", eventually_fired)
        ok, stdout, stderr, tb = results[0]
        check("the real job ran successfully", ok is True)
        check(
            "CONFIG_PATH was resolved against the Desk directory before the job ran",
            stdout.strip() == f"done {directory / 'cfg.json'}",
        )


def test_run_installed_job_raises_synchronously_for_a_validation_failure():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        window = _FakeWindowForRun(directory, [])
        try:
            window.run_installed_job("ghost", None, lambda *a: None)
            check("running a not-installed job raises synchronously, not via on_result", False)
        except ValueError as e:
            check("running a not-installed job raises synchronously, not via on_result", "is not installed" in str(e))


test_hash_is_deterministic_and_reasonably_sized()
test_hash_changes_with_content_and_with_filenames()
test_hash_covers_multiple_files_deterministically_by_path()
test_desk_file_round_trips_installed_jobs()
test_load_desk_defaults_installed_jobs_for_an_old_file_missing_the_key()
test_resolve_config_path()
test_get_installed_job_for_run_raises_for_not_installed_and_stale_hash()
test_run_installed_job_is_non_blocking_and_reports_a_real_result()
test_run_installed_job_raises_synchronously_for_a_validation_failure()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
