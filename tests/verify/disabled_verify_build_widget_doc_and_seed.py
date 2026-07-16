# DISABLED (see tests/verify/README.md) -- TODO 69ebfb0 tracks
# investigating this. Current failure: Fails on DeskWindow._seed_build_widget_script, which no longer
# exists -- TODO 029047b removed it entirely (superseded by the ensure
# mechanism, TODO e57ce5f). Several other assertions here (stale
# TEMPUI_DOC_VERSION == 11, doc mentioning custom_widget_src) predate an
# even earlier TODO (59c5a70) that relocated widget authoring source.
# Reasonable suspicion: this test covers a design superseded twice over
# -- likely just delete it rather than patch it forward.

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from desk.temp_ui import (
    CUSTOM_WIDGETS_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    TEMPUI_DOC_VERSION,
)
from desk.shell.window import DeskWindow

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


check("TEMPUI_DOC_VERSION bumped to 11", TEMPUI_DOC_VERSION == 11)
custom_widgets_doc = SPLIT_DOC_CONTENT[CUSTOM_WIDGETS_DOC_FILENAME]
check("doc mentions custom_widget_src", "custom_widget_src/<name>/" in custom_widgets_doc)
check("doc mentions build_widget.py", "scripts/build_widget.py" in custom_widgets_doc)
check("doc explains why not widgets/", "not** under `widgets/`" in custom_widgets_doc)
check(
    "doc section appears before Invoking a defined widget",
    custom_widgets_doc.index("Authoring from real source")
    < custom_widgets_doc.index("## Invoking a defined widget"),
)

# Seeding: mirror _seed_todo_item_ids_script's own copy-if-missing/
# never-overwrite/executable-bit behavior via an unbound-method-on-a
# -fake-double, same pattern used throughout this session.
class _FakeDesk:
    def __init__(self, directory):
        self.directory = directory


class _FakeWindow:
    def __init__(self, current_desk_dir):
        self.current_desk = _FakeDesk(current_desk_dir)


_FakeWindow._seed_build_widget_script = DeskWindow._seed_build_widget_script

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    source_project = tmp_path / "source"
    dest_project = tmp_path / "dest"
    (source_project / "scripts").mkdir(parents=True)
    (source_project / "scripts" / "build_widget.py").write_text("# stub\n")
    dest_project.mkdir()

    fake = _FakeWindow(source_project)
    fake._seed_build_widget_script(dest_project)
    dest_script = dest_project / "scripts" / "build_widget.py"
    check("script copied into new project", dest_script.is_file())
    check("copied script content matches", dest_script.read_text() == "# stub\n")
    check("copied script is executable", dest_script.stat().st_mode & 0o755 == 0o755)

    # Never overwrite an existing destination.
    dest_script.write_text("# user's own version\n")
    fake._seed_build_widget_script(dest_project)
    check("existing destination never overwritten", dest_script.read_text() == "# user's own version\n")

    # No-op if there's nothing to source from.
    empty_source = tmp_path / "empty_source"
    empty_source.mkdir()
    other_dest = tmp_path / "other_dest"
    other_dest.mkdir()
    _FakeWindow(empty_source)._seed_build_widget_script(other_dest)
    check(
        "no-op when source script doesn't exist",
        not (other_dest / "scripts" / "build_widget.py").exists(),
    )

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
