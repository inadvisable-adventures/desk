import base64
import os
import sys
import tempfile
import uuid as uuid_mod
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
# TODO 78bfa41: canvas.py's own QWebEngineView import (previously used
# by the now-removed _scrollable_at) was the thing actually satisfying
# the "import WebEngine before QApplication" ordering requirement above
# -- import it explicitly instead of depending on that as an incidental
# side effect of an unrelated module.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.chromium_widget import ChromiumWidget  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
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


SAMPLE_HTML = "<html><body><h1>Kanban</h1></body></html>"
SAMPLE_HTML_B64 = base64.b64encode(SAMPLE_HTML.encode()).decode()
SAMPLE_HTML_2_B64 = base64.b64encode((SAMPLE_HTML + "<p>v2</p>").encode()).decode()


def _definition(html_b64=SAMPLE_HTML_B64, keyword="KanbanBoard", label="Kanban Board"):
    return CustomWidgetDefinition(keyword=keyword, label=label, html_b64=html_b64, default_size=(600, 400))


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
        self.confirm_calls = []
        self.confirm_return = True

    def _confirm_stale_reload_recording(self, placed_hash, current_hash):
        self.confirm_calls.append((placed_hash, current_hash))
        return self.confirm_return


_FakeWindow._register_custom_widget = DeskWindow._register_custom_widget
_FakeWindow._refresh_stale_indicators_for = DeskWindow._refresh_stale_indicators_for
_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._on_widget_stale_clicked = DeskWindow._on_widget_stale_clicked


def _make_stale_frame(win, html_b64=SAMPLE_HTML_2_B64):
    """Registers KanbanBoard, places one instance, then live-redefines
    it with different content so the placed instance reads as stale --
    exactly TODO 5995ffd's own established way to get into this state."""
    win._register_custom_widget(_definition(), source="tempui")
    widget = win._widgets["KanbanBoard"]
    frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
    win._register_custom_widget(_definition(html_b64=html_b64), source="tempui")
    return frame


# ---------- clicking the button (real WorkspaceView hit-test/dispatch) ----------


def test_clicking_stale_button_emits_widget_stale_clicked():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        frame = _make_stale_frame(win)
        check("stale button visible", frame._titlebar.stale_button.isVisible())

        emitted = []
        win.view.widget_stale_clicked.connect(lambda f: emitted.append(f))

        button = frame._titlebar.stale_button
        button_center_local = button.rect().center()
        global_pos = button.mapToGlobal(button_center_local)
        viewport_pos = win.view.viewport().mapFromGlobal(global_pos)
        scene_pos = win.view.mapToScene(viewport_pos)
        view_pos = win.view.mapFromScene(scene_pos)
        view_pos_f = QPointF(view_pos)

        hit = win.view._hit_test_chrome(view_pos_f)
        check("hit-test resolves to (frame, 'stale')", hit == (frame, "stale"))


# ---------- _on_widget_stale_clicked's own logic ----------


def test_reload_now_reloads_only_this_instance_and_clears_stale():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        frame = _make_stale_frame(win)
        other_widget = win._widgets["KanbanBoard"]
        other_frame = win._place_widget(
            "KanbanBoard", other_widget, (450, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8]
        )
        # other_frame was placed *after* the live redefinition inside
        # _make_stale_frame, so it's current, not stale -- confirms the
        # two placed instances are genuinely independent.
        check("second instance is not stale", not other_frame._titlebar.stale_button.isVisible())

        placed_hash_before = frame.placed_content_hash
        other_hash_before = other_frame.placed_content_hash
        current_hash = win._custom_widget_content_hash["KanbanBoard"]
        check("placed hash differs from current before reload", placed_hash_before != current_hash)

        # Instance-level mocks (not patch.object(ChromiumWidget, "reload"),
        # which replaces one shared class attribute -- accessed via
        # instance.reload it wouldn't receive `self`/bind per-instance,
        # so it couldn't distinguish which frame's content.reload() was
        # actually called): each frame's own content gets its own Mock.
        frame.content.reload = MagicMock()
        other_frame.content.reload = MagicMock()
        win._confirm_stale_reload = win._confirm_stale_reload_recording
        win._on_widget_stale_clicked(frame)

        check("_confirm_stale_reload called with both hashes", win.confirm_calls == [(placed_hash_before, current_hash)])
        check("reload() called exactly once on the clicked frame's own content", frame.content.reload.call_count == 1)
        check("placed_content_hash updated to the current hash", frame.placed_content_hash == current_hash)
        check("stale button hidden after reload", not frame._titlebar.stale_button.isVisible())
        check("the *other* instance's content.reload was never called", other_frame.content.reload.call_count == 0)
        check("the *other* instance's placed_content_hash was untouched", other_frame.placed_content_hash == other_hash_before)


def test_keep_for_now_changes_nothing():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        frame = _make_stale_frame(win)
        placed_hash_before = frame.placed_content_hash

        frame.content.reload = MagicMock()
        win.confirm_return = False
        win._confirm_stale_reload = win._confirm_stale_reload_recording
        win._on_widget_stale_clicked(frame)

        check("_confirm_stale_reload was called", len(win.confirm_calls) == 1)
        check("reload() never called", frame.content.reload.call_count == 0)
        check("placed_content_hash unchanged", frame.placed_content_hash == placed_hash_before)
        check("still marked stale", frame._titlebar.stale_button.isVisible())


def test_noop_for_non_html_widget():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))

        class _FakeFrame:
            content = object()  # not a ChromiumWidget

        win._confirm_stale_reload = win._confirm_stale_reload_recording
        win._on_widget_stale_clicked(_FakeFrame())
        check("non-ChromiumWidget content: no dialog shown", win.confirm_calls == [])


def test_noop_when_no_longer_actually_stale():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(), source="tempui")
        widget = win._widgets["KanbanBoard"]
        frame = win._place_widget("KanbanBoard", widget, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8])
        # Fresh placement: placed_content_hash already matches current.
        win._confirm_stale_reload = win._confirm_stale_reload_recording
        win._on_widget_stale_clicked(frame)
        check("not actually stale: no dialog shown", win.confirm_calls == [])


test_clicking_stale_button_emits_widget_stale_clicked()
test_reload_now_reloads_only_this_instance_and_clears_stale()
test_keep_for_now_changes_nothing()
test_noop_for_non_html_widget()
test_noop_when_no_longer_actually_stale()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
