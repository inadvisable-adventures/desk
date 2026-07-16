import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from desk.shell.window import (  # noqa: E402
    DEVELOPMENT_PROCESS_FILENAME,
    NOT_DESK_DEVELOPMENT_PROCESS_FILENAME,
    SHARED_DEVELOPMENT_PROCESS_FILENAME,
    DeskWindow,
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


REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")

# ---------- file contents ----------

dev_process = (REPO_ROOT / DEVELOPMENT_PROCESS_FILENAME).read_text()
shared = (REPO_ROOT / SHARED_DEVELOPMENT_PROCESS_FILENAME).read_text()
not_desk = (REPO_ROOT / NOT_DESK_DEVELOPMENT_PROCESS_FILENAME).read_text()

check("top-level doc has 'When working on Desk itself' section", "## When working on Desk itself" in dev_process)
check("top-level doc explains the doc hierarchy", "development-process doc hierarchy" in dev_process.lower() or "three development-process documents" in dev_process)
check("top-level doc instructs asking the user when ambiguous", "ask the user for clarification" in dev_process)
check("top-level doc instructs updating the changelog docs", "tempui-breaking-changes.md" in dev_process and "tempui-new-features.md" in dev_process)
check("top-level doc links to shared_development_process.md", "(./shared_development_process.md)" in dev_process)
check("top-level doc links to the not-desk-itself peer", "(./specifically-not-working-on-desk-itself-development-process.md)" in dev_process)
check("top-level doc no longer carries the full Item IDs section itself", "### Generating an id for a new item" not in dev_process)

check("shared doc carries the forked Item IDs section", "### Generating an id for a new item" in shared)
check("shared doc carries the Planning workflow", "## Planning" in shared)
check("shared doc carries Working on TODO Items", "## Working on TODO Items" in shared)
check("shared doc carries Prioritizing TODO Items", "## Prioritizing TODO Items" in shared)
check("shared doc carries Learnings", "## Learnings" in shared)

check("not-desk-itself peer file is empty", not_desk == "" or not_desk.strip() == "")

# ---------- seeding ----------


class _FakeDesk:
    def __init__(self, directory):
        self.directory = directory


class _FakeWindow:
    def __init__(self, source_directory):
        self.current_desk = _FakeDesk(source_directory)


_FakeWindow._seed_development_process = DeskWindow._seed_development_process


def test_seeds_all_three_into_a_fresh_project():
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d)
        win = _FakeWindow(REPO_ROOT)
        win._seed_development_process(dest)
        check("development-process.md seeded", (dest / DEVELOPMENT_PROCESS_FILENAME).read_text() == dev_process)
        check("shared_development_process.md seeded", (dest / SHARED_DEVELOPMENT_PROCESS_FILENAME).read_text() == shared)
        check("not-working-on-desk-itself peer seeded", (dest / NOT_DESK_DEVELOPMENT_PROCESS_FILENAME).read_text() == not_desk)


def test_never_overwrites_an_existing_destination_file():
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d)
        (dest / SHARED_DEVELOPMENT_PROCESS_FILENAME).write_text("the destination project's own version")
        win = _FakeWindow(REPO_ROOT)
        win._seed_development_process(dest)
        check("existing shared_development_process.md left untouched", (dest / SHARED_DEVELOPMENT_PROCESS_FILENAME).read_text() == "the destination project's own version")
        check("development-process.md still seeded independently", (dest / DEVELOPMENT_PROCESS_FILENAME).read_text() == dev_process)


def test_noop_when_source_has_none():
    with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as dest_dir:
        win = _FakeWindow(Path(source_dir))
        win._seed_development_process(Path(dest_dir))
        check("no files seeded when source Desk has none", list(Path(dest_dir).iterdir()) == [])


test_seeds_all_three_into_a_fresh_project()
test_never_overwrites_an_existing_destination_file()
test_noop_when_source_has_none()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
