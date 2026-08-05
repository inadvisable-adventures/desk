import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.temp_ui import (  # noqa: E402
    CUSTOM_WIDGETS_DOC_FILENAME,
    NEW_FEATURES_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    TEMPUI_DOC_VERSION,
    _CUSTOM_WIDGETS_DOC,
    ensure_docs_current,
    parse_doc_version,
    write_tempui_docs,
)

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

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


def test_version_bumped():
    check("TEMPUI_DOC_VERSION is bumped to at least 27", TEMPUI_DOC_VERSION >= 27)


def test_stale_claim_removed():
    check(
        "the old 'no other storage available' claim is gone from tempui-custom-widgets.md",
        "no other storage available" not in _CUSTOM_WIDGETS_DOC,
    )
    check(
        "the old 'only way to persist' claim is gone",
        "it's the only way to persist" not in _CUSTOM_WIDGETS_DOC,
    )


def test_getlocalstorage_still_recommended():
    idx = _CUSTOM_WIDGETS_DOC.find("The Desk Bridge API")
    section = _CUSTOM_WIDGETS_DOC[idx : idx + 1500]
    check(
        "getLocalStorage/setLocalStorage is still presented as the recommended persistence mechanism",
        "getLocalStorage" in section and "recommended" in section.lower(),
    )
    check(
        "the doc explains getLocalStorage's data lives in the portable .desk file",
        ".desk` file" in section or ".desk file" in section,
    )


def test_new_storage_mechanism_scoped_correctly():
    idx = _CUSTOM_WIDGETS_DOC.find("The Desk Bridge API")
    section = _CUSTOM_WIDGETS_DOC[idx : idx + 1500]
    check(
        "the corrected text mentions real per-instance browser storage now persists",
        "persist" in section and ("QWebEngineProfile" in section or "profile" in section.lower()),
    )
    check(
        "the corrected text notes the new storage is tied to .desk_temp and deleted with the instance",
        ".desk_temp" in section and "deleted" in section.lower(),
    )


def test_new_features_doc_has_version_27_entry():
    new_features_doc = SPLIT_DOC_CONTENT[NEW_FEATURES_DOC_FILENAME]
    check("tempui-new-features.md has a Version 27 entry", "## Version 27" in new_features_doc)
    check(
        "the Version 27 entry mentions the storage claim correction",
        "persist" in new_features_doc.split("## Version 27")[1].split("## Version 26")[0]
        if "## Version 27" in new_features_doc
        else False,
    )


def test_ensure_docs_current_still_works_with_new_version():
    """Real, non-mocked: an existing project's doc set on an older
    version gets rewritten to the current version, and the caller
    learns the real previous version -- reusing the exact scenario
    verify_tempui_doc_versioning.py/verify_tempui_doc_upgrade_notification.py
    already establish, just confirming the bump itself didn't break it."""
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        write_tempui_docs(temp_dir)
        custom_widgets_path = temp_dir / CUSTOM_WIDGETS_DOC_FILENAME
        check("tempui-custom-widgets.md was actually written", custom_widgets_path.is_file())
        check(
            "the written file contains the corrected (not stale) storage text",
            "no other storage available" not in custom_widgets_path.read_text(),
        )

        doc_path = temp_dir / "desk-temporary-ui.md"
        stale_text = doc_path.read_text().replace(f"version: {TEMPUI_DOC_VERSION}", "version: 20")
        doc_path.write_text(stale_text)

        rewrote, previous_version = ensure_docs_current(temp_dir)
        check("ensure_docs_current detects the stale (downgraded) version and rewrites", rewrote is True)
        check("ensure_docs_current reports the real previous version", previous_version == 20)
        check(
            "ensure_docs_current rewrites tempui-custom-widgets.md with the corrected text",
            "no other storage available" not in custom_widgets_path.read_text(),
        )
        check(
            "the rewritten main doc embeds the current version",
            parse_doc_version(doc_path.read_text()) == TEMPUI_DOC_VERSION,
        )


test_version_bumped()
test_stale_claim_removed()
test_getlocalstorage_still_recommended()
test_new_storage_mechanism_scoped_correctly()
test_new_features_doc_has_version_27_entry()
test_ensure_docs_current_still_works_with_new_version()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
