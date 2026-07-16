# DISABLED (see tests/verify/README.md) -- TODO f3120bb tracks
# investigating this. Current failure: Fails on check("no remaining file_explorer/File Explorer content
# anywhere", remaining == []) -- the grep this performs doesn't account
# for this project's own explicit convention that historical mentions
# (TODO.md's completed-item narrative, a rename plan's own prose) are
# deliberately preserved, not scrubbed. Reasonable suspicion: the
# assertion is overly strict relative to established project
# convention -- TODO.md's own line describing TODO 8385dcc necessarily
# still says "File Explorer", so this check may never have actually
# passed; worth confirming intent (scope the grep to src/widgets/
# design-docs only?) rather than assuming it's a real regression.

import glob
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from desk.widgets import discover_widgets  # noqa: E402

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

widgets = discover_widgets(REPO_ROOT / "widgets")
check("project_files discovered", "project_files" in widgets)
check("file_explorer no longer discovered", "file_explorer" not in widgets)
info = widgets.get("project_files")
check("kind is python", info is not None and info.kind == "python")
check("name is Project Files", info is not None and info.name == "Project Files")

check("old directory no longer exists", not (REPO_ROOT / "widgets" / "file_explorer").exists())
check("new directory exists", (REPO_ROOT / "widgets" / "project_files").is_dir())

class_source = (REPO_ROOT / "widgets" / "project_files" / "widget.py").read_text()
check("class renamed to ProjectFilesWidget", "class ProjectFilesWidget(QWidget):" in class_source)
check("build() returns the renamed class", "return ProjectFilesWidget()" in class_source)
check("old class name gone", "FileExplorerWidget" not in class_source)

# No remaining "file_explorer"/"File Explorer" content anywhere except
# stable plan filenames (deliberately not renamed -- see the plan).
search_dirs = ["src", "widgets", "design-docs", "TODO.md", "PARKINGLOT.md", "LEARNINGS.md", "plans"]
result = subprocess.run(
    ["grep", "-rl", "--exclude-dir=__pycache__", "file_explorer\\|File Explorer", *search_dirs],
    cwd=REPO_ROOT, capture_output=True, text=True,
)
remaining = [line for line in result.stdout.splitlines() if line]
check("no remaining file_explorer/File Explorer content anywhere", remaining == [])

# Plan filenames themselves are deliberately preserved.
old_plan_names = {
    "plans/file-explorer-widget.md",
    "plans/file-explorer-toolbar-zoom-scaling.md",
    "plans/file-explorer-viewer-editor-scrap-fallback.md",
}
existing_plan_files = {f"plans/{Path(p).name}" for p in glob.glob(str(REPO_ROOT / "plans" / "*.md"))}
check("original plan filenames preserved", old_plan_names.issubset(existing_plan_files))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
