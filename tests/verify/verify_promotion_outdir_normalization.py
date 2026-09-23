# TODO 3d792f8: promotion normalizes a widget's tsconfig.json outDir to
# .build and clears any stale build cache left over from before the move.
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
    CURRENT_TAGS,
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
        self.peer_calls = []
        self.peer_choice = "leave"
        self.outdir_confirm_choice = True
        self.source_candidate_calls = []

    def _confirm_fn(self, title, message):
        def confirm():
            self.confirmed_messages.append((title, message))
            # Only the outDir-normalization prompt (title "Promotion:
            # build output") is test-controllable via outdir_confirm_choice
            # -- every other confirm this file's promotion path pumps
            # through (starting with "Promote to Desk?" itself) must
            # still default to proceeding, or promotion never reaches
            # this TODO's own code at all.
            return self.outdir_confirm_choice if title == "Promotion: build output" else True

        return confirm

    def _info(self, title, message):
        self.info_messages.append((title, message))

    def _peer_action_fn(self, peer, can_promote):
        self.peer_calls.append((peer.directory.name, can_promote))
        return self.peer_choice

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
# TODO 8a09220: promotion was split into two halves, and relocation now
# reports/handles shared tsconfig dependencies through these.
_FakeWindow._promote_custom_widget = DeskWindow._promote_custom_widget
_FakeWindow._finish_promotion = DeskWindow._finish_promotion
_FakeWindow._display_path = DeskWindow._display_path
_FakeWindow._report_dependency_relocation = DeskWindow._report_dependency_relocation
_FakeWindow._find_promotable_peer = DeskWindow._find_promotable_peer
_FakeWindow._handle_peer_dependent = DeskWindow._handle_peer_dependent
_FakeWindow._choose_peer_dependent_action = lambda self, peer, can_promote: self._peer_action_fn(peer, can_promote)
_FakeWindow._normalize_promoted_build_output = DeskWindow._normalize_promoted_build_output
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


import json  # noqa: E402
import shutil  # noqa: E402

from desk.promotion_deps import (  # noqa: E402
    apply_moves,
    find_peer_dependents,
    plan_dependency_relocation,
    rewrite_files_entries,
)

TEMP_WIDGETS = Path(TEMP_UI_DIRNAME) / CUSTOM_WIDGET_SRC_DIRNAME


def _write_widget(project, name, files, *, tsconfig_extra=None, widget_json=True):
    directory = project / TEMP_WIDGETS / name
    directory.mkdir(parents=True, exist_ok=True)
    if widget_json:
        (directory / "widget.json").write_text("{}")
    (directory / f"{name}.ts").write_text(f"// {name}\n")
    config = {"compilerOptions": {"outDir": "out"}, "files": files}
    config.update(tsconfig_extra or {})
    (directory / "tsconfig.json").write_text(json.dumps(config, indent=2) + "\n")
    return directory


def _files_of(directory):
    return json.loads((directory / "tsconfig.json").read_text())["files"]


def _shared(project, dirname="_shared", filename="base.ts", text="// shared\n"):
    directory = project / TEMP_WIDGETS / dirname
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(text)
    return directory / filename


def _register(win, project, name, keyword):
    win._register_custom_widget(
        _definition(keyword=keyword, label=keyword, source_path=_source_path(name)), source="tempui"
    )
    tempui_path = project / TEMP_UI_DIRNAME / f"{name}-uuid"
    tempui_path.write_text(f"DefineWidget\t{keyword}\t{keyword}\n")
    return tempui_path


def _source_path(name):
    return (TEMP_WIDGETS / name).as_posix()



from desk.promotion_deps import (  # noqa: E402
    clear_stale_build_output,
    out_dir_mismatch,
    out_dir_string,
    rewrite_out_dir,
)


def _write_widget_with_out_dir(project, name, out_dir, *, extra_files=None, widget_json=True, with_widget_html=False):
    """Like _write_widget above but the caller picks compilerOptions.outDir
    directly (this file's own concern), with a real .ts + compiled-looking
    stale output already sitting under it, as if from before a move.
    `with_widget_html` makes the fixture complete enough for
    _register_custom_widget's own automatic post-promotion rebuild to
    fully succeed instead of failing at the widget.html step."""
    directory = _write_widget(project, name, extra_files or [f"{name}.ts"], widget_json=widget_json)
    if with_widget_html:
        (directory / "widget.html").write_text("<html><body><script>/* BUILD:COMPILED_JS */</script></body></html>")
    config = json.loads((directory / "tsconfig.json").read_text())
    config["compilerOptions"]["outDir"] = out_dir
    (directory / "tsconfig.json").write_text(json.dumps(config, indent=2) + "\n")
    stale_dir = directory / out_dir
    stale_dir.mkdir(parents=True, exist_ok=True)
    (stale_dir / "stale.js").write_text("// stale compiled output\n")
    return directory


# ---- pure module ----------------------------------------------------------

def test_out_dir_string_and_mismatch():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        out_widget = _write_widget_with_out_dir(project, "w1", "out")
        build_widget = _write_widget_with_out_dir(project, "w2", ".build")
        check("out_dir_string reads the raw value as written", out_dir_string(out_widget) == "out")
        check("out_dir_mismatch reports it when not already .build", out_dir_mismatch(out_widget) == "out")
        check("out_dir_mismatch is None when already .build", out_dir_mismatch(build_widget) is None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        (project / TEMP_WIDGETS / "bare").mkdir(parents=True)
        check("missing tsconfig.json: out_dir_string is None, not an error", out_dir_string(project / TEMP_WIDGETS / "bare") is None)
        check("missing tsconfig.json: out_dir_mismatch is None too", out_dir_mismatch(project / TEMP_WIDGETS / "bare") is None)


def test_clear_stale_build_output():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        widget = _write_widget_with_out_dir(project, "w1", "out")
        stale = widget / "out"
        check("sanity: stale output exists before clearing", (stale / "stale.js").is_file())
        cleared = clear_stale_build_output(widget)
        check("clear_stale_build_output returns the path it deleted", cleared == stale)
        check("the stale directory is actually gone", not stale.exists())
        check("clearing again (nothing there) is a no-op, returns None", clear_stale_build_output(widget) is None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        directory = _write_widget(project, "solo", ["solo.ts"])  # outDir "out", never created
        check("no existing outDir directory: nothing to clear, no error", clear_stale_build_output(directory) is None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        (project / TEMP_WIDGETS / "bare").mkdir(parents=True)
        check("missing tsconfig.json: clear_stale_build_output is a silent no-op", clear_stale_build_output(project / TEMP_WIDGETS / "bare") is None)


def test_rewrite_out_dir_preserves_formatting():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        text = '{\n\t"compilerOptions": { "outDir": "out", "strict": true },\n\t"files": [ "w.ts" ]\n}\n'
        (directory / "tsconfig.json").write_text(text)
        changed = rewrite_out_dir(directory, ".build")
        result = (directory / "tsconfig.json").read_text()
        check("rewrite_out_dir reports a change", changed)
        check("rewrite_out_dir is exact-string, formatting kept", result == text.replace('"out"', '".build"'))
        check("other keys (strict, files) untouched", json.loads(result)["compilerOptions"]["strict"] is True and json.loads(result)["files"] == ["w.ts"])
        check("rewriting again (already .build) is a no-op", not rewrite_out_dir(directory, ".build"))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        (directory / "tsconfig.json").write_text("not json")
        check("malformed tsconfig.json: rewrite_out_dir is a silent no-op", not rewrite_out_dir(directory, ".build"))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        (directory / "tsconfig.json").write_text(json.dumps({"files": ["w.ts"]}))
        check("no compilerOptions at all: rewrite_out_dir is a silent no-op", not rewrite_out_dir(directory, ".build"))


def test_rewrite_out_dir_falls_back_to_redump_when_exact_replace_is_ambiguous():
    # The literal string "out" also appears in an unrelated key's value --
    # an exact-string replace of just `"out"` would corrupt it, so this
    # must fall back to a full re-dump instead.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        config = {"compilerOptions": {"outDir": "out"}, "comment": "about out"}
        (directory / "tsconfig.json").write_text(json.dumps(config))
        rewrite_out_dir(directory, ".build")
        result = json.loads((directory / "tsconfig.json").read_text())
        check("ambiguous exact-string case: outDir updated", result["compilerOptions"]["outDir"] == ".build")
        check("ambiguous exact-string case: unrelated value using the same text is untouched", result["comment"] == "about out")


# ---- through DeskWindow ---------------------------------------------------

def test_promotion_clears_stale_output_and_offers_normalization():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        # tsc is real here (this repo has it on PATH) -- with_widget_html
        # so _register_custom_widget's own automatic post-promotion
        # rebuild fully succeeds, which is what actually proves the
        # stale.js below never leaks into the freshly built widget.
        old = _write_widget_with_out_dir(project, "cam", "out", with_widget_html=True)
        path = _register(win, project, "cam", "Cam")
        win.outdir_confirm_choice = True

        _promote(win, "Cam", path)

        new_dir = project / PROMOTED_WIDGET_SRC_DIRNAME / "cam"
        check("promotion moved the widget's directory (its own stale out/ moved with it)", new_dir.is_dir())
        check("the moved-along stale out/ is gone after promotion", not (new_dir / "out").exists())
        check("outDir was rewritten to .build (confirm accepted)", out_dir_string(new_dir) == ".build")
        if shutil.which("tsc") is not None:
            check("the automatic post-promotion rebuild produced a real .build/index.html", (new_dir / ".build" / "index.html").is_file())
            check(
                "the stale.js content never leaked into the freshly built widget",
                "stale compiled output" not in (new_dir / ".build" / "index.html").read_text(),
            )
            check("no leftover stale.js sitting alongside the fresh build output", not (new_dir / ".build" / "stale.js").exists())
        check(
            "user was told a stale cache was cleared",
            any("cleared a stale build cache" in m and "out" in m for _, m in win.info_messages),
        )
        check(
            "user was asked to confirm the outDir rewrite",
            any("builds to" in m and ".build" in m for _, m in win.confirmed_messages),
        )


def test_declining_the_prompt_leaves_out_dir_alone():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        # with_widget_html so _register_custom_widget's own automatic
        # post-promotion rebuild fully succeeds and recompiles into
        # "build/" -- without it, that rebuild's own partial tsc run
        # would recreate "build/" regardless of whether the clearing
        # below worked, making this check meaningless either way.
        _write_widget_with_out_dir(project, "cam", "build", with_widget_html=True)
        path = _register(win, project, "cam", "Cam")
        win.outdir_confirm_choice = False

        _promote(win, "Cam", path)

        new_dir = project / PROMOTED_WIDGET_SRC_DIRNAME / "cam"
        check("declining: outDir left exactly as the author wrote it", out_dir_string(new_dir) == "build")
        if shutil.which("tsc") is not None:
            # build_from_source's own final packaged index.html always
            # lands in the hardcoded ".build" (SOURCE_BUILD_CACHE_DIRNAME)
            # regardless of what tsconfig.json's own outDir says -- "build"
            # (left alone by declining) is only where tsc's own raw .js
            # compiles to; _concatenate_compiled_js globs every *.js under
            # it with no "files" list to disambiguate, so a stale.js left
            # there would otherwise leak straight into this file's content.
            check(
                "declining: the stale cache was still cleared before the fresh rebuild (never gated on the confirm)",
                "stale compiled output" not in (new_dir / ".build" / "index.html").read_text(),
            )


def test_already_build_widget_is_never_prompted_but_still_cleared():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        _write_widget_with_out_dir(project, "cam", ".build", with_widget_html=True)
        path = _register(win, project, "cam", "Cam")

        _promote(win, "Cam", path)

        new_dir = project / PROMOTED_WIDGET_SRC_DIRNAME / "cam"
        check("already .build: no normalization prompt shown", not any("builds to" in m for _, m in win.confirmed_messages))
        if shutil.which("tsc") is not None:
            check("already .build: the stale pre-move compile is cleared, then a fresh one built", (new_dir / ".build" / "index.html").is_file())
            check("already .build: no leftover stale.js from before the move", not (new_dir / ".build" / "stale.js").exists())


def test_no_prior_build_output_is_silent():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        _write_widget(project, "solo", ["solo.ts"])  # outDir "out", never built -- nothing under it yet
        path = _register(win, project, "solo", "Solo")

        _promote(win, "Solo", path)

        check("nothing was ever compiled: no 'cleared a stale build cache' message", not any("cleared a stale build cache" in m for _, m in win.info_messages))
        check("outDir mismatch ('out' != .build) is still offered", any("builds to" in m for _, m in win.confirmed_messages))


def test_no_source_dependent_widget_is_unaffected():
    # A hand-authored, inline-only widget (no source_path) never reaches
    # _normalize_promoted_build_output at all -- _relocate_promoted_widget_source
    # returns before it for exactly this case.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        win._register_custom_widget(_definition(), source="tempui")  # source_path=None
        tempui_path = project / TEMP_UI_DIRNAME / "some-uuid"
        tempui_path.write_text("DefineWidget\tKanbanBoard\tKanban Board\n")

        _promote(win, "KanbanBoard", tempui_path)

        check("hand-authored widget: no build-output messages of any kind", not any("build output" in t for t, _ in win.info_messages + win.confirmed_messages))


def test_real_tsc_rebuild_succeeds_after_normalization():
    if shutil.which("tsc") is None:
        print("SKIP: tsc not installed")
        return
    from desk.custom_widgets import build_from_source

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        old = _write_widget(project, "cam", ["cam.ts"], tsconfig_extra={"compilerOptions": {"outDir": "out", "target": "es2020"}})
        (old / "cam.ts").write_text("class Cam { hello(): string { return 'hi'; } }\nnew Cam().hello();\n")
        (old / "widget.html").write_text("<html><body><script>/* BUILD:COMPILED_JS */</script></body></html>")
        path = _register(win, project, "cam", "Cam")
        win.outdir_confirm_choice = True

        _promote(win, "Cam", path)

        new_dir = project / PROMOTED_WIDGET_SRC_DIRNAME / "cam"
        check("outDir normalized to .build for the real rebuild below", out_dir_string(new_dir) == ".build")
        result = build_from_source(project, f"{PROMOTED_WIDGET_SRC_DIRNAME}/cam")
        check(
            "tsc's own compiled .js and build_from_source's index.html coexist fine in .build/",
            result is not None and (result / "index.html").is_file() and "hello" in (result / "index.html").read_text(),
        )


def test_changelog_and_doc_cover_this():
    from desk.temp_ui import _CUSTOM_WIDGETS_DOC, _NEW_FEATURES

    tag = "promotion normalizes tsconfig outDir to .build #941549"
    check("tag is in CURRENT_TAGS with a _NEW_FEATURES entry", tag in CURRENT_TAGS and tag in _NEW_FEATURES)
    check(
        "doc names .build as the recommended outDir",
        "**Set it to `.build`**" in _CUSTOM_WIDGETS_DOC,
    )
    check(
        "doc's promotion section explains the normalization offer and unconditional clearing",
        "widget's own build output is normalized too" in _CUSTOM_WIDGETS_DOC,
    )


for name, fn in list(globals().items()):
    if name.startswith("test_") and callable(fn):
        fn()

# Same os._exit() ending as verify_promotion_tsconfig_dependencies.py's own
# sibling scripts (see LEARNINGS.md's TODO a5f66cc entry): real
# WebEngine profiles/pages can segfault at normal interpreter shutdown,
# clobbering the exit code after every check has already run.
print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
