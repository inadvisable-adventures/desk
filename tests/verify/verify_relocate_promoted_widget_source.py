import base64
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
# TODO 78bfa41: canvas.py's own QWebEngineView import (previously used
# by the now-removed _scrollable_at) was the thing actually satisfying
# the "import WebEngine before QApplication" ordering requirement above
# -- import it explicitly instead of depending on that as an incidental
# side effect of an unrelated module.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

import desk.shell.window as window_module  # noqa: E402
from desk.desks import Desk  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.schema_registry import SchemaRegistry  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.shell.promoted_widget_source_watcher import PromotedWidgetSourceWatcher  # noqa: E402
from desk.custom_widgets import LikelySourceCandidate  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    BUILD_WIDGET_SCRIPT_FILENAME,
    CUSTOM_WIDGET_SRC_DIRNAME,
    CUSTOM_WIDGETS_DOC_FILENAME,
    DESK_WIDGETS_BUILD_GITIGNORE_ENTRY,
    PROMOTED_WIDGET_SRC_DIRNAME,
    SPLIT_DOC_CONTENT,
    TEMP_UI_DIRNAME,
    TEMPUI_DOC_VERSION,
    CustomWidgetDefinition,
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


class _CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class _WindowLogCapture:
    """A real logging.Handler attached to desk.shell.window's own
    logger for the duration of a `with` block (TODO a820354) -- no
    existing precedent for capturing log output in this repo's own
    tests/verify/ scripts, so this is the direct approach: attach,
    yield the handler's records list, detach."""
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


SAMPLE_HTML_B64 = base64.b64encode(b"<html><body>Hi</body></html>").decode()


def _definition(keyword="KanbanBoard", label="Kanban Board", source_path=None):
    return CustomWidgetDefinition(
        keyword=keyword, label=label, html_b64=SAMPLE_HTML_B64, default_size=(600, 400), source_path=source_path
    )


class _FakeHandle:
    def __init__(self):
        self.widgets = {}
        self.mounted = []
        self.token = "tok"

    def widget_url(self, widget_id):
        return f"http://fake/{widget_id}"

    def mount_html_widget(self, widget_id, directory, info):
        self.widgets[widget_id] = info
        self.mounted.append((widget_id, directory))


class _FakeWindow:
    def __init__(self, directory):
        self.current_desk = Desk(path=directory / "test.desk")
        self._widgets = {}
        self._handle = _FakeHandle()
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self._broker = HotReloadBroker()
        self._event_mediator = None
        self._custom_widget_definitions = {}
        self._custom_widget_sources = {}
        self._custom_widget_source_paths = {}
        self._custom_widget_content_hash = {}
        # TODO 4eb3d9e: _register_custom_widget now also (re)starts a
        # promoted widget's own source watch at its tail -- a real
        # instance, not a fake, since this file exercises real
        # desk_widgets/<name>/ source directories and this test cares
        # about promotion/relocation, not watch behavior itself.
        self._promoted_widget_source_watcher = PromotedWidgetSourceWatcher()
        self._promoted_widget_source_dirty = set()
        self._schema_registry = SchemaRegistry()
        self.saved = []
        self.confirmed_messages = []
        self.info_messages = []
        # TODO 9613bb0: test-controllable stand-ins for the two new
        # promotion-source dialogs -- default to "proceed, keep the
        # widget inline" so tests that don't care about this behavior
        # (added before this TODO) don't need to opt in.
        self.no_source_choice = True
        self.source_candidate_choice = "keep_inline"  # or a LikelySourceCandidate, or "cancel"
        self.no_source_calls = []
        self.source_candidate_calls = []

    def _confirm_fn(self, title, message):
        def confirm():
            self.confirmed_messages.append((title, message))
            return True

        return confirm

    def _info(self, title, message):
        self.info_messages.append((title, message))

    def save_current_desk(self):
        self.saved.append(True)

    def _confirm_promotion_no_source(self, definition):
        self.no_source_calls.append(definition.keyword)
        return self.no_source_choice

    def _confirm_promotion_source_candidate(self, definition, candidates):
        self.source_candidate_calls.append((definition.keyword, list(candidates)))
        choice = self.source_candidate_choice
        if choice == "cancel":
            return False, None
        if choice == "keep_inline":
            return True, None
        return True, choice


_FakeWindow._resolve_promotion_source = DeskWindow._resolve_promotion_source
_FakeWindow._register_custom_widget = DeskWindow._register_custom_widget
_FakeWindow._refresh_stale_indicators_for = DeskWindow._refresh_stale_indicators_for
_FakeWindow._on_tempui_promote_requested = DeskWindow._on_tempui_promote_requested
_FakeWindow._relocate_promoted_widget_source = DeskWindow._relocate_promoted_widget_source
_FakeWindow._sync_tempui_doc = DeskWindow._sync_tempui_doc
_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._chromium_profile_dir = DeskWindow._chromium_profile_dir
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._bind_error_indicator = DeskWindow._bind_error_indicator
_FakeWindow._check_schema_conflict = DeskWindow._check_schema_conflict
_FakeWindow._is_instance_currently_placed = DeskWindow._is_instance_currently_placed
_FakeWindow._notify_schema_conflict = DeskWindow._notify_schema_conflict
_FakeWindow._show_schema_conflict_popup = DeskWindow._show_schema_conflict_popup
_FakeWindow.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id


def _promote(win, keyword, tempui_path):
    definition = win._custom_widget_definitions[keyword]
    frame = win._place_widget(keyword, win._widgets[keyword], (0, 0), (400, 300), instance_id="abc12345")
    win._custom_widget_source_paths[keyword] = tempui_path
    win._on_tempui_promote_requested(frame)
    return definition


def _source_path(name):
    return (Path(TEMP_UI_DIRNAME) / CUSTOM_WIDGET_SRC_DIRNAME / name).as_posix()


def test_source_directory_moved_using_recorded_path():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(source_path=_source_path("KanbanBoard")), source="tempui")

        source_dir = directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / "KanbanBoard"
        source_dir.mkdir(parents=True)
        (source_dir / "widget.json").write_text("{}")
        (source_dir / "KanbanBoard.ts").write_text("// source")

        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        _promote(win, "KanbanBoard", tempui_path)

        destination_dir = directory / PROMOTED_WIDGET_SRC_DIRNAME / "KanbanBoard"
        check("source directory moved to desk_widgets/<name>/", destination_dir.is_dir())
        check("moved widget.json present", (destination_dir / "widget.json").is_file())
        check("moved .ts file present", (destination_dir / "KanbanBoard.ts").is_file())
        check("original .desk_temp/widgets/<name>/ is gone", not source_dir.exists())
        check("tempui invocation file removed", not tempui_path.exists())
        check("promotion still recorded in .desk file", any(cw.keyword == "KanbanBoard" for cw in win.current_desk.custom_widgets))


def test_relocation_uses_recorded_path_not_keyword_guess():
    # TODO 13f4ad5: the confirmed bug -- a source directory's real
    # (kebab-case) name almost never matches its DSL keyword (typically
    # CamelCase). Before this fix, relocation reconstructed
    # .desk_temp/widgets/<keyword>/ from the keyword and silently
    # no-op'd whenever that guess was wrong, which is nearly always.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(
            _definition(keyword="PdfViewer", label="PDF Viewer", source_path=_source_path("pdf-viewer")),
            source="tempui",
        )

        source_dir = directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / "pdf-viewer"
        source_dir.mkdir(parents=True)
        (source_dir / "widget.json").write_text("{}")

        # A directory literally named after the keyword must NOT exist
        # -- if the (buggy) old keyword-guessing code path ever crept
        # back in, this guards against it silently "working" by
        # coincidence.
        keyword_guessed_dir = directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / "PdfViewer"
        check("sanity: no directory literally named after the keyword", not keyword_guessed_dir.exists())

        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tPdfViewer\tPDF Viewer\n")

        definition = _promote(win, "PdfViewer", tempui_path)

        destination_dir = directory / PROMOTED_WIDGET_SRC_DIRNAME / "pdf-viewer"
        check("real (kebab-case) source directory relocated to desk_widgets/pdf-viewer/", destination_dir.is_dir())
        check("original .desk_temp/widgets/pdf-viewer/ is gone", not source_dir.exists())
        check(
            "destination is NOT named after the CamelCase keyword",
            not (directory / PROMOTED_WIDGET_SRC_DIRNAME / "PdfViewer").exists(),
        )
        check("definition's source_path updated to the new location", definition.source_path == "desk_widgets/pdf-viewer")


def test_no_recorded_source_path_is_a_noop_with_an_info_log():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(), source="tempui")  # source_path=None (hand-authored)
        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        with _WindowLogCapture() as records:
            definition = _promote(win, "KanbanBoard", tempui_path)

        # TODO 9613bb0: no .desk_temp/widgets/ at all -- no candidate to
        # offer, so the "no source at all" dialog fires (defaulted to
        # "Promote Anyway" above) rather than the "here's a match" one.
        check("the no-source-found dialog was shown", win.no_source_calls == ["KanbanBoard"])
        check("the candidate-found dialog was NOT shown", win.source_candidate_calls == [])
        check("promotion still succeeded", any(cw.keyword == "KanbanBoard" for cw in win.current_desk.custom_widgets))
        check("no source_path means html_b64 is still baked in (hand-authored fallback)", definition.html_b64 == SAMPLE_HTML_B64)

        # TODO a820354: a real breadcrumb (INFO, not silence, not a
        # warning) naming the widget.
        info_records = [r for r in records if r.levelno == logging.INFO]
        check("exactly one INFO record logged for the no-source-path case", len(info_records) == 1)
        if info_records:
            message = info_records[0].getMessage()
            check("the INFO message names the widget keyword", "KanbanBoard" in message)
        check("no WARNING-or-above record logged for this case (still not treated as surprising)", not any(r.levelno >= logging.WARNING for r in records))


def test_recorded_source_path_missing_is_a_noop():
    # The source_path is recorded, but its directory no longer exists
    # on disk (e.g. deleted outside Desk between authoring and
    # promoting) -- still a quiet no-op, and html_b64 stays baked in
    # since there's no confirmed source to rebuild from.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(source_path=_source_path("KanbanBoard")), source="tempui")
        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        with _WindowLogCapture() as records:
            definition = _promote(win, "KanbanBoard", tempui_path)

        # TODO 9613bb0: a recorded-but-missing source directory is the
        # same "nothing usable" situation as no source_path at all --
        # still routes through the no-source dialog (no .desk_temp/
        # widgets/ candidates exist in this test either).
        check("the no-source-found dialog was shown for a missing recorded path too", win.no_source_calls == ["KanbanBoard"])
        destination_dir = directory / PROMOTED_WIDGET_SRC_DIRNAME / "KanbanBoard"
        check("no source dir to move: no destination created", not destination_dir.exists())
        check("promotion still succeeded", any(cw.keyword == "KanbanBoard" for cw in win.current_desk.custom_widgets))
        check("html_b64 preserved -- recorded source directory was missing, nothing confirmed to rebuild from", definition.html_b64 == SAMPLE_HTML_B64)
        info_records = [r for r in records if r.levelno == logging.INFO]
        check("exactly one INFO record logged", len(info_records) == 1)
        check("no WARNING-or-above record logged for this case", not any(r.levelno >= logging.WARNING for r in records))


def test_preexisting_destination_is_not_clobbered():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(source_path=_source_path("KanbanBoard")), source="tempui")

        source_dir = directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / "KanbanBoard"
        source_dir.mkdir(parents=True)
        (source_dir / "marker.txt").write_text("original source")

        destination_dir = directory / PROMOTED_WIDGET_SRC_DIRNAME / "KanbanBoard"
        destination_dir.mkdir(parents=True)
        (destination_dir / "marker.txt").write_text("pre-existing, unrelated content")

        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        with _WindowLogCapture() as records:
            _promote(win, "KanbanBoard", tempui_path)

        check("source dir left in place, not clobbered", source_dir.is_dir())
        check("pre-existing destination content untouched", (destination_dir / "marker.txt").read_text() == "pre-existing, unrelated content")

        # Regression check (TODO a820354 touched the sibling no-source
        # branch, not this one): the existing pre-existing-destination
        # WARNING is unchanged, and this case does not also log the new
        # INFO message (the source directory *was* found here).
        check("still logs at WARNING for a pre-existing destination", any(r.levelno == logging.WARNING for r in records))
        check("does not log the no-source-path INFO message for this case", not any(r.levelno == logging.INFO for r in records))
        check("promotion (the .desk file part) still succeeded despite the move being skipped", any(cw.keyword == "KanbanBoard" for cw in win.current_desk.custom_widgets))
        check("neither new dialog fired -- the recorded source_path was already usable", win.no_source_calls == [] and win.source_candidate_calls == [])


def test_source_backed_promotion_rebuilds_and_strips_html_b64():
    # TODO 13f4ad5: once a source-backed widget's source directory is
    # confirmed relocated, the .desk file entry no longer bakes
    # html_b64 -- content is rebuilt on demand instead. build_from_source
    # itself (real tsc compile) is covered separately in
    # verify_build_from_source.py; here it's monkeypatched so this test
    # exercises _on_tempui_promote_requested's own orchestration without
    # requiring a real TypeScript toolchain.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        keyword_source_path = _source_path("pdf-viewer")
        win._register_custom_widget(
            _definition(keyword="PdfViewer", label="PDF Viewer", source_path=keyword_source_path), source="tempui"
        )

        source_dir = directory / keyword_source_path
        source_dir.mkdir(parents=True)
        (source_dir / "widget.json").write_text("{}")

        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tPdfViewer\tPDF Viewer\n")

        def _fake_build_from_source(project_dir, source_path):
            build_dir = project_dir / source_path / ".build"
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / "index.html").write_text("<html><body>rebuilt</body></html>")
            return build_dir

        real_build_from_source = window_module.build_from_source
        window_module.build_from_source = _fake_build_from_source
        try:
            definition = _promote(win, "PdfViewer", tempui_path)
        finally:
            window_module.build_from_source = real_build_from_source

        check("promoted definition's html_b64 is stripped (rebuilt on demand instead)", definition.html_b64 == "")
        check("source_path relocated to desk_widgets/pdf-viewer", definition.source_path == "desk_widgets/pdf-viewer")
        check("the .desk file's own list holds this same, already-mutated object", win.current_desk.custom_widgets[-1] is definition)
        check("re-registration remounted PdfViewer from the fresh build", any(w == "PdfViewer" for w, _ in win._handle.mounted))


def test_promotion_ensures_desk_widgets_build_gitignore_entry():
    # TODO 1c67fe5: the other moment (besides DeskWindow._provision_temp_ui
    # at startup/Desk-switch, covered in
    # verify_desk_widgets_build_gitignore.py) desk_widgets/ can first come
    # to exist -- promotion itself must ensure the rebuilt-on-demand
    # .build/ cache under it is gitignored right away. Needs a real git
    # repo (ensure_desk_widgets_gitignore_entry calls find_git_root for
    # real) -- a plain tempdir is never itself inside one.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        subprocess.run(["git", "init", "-q"], cwd=directory, check=True)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(source_path=_source_path("KanbanBoard")), source="tempui")

        source_dir = directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / "KanbanBoard"
        source_dir.mkdir(parents=True)
        (source_dir / "widget.json").write_text("{}")

        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        _promote(win, "KanbanBoard", tempui_path)

        gitignore_text = (directory / ".gitignore").read_text() if (directory / ".gitignore").is_file() else ""
        check(
            "promotion adds the desk_widgets/**/.build/ entry to the project's real .gitignore",
            DESK_WIDGETS_BUILD_GITIGNORE_ENTRY in gitignore_text,
        )
        check(
            "promotion asked about it under a distinct ('Custom Widgets') title",
            any(title == "Custom Widgets" for title, _ in win.confirmed_messages),
        )


def test_candidate_found_by_widget_json_keyword_match():
    # TODO 9613bb0: a .desk_temp/widgets/ subdirectory whose widget.json
    # "keyword" matches exactly is a candidate even when the directory's
    # own name doesn't resemble the keyword at all.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(), source="tempui")  # source_path=None

        candidate_dir = directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / "totally-different-name"
        candidate_dir.mkdir(parents=True)
        (candidate_dir / "widget.json").write_text('{"keyword": "KanbanBoard", "label": "Kanban Board"}')

        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        win.source_candidate_choice = "keep_inline"
        _promote(win, "KanbanBoard", tempui_path)

        check("the candidate-found dialog was shown", len(win.source_candidate_calls) == 1)
        _, candidates = win.source_candidate_calls[0]
        check("exactly one candidate found", len(candidates) == 1)
        check("found via the widget.json keyword match, not a name variant", candidates[0].matched_by == "keyword")
        check("candidate path is the differently-named directory", candidates[0].path == candidate_dir)
        check("the no-source-at-all dialog was NOT also shown", win.no_source_calls == [])


def test_candidate_found_by_name_variant_and_adopted():
    # TODO 9613bb0: a bare .desk_temp/widgets/pdf-viewer/ (kebab-case)
    # is found as a likely match for keyword "PdfViewer" (PascalCase)
    # purely by normalized name -- no widget.json keyword needed.
    # Adopting it drives the exact same relocate + strip-html_b64 path
    # a recorded SourcePath line would (test_source_backed_promotion_
    # rebuilds_and_strips_html_b64's own real-source scenario).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(
            _definition(keyword="PdfViewer", label="PDF Viewer"), source="tempui"
        )  # source_path=None

        candidate_dir = directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / "pdf-viewer"
        candidate_dir.mkdir(parents=True)
        (candidate_dir / "widget.json").write_text("{}")  # no keyword field -- name match only

        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tPdfViewer\tPDF Viewer\n")

        # Instance-attribute override (not a class-level swap): picks
        # whatever find_likely_source_candidates actually found, rather
        # than a canned candidate this test would have to hand-construct.
        def _confirm_promotion_source_candidate(definition, candidates):
            win.source_candidate_calls.append((definition.keyword, list(candidates)))
            return True, candidates[0]

        win._confirm_promotion_source_candidate = _confirm_promotion_source_candidate

        def _fake_build_from_source(project_dir, source_path):
            build_dir = project_dir / source_path / ".build"
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / "index.html").write_text("<html><body>rebuilt</body></html>")
            return build_dir

        real_build_from_source = window_module.build_from_source
        window_module.build_from_source = _fake_build_from_source
        try:
            definition = _promote(win, "PdfViewer", tempui_path)
        finally:
            window_module.build_from_source = real_build_from_source

        check("exactly one candidate found, by name variant", len(win.source_candidate_calls[0][1]) == 1)
        check("matched via directory-name variant, not a widget.json keyword", win.source_candidate_calls[0][1][0].matched_by == "name")
        check("adopting the candidate strips html_b64 (rebuilt on demand instead)", definition.html_b64 == "")
        check("source_path relocated to desk_widgets/pdf-viewer, same as a recorded SourcePath would", definition.source_path == "desk_widgets/pdf-viewer")
        check("real source directory relocated out of .desk_temp/widgets/", not candidate_dir.exists())


def test_unrelated_directory_without_widget_json_is_not_a_candidate():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(), source="tempui")  # source_path=None

        unrelated_dir = directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / "kanban-board"
        unrelated_dir.mkdir(parents=True)
        (unrelated_dir / "notes.txt").write_text("not a widget source directory")

        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        _promote(win, "KanbanBoard", tempui_path)

        check("no widget.json means no candidate, despite the matching name", win.source_candidate_calls == [])
        check("falls back to the no-source-found dialog instead", win.no_source_calls == ["KanbanBoard"])


def test_cancelling_the_source_dialog_aborts_the_whole_promotion():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        win._register_custom_widget(_definition(), source="tempui")  # source_path=None
        win.no_source_choice = False  # "Cancel"

        tempui_path = directory / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        _promote(win, "KanbanBoard", tempui_path)

        check("promotion did not add the widget to the .desk file", not any(cw.keyword == "KanbanBoard" for cw in win.current_desk.custom_widgets))
        check("the source was still recorded as tempui, not desk", win._custom_widget_sources.get("KanbanBoard") != "desk")
        check("the tempui invocation file was NOT removed", tempui_path.exists())
        check("the Desk was never saved", win.saved == [])


def test_doc_content():
    check("TEMPUI_DOC_VERSION bumped to at least 42", TEMPUI_DOC_VERSION >= 42)
    doc = SPLIT_DOC_CONTENT[CUSTOM_WIDGETS_DOC_FILENAME]
    check("doc recommends .desk_temp/widgets/<name>/", ".desk_temp/widgets/<name>/" in doc)
    check("custom_widget_src no longer mentioned", "custom_widget_src" not in doc)
    check("doc mentions desk_widgets/<name>/ post-promotion", "desk_widgets/<name>/" in doc)
    check("doc mentions the SourcePath line", "SourcePath" in doc)
    check("doc mentions the rebuilt-on-demand .build/ cache", ".build/" in doc)


def test_build_widget_script_docstring_updated():
    # TODO 029047b: the script now lives generated in-memory
    # (SPLIT_DOC_CONTENT), not as a static scripts/build_widget.py file.
    text = SPLIT_DOC_CONTENT[BUILD_WIDGET_SCRIPT_FILENAME]
    check("build_widget.py docstring no longer hardcodes custom_widget_src", "custom_widget_src" not in text)
    check("build_widget.py docstring mentions .desk_temp/widgets", ".desk_temp/widgets/<name>" in text)
    check("build_widget.py docstring mentions desk_widgets", "desk_widgets/<name>" in text)


test_source_directory_moved_using_recorded_path()
test_relocation_uses_recorded_path_not_keyword_guess()
test_no_recorded_source_path_is_a_noop_with_an_info_log()
test_recorded_source_path_missing_is_a_noop()
test_preexisting_destination_is_not_clobbered()
test_source_backed_promotion_rebuilds_and_strips_html_b64()
test_promotion_ensures_desk_widgets_build_gitignore_entry()
test_candidate_found_by_widget_json_keyword_match()
test_candidate_found_by_name_variant_and_adopted()
test_unrelated_directory_without_widget_json_is_not_a_candidate()
test_cancelling_the_source_dialog_aborts_the_whole_promotion()
test_doc_content()
test_build_widget_script_docstring_updated()

# TODO a5f66cc: os._exit(), not sys.exit() -- this script places
# several kind:"html" (ChromiumWidget-backed) widgets across its test
# functions, each now with its own real QWebEngineProfile (previously
# all shared Qt's one default profile). Confirmed directly (see
# LEARNINGS.md's TODO a5f66cc entry): once every check() above has
# already passed correctly, normal Python interpreter shutdown can
# still segfault tearing down 2+ such profiles/pages -- a real,
# reproducible Qt/WebEngine internals race specific to that shutdown
# path, not a bug in anything this script actually verifies. os._exit()
# terminates immediately, skipping that teardown path entirely (the
# same way force-quitting a process does), so the reported exit code
# reliably reflects the real check() results above instead of being
# clobbered by an unrelated crash.
print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
