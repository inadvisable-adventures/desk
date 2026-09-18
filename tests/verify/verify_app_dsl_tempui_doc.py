import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.temp_ui import (  # noqa: E402
    CUSTOM_WIDGETS_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    TEMPUI_DOC_VERSION,
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


check("TEMPUI_DOC_VERSION bumped to at least 33", TEMPUI_DOC_VERSION >= 33)

custom_widgets_doc = SPLIT_DOC_CONTENT[CUSTOM_WIDGETS_DOC_FILENAME]
check("tempui-custom-widgets.md cross-references app_dsl/README.md", "app_dsl/README.md" in custom_widgets_doc)
check(
    "the cross-reference documents both codegen modes, not just the standalone one",
    "--mode=module" in custom_widgets_doc and "--mode=global" in custom_widgets_doc,
)
check(
    "the cross-reference names build_widget.py as the global-mode consumer",
    "build_widget.py" in custom_widgets_doc,
)

new_features_doc = SPLIT_DOC_CONTENT["tempui-new-features.md"]
check("new-features doc has a Version 32 entry", "## Version 32" in new_features_doc)
check("new-features doc has a Version 33 entry", "## Version 33" in new_features_doc)
version_32_section = new_features_doc.split("## Version 32", 1)[1].split("## Version 31", 1)[0]
check("Version 32 entry mentions app_dsl", "app_dsl" in version_32_section)
check("Version 32 entry points to the README for the DSL format", "app_dsl/README.md" in version_32_section)
version_33_section = new_features_doc.split("## Version 33", 1)[1].split("## Version 32", 1)[0]
check("Version 33 entry mentions the new --mode=global option", "--mode=global" in version_33_section)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
