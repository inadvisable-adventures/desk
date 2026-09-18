import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.temp_ui import (  # noqa: E402
    INSTALLED_JOBS_DOC_FILENAME,
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


check("changelog still covers this feature (version-40)", "version-40" in CURRENT_TAGS)

main_doc = render_static_doc()
check(
    "main doc links tempui-installed-jobs.md (the every-split-file-linked invariant)",
    "tempui-installed-jobs.md" in main_doc,
)
check(
    "Installed Jobs is introduced in the \"a few more files\" paragraph, not the DSL keyword list",
    "A few more files live here too, but aren't DSL file types" in main_doc
    and "tempui-installed-jobs.md" in main_doc.split("A few more files live here too", 1)[1],
)
check(
    "the main file-type count was NOT bumped (Installed Jobs isn't a dropped-file DSL keyword)",
    "ten\nbuilt-in file types" in main_doc or "ten built-in file types" in main_doc,
)

check("tempui-installed-jobs.md is registered in SPLIT_DOC_CONTENT", INSTALLED_JOBS_DOC_FILENAME in SPLIT_DOC_CONTENT)
installed_jobs_doc = SPLIT_DOC_CONTENT[INSTALLED_JOBS_DOC_FILENAME]
check(
    "doc documents the desk-installed-jobs/<name>/main.py storage convention",
    "desk-installed-jobs/<name>/main.py" in installed_jobs_doc,
)
check("doc documents the desk_install_job tool", "desk_install_job" in installed_jobs_doc)
check("doc documents the desk_run_installed_job tool", "desk_run_installed_job" in installed_jobs_doc)
check("doc documents the config_path argument", "config_path" in installed_jobs_doc)
check("doc documents the CONFIG_PATH global convention", "CONFIG_PATH" in installed_jobs_doc)
check(
    "doc explains config generally lives under .desk_temp/ unless otherwise specified",
    ".desk_temp/" in installed_jobs_doc,
)
check(
    "doc explains approval happens once, at install, not on every run",
    "never prompts for approval" in installed_jobs_doc or "no further prompt" in installed_jobs_doc,
)
check("doc explains the stale-source refusal", "no longer matches" in installed_jobs_doc)
check("doc mentions the Installed Jobs widget's View Source/Uninstall actions", "View Source" in installed_jobs_doc)
check("doc explains uninstall keeps the source on disk", "left on disk" in installed_jobs_doc)
check(
    "doc cross-references the ephemeral Job mechanism it's an alternative to",
    "tempui-jobs.md" in installed_jobs_doc,
)
check(
    "doc documents the Bridge API's installedJobs.run for kind:html widgets (TODO 888b537)",
    "desk.installedJobs.run" in installed_jobs_doc and "installed_jobs" in installed_jobs_doc,
)
check(
    "doc cross-references tempui-custom-widgets.md for the Bridge API's full call shape",
    "tempui-custom-widgets.md" in installed_jobs_doc,
)
check("doc explains the Bridge API path's own 120-second bound", "120 second" in installed_jobs_doc)

new_features_doc = SPLIT_DOC_CONTENT["tempui-new-features.md"]
check("new-features doc has a Version 40 entry", "## Version 40" in new_features_doc)
check(
    "Version 40 entry mentions Installed Jobs",
    "Installed Jobs" in new_features_doc.split("## Version 40", 1)[1].split("## Version 39", 1)[0],
)
check("new-features doc has a Version 41 entry", "## Version 41" in new_features_doc)
check(
    "Version 41 entry mentions the installed_jobs Bridge API capability",
    "installed_jobs" in new_features_doc.split("## Version 41", 1)[1].split("## Version 40", 1)[0],
)

custom_widgets_doc = SPLIT_DOC_CONTENT["tempui-custom-widgets.md"]
check(
    "custom-widgets doc's Bridge API section documents desk.installedJobs.run",
    "desk.installedJobs.run(name, configPath)" in custom_widgets_doc,
)
check(
    "custom-widgets doc's Bridge API bullet names the installed_jobs capability",
    "capability\n  `installed_jobs`" in custom_widgets_doc or "capability `installed_jobs`" in custom_widgets_doc,
)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
