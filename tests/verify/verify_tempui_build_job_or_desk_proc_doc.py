import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.temp_ui import (  # noqa: E402
    BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME,
    DESK_PROC_DOC_FILENAME,
    JOBS_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    CURRENT_TAGS,
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


check("changelog still covers this feature (version-30)", "version-30" in CURRENT_TAGS)

main_doc = render_static_doc()
check("main doc's build-script paragraph mentions build_job_or_desk_proc.py", "build_job_or_desk_proc.py" in main_doc)

check(
    "build_job_or_desk_proc.py is registered in SPLIT_DOC_CONTENT",
    BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME in SPLIT_DOC_CONTENT,
)
script_content = SPLIT_DOC_CONTENT[BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME]
check("the generated script has a real shebang", script_content.startswith("#!/usr/bin/env python3"))
check("the generated script documents the desk-proc subcommand", "desk-proc" in script_content)
check("the generated script documents the job subcommand", "job KIND SUMMARY SCRIPT" in script_content)
check("the generated script compiles as valid Python", compile(script_content, BUILD_JOB_OR_DESK_PROC_SCRIPT_FILENAME, "exec"))

jobs_doc = SPLIT_DOC_CONTENT[JOBS_DOC_FILENAME]
check("jobs doc cross-references the build helper", "build_job_or_desk_proc.py" in jobs_doc)

desk_proc_doc = SPLIT_DOC_CONTENT[DESK_PROC_DOC_FILENAME]
check("desk-proc doc cross-references the build helper", "build_job_or_desk_proc.py" in desk_proc_doc)

new_features_doc = SPLIT_DOC_CONTENT["tempui-new-features.md"]
check("new-features doc has a Version 39 entry", "## Version 39" in new_features_doc)
check(
    "Version 39 entry mentions the build helper",
    "build_job_or_desk_proc.py" in new_features_doc.split("## Version 39", 1)[1].split("## Version 38", 1)[0],
)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
