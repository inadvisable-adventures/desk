# TODO 8a09220: promotion handles a widget's tsconfig.json shared dependencies.
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
        self.source_candidate_calls = []

    def _confirm_fn(self, title, message):
        def confirm():
            self.confirmed_messages.append((title, message))
            return True

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
# TODO 3d792f8: promotion also normalizes/clears the widget's own build output.
_FakeWindow._normalize_promoted_build_output = DeskWindow._normalize_promoted_build_output
_FakeWindow._choose_peer_dependent_action = lambda self, peer, can_promote: self._peer_action_fn(peer, can_promote)
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


# ---- pure module ----------------------------------------------------------

def test_plan_moves_shared_file_and_keeps_relative_path():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        shared = _shared(project)
        old = _write_widget(project, "cam", ["../_shared/base.ts", "cam.ts"])
        new = project / PROMOTED_WIDGET_SRC_DIRNAME / "cam"
        plan = plan_dependency_relocation(project, old, new)
        final = project / PROMOTED_WIDGET_SRC_DIRNAME / "_shared" / "base.ts"
        check("plan: shared file under .desk_temp/widgets moves to desk_widgets/", plan.moves == {shared: final})
        check("plan: same-shape relative path needs no rewrite", plan.rewrites == {})
        check("plan: nothing on disk changed yet", shared.is_file() and not final.exists())
        apply_moves(plan)
        check("apply_moves moved the file", final.is_file() and not shared.exists())


def test_plan_already_final_location_only_rewrites():
    # Second feedback report: shared file already at desk_widgets/_shared/,
    # widget authored with a three-levels-up path.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        final = project / PROMOTED_WIDGET_SRC_DIRNAME / "_shared" / "base.ts"
        final.parent.mkdir(parents=True)
        final.write_text("// shared\n")
        old = _write_widget(project, "fmt", ["../../../desk_widgets/_shared/base.ts", "fmt.ts"])
        new = project / PROMOTED_WIDGET_SRC_DIRNAME / "fmt"
        plan = plan_dependency_relocation(project, old, new)
        check("plan: file already final is not moved", plan.moves == {})
        check(
            "plan: entry rewritten relative to the new directory",
            plan.rewrites == {"../../../desk_widgets/_shared/base.ts": "../_shared/base.ts"},
        )


def test_plan_shared_components_mirror_not_moved_but_rewritten():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        mirror = project / TEMP_UI_DIRNAME / "shared-components" / "x" / "x.ts"
        mirror.parent.mkdir(parents=True)
        mirror.write_text("// x\n")
        old = _write_widget(project, "w", ["../../shared-components/x/x.ts", "w.ts"])
        new = project / PROMOTED_WIDGET_SRC_DIRNAME / "w"
        plan = plan_dependency_relocation(project, old, new)
        check("plan: the regenerated shared-components mirror is never moved", plan.moves == {})
        check(
            "plan: entry now reaches back into .desk_temp",
            plan.rewrites == {"../../shared-components/x/x.ts": "../../.desk_temp/shared-components/x/x.ts"},
        )


def test_plan_other_widgets_file_left_alone():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        other = _write_widget(project, "other", ["other.ts"])
        old = _write_widget(project, "w", ["../other/other.ts", "w.ts"])
        new = project / PROMOTED_WIDGET_SRC_DIRNAME / "w"
        plan = plan_dependency_relocation(project, old, new)
        check("plan: a file inside another widget's directory is not moved", plan.moves == {} and (other / "other.ts").is_file())
        check("plan: and a note says so", any("belongs to another widget" in n for n in plan.notes))


def test_plan_conflict_and_identical_destination():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        shared = _shared(project, text="// new\n")
        final = project / PROMOTED_WIDGET_SRC_DIRNAME / "_shared" / "base.ts"
        final.parent.mkdir(parents=True)
        final.write_text("// different\n")
        old = _write_widget(project, "w", ["../_shared/base.ts", "w.ts"])
        new = project / PROMOTED_WIDGET_SRC_DIRNAME / "w"
        plan = plan_dependency_relocation(project, old, new)
        check("conflict: nothing moved", plan.moves == {} and shared.is_file())
        check("conflict: note explains", any("differs" in n for n in plan.notes))
        check(
            "conflict: widget still points at the original",
            plan.rewrites == {"../_shared/base.ts": "../../.desk_temp/widgets/_shared/base.ts"},
        )
        final.write_text("// new\n")
        plan = plan_dependency_relocation(project, old, new)
        check("identical: nothing moved, original kept, noted", plan.moves == {} and shared.is_file() and any("identical" in n for n in plan.notes))


def test_plan_missing_file_and_own_files_ignored():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        old = _write_widget(project, "w", ["../_nope/gone.ts", "w.ts", "./sub/inner.ts"])
        new = project / PROMOTED_WIDGET_SRC_DIRNAME / "w"
        plan = plan_dependency_relocation(project, old, new)
        check("missing file: noted, not moved, not rewritten", plan.moves == {} and plan.rewrites == {} and len(plan.notes) == 1)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        (project / TEMP_WIDGETS / "w").mkdir(parents=True)
        check("no tsconfig.json: empty plan, no error", plan_dependency_relocation(project, project / TEMP_WIDGETS / "w", project / "desk_widgets" / "w") == type(plan)())


def test_rewrite_preserves_formatting():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        text = '{\n\t"compilerOptions": { "outDir": "out", "strict": true },\n\t"files": [ "../a.ts", "w.ts" ]\n}\n'
        (directory / "tsconfig.json").write_text(text)
        changed = rewrite_files_entries(directory, {"../a.ts": "../../b/a.ts"})
        result = (directory / "tsconfig.json").read_text()
        check("rewrite reports a change", changed)
        check("rewrite is exact-string, formatting kept", result == text.replace("../a.ts", "../../b/a.ts"))
        check("rewrite is a no-op with nothing to rewrite", not rewrite_files_entries(directory, {}))


def test_find_peer_dependents():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        shared = _shared(project)
        _write_widget(project, "a", ["../_shared/base.ts", "a.ts"])
        _write_widget(project, "b", ["../_shared/base.ts", "b.ts"])
        _write_widget(project, "c", ["c.ts"])
        final = project / PROMOTED_WIDGET_SRC_DIRNAME / "_shared" / "base.ts"
        peers = find_peer_dependents(project, {shared: final}, exclude={project / TEMP_WIDGETS / "a"})
        check("peers: only the un-excluded dependent is found", [p.directory.name for p in peers] == ["b"])
        check(
            "peers: rewrite is relative to the peer's own unmoved directory",
            peers[0].rewrites == {"../_shared/base.ts": "../../../desk_widgets/_shared/base.ts"},
        )


# ---- through DeskWindow ---------------------------------------------------

def test_promote_two_widgets_sharing_one_file():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        shared = _shared(project)
        _write_widget(project, "cam", ["../_shared/base.ts", "cam.ts"])
        _write_widget(project, "scene", ["../_shared/base.ts", "scene.ts"])
        cam_path = _register(win, project, "cam", "Cam")
        scene_path = _register(win, project, "scene", "Scene")
        win.peer_choice = "leave"

        _promote(win, "Cam", cam_path)
        final = project / PROMOTED_WIDGET_SRC_DIRNAME / "_shared" / "base.ts"
        check("first promotion moved the shared file once", final.is_file() and not shared.exists())
        check("first promotion left a valid relative path", _files_of(project / PROMOTED_WIDGET_SRC_DIRNAME / "cam")[0] == "../_shared/base.ts")
        check("user was told what moved", any("Moved" in m and "base.ts" in m for _, m in win.info_messages))
        check("the un-promoted peer was offered a choice", win.peer_calls == [("scene", True)])

        win.info_messages.clear()
        win.peer_calls.clear()
        _promote(win, "Scene", scene_path)
        check("second promotion: nothing left to move, path stays valid", _files_of(project / PROMOTED_WIDGET_SRC_DIRNAME / "scene")[0] == "../_shared/base.ts")
        check("second promotion: no peer prompt (no other dependents)", win.peer_calls == [])
        check("second promotion: shared file untouched", final.read_text() == "// shared\n")


def test_peer_fix_action_rewrites_peer_tsconfig():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        _shared(project)
        _write_widget(project, "cam", ["../_shared/base.ts", "cam.ts"])
        peer = _write_widget(project, "scene", ["../_shared/base.ts", "scene.ts"])
        cam_path = _register(win, project, "cam", "Cam")
        win.peer_choice = "fix"
        _promote(win, "Cam", cam_path)
        check("peer 'fix': peer's tsconfig now reaches the moved file", _files_of(peer)[0] == "../../../desk_widgets/_shared/base.ts")
        check("peer 'fix': the referenced file exists from the peer's directory", (peer / _files_of(peer)[0]).resolve().is_file())
        check("peer 'fix': peer itself not promoted", peer.is_dir())


def test_peer_promote_action_promotes_peer():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        _shared(project)
        _write_widget(project, "cam", ["../_shared/base.ts", "cam.ts"])
        peer = _write_widget(project, "scene", ["../_shared/base.ts", "scene.ts"])
        cam_path = _register(win, project, "cam", "Cam")
        _register(win, project, "scene", "Scene")
        win.peer_choice = "promote"
        _promote(win, "Cam", cam_path)
        promoted = project / PROMOTED_WIDGET_SRC_DIRNAME / "scene"
        check("peer 'promote': peer directory moved to desk_widgets/", promoted.is_dir() and not peer.exists())
        check("peer 'promote': peer's tsconfig valid from its new home", (promoted / _files_of(promoted)[0]).resolve().is_file())
        check("peer 'promote': recorded in the .desk file", any(cw.keyword == "Scene" for cw in win.current_desk.custom_widgets))
        check("peer 'promote': marked desk-sourced", win._custom_widget_sources.get("Scene") == "desk")


def test_peer_unregistered_directory_cannot_be_promoted():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        _shared(project)
        _write_widget(project, "cam", ["../_shared/base.ts", "cam.ts"])
        _write_widget(project, "orphan", ["../_shared/base.ts", "orphan.ts"])
        cam_path = _register(win, project, "cam", "Cam")
        _promote(win, "Cam", cam_path)
        check("peer without a registered definition is not offered promotion", win.peer_calls == [("orphan", False)])


def test_no_external_files_is_silent_and_unchanged():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        _write_widget(project, "solo", ["solo.ts"])
        path = _register(win, project, "solo", "Solo")
        _promote(win, "Solo", path)
        new = project / PROMOTED_WIDGET_SRC_DIRNAME / "solo"
        # TODO 3d792f8: promotion's own separate outDir-normalization step
        # (verify_promotion_outdir_normalization.py's own concern) also
        # touches tsconfig.json when outDir isn't already .build -- this
        # test only cares about this TODO's own "files" entries.
        check("no external files: 'files' entries untouched", _files_of(new) == ["solo.ts"])
        check("no external files: no dependency message", not any("shared dependencies" in t for t, _ in win.info_messages))


def test_promoted_widget_still_builds_with_tsc():
    if shutil.which("tsc") is None:
        print("SKIP: tsc not installed")
        return
    from desk.custom_widgets import build_from_source

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        project = Path(d)
        win = _FakeWindow(project)
        _shared(project, filename="base.ts", text="class Base { hello(): string { return 'hi'; } }\n")
        old = _write_widget(
            project, "cam", ["../_shared/base.ts", "cam.ts"],
            tsconfig_extra={"compilerOptions": {"outDir": "out", "strict": True, "target": "es2020"}},
        )
        (old / "cam.ts").write_text("class Cam extends Base {}\nnew Cam().hello();\n")
        (old / "widget.html").write_text("<html><body><script>/* BUILD:COMPILED_JS */</script></body></html>")
        check("sanity: builds before promotion", build_from_source(project, _source_path("cam")) is not None)
        path = _register(win, project, "cam", "Cam")
        _promote(win, "Cam", path)
        result = build_from_source(project, f"{PROMOTED_WIDGET_SRC_DIRNAME}/cam")
        check("promoted widget rebuilds after its shared file moved", result is not None)
        if result is not None:
            html = (result / "index.html").read_text()
            check("rebuilt output includes the moved shared code", "hello" in html and "Cam" in html)


def test_changelog_and_doc_cover_this():
    from desk.temp_ui import _CUSTOM_WIDGETS_DOC, _NEW_FEATURES

    tag = "promotion moves shared tsconfig files #586922"
    check("tag is in CURRENT_TAGS with a _NEW_FEATURES entry", tag in CURRENT_TAGS and tag in _NEW_FEATURES)
    check("promotion section documents shared tsconfig files", "Shared files a widget's `tsconfig.json` lists" in _CUSTOM_WIDGETS_DOC)


for name, fn in list(globals().items()):
    if name.startswith("test_") and callable(fn):
        fn()

# Same os._exit() ending as verify_relocate_promoted_widget_source.py
# (see LEARNINGS.md's TODO a5f66cc entry): several real WebEngine
# profiles/pages can segfault at normal interpreter shutdown, clobbering
# the exit code after every check has already run.
print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
