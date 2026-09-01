import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from desk.temp_ui import (  # noqa: E402
    JOBS_DOC_FILENAME,
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


check("TEMPUI_DOC_VERSION bumped to at least 31", TEMPUI_DOC_VERSION >= 31)

main_doc = render_static_doc()
check("main doc's file-type list mentions Job", "`Job`" in main_doc)
check("main doc links tempui-jobs.md (the every-split-file-linked invariant)", "tempui-jobs.md" in main_doc)
check(
    # TODO 97bd090: this count moved on again (nine -> ten) when the
    # DeskProc keyword was added -- was "nine, not eight" when this
    # assertion was first written for the Job keyword itself; updated
    # to check the current count rather than the historical one, same
    # as the file-type list's own text always reflects the current
    # count, not whichever keyword most recently bumped it.
    "main doc's file-type count reflects the current built-in count (ten)",
    "ten\nbuilt-in file types" in main_doc or "ten built-in file types" in main_doc,
)

check("tempui-jobs.md is registered in SPLIT_DOC_CONTENT", JOBS_DOC_FILENAME in SPLIT_DOC_CONTENT)
jobs_doc = SPLIT_DOC_CONTENT[JOBS_DOC_FILENAME]
check("jobs doc documents the Job/kind/summary first-line format", "Job<TAB>kind<TAB>summary" in jobs_doc)
check("jobs doc documents Capability lines", "Capability<TAB>name" in jobs_doc)
check("jobs doc documents Script lines", "Script<TAB>base64-chunk" in jobs_doc)
check("jobs doc lists the real capability namespace names", all(name in jobs_doc for name in ("workspace", "fs", "widgets", "events", "filetypes", "editor", "popups", "transforms", "introspect")))
check("jobs doc cross-references the Bridge API's full documentation rather than duplicating it", "tempui-custom-widgets.md" in jobs_doc)
check("jobs doc explains the html-kind 'Done' caveat", "async" in jobs_doc and "Done" in jobs_doc)
check("jobs doc explains that Start is disabled/one-shot", "disabled" in jobs_doc)

new_features_doc = SPLIT_DOC_CONTENT["tempui-new-features.md"]
check("new-features doc has a Version 31 entry", "## Version 31" in new_features_doc)
check("Version 31 entry mentions the Job keyword", "Job" in new_features_doc.split("## Version 31", 1)[1].split("## Version 30", 1)[0])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
