# DISABLED (see tests/verify/README.md) -- TODO 28119c6 tracks
# investigating this. Current failure: Fails on 3 stale range assertions ("features doc covers versions
# 7-14", "breaking doc covers only version 14") written when
# TEMPUI_DOC_VERSION was 14 (TODO 7462cdb, which created these docs) --
# the doc set has since grown through version 17 across later TODOs
# (1a96c9f, 029047b). Reasonable suspicion: not a real bug, just
# assertions that need to grow alongside every future version bump --
# worth deciding whether to keep updating them by hand or rewrite as a
# looser "covers every version up to the current TEMPUI_DOC_VERSION"
# check.

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from desk.temp_ui import (  # noqa: E402
    BREAKING_CHANGES_DOC_FILENAME,
    NEW_FEATURES_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    TEMPUI_DOC_VERSION,
    render_static_doc,
    write_tempui_docs,
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


check("TEMPUI_DOC_VERSION bumped to 15", TEMPUI_DOC_VERSION == 15)
check("breaking-changes doc registered", BREAKING_CHANGES_DOC_FILENAME in SPLIT_DOC_CONTENT)
check("new-features doc registered", NEW_FEATURES_DOC_FILENAME in SPLIT_DOC_CONTENT)

breaking = SPLIT_DOC_CONTENT[BREAKING_CHANGES_DOC_FILENAME]
features = SPLIT_DOC_CONTENT[NEW_FEATURES_DOC_FILENAME]

import re  # noqa: E402

breaking_versions = [int(m) for m in re.findall(r"## Version (\d+)", breaking)]
features_versions = [int(m) for m in re.findall(r"## Version (\d+)", features)]
check("breaking doc versions strictly descending", breaking_versions == sorted(breaking_versions, reverse=True))
check("features doc versions strictly descending", features_versions == sorted(features_versions, reverse=True))
check("features doc covers versions 7-14", features_versions == [14, 13, 12, 11, 10, 9, 8, 7])
check("breaking doc covers only version 14 (the one real breaking change)", breaking_versions == [14])

check("breaking doc mentions the source-directory move", "custom_widget_src" in breaking and ".desk_temp/widgets" in breaking)
check("features doc mentions events capability (v7)", "events" in features.lower())
check("features doc mentions OpenImage (v10)", "OpenImage" in features)
check("both docs note versions 1-6 predate the changelog", "predate this changelog" in breaking and "predate this changelog" in features)

doc_template = render_static_doc()
check("main doc links tempui-breaking-changes.md", "tempui-breaking-changes.md" in doc_template)
check("main doc links tempui-new-features.md", "tempui-new-features.md" in doc_template)
check(
    "the changelog paragraph appears after the built-in file types list",
    doc_template.index("Every file named above lives in this same directory.")
    < doc_template.index("tempui-breaking-changes.md"),
)

# ---------- write_tempui_docs writes both files into a fresh .desk_temp ----------

with tempfile.TemporaryDirectory() as d:
    temp_dir = Path(d) / ".desk_temp"
    temp_dir.mkdir()
    write_tempui_docs(temp_dir)
    check("tempui-breaking-changes.md written to disk", (temp_dir / BREAKING_CHANGES_DOC_FILENAME).is_file())
    check("tempui-new-features.md written to disk", (temp_dir / NEW_FEATURES_DOC_FILENAME).is_file())
    check(
        "written breaking-changes content matches SPLIT_DOC_CONTENT",
        (temp_dir / BREAKING_CHANGES_DOC_FILENAME).read_text() == breaking,
    )

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
