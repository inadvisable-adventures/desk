import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.temp_ui import (  # noqa: E402
    DESK_PROC_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    TEMPUI_DOC_VERSION,
    render_static_doc,
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


check("TEMPUI_DOC_VERSION bumped to at least 38", TEMPUI_DOC_VERSION >= 38)

main_doc = render_static_doc()
check("main doc's file-type list mentions DeskProc", "`DeskProc`" in main_doc)
check("main doc links tempui-desk-proc.md (the every-split-file-linked invariant)", "tempui-desk-proc.md" in main_doc)
check("main doc's file-type count was bumped (ten, not nine)", "ten\nbuilt-in file types" in main_doc or "ten built-in file types" in main_doc)

check("tempui-desk-proc.md is registered in SPLIT_DOC_CONTENT", DESK_PROC_DOC_FILENAME in SPLIT_DOC_CONTENT)
desk_proc_doc = SPLIT_DOC_CONTENT[DESK_PROC_DOC_FILENAME]
check("desk-proc doc documents the DeskProc/summary first-line format", "DeskProc<TAB>summary" in desk_proc_doc)
check("desk-proc doc documents Script lines", "Script<TAB>base64-chunk" in desk_proc_doc)
check("desk-proc doc documents the deskproc.reveal_widget method", "deskproc.reveal_widget" in desk_proc_doc)
check("desk-proc doc documents the deskproc.screenshot_widget method", "deskproc.screenshot_widget" in desk_proc_doc)
check("desk-proc doc documents the deskproc.screenshot_desk method", "deskproc.screenshot_desk" in desk_proc_doc)
check("desk-proc doc documents the deskproc.list_widget_instances method", "deskproc.list_widget_instances" in desk_proc_doc)
check("desk-proc doc cross-references Job for the Bridge-API-only case", "`Job`" in desk_proc_doc or "tempui-jobs.md" in desk_proc_doc)
check("desk-proc doc explains there is no html-kind variant", "html" in desk_proc_doc.lower())
check("desk-proc doc explains Start is disabled/one-shot", "disabled" in desk_proc_doc)
check("desk-proc doc explains the notification is visually distinct", "DESK PROC" in desk_proc_doc)

new_features_doc = SPLIT_DOC_CONTENT["tempui-new-features.md"]
check("new-features doc has a Version 38 entry", "## Version 38" in new_features_doc)
check(
    "Version 38 entry mentions the DeskProc keyword",
    "DeskProc" in new_features_doc.split("## Version 38", 1)[1].split("## Version 37", 1)[0],
)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
