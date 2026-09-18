"""TODO 4eb3d9e -- see plans/promoted-widget-source-staleness.md.
Cites ../FEEDBACK/FEEDBACK-DESK-promoted-widgets-no-stale-marker-2026-09-15-1744.md.
"""

import os
import shutil
import sys
import tempfile
import time
import uuid as uuid_mod
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.schema_registry import SchemaRegistry  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell import window as window_module  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.shell.promoted_widget_source_watcher import PromotedWidgetSourceWatcher  # noqa: E402
from desk.custom_widgets import SOURCE_BUILD_CACHE_DIRNAME, source_watch_exclusions  # noqa: E402
from desk.temp_ui import CustomWidgetDefinition  # noqa: E402

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


def _wait_for(predicate, timeout=3.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        app.processEvents()
        time.sleep(interval)
    return predicate()


# ---------- source_watch_exclusions ----------


def _write_widget_source(widget_dir, out_dir="out", keyword="Hello"):
    widget_dir.mkdir(parents=True, exist_ok=True)
    (widget_dir / "tsconfig.json").write_text(f'{{"compilerOptions": {{"outDir": "{out_dir}"}}}}')
    (widget_dir / f"{widget_dir.name}.ts").write_text(f'console.log("{keyword}");\n')
    (widget_dir / "widget.html").write_text(
        "<!doctype html>\n<html><head>\n<script>\n/* BUILD:COMPILED_JS */\n</script>\n</head><body></body></html>\n"
    )


def test_source_watch_exclusions_includes_build_cache_and_outdir():
    with tempfile.TemporaryDirectory() as d:
        widget_dir = Path(d) / "hello"
        _write_widget_source(widget_dir, out_dir="out")
        exclusions = source_watch_exclusions(widget_dir)
        check("always excludes .build", widget_dir / SOURCE_BUILD_CACHE_DIRNAME in exclusions)
        check("excludes tsconfig's own outDir", widget_dir / "out" in exclusions)


def test_source_watch_exclusions_degrades_gracefully_without_tsconfig():
    with tempfile.TemporaryDirectory() as d:
        widget_dir = Path(d) / "hello"
        widget_dir.mkdir(parents=True)
        exclusions = source_watch_exclusions(widget_dir)
        check("missing tsconfig.json: still excludes .build, no exception", exclusions == {widget_dir / SOURCE_BUILD_CACHE_DIRNAME})


def test_source_watch_exclusions_degrades_gracefully_with_malformed_tsconfig():
    with tempfile.TemporaryDirectory() as d:
        widget_dir = Path(d) / "hello"
        widget_dir.mkdir(parents=True)
        (widget_dir / "tsconfig.json").write_text("{ not valid json")
        exclusions = source_watch_exclusions(widget_dir)
        check("malformed tsconfig.json: still excludes .build, no exception", exclusions == {widget_dir / SOURCE_BUILD_CACHE_DIRNAME})


# ---------- PromotedWidgetSourceWatcher (real file watching) ----------


def test_watcher_fires_changed_for_a_real_source_edit():
    with tempfile.TemporaryDirectory() as d:
        widget_dir = Path(d) / "hello"
        _write_widget_source(widget_dir)
        watcher = PromotedWidgetSourceWatcher()
        seen = []
        watcher.changed.connect(seen.append)
        try:
            watcher.watch("Hello", widget_dir)
            (widget_dir / "hello.ts").write_text('console.log("edited");\n')
            check("a real edit to a watched source file fires changed with the keyword", _wait_for(lambda: seen == ["Hello"]))
        finally:
            watcher.stop_all()


def test_watcher_ignores_changes_under_build_cache_dir():
    with tempfile.TemporaryDirectory() as d:
        widget_dir = Path(d) / "hello"
        _write_widget_source(widget_dir)
        watcher = PromotedWidgetSourceWatcher()
        seen = []
        watcher.changed.connect(seen.append)
        try:
            watcher.watch("Hello", widget_dir)
            build_dir = widget_dir / SOURCE_BUILD_CACHE_DIRNAME
            build_dir.mkdir()
            (build_dir / "index.html").write_text("<html></html>")
            # A real source edit afterward still must fire -- confirms
            # the watch itself is alive and it's specifically the
            # .build/ write that's excluded, not a broken watch.
            (widget_dir / "hello.ts").write_text('console.log("edited");\n')
            check("a .build/ write alone never fires changed, only the later real source edit does", _wait_for(lambda: seen == ["Hello"]))
        finally:
            watcher.stop_all()


def test_watcher_stop_watching_and_stop_all():
    with tempfile.TemporaryDirectory() as d:
        widget_dir = Path(d) / "hello"
        _write_widget_source(widget_dir)
        watcher = PromotedWidgetSourceWatcher()
        seen = []
        watcher.changed.connect(seen.append)
        watcher.watch("Hello", widget_dir)
        watcher.stop_watching("Hello")
        (widget_dir / "hello.ts").write_text('console.log("after stop");\n')
        app.processEvents()
        time.sleep(0.5)
        check("stop_watching prevents further events from firing", seen == [])

        widget_dir_2 = Path(d) / "world"
        _write_widget_source(widget_dir_2, keyword="World")
        watcher.watch("World", widget_dir_2)
        watcher.stop_all()
        (widget_dir_2 / "world.ts").write_text('console.log("after stop_all");\n')
        app.processEvents()
        time.sleep(0.5)
        check("stop_all prevents further events from firing", seen == [])


# ---------- DeskWindow wiring: _register_custom_widget / _place_widget / _on_widget_stale_clicked ----------


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
        self._promoted_widget_source_watcher = PromotedWidgetSourceWatcher()
        self._promoted_widget_source_dirty = set()
        self._schema_registry = SchemaRegistry()
        self.rebuild_confirm_calls = []
        self.rebuild_confirm_return = True
        self.rebuild_failed_calls = []

    def _confirm_promoted_widget_rebuild_recording(self, keyword):
        self.rebuild_confirm_calls.append(keyword)
        return self.rebuild_confirm_return

    def _notify_promoted_widget_rebuild_failed_recording(self, keyword):
        self.rebuild_failed_calls.append(keyword)


_FakeWindow._register_custom_widget = DeskWindow._register_custom_widget
_FakeWindow._refresh_stale_indicators_for = DeskWindow._refresh_stale_indicators_for
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
_FakeWindow._on_widget_stale_clicked = DeskWindow._on_widget_stale_clicked
_FakeWindow._on_promoted_widget_source_changed = DeskWindow._on_promoted_widget_source_changed
_FakeWindow._on_promoted_widget_stale_clicked = DeskWindow._on_promoted_widget_stale_clicked


def _promoted_definition(keyword="KanbanBoard", label="Kanban Board", source_path="desk_widgets/KanbanBoard"):
    return CustomWidgetDefinition(keyword=keyword, label=label, html_b64="", default_size=(600, 400), source_path=source_path)


def _fake_build_from_source_factory(html_text="<html>v1</html>"):
    """Mirrors verify_relocate_promoted_widget_source.py's own
    monkeypatching convention -- avoids depending on a real tsc
    invocation for tests that only care about _register_custom_widget's
    own bookkeeping (a real end-to-end tsc build is covered separately
    below and in verify_build_from_source.py)."""

    def _fake_build_from_source(project_dir, source_path):
        build_dir = project_dir / source_path / SOURCE_BUILD_CACHE_DIRNAME
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "index.html").write_text(html_text)
        return build_dir

    return _fake_build_from_source


def _register_promoted(win, keyword="KanbanBoard", html_text="<html>v1</html>", source_path=None):
    source_path = source_path or f"desk_widgets/{keyword}"
    (win.current_desk.directory / source_path).mkdir(parents=True, exist_ok=True)
    definition = _promoted_definition(keyword=keyword, source_path=source_path)
    real_build_from_source = window_module.build_from_source
    window_module.build_from_source = _fake_build_from_source_factory(html_text)
    try:
        win._register_custom_widget(definition, source="desk")
    finally:
        window_module.build_from_source = real_build_from_source
    return definition


def test_register_custom_widget_starts_watch_for_promoted_source_backed_widget():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        _register_promoted(win)
        check("a watch is registered for the promoted keyword", "KanbanBoard" in win._promoted_widget_source_watcher._handles)


def test_register_custom_widget_does_not_watch_tempui_sourced_widget():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        definition = CustomWidgetDefinition(keyword="Scratch2", label="Scratch2", html_b64="aGVsbG8=", default_size=(400, 300))
        win._register_custom_widget(definition, source="tempui")
        check("no watch for a still-tempui-sourced widget", "Scratch2" not in win._promoted_widget_source_watcher._handles)


def test_register_custom_widget_does_not_watch_inline_promoted_widget():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        definition = CustomWidgetDefinition(keyword="Inline", label="Inline", html_b64="aGVsbG8=", default_size=(400, 300))
        win._register_custom_widget(definition, source="desk")
        check("no watch for a hand-authored, inline-only (no source_path) promoted widget", "Inline" not in win._promoted_widget_source_watcher._handles)


def test_on_promoted_widget_source_changed_marks_frames_stale_and_dirty():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        _register_promoted(win)
        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        check("fresh placement is not stale", not frame._titlebar.stale_button.isVisible())

        win._on_promoted_widget_source_changed("KanbanBoard")

        check("keyword added to the dirty set", "KanbanBoard" in win._promoted_widget_source_dirty)
        check("already-placed instance is marked [STALE]", frame._titlebar.stale_button.isVisible())


def test_on_widget_stale_clicked_routes_dirty_keyword_to_promoted_handler():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        _register_promoted(win)
        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        win._on_promoted_widget_source_changed("KanbanBoard")

        win._confirm_promoted_widget_rebuild = win._confirm_promoted_widget_rebuild_recording
        win._confirm_stale_reload = lambda *a: (_ for _ in ()).throw(AssertionError("hash-diff dialog must not fire for a dirty keyword"))
        frame.content.reload = MagicMock()

        real_build_from_source = window_module.build_from_source
        window_module.build_from_source = _fake_build_from_source_factory("<html>v2</html>")
        try:
            win._on_widget_stale_clicked(frame)
        finally:
            window_module.build_from_source = real_build_from_source

        check("routed to the promoted-widget rebuild confirm, not the hash-diff one", win.rebuild_confirm_calls == ["KanbanBoard"])


def test_decline_rebuild_leaves_everything_stale_and_dirty():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        _register_promoted(win)
        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        win._on_promoted_widget_source_changed("KanbanBoard")

        win.rebuild_confirm_return = False
        win._confirm_promoted_widget_rebuild = win._confirm_promoted_widget_rebuild_recording
        frame.content.reload = MagicMock()

        win._on_promoted_widget_stale_clicked(frame, "KanbanBoard")

        check("decline: reload never called", frame.content.reload.call_count == 0)
        check("decline: still marked stale", frame._titlebar.stale_button.isVisible())
        check("decline: keyword still dirty", "KanbanBoard" in win._promoted_widget_source_dirty)


def test_confirm_success_rebuilds_reloads_only_clicked_instance_and_leaves_sibling_stale():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        _register_promoted(win)
        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        other_frame = win._place_widget("KanbanBoard", widget, (450, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        win._on_promoted_widget_source_changed("KanbanBoard")
        check("both instances start stale", frame._titlebar.stale_button.isVisible() and other_frame._titlebar.stale_button.isVisible())

        win._confirm_promoted_widget_rebuild = win._confirm_promoted_widget_rebuild_recording
        frame.content.reload = MagicMock()
        other_frame.content.reload = MagicMock()

        real_build_from_source = window_module.build_from_source
        window_module.build_from_source = _fake_build_from_source_factory("<html>v2, actually rebuilt</html>")
        try:
            win._on_promoted_widget_stale_clicked(frame, "KanbanBoard")
        finally:
            window_module.build_from_source = real_build_from_source

        check("confirm: keyword no longer dirty", "KanbanBoard" not in win._promoted_widget_source_dirty)
        check("confirm: the clicked instance's content.reload was called", frame.content.reload.call_count == 1)
        check("confirm: the clicked instance is no longer stale", not frame._titlebar.stale_button.isVisible())
        check("confirm: the clicked instance's placed_content_hash now matches the freshly-registered one", frame.placed_content_hash == win._custom_widget_content_hash["KanbanBoard"])
        check("confirm: the *other* instance's content was never reloaded (per-instance choice)", other_frame.content.reload.call_count == 0)
        check("confirm: the *other* instance stays [STALE] until it's clicked too", other_frame._titlebar.stale_button.isVisible())


def test_confirm_failure_shows_dialog_and_stays_dirty():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        _register_promoted(win)
        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        win._on_promoted_widget_source_changed("KanbanBoard")

        win._confirm_promoted_widget_rebuild = win._confirm_promoted_widget_rebuild_recording
        win._notify_promoted_widget_rebuild_failed = win._notify_promoted_widget_rebuild_failed_recording
        frame.content.reload = MagicMock()

        real_build_from_source = window_module.build_from_source
        window_module.build_from_source = lambda project_dir, source_path: None  # simulates a real build failure
        try:
            win._on_promoted_widget_stale_clicked(frame, "KanbanBoard")
        finally:
            window_module.build_from_source = real_build_from_source

        check("failure dialog shown", win.rebuild_failed_calls == ["KanbanBoard"])
        check("reload never called on a failed rebuild", frame.content.reload.call_count == 0)
        check("still marked stale so it can be retried", frame._titlebar.stale_button.isVisible())
        check("still dirty so it can be retried", "KanbanBoard" in win._promoted_widget_source_dirty)


def test_fresh_placement_while_dirty_starts_stale():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        _register_promoted(win)
        win._promoted_widget_source_dirty.add("KanbanBoard")

        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])

        check("a freshly-placed instance of an already-dirty keyword starts [STALE]", frame._titlebar.stale_button.isVisible())


# ---------- one real, end-to-end tsc-driven rebuild ----------


def test_end_to_end_real_tsc_rebuild_via_stale_click():
    if shutil.which("tsc") is None:
        check("tsc available for this script's own end-to-end check", False)
        return
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        win = _FakeWindow(Path(d))
        source_path = "desk_widgets/RealBuild"
        widget_dir = win.current_desk.directory / source_path
        _write_widget_source(widget_dir, out_dir="out", keyword="v1")
        definition = _promoted_definition(keyword="RealBuild", source_path=source_path)
        win._register_custom_widget(definition, source="desk")

        widget = win._widgets["RealBuild"]
        frame = win._place_widget("RealBuild", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        v1_hash = win._custom_widget_content_hash["RealBuild"]

        # A real edit to the .ts source, then a real rebuild triggered
        # through the exact same click+confirm path a user would use.
        (widget_dir / "RealBuild.ts").write_text('console.log("v2, actually edited");\n')
        win._on_promoted_widget_source_changed("RealBuild")
        check("real source edit -> [STALE]", frame._titlebar.stale_button.isVisible())

        win._confirm_promoted_widget_rebuild = win._confirm_promoted_widget_rebuild_recording
        frame.content.reload = MagicMock()
        win._on_promoted_widget_stale_clicked(frame, "RealBuild")

        v2_hash = win._custom_widget_content_hash["RealBuild"]
        check("a real tsc rebuild produced a different content hash", v2_hash != v1_hash)
        check("the rebuilt .build/index.html contains the new source's own output", "v2, actually edited" in (widget_dir / SOURCE_BUILD_CACHE_DIRNAME / "index.html").read_text())
        check("no longer dirty after a real successful rebuild", "RealBuild" not in win._promoted_widget_source_dirty)
        check("clicked instance no longer stale", not frame._titlebar.stale_button.isVisible())


test_source_watch_exclusions_includes_build_cache_and_outdir()
test_source_watch_exclusions_degrades_gracefully_without_tsconfig()
test_source_watch_exclusions_degrades_gracefully_with_malformed_tsconfig()
test_watcher_fires_changed_for_a_real_source_edit()
test_watcher_ignores_changes_under_build_cache_dir()
test_watcher_stop_watching_and_stop_all()
test_register_custom_widget_starts_watch_for_promoted_source_backed_widget()
test_register_custom_widget_does_not_watch_tempui_sourced_widget()
test_register_custom_widget_does_not_watch_inline_promoted_widget()
test_on_promoted_widget_source_changed_marks_frames_stale_and_dirty()
test_on_widget_stale_clicked_routes_dirty_keyword_to_promoted_handler()
test_decline_rebuild_leaves_everything_stale_and_dirty()
test_confirm_success_rebuilds_reloads_only_clicked_instance_and_leaves_sibling_stale()
test_confirm_failure_shows_dialog_and_stays_dirty()
test_fresh_placement_while_dirty_starts_stale()
test_end_to_end_real_tsc_rebuild_via_stale_click()

# TODO a5f66cc: os._exit(), not sys.exit() -- this script places
# several kind:"html" (ChromiumWidget-backed) widgets across its test
# functions, each with its own real QWebEngineProfile. See
# verify_stale_marker_click_dialog.py's own identical comment for the
# confirmed reason (a real, reproducible Qt/WebEngine shutdown race
# tearing down 2+ such profiles, unrelated to anything this script
# actually verifies).
print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
