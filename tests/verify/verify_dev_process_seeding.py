import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "widgets/claude")

from desk.shell.window import (  # noqa: E402
    DeskWindow,
    NOT_DESK_DEVELOPMENT_PROCESS_FILENAME,
    SHARED_DEVELOPMENT_PROCESS_FILENAME,
)
from desk.desks import Desk  # noqa: E402
from desk.shell import current_context  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import widget as claude_mod  # noqa: E402


class _FakeWindow:
    def __init__(self, current_desk):
        self.current_desk = current_desk


_FakeWindow._seed_development_process = DeskWindow._seed_development_process


def test_seed_copies_when_source_exists_and_destination_does_not():
    with tempfile.TemporaryDirectory() as d:
        current_dir = Path(d) / "current"
        current_dir.mkdir()
        (current_dir / "development-process.md").write_text("# My process\n\nDo things carefully.\n")
        new_dir = Path(d) / "new"
        new_dir.mkdir()

        window = _FakeWindow(Desk(path=current_dir / "default.desk"))
        window._seed_development_process(new_dir)

        seeded = new_dir / "development-process.md"
        assert seeded.is_file()
        assert seeded.read_text() == "# My process\n\nDo things carefully.\n"
    print("seeds a real copy when source exists and destination doesn't: PASS")


def test_seed_noop_when_no_source():
    with tempfile.TemporaryDirectory() as d:
        current_dir = Path(d) / "current"
        current_dir.mkdir()
        new_dir = Path(d) / "new"
        new_dir.mkdir()

        window = _FakeWindow(Desk(path=current_dir / "default.desk"))
        window._seed_development_process(new_dir)

        assert not (new_dir / "development-process.md").exists()
    print("no-ops when current Desk has no development-process.md: PASS")


def test_seed_never_overwrites_existing_destination():
    with tempfile.TemporaryDirectory() as d:
        current_dir = Path(d) / "current"
        current_dir.mkdir()
        (current_dir / "development-process.md").write_text("SOURCE CONTENT")
        new_dir = Path(d) / "new"
        new_dir.mkdir()
        (new_dir / "development-process.md").write_text("EXISTING DESTINATION CONTENT")

        window = _FakeWindow(Desk(path=current_dir / "default.desk"))
        window._seed_development_process(new_dir)

        assert (new_dir / "development-process.md").read_text() == "EXISTING DESTINATION CONTENT"
    print("never overwrites an existing destination file: PASS")


def test_seed_noop_when_same_directory():
    with tempfile.TemporaryDirectory() as d:
        current_dir = Path(d)
        (current_dir / "development-process.md").write_text("SOURCE CONTENT")

        window = _FakeWindow(Desk(path=current_dir / "default.desk"))
        # Same directory as current -- source and destination resolve
        # identically; _seed_development_process itself should just leave
        # the file as-is (destination.exists() is already True).
        window._seed_development_process(current_dir)
        assert (current_dir / "development-process.md").read_text() == "SOURCE CONTENT"
    print("no-ops when source and destination are the same file: PASS")


def test_seed_return_value_true_when_peer_seeded_alongside_pre_existing_top_level():
    with tempfile.TemporaryDirectory() as d:
        current_dir = Path(d) / "current"
        current_dir.mkdir()
        (current_dir / "development-process.md").write_text("SOURCE TOP LEVEL")
        (current_dir / SHARED_DEVELOPMENT_PROCESS_FILENAME).write_text("SOURCE SHARED")
        (current_dir / NOT_DESK_DEVELOPMENT_PROCESS_FILENAME).write_text("SOURCE NOT-DESK")
        new_dir = Path(d) / "new"
        new_dir.mkdir()
        (new_dir / "development-process.md").write_text("PRE-EXISTING TOP LEVEL")

        window = _FakeWindow(Desk(path=current_dir / "default.desk"))
        result = window._seed_development_process(new_dir)

        assert result is True
        assert (new_dir / "development-process.md").read_text() == "PRE-EXISTING TOP LEVEL"
        assert (new_dir / SHARED_DEVELOPMENT_PROCESS_FILENAME).read_text() == "SOURCE SHARED"
        assert (new_dir / NOT_DESK_DEVELOPMENT_PROCESS_FILENAME).read_text() == "SOURCE NOT-DESK"
    print("returns True: peer(s) newly seeded alongside a pre-existing top-level file: PASS")


def test_seed_return_value_false_for_brand_new_project():
    with tempfile.TemporaryDirectory() as d:
        current_dir = Path(d) / "current"
        current_dir.mkdir()
        (current_dir / "development-process.md").write_text("SOURCE TOP LEVEL")
        (current_dir / SHARED_DEVELOPMENT_PROCESS_FILENAME).write_text("SOURCE SHARED")
        new_dir = Path(d) / "new"
        new_dir.mkdir()  # nothing pre-existing here at all

        window = _FakeWindow(Desk(path=current_dir / "default.desk"))
        result = window._seed_development_process(new_dir)

        assert result is False
        assert (new_dir / "development-process.md").is_file()
        assert (new_dir / SHARED_DEVELOPMENT_PROCESS_FILENAME).is_file()
    print("returns False: brand-new project, nothing pre-existing to explain: PASS")


def test_seed_return_value_false_when_nothing_newly_seeded():
    with tempfile.TemporaryDirectory() as d:
        current_dir = Path(d) / "current"
        current_dir.mkdir()
        (current_dir / "development-process.md").write_text("SOURCE TOP LEVEL")
        (current_dir / SHARED_DEVELOPMENT_PROCESS_FILENAME).write_text("SOURCE SHARED")
        new_dir = Path(d) / "new"
        new_dir.mkdir()
        (new_dir / "development-process.md").write_text("PRE-EXISTING TOP LEVEL")
        (new_dir / SHARED_DEVELOPMENT_PROCESS_FILENAME).write_text("PRE-EXISTING SHARED")

        window = _FakeWindow(Desk(path=current_dir / "default.desk"))
        result = window._seed_development_process(new_dir)

        assert result is False
        assert (new_dir / SHARED_DEVELOPMENT_PROCESS_FILENAME).read_text() == "PRE-EXISTING SHARED"
    print("returns False: destination already had every file, nothing newly seeded: PASS")


def test_claude_prompt_mentions_file_when_present():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / "development-process.md").write_text("# process\n")
        current_context.set_current_desk_directory(directory)
        instruction = claude_mod._development_process_instruction()
        assert instruction != ""
        assert "development-process.md" in instruction
        assert str(directory / "development-process.md") in instruction
        # TODO b78e7b8: orientation only, for both widgets.
        assert "orientation only" in instruction
        assert "unless the message from the user separately asks for it" in instruction
        import importlib.util

        spec = importlib.util.spec_from_file_location("claude_desk_widget", "widgets/claude_desk/widget.py")
        desk_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(desk_mod)
        desk_instruction = desk_mod._development_process_instruction()
        assert str(directory / "development-process.md") in desk_instruction
        assert "orientation only" in desk_instruction
        assert "unless the message from the user separately asks for it" in desk_instruction
    print("Claude prompt instruction mentions the file when present: PASS")


def test_claude_prompt_unchanged_when_absent():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)  # no development-process.md here
        current_context.set_current_desk_directory(directory)
        instruction = claude_mod._development_process_instruction()
        assert instruction == ""

        full_prompt = claude_mod.CLAUDE_WIDGET_PROMPT.format(doc_path=claude_mod._doc_path()) + instruction
        assert full_prompt == claude_mod.CLAUDE_WIDGET_PROMPT.format(doc_path=claude_mod._doc_path())
    print("prompt construction unchanged (regression) when file absent: PASS")


def test_claude_prompt_empty_when_no_current_directory():
    current_context.set_current_desk_directory(None)
    assert claude_mod._development_process_instruction() == ""
    print("empty instruction when no current Desk directory known yet: PASS")


test_seed_copies_when_source_exists_and_destination_does_not()
test_seed_noop_when_no_source()
test_seed_never_overwrites_existing_destination()
test_seed_noop_when_same_directory()
test_seed_return_value_true_when_peer_seeded_alongside_pre_existing_top_level()
test_seed_return_value_false_for_brand_new_project()
test_seed_return_value_false_when_nothing_newly_seeded()
test_claude_prompt_mentions_file_when_present()
test_claude_prompt_unchanged_when_absent()
test_claude_prompt_empty_when_no_current_directory()
print("ALL PASS")
