import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.desks import Desk, desk_state_dict, load_desk, save_desk  # noqa: E402
from desk.installed_jobs import InstalledJobDefinition, compute_version_hash, installed_job_dir  # noqa: E402

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
        desk = Desk(
            path=desk_path,
            installed_jobs=[
                InstalledJobDefinition(name="greet", version_hash="abc123def456", installed_at="2026-01-01T00:00:00")
            ],
        )
        save_desk(desk)

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


test_hash_is_deterministic_and_reasonably_sized()
test_hash_changes_with_content_and_with_filenames()
test_hash_covers_multiple_files_deterministically_by_path()
test_desk_file_round_trips_installed_jobs()
test_load_desk_defaults_installed_jobs_for_an_old_file_missing_the_key()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
