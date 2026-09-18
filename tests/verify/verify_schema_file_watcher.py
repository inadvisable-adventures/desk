import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.shell.schema_file_watcher import SchemaFileWatcher, TOP_LEVEL_SCHEMAS_DIRNAME  # noqa: E402

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


def _pump_until(predicate, timeout=6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        app.processEvents()
        time.sleep(0.02)
    return predicate()


def test_initial_scan_picks_up_pre_existing_files():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        ephemeral = directory / ".desk_temp" / "schemas"
        ephemeral.mkdir(parents=True)
        (ephemeral / "existing.json").write_text(json.dumps({"a": "number"}))
        (ephemeral / "ignored.txt").write_text("not json")

        seen = []
        watcher = SchemaFileWatcher()
        watcher.changed.connect(seen.append)
        watcher.provision(ephemeral, directory)

        _pump_until(lambda: len(seen) >= 1)
        check("a pre-existing .json file is picked up by the initial scan", len(seen) == 1)
        check(
            "the emitted path resolves to the real file",
            seen and seen[0].resolve() == (ephemeral / "existing.json").resolve(),
        )
        check("a non-.json file in the same directory is ignored", not any(p.suffix == ".txt" for p in seen))


def test_live_add_edit_delete_on_ephemeral_directory():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        ephemeral = directory / ".desk_temp" / "schemas"
        ephemeral.mkdir(parents=True)

        seen = []
        watcher = SchemaFileWatcher()
        watcher.changed.connect(seen.append)
        watcher.provision(ephemeral, directory)

        target = ephemeral / "live.json"
        target.write_text(json.dumps({"a": "number"}))
        _pump_until(lambda: len(seen) >= 1)
        check("a file added after provisioning fires changed", len(seen) == 1)
        added_path = seen[0].resolve()

        seen.clear()
        target.write_text(json.dumps({"a": "string"}))
        _pump_until(lambda: len(seen) >= 1)
        check("editing the same file fires changed again", len(seen) == 1)
        check("the edited file's path matches the added one exactly", seen and seen[0].resolve() == added_path)

        seen.clear()
        target.unlink()
        _pump_until(lambda: len(seen) >= 1)
        check("deleting the file fires changed", len(seen) == 1)
        check("the deleted file no longer exists at the emitted path", seen and not seen[0].is_file())


def test_top_level_directory_is_polled_until_it_exists():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        top_level = directory / TOP_LEVEL_SCHEMAS_DIRNAME
        check("the top-level directory does not exist yet", not top_level.is_dir())

        seen = []
        watcher = SchemaFileWatcher()
        watcher.changed.connect(seen.append)
        watcher.provision(None, directory)

        # Nothing should be created by Desk itself.
        app.processEvents()
        check("SchemaFileWatcher never creates the top-level directory itself", not top_level.is_dir())

        top_level.mkdir()
        (top_level / "top.json").write_text(json.dumps({"b": "boolean"}))
        # Generous timeout: this exercises the real poll interval, not a live watch.
        _pump_until(lambda: len(seen) >= 1, timeout=10.0)
        check(
            "a file in the newly-created top-level directory is picked up once polling notices it",
            len(seen) == 1,
        )

        seen.clear()
        (top_level / "second.json").write_text(json.dumps({"c": "string"}))
        _pump_until(lambda: len(seen) >= 1)
        check(
            "a second file added after the directory is found uses a real live watch, not another poll cycle",
            len(seen) == 1,
        )


test_initial_scan_picks_up_pre_existing_files()
test_live_add_edit_delete_on_ephemeral_directory()
test_top_level_directory_is_polled_until_it_exists()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
