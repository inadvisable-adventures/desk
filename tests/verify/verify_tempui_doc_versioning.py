import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.temp_ui import (  # noqa: E402
    TEMPUI_DOC_VERSION,
    CUSTOM_WIDGETS_SECTION_START,
    CUSTOM_WIDGETS_SECTION_END,
    CustomWidgetDefinition,
    SPLIT_DOC_CONTENT,
    DOC_FILENAME,
    ensure_docs_current,
    parse_doc_version,
    render_static_doc,
    render_custom_widgets_section,
    write_tempui_docs,
)

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.shell.temp_ui_manager import TempUiManager  # noqa: E402

REPO_REFERENCE_STRINGS = ("design-docs", "markdown-rendering.md", "plans/", "src/desk")


def _all_doc_content() -> str:
    return render_static_doc() + "".join(SPLIT_DOC_CONTENT.values())


# ---------- pure parsing/rendering ----------


def test_parse_doc_version_present():
    doc = render_static_doc()
    assert parse_doc_version(doc) == TEMPUI_DOC_VERSION
    print("parse_doc_version: extracts the current version from a freshly rendered doc: PASS")


def test_parse_doc_version_missing():
    assert parse_doc_version("# Temporary UI\n\nNo version note here.\n") is None
    assert parse_doc_version("") is None
    print("parse_doc_version: returns None when there's no version note at all: PASS")


def test_parse_doc_version_malformed():
    assert parse_doc_version("<!-- desk-temporary-ui.md version: not-a-number -->\n") is None
    print("parse_doc_version: returns None for a malformed (non-numeric) version note: PASS")


def test_render_static_doc_no_placeholder_leftover():
    doc = render_static_doc()
    assert "{{TEMPUI_DOC_VERSION}}" not in doc
    assert f"version: {TEMPUI_DOC_VERSION}" in doc
    print("render_static_doc: placeholder fully substituted, no leftover token: PASS")


def test_split_docs_carry_no_version_note():
    for filename, content in SPLIT_DOC_CONTENT.items():
        assert parse_doc_version(content) is None, filename
    print("split docs: none carry their own version note -- the main file's stands for all: PASS")


def test_no_doc_mentions_desk_repo_material():
    all_docs = _all_doc_content()
    for needle in REPO_REFERENCE_STRINGS:
        assert needle not in all_docs, f"found {needle!r} in the tempui doc set"
    print("no tempui doc (main or split) mentions Desk source code or repo documents: PASS")


def test_main_doc_links_to_every_split_file():
    doc = render_static_doc()
    for filename in SPLIT_DOC_CONTENT:
        assert filename in doc, f"{filename} not referenced from the main doc"
    print("the main doc references every split-out file by its relative filename: PASS")


# ---------- write_tempui_docs / ensure_docs_current ----------


def test_write_tempui_docs_writes_main_and_every_split_file():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        write_tempui_docs(temp_dir)
        doc_path = temp_dir / DOC_FILENAME
        assert doc_path.is_file()
        assert parse_doc_version(doc_path.read_text()) == TEMPUI_DOC_VERSION
        assert CUSTOM_WIDGETS_SECTION_START not in doc_path.read_text()  # not this function's job
        for filename, content in SPLIT_DOC_CONTENT.items():
            split_path = temp_dir / filename
            assert split_path.is_file()
            assert split_path.read_text() == content
    print("write_tempui_docs: writes the main file (no custom-widgets section) and every split file: PASS")


def test_ensure_docs_current_noop_when_main_missing():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        ensure_docs_current(temp_dir)
        assert not (temp_dir / DOC_FILENAME).exists()
        assert not any((temp_dir / filename).exists() for filename in SPLIT_DOC_CONTENT)
    print("ensure_docs_current: no-op (creates nothing) when the main file is missing: PASS")


def test_ensure_docs_current_noop_when_current_and_all_present():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        write_tempui_docs(temp_dir)
        main_before = (temp_dir / DOC_FILENAME).read_text()
        split_before = {filename: (temp_dir / filename).read_text() for filename in SPLIT_DOC_CONTENT}

        ensure_docs_current(temp_dir)

        assert (temp_dir / DOC_FILENAME).read_text() == main_before
        for filename, text in split_before.items():
            assert (temp_dir / filename).read_text() == text
    print("ensure_docs_current: no-op (byte-for-byte untouched) when version matches and every split file is present: PASS")


def test_ensure_docs_current_refreshes_when_split_file_missing_even_if_version_current():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        write_tempui_docs(temp_dir)
        missing_name = next(iter(SPLIT_DOC_CONTENT))
        (temp_dir / missing_name).unlink()

        ensure_docs_current(temp_dir)

        assert (temp_dir / missing_name).is_file()
        assert (temp_dir / missing_name).read_text() == SPLIT_DOC_CONTENT[missing_name]
    print("ensure_docs_current: refreshes the whole set if a split file is missing, even with a current version: PASS")


def test_ensure_docs_current_refreshes_when_no_version_note():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        (temp_dir / DOC_FILENAME).write_text("# Temporary UI\n\nSome ancient, pre-versioning content.\n")

        ensure_docs_current(temp_dir)

        text = (temp_dir / DOC_FILENAME).read_text()
        assert parse_doc_version(text) == TEMPUI_DOC_VERSION
        assert "Some ancient, pre-versioning content." not in text
        for filename in SPLIT_DOC_CONTENT:
            assert (temp_dir / filename).is_file()
    print("ensure_docs_current: an unversioned main file is out of date -- refreshes the whole set: PASS")


def test_ensure_docs_current_refreshes_old_version_preserving_custom_section():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        old_static = render_static_doc().replace(f"version: {TEMPUI_DOC_VERSION}", "version: 0")
        definition = CustomWidgetDefinition(keyword="KanbanBoard", label="Kanban Board", html_b64="x")
        custom_section = render_custom_widgets_section([(definition, "tempui")])
        (temp_dir / DOC_FILENAME).write_text(old_static.rstrip("\n") + "\n\n" + custom_section + "\n")

        ensure_docs_current(temp_dir)

        text = (temp_dir / DOC_FILENAME).read_text()
        assert parse_doc_version(text) == TEMPUI_DOC_VERSION
        assert "Kanban Board" in text  # custom-widgets section preserved
        assert text.count(CUSTOM_WIDGETS_SECTION_START) == 1
        for filename, content in SPLIT_DOC_CONTENT.items():
            assert (temp_dir / filename).read_text() == content
    print("ensure_docs_current: refreshes an old version, preserving the custom-widgets section, writing every split file: PASS")


def test_ensure_docs_current_refreshes_old_version_no_custom_section():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        old_static = render_static_doc().replace(f"version: {TEMPUI_DOC_VERSION}", "version: 0")
        (temp_dir / DOC_FILENAME).write_text(old_static)

        ensure_docs_current(temp_dir)

        text = (temp_dir / DOC_FILENAME).read_text()
        assert parse_doc_version(text) == TEMPUI_DOC_VERSION
        assert CUSTOM_WIDGETS_SECTION_START not in text  # nothing fabricated
    print("ensure_docs_current: refreshes an old version with no custom-widgets section, fabricates none: PASS")


# ---------- TempUiManager.provision integration ----------


def test_provision_first_creation_writes_whole_set_at_current_version():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        manager = TempUiManager()
        manager.provision(directory, ask_create_dir=lambda: True, ask_gitignore=lambda: False)
        temp_dir = directory / ".desk_temp"
        doc_path = temp_dir / DOC_FILENAME
        assert doc_path.is_file()
        assert parse_doc_version(doc_path.read_text()) == TEMPUI_DOC_VERSION
        for filename in SPLIT_DOC_CONTENT:
            assert (temp_dir / filename).is_file()
    print("TempUiManager.provision: first creation writes the whole doc set at the current version: PASS")


def test_provision_refreshes_stale_existing_doc_set():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        doc_path = temp_dir / DOC_FILENAME
        definition = CustomWidgetDefinition(keyword="KanbanBoard", label="Kanban Board", html_b64="x")
        custom_section = render_custom_widgets_section([(definition, "desk")])
        doc_path.write_text("# Temporary UI\n\nPre-versioning content.\n\n" + custom_section + "\n")
        # No split files at all yet either -- simulates a Desk provisioned
        # before TODO e57ce5f existed.

        manager = TempUiManager()
        manager.provision(directory, ask_create_dir=lambda: True, ask_gitignore=lambda: False)

        text = doc_path.read_text()
        assert parse_doc_version(text) == TEMPUI_DOC_VERSION
        assert "Pre-versioning content." not in text
        assert "Kanban Board" in text  # custom-widgets section survived provisioning too
        for filename in SPLIT_DOC_CONTENT:
            assert (temp_dir / filename).is_file()
    print("TempUiManager.provision: refreshes a stale pre-split doc set in place, preserving its custom-widgets section: PASS")


test_parse_doc_version_present()
test_parse_doc_version_missing()
test_parse_doc_version_malformed()
test_render_static_doc_no_placeholder_leftover()
test_split_docs_carry_no_version_note()
test_no_doc_mentions_desk_repo_material()
test_main_doc_links_to_every_split_file()
test_write_tempui_docs_writes_main_and_every_split_file()
test_ensure_docs_current_noop_when_main_missing()
test_ensure_docs_current_noop_when_current_and_all_present()
test_ensure_docs_current_refreshes_when_split_file_missing_even_if_version_current()
test_ensure_docs_current_refreshes_when_no_version_note()
test_ensure_docs_current_refreshes_old_version_preserving_custom_section()
test_ensure_docs_current_refreshes_old_version_no_custom_section()
test_provision_first_creation_writes_whole_set_at_current_version()
test_provision_refreshes_stale_existing_doc_set()
print("ALL PASS")
