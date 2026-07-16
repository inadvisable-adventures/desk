import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.window import DeskWindow  # noqa: E402
from desk.desks import Desk  # noqa: E402
from desk.temp_ui import ensure_gitignore_entry, GITIGNORE_ENTRIES, GITIGNORE_COMMENT  # noqa: E402
from desk.todo_ids import make_item_id  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)


class _FakeWindow:
    def __init__(self, current_desk):
        self.current_desk = current_desk


_FakeWindow._seed_todo_item_ids_script = DeskWindow._seed_todo_item_ids_script


def test_seed_copies_and_marks_executable():
    with tempfile.TemporaryDirectory() as d:
        current_dir = Path(d) / "current"
        current_dir.mkdir()
        (current_dir / "scripts").mkdir()
        script_text = "#!/usr/bin/env python3\nprint('hi')\n"
        (current_dir / "scripts" / "todo_item_ids.py").write_text(script_text)
        new_dir = Path(d) / "new"
        new_dir.mkdir()

        window = _FakeWindow(Desk(path=current_dir / "default.desk"))
        window._seed_todo_item_ids_script(new_dir)

        seeded = new_dir / "scripts" / "todo_item_ids.py"
        assert seeded.is_file()
        assert seeded.read_text() == script_text
        assert seeded.stat().st_mode & 0o777 == 0o755
    print("seeds a real copy (creating scripts/) and marks it executable: PASS")


def test_seed_noop_when_no_source():
    with tempfile.TemporaryDirectory() as d:
        current_dir = Path(d) / "current"
        current_dir.mkdir()
        new_dir = Path(d) / "new"
        new_dir.mkdir()

        window = _FakeWindow(Desk(path=current_dir / "default.desk"))
        window._seed_todo_item_ids_script(new_dir)

        assert not (new_dir / "scripts" / "todo_item_ids.py").exists()
        assert not (new_dir / "scripts").exists()
    print("no-ops (no scripts/ dir created) when current Desk has no script: PASS")


def test_seed_never_overwrites_existing_destination():
    with tempfile.TemporaryDirectory() as d:
        current_dir = Path(d) / "current"
        current_dir.mkdir()
        (current_dir / "scripts").mkdir()
        (current_dir / "scripts" / "todo_item_ids.py").write_text("SOURCE CONTENT")
        new_dir = Path(d) / "new"
        (new_dir / "scripts").mkdir(parents=True)
        (new_dir / "scripts" / "todo_item_ids.py").write_text("EXISTING DESTINATION CONTENT")

        window = _FakeWindow(Desk(path=current_dir / "default.desk"))
        window._seed_todo_item_ids_script(new_dir)

        assert (new_dir / "scripts" / "todo_item_ids.py").read_text() == "EXISTING DESTINATION CONTENT"
    print("never overwrites an existing destination file: PASS")


def test_seed_noop_when_same_directory():
    with tempfile.TemporaryDirectory() as d:
        current_dir = Path(d)
        (current_dir / "scripts").mkdir()
        (current_dir / "scripts" / "todo_item_ids.py").write_text("SOURCE CONTENT")

        window = _FakeWindow(Desk(path=current_dir / "default.desk"))
        window._seed_todo_item_ids_script(current_dir)
        assert (current_dir / "scripts" / "todo_item_ids.py").read_text() == "SOURCE CONTENT"
    print("no-ops when source and destination are the same file: PASS")


def test_real_script_is_self_contained_and_matches_desk_todo_ids():
    script_path = Path("scripts/todo_item_ids.py").resolve()
    assert script_path.is_file()
    source_text = script_path.read_text()
    # Static check, not just "it happened to run OK": this project's own
    # venv has `desk` installed editable regardless of PYTHONPATH, so a
    # subprocess run alone wouldn't actually prove independence.
    assert "import desk" not in source_text and "from desk" not in source_text, source_text
    with tempfile.TemporaryDirectory() as d:
        isolated_copy = Path(d) / "todo_item_ids.py"
        isolated_copy.write_text(source_text)
        # A bare system python3, deliberately not sys.executable (this
        # project's own venv, where `desk` is installed editable
        # regardless of cwd/PYTHONPATH) -- a real stand-in for "some
        # other project with no relation to this repo or its venv."
        result = subprocess.run(
            ["/usr/bin/env", "python3", str(isolated_copy), "new", "a sufficiently long description"],
            cwd=d,
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        printed_id = result.stdout.strip()
        assert printed_id == make_item_id("a sufficiently long description"), (
            printed_id,
            make_item_id("a sufficiently long description"),
        )
    print("real scripts/todo_item_ids.py has no desk-package import, and runs standalone "
          "and agrees with desk.todo_ids.make_item_id: PASS")


def test_gitignore_fresh_file_gets_both_entries():
    with tempfile.TemporaryDirectory() as d:
        git_root = Path(d)
        (git_root / ".git").mkdir()
        ensure_gitignore_entry(git_root, ask=lambda: True)
        text = (git_root / ".gitignore").read_text()
        expected_block = "\n".join(GITIGNORE_ENTRIES)
        assert text == f"\n{GITIGNORE_COMMENT}\n{expected_block}\n", repr(text)
    print("fresh .gitignore gets both entries under one comment block: PASS")


def test_gitignore_only_appends_missing_entry():
    with tempfile.TemporaryDirectory() as d:
        git_root = Path(d)
        (git_root / ".git").mkdir()
        (git_root / ".gitignore").write_text(".desk_temp/\n")
        ensure_gitignore_entry(git_root, ask=lambda: True)
        text = (git_root / ".gitignore").read_text()
        assert text.count(".desk_temp/") == 1, text
        assert "**/__pycache__/" in text
    print("only the missing entry gets appended when one already exists: PASS")


def test_gitignore_already_present_is_noop():
    with tempfile.TemporaryDirectory() as d:
        git_root = Path(d)
        (git_root / ".git").mkdir()
        (git_root / ".gitignore").write_text("\n".join(GITIGNORE_ENTRIES) + "\n")
        calls = []
        ensure_gitignore_entry(git_root, ask=lambda: calls.append(1) or True)
        assert calls == []
        assert (git_root / ".gitignore").read_text() == "\n".join(GITIGNORE_ENTRIES) + "\n"
    print("both entries already present: no-op, ask() never called: PASS")


test_seed_copies_and_marks_executable()
test_seed_noop_when_no_source()
test_seed_never_overwrites_existing_destination()
test_seed_noop_when_same_directory()
test_real_script_is_self_contained_and_matches_desk_todo_ids()
test_gitignore_fresh_file_gets_both_entries()
test_gitignore_only_appends_missing_entry()
test_gitignore_already_present_is_noop()
print("ALL PASS")
