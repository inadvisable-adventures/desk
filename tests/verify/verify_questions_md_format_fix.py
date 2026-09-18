import logging
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.questions_file import unparsed_heading_count  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.temp_ui import DOC_TEMPLATE, CURRENT_TAGS, _NEW_FEATURES_DOC  # noqa: E402

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


class _CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class _WindowLogCapture:
    """Same recipe as verify_relocate_promoted_widget_source.py's own
    _WindowLogCapture -- a real logging.Handler attached to
    desk.shell.window's own logger for the duration of a `with`
    block."""

    def __enter__(self):
        self._logger = logging.getLogger("desk.shell.window")
        self._previous_level = self._logger.level
        self._handler = _CapturingHandler()
        self._logger.addHandler(self._handler)
        self._logger.setLevel(logging.INFO)
        return self._handler.records

    def __exit__(self, *exc_info):
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._previous_level)


# ---------- doc content ----------


def test_version_bumped():
    check("changelog still covers this feature (version-20)", "version-20" in CURRENT_TAGS)


def test_doc_states_the_real_required_heading_shape():
    idx = DOC_TEMPLATE.find("Questions for the user")
    section = DOC_TEMPLATE[idx : idx + 1500]
    check("the doc mentions the literal leading TODO requirement", "must start with the literal word `TODO`" in section)
    check("the doc mentions backtick-wrapped ids", "backtick-wrapped" in section)
    check(
        "the doc no longer presents the old, wrong '## <short summary>' shape as the format",
        "## <short summary>" not in section,
    )
    check(
        "the doc states this is scoped to TODO-blocking questions, not free-standing ones",
        "no supported way to add a" in section and "free-standing question" in section,
    )


def test_new_features_doc_has_a_matching_entry():
    check("tempui-new-features.md has a Version 28 entry", "## Version 28" in _NEW_FEATURES_DOC)
    entry = _NEW_FEATURES_DOC.split("## Version 28")[1].split("## Version 27")[0]
    check("the Version 28 entry mentions the corrected heading requirement", "TODO" in entry and "backtick" in entry)


# ---------- unparsed_heading_count ----------

WELL_FORMED_QUESTIONS_MD = """# Questions with optional answers

## TODO `9743419`: What should the filename be?
Some question text here.
(Answer: )
"""

MALFORMED_QUESTIONS_MD = """# Questions with optional answers

## Should we use approach A or B?
Some question text here, using the old documented (but never actually
accepted) heading shape -- no leading TODO at all.
(Answer: )

## A second malformed heading, also with no leading TODO
More text.
(Answer: )
"""

MIXED_QUESTIONS_MD = """# Questions with optional answers

## TODO `9743419`: a real, correctly-formatted entry
Real question text.
(Answer: )

## a malformed one right after it
More text.
(Answer: )
"""


def test_unparsed_heading_count_zero_for_a_well_formed_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "QUESTIONS.md"
        path.write_text(WELL_FORMED_QUESTIONS_MD)
        check("a real, correctly-formatted QUESTIONS.md has zero unparsed headings", unparsed_heading_count(path) == 0)


def test_unparsed_heading_count_zero_for_a_file_with_no_headings_at_all():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "QUESTIONS.md"
        path.write_text("# Questions with optional answers\n\nNothing here yet.\n")
        check("a file with no '## ' headings at all has zero unparsed headings", unparsed_heading_count(path) == 0)


def test_unparsed_heading_count_reports_the_real_count():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "QUESTIONS.md"
        path.write_text(MALFORMED_QUESTIONS_MD)
        check(
            "unparsed_heading_count reports exactly the number of malformed headings, not just nonzero",
            unparsed_heading_count(path) == 2,
        )


def test_unparsed_heading_count_ignores_real_entries_mixed_with_malformed_ones():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "QUESTIONS.md"
        path.write_text(MIXED_QUESTIONS_MD)
        check(
            "a real entry mixed with a malformed one only counts the malformed one",
            unparsed_heading_count(path) == 1,
        )


# ---------- _on_questions_file_changed logging ----------


class _FakeWindow:
    def __init__(self, questions_path):
        self._questions_path = questions_path
        self._known_question_keys = None
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()

    def _focus_questions_widget(self):
        pass


_FakeWindow._on_questions_file_changed = DeskWindow._on_questions_file_changed


def test_malformed_file_logs_a_warning():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "QUESTIONS.md"
        path.write_text(MALFORMED_QUESTIONS_MD)
        win = _FakeWindow(path)

        with _WindowLogCapture() as records:
            win._on_questions_file_changed()

        warnings = [r for r in records if r.levelno == logging.WARNING]
        check("a malformed QUESTIONS.md logs exactly one warning", len(warnings) == 1)
        if warnings:
            message = warnings[0].getMessage()
            check("the warning names the file path", str(path) in message)
            check("the warning names the real unparsed count", "2" in message)


def test_well_formed_file_logs_nothing():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "QUESTIONS.md"
        path.write_text(WELL_FORMED_QUESTIONS_MD)
        win = _FakeWindow(path)

        with _WindowLogCapture() as records:
            win._on_questions_file_changed()

        warnings = [r for r in records if r.levelno == logging.WARNING]
        check("a well-formed QUESTIONS.md logs no warning", warnings == [])


test_version_bumped()
test_doc_states_the_real_required_heading_shape()
test_new_features_doc_has_a_matching_entry()
test_unparsed_heading_count_zero_for_a_well_formed_file()
test_unparsed_heading_count_zero_for_a_file_with_no_headings_at_all()
test_unparsed_heading_count_reports_the_real_count()
test_unparsed_heading_count_ignores_real_entries_mixed_with_malformed_ones()
test_malformed_file_logs_a_warning()
test_well_formed_file_logs_nothing()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
