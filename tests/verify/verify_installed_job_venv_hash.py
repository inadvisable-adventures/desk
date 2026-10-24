"""TODO e5b5567: compute_version_hash skips a job's own top-level .venv but still
covers requirements.txt."""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.installed_jobs import compute_version_hash  # noqa: E402
from desk.temp_ui import CURRENT_TAGS, _NEW_FEATURES  # noqa: E402

passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    job = Path(d) / "job"
    job.mkdir()
    (job / "main.py").write_text("print(1)\n")
    (job / "requirements.txt").write_text("numpy==1.0\n")
    base = compute_version_hash(job)

    (job / ".venv" / "lib" / "site-packages").mkdir(parents=True)
    (job / ".venv" / "lib" / "site-packages" / "numpy.py").write_text("x")
    (job / ".venv" / "pyvenv.cfg").write_text("home = /x\n")
    check("adding a .venv does not change the hash", compute_version_hash(job) == base)
    (job / ".venv" / "lib" / "site-packages" / "numpy.py").write_text("changed")
    check("changing .venv contents does not change the hash", compute_version_hash(job) == base)

    (job / "requirements.txt").write_text("numpy==2.0\n")
    changed = compute_version_hash(job)
    check("bumping requirements.txt changes the hash", changed != base)
    (job / "requirements.txt").write_text("numpy==1.0\n")

    (job / "sub" / ".venv").mkdir(parents=True)
    (job / "sub" / ".venv" / "f.txt").write_text("a")
    nested = compute_version_hash(job)
    check("a nested .venv elsewhere in the tree is still hashed", nested != base)
    (job / "sub" / ".venv" / "f.txt").write_text("b")
    check("...and its contents count", compute_version_hash(job) != nested)

    # only the exact name `.venv` is skipped
    other = Path(d) / "job2"
    other.mkdir()
    (other / "main.py").write_text("print(1)\n")
    (other / "venv").mkdir()
    (other / "venv" / "x").write_text("1")
    before = compute_version_hash(other)
    (other / "venv" / "x").write_text("2")
    check("only .venv is special: a root `venv/` is still hashed", compute_version_hash(other) != before)

    # speed: a big venv costs nothing
    big = Path(d) / "big"
    (big / ".venv").mkdir(parents=True)
    (big / "main.py").write_text("x")
    for n in range(2000):
        (big / ".venv" / f"f{n}.bin").write_bytes(b"0" * 1024)
    start = time.time()
    compute_version_hash(big)
    check("2000-file venv adds no hashing cost (< 0.5 s)", time.time() - start < 0.5)

check("tag minted", "installed job version hash skips .venv #284781" in CURRENT_TAGS)
check("changelog entry present and mentions re-approval", "call `desk_install_job` again" in _NEW_FEATURES["installed job version hash skips .venv #284781"])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
