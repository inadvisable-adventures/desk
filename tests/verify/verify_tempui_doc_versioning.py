import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.temp_ui import (  # noqa: E402
    CURRENT_TAG_SET,
    CURRENT_TAGS,
    CUSTOM_WIDGETS_SECTION_START,
    CUSTOM_WIDGETS_SECTION_END,
    CustomWidgetDefinition,
    SPLIT_DOC_CONTENT,
    DOC_FILENAME,
    Tag,
    TAG_COLLAPSES,
    _canonicalize_tags,
    _legacy_version_tags,
    ensure_docs_current,
    generate_tag,
    parse_doc_tags,
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


def _strip_tag_lines(text: str) -> str:
    import re

    return re.sub(r"<!-- desk-temporary-ui\.md tag: .+? -->\n?", "", text)


# ---------- Tag / generate_tag ----------


def test_generate_tag_validates_length():
    tag = generate_tag("a perfectly reasonable summary", now=1_000_000.0)
    assert isinstance(tag, Tag)
    assert tag.summary == "a perfectly reasonable summary"
    assert tag.hash == f"{int(1_000_000.0 * 1000) % 1_000_000:06d}"
    assert tag.id == f"{tag.summary} #{tag.hash}"
    try:
        generate_tag("short")
        assert False, "expected ValueError for a too-short summary"
    except ValueError:
        pass
    try:
        generate_tag("x" * 51)
        assert False, "expected ValueError for a too-long summary"
    except ValueError:
        pass
    print("generate_tag: validates summary length, derives a deterministic hash from `now`: PASS")


def test_generate_tag_deterministic_and_distinct():
    a = generate_tag("first workstream's own tag", now=1000.0)
    b = generate_tag("second workstream's own tag", now=1000.001)
    assert a.id != b.id
    assert generate_tag("first workstream's own tag", now=1000.0).id == a.id
    print("generate_tag: same (summary, now) is deterministic; different `now` never collides here: PASS")


# ---------- _legacy_version_tags ----------


def test_legacy_version_tags_excludes_own_bucket():
    # TODO ee1a474: a project's own bucket is never assumed fully known
    # -- only every bucket strictly below it. A bucket covers ten
    # version numbers, being somewhere inside one doesn't mean being at
    # its top, and old version numbers weren't reliably unique besides
    # (two branches once both claimed "44" on different content), so
    # the bucket a project's own version falls into always comes back
    # missing regardless of where in that bucket the version actually
    # sits.
    assert _legacy_version_tags(5) == frozenset()
    assert _legacy_version_tags(9) == frozenset()
    assert _legacy_version_tags(10) == frozenset({"version-00"})
    assert _legacy_version_tags(20) == frozenset({"version-00", "version-10"})
    assert _legacy_version_tags(25) == frozenset({"version-00", "version-10"})
    assert _legacy_version_tags(29) == frozenset({"version-00", "version-10"})
    assert _legacy_version_tags(42) == frozenset({"version-00", "version-10", "version-20", "version-30"})
    assert _legacy_version_tags(46) == frozenset({"version-00", "version-10", "version-20", "version-30"})
    print("_legacy_version_tags: buckets by decade, strictly below the project's own bucket only: PASS")


# ---------- _canonicalize_tags / TAG_COLLAPSES ----------


def test_canonicalize_tags_passthrough_when_no_collapses():
    assert _canonicalize_tags({"version-00", "version-10"}) == frozenset({"version-00", "version-10"})
    print("_canonicalize_tags: passes tags through unchanged when TAG_COLLAPSES is empty: PASS")


def test_canonicalize_tags_resolves_chained_collapses():
    fake_collapses = {"A": "C", "B": "C", "C": "D"}
    TAG_COLLAPSES.update(fake_collapses)
    try:
        assert _canonicalize_tags({"A", "B", "X"}) == frozenset({"D", "X"})
    finally:
        for key in fake_collapses:
            del TAG_COLLAPSES[key]
    print("_canonicalize_tags: resolves an old tag through a chain of collapses to its final id: PASS")


# ---------- pure parsing/rendering ----------


def test_parse_doc_tags_present():
    doc = render_static_doc()
    assert parse_doc_tags(doc) == set(CURRENT_TAGS)
    print("parse_doc_tags: extracts every current tag from a freshly rendered doc: PASS")


def test_parse_doc_tags_missing():
    assert parse_doc_tags("# Temporary UI\n\nNo tag or version note here.\n") is None
    assert parse_doc_tags("") is None
    print("parse_doc_tags: returns None when there's no tag or legacy version note at all: PASS")


def test_parse_doc_tags_legacy_version_migration():
    text = "# Temporary UI\n\n<!-- desk-temporary-ui.md version: 25 -->\n"
    assert parse_doc_tags(text) == set(_legacy_version_tags(25))
    print("parse_doc_tags: migrates a pre-tags file's legacy version note via _legacy_version_tags: PASS")


def test_parse_doc_tags_malformed_legacy_version():
    assert parse_doc_tags("<!-- desk-temporary-ui.md version: not-a-number -->\n") is None
    print("parse_doc_tags: returns None for a malformed (non-numeric) legacy version note: PASS")


def test_render_static_doc_no_placeholder_leftover():
    doc = render_static_doc()
    assert "{{TEMPUI_DOC_TAGS}}" not in doc
    for tag in CURRENT_TAGS:
        assert f"<!-- desk-temporary-ui.md tag: {tag} -->" in doc
    print("render_static_doc: placeholder fully substituted with one comment per current tag: PASS")


def test_split_docs_carry_no_tag_note():
    for filename, content in SPLIT_DOC_CONTENT.items():
        assert parse_doc_tags(content) is None, filename
    print("split docs: none carry their own tag comments -- the main file's stand for all: PASS")


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
        assert parse_doc_tags(doc_path.read_text()) == set(CURRENT_TAGS)
        assert CUSTOM_WIDGETS_SECTION_START not in doc_path.read_text()  # not this function's job
        for filename, content in SPLIT_DOC_CONTENT.items():
            split_path = temp_dir / filename
            assert split_path.is_file()
            assert split_path.read_text() == content
    print("write_tempui_docs: writes the main file (no custom-widgets section) and every split file: PASS")


def test_ensure_docs_current_noop_when_main_missing():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        rewrote, missing = ensure_docs_current(temp_dir)
        assert (rewrote, missing) == (False, frozenset())
        assert not (temp_dir / DOC_FILENAME).exists()
        assert not any((temp_dir / filename).exists() for filename in SPLIT_DOC_CONTENT)
    print("ensure_docs_current: no-op (creates nothing) when the main file is missing: PASS")


def test_ensure_docs_current_noop_when_current_and_all_present():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        write_tempui_docs(temp_dir)
        main_before = (temp_dir / DOC_FILENAME).read_text()
        split_before = {filename: (temp_dir / filename).read_text() for filename in SPLIT_DOC_CONTENT}

        rewrote, missing = ensure_docs_current(temp_dir)

        assert (rewrote, missing) == (False, frozenset())
        assert (temp_dir / DOC_FILENAME).read_text() == main_before
        for filename, text in split_before.items():
            assert (temp_dir / filename).read_text() == text
    print("ensure_docs_current: no-op (byte-for-byte untouched) when every tag matches and every split file is present: PASS")


def test_ensure_docs_current_refreshes_when_split_file_missing_even_if_tags_current():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        write_tempui_docs(temp_dir)
        missing_name = next(iter(SPLIT_DOC_CONTENT))
        (temp_dir / missing_name).unlink()

        rewrote, missing = ensure_docs_current(temp_dir)

        assert rewrote is True
        assert missing == frozenset()  # nothing was actually behind on tags, just a missing file
        assert (temp_dir / missing_name).is_file()
        assert (temp_dir / missing_name).read_text() == SPLIT_DOC_CONTENT[missing_name]
    print("ensure_docs_current: refreshes the whole set if a split file is missing, even with a current tag set: PASS")


def test_ensure_docs_current_refreshes_when_no_tag_note():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        (temp_dir / DOC_FILENAME).write_text("# Temporary UI\n\nSome ancient, pre-tracking content.\n")

        rewrote, missing = ensure_docs_current(temp_dir)

        text = (temp_dir / DOC_FILENAME).read_text()
        assert rewrote is True
        assert missing == frozenset()  # nothing to diff against -- silently topped up, not "notify-worthy"
        assert parse_doc_tags(text) == set(CURRENT_TAGS)
        assert "Some ancient, pre-tracking content." not in text
        for filename in SPLIT_DOC_CONTENT:
            assert (temp_dir / filename).is_file()
    print("ensure_docs_current: a file with no tag/version note is out of date -- refreshes the whole set, silently: PASS")


def test_ensure_docs_current_refreshes_legacy_version_preserving_custom_section():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        old_static = _strip_tag_lines(render_static_doc()).replace(
            "# Temporary UI\n", "# Temporary UI\n\n<!-- desk-temporary-ui.md version: 0 -->\n", 1
        )
        definition = CustomWidgetDefinition(keyword="KanbanBoard", label="Kanban Board", html_b64="x")
        custom_section = render_custom_widgets_section([(definition, "tempui")])
        (temp_dir / DOC_FILENAME).write_text(old_static.rstrip("\n") + "\n\n" + custom_section + "\n")

        rewrote, missing = ensure_docs_current(temp_dir)

        text = (temp_dir / DOC_FILENAME).read_text()
        assert rewrote is True
        assert missing == CURRENT_TAG_SET - _legacy_version_tags(0)
        assert parse_doc_tags(text) == set(CURRENT_TAGS)
        assert "Kanban Board" in text  # custom-widgets section preserved
        assert text.count(CUSTOM_WIDGETS_SECTION_START) == 1
        for filename, content in SPLIT_DOC_CONTENT.items():
            assert (temp_dir / filename).read_text() == content
    print("ensure_docs_current: refreshes a legacy version note, preserving the custom-widgets section, writing every split file: PASS")


def test_ensure_docs_current_refreshes_legacy_version_no_custom_section():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)
        old_static = _strip_tag_lines(render_static_doc()).replace(
            "# Temporary UI\n", "# Temporary UI\n\n<!-- desk-temporary-ui.md version: 0 -->\n", 1
        )
        (temp_dir / DOC_FILENAME).write_text(old_static)

        rewrote, missing = ensure_docs_current(temp_dir)

        text = (temp_dir / DOC_FILENAME).read_text()
        assert rewrote is True
        assert missing == CURRENT_TAG_SET - _legacy_version_tags(0)
        assert parse_doc_tags(text) == set(CURRENT_TAGS)
        assert CUSTOM_WIDGETS_SECTION_START not in text  # nothing fabricated
    print("ensure_docs_current: refreshes a legacy version note with no custom-widgets section, fabricates none: PASS")


# ---------- TempUiManager.provision integration ----------


def test_provision_first_creation_writes_whole_set_at_current_tags():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        manager = TempUiManager()
        manager.provision(directory, ask_create_dir=lambda: True, ask_gitignore=lambda: False)
        temp_dir = directory / ".desk_temp"
        doc_path = temp_dir / DOC_FILENAME
        assert doc_path.is_file()
        assert parse_doc_tags(doc_path.read_text()) == set(CURRENT_TAGS)
        for filename in SPLIT_DOC_CONTENT:
            assert (temp_dir / filename).is_file()
    print("TempUiManager.provision: first creation writes the whole doc set with every current tag: PASS")


def test_provision_refreshes_stale_existing_doc_set():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        doc_path = temp_dir / DOC_FILENAME
        definition = CustomWidgetDefinition(keyword="KanbanBoard", label="Kanban Board", html_b64="x")
        custom_section = render_custom_widgets_section([(definition, "desk")])
        doc_path.write_text("# Temporary UI\n\nPre-tracking content.\n\n" + custom_section + "\n")
        # No split files at all yet either -- simulates a Desk provisioned
        # before TODO e57ce5f existed.

        manager = TempUiManager()
        manager.provision(directory, ask_create_dir=lambda: True, ask_gitignore=lambda: False)

        text = doc_path.read_text()
        assert parse_doc_tags(text) == set(CURRENT_TAGS)
        assert "Pre-tracking content." not in text
        assert "Kanban Board" in text  # custom-widgets section survived provisioning too
        for filename in SPLIT_DOC_CONTENT:
            assert (temp_dir / filename).is_file()
    print("TempUiManager.provision: refreshes a stale pre-split doc set in place, preserving its custom-widgets section: PASS")


test_generate_tag_validates_length()
test_generate_tag_deterministic_and_distinct()
test_legacy_version_tags_excludes_own_bucket()
test_canonicalize_tags_passthrough_when_no_collapses()
test_canonicalize_tags_resolves_chained_collapses()
test_parse_doc_tags_present()
test_parse_doc_tags_missing()
test_parse_doc_tags_legacy_version_migration()
test_parse_doc_tags_malformed_legacy_version()
test_render_static_doc_no_placeholder_leftover()
test_split_docs_carry_no_tag_note()
test_no_doc_mentions_desk_repo_material()
test_main_doc_links_to_every_split_file()
test_write_tempui_docs_writes_main_and_every_split_file()
test_ensure_docs_current_noop_when_main_missing()
test_ensure_docs_current_noop_when_current_and_all_present()
test_ensure_docs_current_refreshes_when_split_file_missing_even_if_tags_current()
test_ensure_docs_current_refreshes_when_no_tag_note()
test_ensure_docs_current_refreshes_legacy_version_preserving_custom_section()
test_ensure_docs_current_refreshes_legacy_version_no_custom_section()
test_provision_first_creation_writes_whole_set_at_current_tags()
test_provision_refreshes_stale_existing_doc_set()
print("ALL PASS")
