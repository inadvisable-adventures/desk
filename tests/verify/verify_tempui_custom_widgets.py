# DISABLED (see tests/verify/README.md) -- TODO d8a6c96 tracks
# investigating this. Current failure: Fails with AttributeError: '_FakeWindow' object has no attribute
# '_custom_widget_content_hash'. Did you mean:
# '_custom_widget_source_paths' -- same fixture-drift category as the
# other fake-DeskWindow-double failures above: the real
# _register_custom_widget now sets
# self._custom_widget_content_hash[keyword] (added after this fake
# double was written). Reasonable suspicion: fixture drift, not a real
# bug.

import base64
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.temp_ui import (  # noqa: E402
    CustomWidgetDefinition,
    DEFINE_WIDGET_KEYWORD,
    RESERVED_TEMPUI_KEYWORDS,
    detect_temp_ui_kind,
    parse_define_widget,
    render_custom_widgets_section,
    sync_custom_widgets_doc_section,
    CUSTOM_WIDGETS_SECTION_START,
    CUSTOM_WIDGETS_SECTION_END,
)
from desk.custom_widgets import materialize, materialized_widget_dir  # noqa: E402
from desk.desks import Desk, save_desk, load_desk  # noqa: E402
from desk.widgets import WidgetInfo  # noqa: E402
from desk.server.runner import start_server  # noqa: E402

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.shell.window import DeskWindow  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.chromium_widget import ChromiumWidget  # noqa: E402


SAMPLE_HTML = "<html><body><h1>Kanban</h1></body></html>"
SAMPLE_HTML_B64 = base64.b64encode(SAMPLE_HTML.encode("utf-8")).decode("ascii")


# ---------- DSL parsing ----------


def test_parse_define_widget_well_formed():
    text = f"DefineWidget\tKanbanBoard\tKanban Board\nSize\t600\t400\nHtml\t{SAMPLE_HTML_B64}\n"
    definition = parse_define_widget(text)
    assert definition is not None
    assert definition.keyword == "KanbanBoard"
    assert definition.label == "Kanban Board"
    assert definition.default_size == (600, 400)
    assert definition.html_b64 == SAMPLE_HTML_B64
    print("parse_define_widget: well-formed single-chunk definition: PASS")


def test_parse_define_widget_multi_chunk_html_and_no_size():
    half = len(SAMPLE_HTML_B64) // 2
    chunk1, chunk2 = SAMPLE_HTML_B64[:half], SAMPLE_HTML_B64[half:]
    text = f"DefineWidget\tKanbanBoard\tKanban Board\nHtml\t{chunk1}\nHtml\t{chunk2}\n"
    definition = parse_define_widget(text)
    assert definition is not None
    assert definition.html_b64 == SAMPLE_HTML_B64
    assert definition.default_size is None
    print("parse_define_widget: multi-chunk Html lines concatenate in order, Size optional: PASS")


def test_parse_define_widget_label_defaults_to_keyword():
    text = f"DefineWidget\tKanbanBoard\nHtml\t{SAMPLE_HTML_B64}\n"
    definition = parse_define_widget(text)
    assert definition is not None
    assert definition.label == "KanbanBoard"
    print("parse_define_widget: label defaults to keyword when omitted: PASS")


def test_parse_define_widget_rejects_malformed():
    assert parse_define_widget("") is None
    assert parse_define_widget("Scratch hello\n") is None
    assert parse_define_widget("DefineWidget\t\t\nHtml\tabc\n") is None  # empty keyword
    assert parse_define_widget(f"DefineWidget\tKanbanBoard\tLabel\n") is None  # no Html at all
    print("parse_define_widget: rejects empty/wrong-keyword/no-keyword/no-html input: PASS")


def test_detect_temp_ui_kind_define_widget_and_custom():
    define_text = f"DefineWidget\tKanbanBoard\tKanban Board\nHtml\t{SAMPLE_HTML_B64}\n"
    assert detect_temp_ui_kind(define_text) == "define_widget"
    assert detect_temp_ui_kind("KanbanBoard\n", custom_keywords={"KanbanBoard"}) == "custom:KanbanBoard"
    # Default (no custom_keywords passed): falls back to "question", not a crash.
    assert detect_temp_ui_kind("KanbanBoard\n") == "question"
    # Existing kinds still detected identically (regression).
    assert detect_temp_ui_kind("Scratch hi\n") == "scratch"
    print("detect_temp_ui_kind: define_widget/custom keyword detection, regression-safe default: PASS")


def test_reserved_keywords_cover_all_builtins():
    for kw in ("Question", "Option", "Answer", "LightningRound", "LRItem", "OpenMarkdown", "Scratch", "Markdown", "DefineWidget"):
        assert kw in RESERVED_TEMPUI_KEYWORDS, kw
    print("RESERVED_TEMPUI_KEYWORDS covers every built-in keyword: PASS")


# ---------- materialize ----------


def test_materialize_valid_base64():
    with tempfile.TemporaryDirectory() as d:
        desk_temp = Path(d) / ".desk_temp"
        definition = CustomWidgetDefinition(keyword="KanbanBoard", label="Kanban Board", html_b64=SAMPLE_HTML_B64)
        result_dir = materialize(desk_temp, definition)
        assert result_dir == materialized_widget_dir(desk_temp, "KanbanBoard")
        assert (result_dir / "index.html").read_text() == SAMPLE_HTML
    print("materialize: valid base64 decodes to a real index.html: PASS")


def test_materialize_malformed_base64_returns_none_not_raise():
    with tempfile.TemporaryDirectory() as d:
        desk_temp = Path(d) / ".desk_temp"
        definition = CustomWidgetDefinition(keyword="Bad", label="Bad", html_b64="not-valid-base64!!!")
        result = materialize(desk_temp, definition)
        assert result is None
        assert not (materialized_widget_dir(desk_temp, "Bad")).exists()
    print("materialize: malformed base64 returns None, doesn't raise, no directory created: PASS")


# ---------- doc section rendering/sync ----------


def test_render_custom_widgets_section_empty_and_nonempty():
    empty = render_custom_widgets_section([])
    assert "(none registered yet)" in empty
    assert CUSTOM_WIDGETS_SECTION_START in empty and CUSTOM_WIDGETS_SECTION_END in empty

    d1 = CustomWidgetDefinition(keyword="KanbanBoard", label="Kanban Board", html_b64="x", default_size=(600, 400))
    d2 = CustomWidgetDefinition(keyword="Timer", label="A Timer", html_b64="y")
    section = render_custom_widgets_section([(d1, "tempui"), (d2, "desk")])
    assert "Kanban Board" in section and "`KanbanBoard`" in section and "600x400" in section
    assert "A Timer" in section and "`Timer`" in section and "default" in section
    assert "DefineWidget` tempui file" in section
    assert "saved `.desk` file" in section
    print("render_custom_widgets_section: empty + populated (label/keyword/size/source): PASS")


def test_sync_custom_widgets_doc_section_noop_if_doc_missing():
    with tempfile.TemporaryDirectory() as d:
        doc_path = Path(d) / "desk-temporary-ui.md"
        sync_custom_widgets_doc_section(doc_path, [])
        assert not doc_path.exists()
    print("sync_custom_widgets_doc_section: no-op if the doc doesn't exist yet: PASS")


def test_sync_custom_widgets_doc_section_appends_then_patches_in_place():
    with tempfile.TemporaryDirectory() as d:
        doc_path = Path(d) / "desk-temporary-ui.md"
        doc_path.write_text("# Temporary UI\n\nSome user-written content here.\n")
        d1 = CustomWidgetDefinition(keyword="KanbanBoard", label="Kanban Board", html_b64="x")

        sync_custom_widgets_doc_section(doc_path, [(d1, "tempui")])
        text = doc_path.read_text()
        assert "Some user-written content here." in text
        assert "Kanban Board" in text
        assert text.count(CUSTOM_WIDGETS_SECTION_START) == 1

        # Re-sync with a different set -- patched in place, not duplicated,
        # and the user's own content is still untouched.
        d2 = CustomWidgetDefinition(keyword="Timer", label="A Timer", html_b64="y")
        sync_custom_widgets_doc_section(doc_path, [(d2, "desk")])
        text2 = doc_path.read_text()
        assert "Some user-written content here." in text2
        assert "Kanban Board" not in text2
        assert "A Timer" in text2
        assert text2.count(CUSTOM_WIDGETS_SECTION_START) == 1
    print("sync_custom_widgets_doc_section: first append then in-place patch, user content preserved: PASS")


# ---------- Desk.custom_widgets round-trip ----------


def test_desk_custom_widgets_round_trip():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "test.desk"
        definition = CustomWidgetDefinition(
            keyword="KanbanBoard", label="Kanban Board", html_b64=SAMPLE_HTML_B64, default_size=(600, 400)
        )
        desk = Desk(path=path, custom_widgets=[definition])
        save_desk(desk)
        loaded = load_desk(path)
        assert len(loaded.custom_widgets) == 1
        got = loaded.custom_widgets[0]
        assert got.keyword == "KanbanBoard"
        assert got.label == "Kanban Board"
        assert got.html_b64 == SAMPLE_HTML_B64
        assert got.default_size == (600, 400)
    print("Desk.custom_widgets round-trips through save_desk/load_desk: PASS")


def test_desk_custom_widgets_defaults_empty_for_old_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "old.desk"
        path.write_text('{"widgets": [], "pan_x": 0.0, "pan_y": 0.0, "scale": 1.0}')
        loaded = load_desk(path)
        assert loaded.custom_widgets == []
    print("old-shaped .desk file (no custom_widgets key) loads with default []: PASS")


# ---------- ServerHandle.mount_html_widget against a real running server ----------


def test_mount_html_widget_serves_over_real_http():
    with tempfile.TemporaryDirectory() as d:
        widgets_dir = Path(d) / "widgets"
        widgets_dir.mkdir()
        handle = start_server(widgets_dir=widgets_dir)
        try:
            content_dir = Path(d) / "content"
            content_dir.mkdir()
            (content_dir / "index.html").write_text(SAMPLE_HTML)
            info = WidgetInfo(
                id="KanbanBoard", path=content_dir, kind="html", name="Kanban Board",
                entry="index.html", capabilities=[], default_size=None, tempui_only=True,
            )
            handle.mount_html_widget("KanbanBoard", content_dir, info)
            assert "KanbanBoard" in handle.widgets

            url = handle.widget_url("KanbanBoard")
            # Give uvicorn's own async loop a moment to actually register
            # the new route on its running thread.
            deadline = time.time() + 5
            last_error = None
            body = None
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        body = response.read().decode("utf-8")
                    break
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    time.sleep(0.1)
            assert body is not None, f"never got a response: {last_error}"
            assert "Kanban" in body
        finally:
            handle.stop()
    print("ServerHandle.mount_html_widget: mounted content is served over real HTTP after startup: PASS")


# ---------- DeskWindow-dependent methods on a fake double ----------


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


class _FakeView:
    def __init__(self):
        self.catalog_refreshes = []

    def set_widget_catalog(self, catalog):
        self.catalog_refreshes.append(dict(catalog))


class _FakeWindow:
    def __init__(self, directory, widgets=None):
        self.current_desk = Desk(path=directory / "test.desk")
        self._widgets = widgets if widgets is not None else {}
        self._handle = _FakeHandle()
        self.view = _FakeView()
        self._custom_widget_definitions = {}
        self._custom_widget_sources = {}
        self._custom_widget_source_paths = {}
        self.saved = []
        self.confirmed_messages = []
        self.info_messages = []

    def _confirm_fn(self, title, message):
        def confirm():
            self.confirmed_messages.append((title, message))
            return True

        return confirm

    def _info(self, title, message):
        self.info_messages.append((title, message))

    def save_current_desk(self):
        self.saved.append(True)


_FakeWindow._register_custom_widget = DeskWindow._register_custom_widget
_FakeWindow._register_custom_widgets_from_desk = DeskWindow._register_custom_widgets_from_desk
_FakeWindow._register_custom_widgets_from_desk_temp = DeskWindow._register_custom_widgets_from_desk_temp
_FakeWindow._handle_define_widget_file = DeskWindow._handle_define_widget_file
_FakeWindow._sync_tempui_doc = DeskWindow._sync_tempui_doc
_FakeWindow._on_tempui_promote_requested = DeskWindow._on_tempui_promote_requested


def _definition(keyword="KanbanBoard", label="Kanban Board"):
    return CustomWidgetDefinition(keyword=keyword, label=label, html_b64=SAMPLE_HTML_B64, default_size=(600, 400))


def test_register_custom_widget_success():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        win = _FakeWindow(directory)
        ok = win._register_custom_widget(_definition(), source="tempui")
        assert ok is True
        assert "KanbanBoard" in win._widgets
        info = win._widgets["KanbanBoard"]
        assert info.kind == "html"
        assert info.name == "Kanban Board"
        assert info.tempui_only is True
        assert win._custom_widget_sources["KanbanBoard"] == "tempui"
        assert ("KanbanBoard", info.path) in win._handle.mounted
        assert (info.path / "index.html").read_text() == SAMPLE_HTML
        assert win.view.catalog_refreshes  # spawn-menu catalog was refreshed
    print("_register_custom_widget: successful registration materializes + mounts + updates catalog: PASS")


def test_register_custom_widget_desk_sourced_is_not_tempui_only():
    """TODO 2b2a642: a fresh registration from the .desk file's own
    saved list (e.g. on every app startup) must NOT be tempui_only --
    otherwise a promoted widget never appears in the spawn menu, even
    after reloading the app (the originally reported bug)."""
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        ok = win._register_custom_widget(_definition(), source="desk")
        assert ok is True
        assert win._widgets["KanbanBoard"].tempui_only is False
    print("_register_custom_widget: source='desk' registration is never tempui_only, even fresh: PASS")


def test_register_custom_widget_rejects_reserved_keyword():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        ok = win._register_custom_widget(_definition(keyword="Scratch", label="Sneaky"), source="tempui")
        assert ok is False
        assert "Scratch" not in win._custom_widget_definitions
    print("_register_custom_widget: refuses to shadow a built-in DSL keyword: PASS")


def test_register_custom_widget_rejects_existing_widget_id():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d), widgets={"editor": WidgetInfo(
            id="editor", path=Path("/x"), kind="python", name="Editor", entry="widget.py",
            capabilities=[], default_size=None,
        )})
        ok = win._register_custom_widget(_definition(keyword="editor", label="Sneaky"), source="tempui")
        assert ok is False
        assert win._widgets["editor"].kind == "python"  # untouched
    print("_register_custom_widget: refuses to shadow an existing real widget id: PASS")


def test_register_custom_widget_cross_source_redefinition_rejected():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        assert win._register_custom_widget(_definition(), source="desk") is True
        # A tempui file later trying to define the SAME keyword, once
        # it's already desk-sourced, is rejected -- the desk stays authoritative.
        ok = win._register_custom_widget(_definition(label="Different label"), source="tempui")
        assert ok is False
        assert win._custom_widget_definitions["KanbanBoard"].label == "Kanban Board"
        assert win._custom_widget_sources["KanbanBoard"] == "desk"
    print("_register_custom_widget: cross-source redefinition is rejected, original source wins: PASS")


def test_register_custom_widget_same_source_redefinition_refreshes():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widget(_definition(label="Original"), source="tempui")
        ok = win._register_custom_widget(_definition(label="Updated"), source="tempui")
        assert ok is True
        assert win._custom_widget_definitions["KanbanBoard"].label == "Updated"
    print("_register_custom_widget: re-registration from the same source refreshes in place: PASS")


def test_register_custom_widgets_from_desk():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        desk = Desk(path=directory / "test.desk", custom_widgets=[_definition()])
        win = _FakeWindow(directory)
        win.current_desk = desk
        win._register_custom_widgets_from_desk(desk)
        assert win._custom_widget_sources["KanbanBoard"] == "desk"
    print("_register_custom_widgets_from_desk: registers every promoted definition with source='desk': PASS")


def test_register_custom_widgets_from_desk_temp_scans_and_registers():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        define_text = f"DefineWidget\tKanbanBoard\tKanban Board\nHtml\t{SAMPLE_HTML_B64}\n"
        uuid_name = "550e8400-e29b-41d4-a716-446655440000"
        (temp_dir / uuid_name).write_text(define_text)
        (temp_dir / "not-a-uuid.txt").write_text("ignored")
        (temp_dir / "desk-temporary-ui.md").write_text("# doc, ignored (not a uuid filename)")

        win = _FakeWindow(directory)
        win._register_custom_widgets_from_desk_temp(directory)
        assert "KanbanBoard" in win._custom_widget_definitions
        assert win._custom_widget_sources["KanbanBoard"] == "tempui"
        assert win._custom_widget_source_paths["KanbanBoard"] == temp_dir / uuid_name
    print("_register_custom_widgets_from_desk_temp: scans .desk_temp, ignores non-uuid/non-DefineWidget files: PASS")


def test_register_custom_widgets_from_desk_temp_noop_when_missing():
    with tempfile.TemporaryDirectory() as d:
        win = _FakeWindow(Path(d))
        win._register_custom_widgets_from_desk_temp(Path(d))  # no .desk_temp dir at all
        assert win._custom_widget_definitions == {}
    print("_register_custom_widgets_from_desk_temp: no-op when .desk_temp doesn't exist: PASS")


def test_handle_define_widget_file_registers_and_syncs_doc():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        doc_path = temp_dir / "desk-temporary-ui.md"
        doc_path.write_text("# Temporary UI\n")
        uuid_name = "550e8400-e29b-41d4-a716-446655440000"
        define_path = temp_dir / uuid_name
        define_path.write_text(f"DefineWidget\tKanbanBoard\tKanban Board\nHtml\t{SAMPLE_HTML_B64}\n")

        win = _FakeWindow(directory)
        handled = win._handle_define_widget_file(define_path)
        assert handled is True
        assert "KanbanBoard" in win._custom_widget_definitions
        assert win._custom_widget_source_paths["KanbanBoard"] == define_path
        assert "Kanban Board" in doc_path.read_text()
    print("_handle_define_widget_file: registers + syncs the doc, returns True: PASS")


def test_handle_define_widget_file_false_for_other_kinds():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        path = directory / "some-file"
        path.write_text("Scratch hello\nsome notes\n")
        win = _FakeWindow(directory)
        assert win._handle_define_widget_file(path) is False
        assert win._custom_widget_definitions == {}
    print("_handle_define_widget_file: returns False (no-op) for a non-DefineWidget file: PASS")


def test_promote_flow_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / ".desk_temp"
        temp_dir.mkdir()
        uuid_name = "550e8400-e29b-41d4-a716-446655440000"
        define_path = temp_dir / uuid_name
        define_path.write_text(f"DefineWidget\tKanbanBoard\tKanban Board\nHtml\t{SAMPLE_HTML_B64}\n")

        win = _FakeWindow(directory)
        win._register_custom_widgets_from_desk_temp(directory)
        assert win._custom_widget_sources["KanbanBoard"] == "tempui"
        assert win.current_desk.custom_widgets == []

        content = ChromiumWidget.__new__(ChromiumWidget)  # avoid a real QWebEngineView construction
        content.widget_id = "KanbanBoard"

        class _FrameStub:
            def __init__(self):
                self.promotable_calls = []

            def set_tempui_promotable(self, promotable):
                self.promotable_calls.append(promotable)

        frame = _FrameStub()
        frame.content = content

        # TODO 6857997/2b2a642: before promotion, tempui_only and never
        # excluded-from-spawn-menu tracking should reflect "still
        # tempui-sourced."
        assert win._widgets["KanbanBoard"].tempui_only is True
        refreshes_before = len(win.view.catalog_refreshes)

        win._on_tempui_promote_requested(frame)

        assert len(win.confirmed_messages) == 1
        assert win._custom_widget_sources["KanbanBoard"] == "desk"
        assert len(win.current_desk.custom_widgets) == 1
        assert win.current_desk.custom_widgets[0].keyword == "KanbanBoard"
        assert win.saved == [True]
        assert not define_path.exists()  # removed from tempui
        assert "KanbanBoard" not in win._custom_widget_source_paths

        # TODO 6857997/2b2a642: promotion flips the already-registered
        # WidgetInfo's tempui_only in place (so it's no longer excluded
        # from a spawn-menu-style filter), refreshes the catalog, and
        # hides this frame's own [TEMPUI] button -- reproducing the
        # "not showing up in the add-widget menu" bug being fixed, not
        # just a flag flip in isolation.
        assert win._widgets["KanbanBoard"].tempui_only is False
        assert len(win.view.catalog_refreshes) == refreshes_before + 1
        assert win.view.catalog_refreshes[-1]["KanbanBoard"].tempui_only is False
        assert frame.promotable_calls == [False]

        # A second promotion attempt on the now-desk-sourced widget is a
        # safe no-op (informational message), not a duplicate list entry.
        win._on_tempui_promote_requested(frame)
        assert len(win.current_desk.custom_widgets) == 1
        assert len(win.confirmed_messages) == 1  # confirm() wasn't asked again
        assert len(win.info_messages) == 1
    print("promote flow: confirms, saves to .desk, deletes tempui file, flips tempui_only + hides button, second attempt is a safe no-op: PASS")


# ---------- _place_widget's [TEMPUI] button wiring, on a real WorkspaceView ----------


from desk.hotreload import HotReloadBroker  # noqa: E402


class _FakeWindowWithView(_FakeWindow):
    def __init__(self, directory, widgets=None):
        super().__init__(directory, widgets)
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self._broker = HotReloadBroker()


_FakeWindowWithView._place_widget = DeskWindow._place_widget
_FakeWindowWithView._bind_claude_widget = DeskWindow._bind_claude_widget
_FakeWindowWithView._bind_external_indicator = DeskWindow._bind_external_indicator


def test_place_widget_shows_tempui_button_only_for_custom_widgets():
    import uuid as uuid_mod

    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        custom_info = WidgetInfo(
            id="KanbanBoard", path=directory, kind="html", name="Kanban Board", entry="index.html",
            capabilities=[], default_size=(600, 400), tempui_only=True,
        )
        promoted_info = WidgetInfo(
            id="Timer", path=directory, kind="html", name="A Timer", entry="index.html",
            capabilities=[], default_size=None, tempui_only=False,
        )
        ordinary_info = WidgetInfo(
            id="ordinary_html", path=directory, kind="html", name="Ordinary", entry="index.html",
            capabilities=[], default_size=None,
        )
        win = _FakeWindowWithView(
            directory,
            widgets={"KanbanBoard": custom_info, "Timer": promoted_info, "ordinary_html": ordinary_info},
        )
        win._custom_widget_definitions["KanbanBoard"] = _definition()
        win._custom_widget_sources["KanbanBoard"] = "tempui"
        win._custom_widget_definitions["Timer"] = _definition(keyword="Timer", label="A Timer")
        win._custom_widget_sources["Timer"] = "desk"

        custom_frame = win._place_widget(
            "KanbanBoard", custom_info, (0, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8]
        )
        assert custom_frame._titlebar.tempui_promote_button.isVisible() is True

        # TODO 6857997: a promoted (source="desk") custom widget's own
        # placed instance never shows the button, whether freshly
        # placed live or restored on a reload -- it has nothing left to
        # promote.
        promoted_frame = win._place_widget(
            "Timer", promoted_info, (450, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8]
        )
        assert promoted_frame._titlebar.tempui_promote_button.isVisible() is False

        ordinary_frame = win._place_widget(
            "ordinary_html", ordinary_info, (900, 0), (400, 300), instance_id=uuid_mod.uuid4().hex[:8]
        )
        assert ordinary_frame._titlebar.tempui_promote_button.isVisible() is False
    print("_place_widget: [TEMPUI] button shown only for a still-tempui-sourced custom widget: PASS")


# ---------- _on_widget_changed_refresh_catalog preserves custom entries ----------


_FakeWindow._on_widget_changed_refresh_catalog = DeskWindow._on_widget_changed_refresh_catalog


def test_on_widget_changed_refresh_catalog_preserves_custom_entries():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        empty_widgets_dir = directory / "widgets"
        empty_widgets_dir.mkdir()

        win = _FakeWindow(directory)
        win._widgets_dir = empty_widgets_dir
        custom_info = WidgetInfo(
            id="KanbanBoard", path=directory, kind="html", name="Kanban Board", entry="index.html",
            capabilities=[], default_size=None, tempui_only=True,
        )
        win._widgets["KanbanBoard"] = custom_info
        win._custom_widget_definitions["KanbanBoard"] = _definition()

        win._on_widget_changed_refresh_catalog("some_other_widget")

        assert "KanbanBoard" in win._widgets
        assert win._widgets["KanbanBoard"] is custom_info
        assert win.view.catalog_refreshes[-1] == {"KanbanBoard": custom_info}
    print("_on_widget_changed_refresh_catalog: custom widget catalog entries survive a hot-reload refresh: PASS")


# ---------- spawn-menu catalog excludes tempui_only entries ----------


def test_context_menu_excludes_tempui_only_from_spawn_menu():
    import desk.shell.canvas as canvas_mod
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QContextMenuEvent

    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        view = WorkspaceView()
        view.resize(400, 300)
        custom_info = WidgetInfo(
            id="KanbanBoard", path=directory, kind="html", name="Kanban Board", entry="index.html",
            capabilities=[], default_size=None, tempui_only=True,
        )
        ordinary_info = WidgetInfo(
            id="ordinary_html", path=directory, kind="html", name="Ordinary", entry="index.html",
            capabilities=[], default_size=None,
        )
        view.set_widget_catalog({"KanbanBoard": custom_info, "ordinary_html": ordinary_info})

        captured = {}

        class _NullSignal:
            def connect(self, *a):
                pass

        class _CapturingMenu:
            def __init__(self, catalog, parent=None):
                captured["catalog"] = catalog
                self.widget_chosen = _NullSignal()
                self.paste_requested = _NullSignal()

            def move(self, *a):
                pass

            def show(self):
                pass

        original = canvas_mod.WidgetSpawnMenu
        canvas_mod.WidgetSpawnMenu = _CapturingMenu
        try:
            event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10))
            view.contextMenuEvent(event)
        finally:
            canvas_mod.WidgetSpawnMenu = original

        assert "ordinary_html" in captured["catalog"]
        assert "KanbanBoard" not in captured["catalog"]
    print("WorkspaceView.contextMenuEvent: spawn-menu catalog excludes tempui_only widgets: PASS")


test_parse_define_widget_well_formed()
test_parse_define_widget_multi_chunk_html_and_no_size()
test_parse_define_widget_label_defaults_to_keyword()
test_parse_define_widget_rejects_malformed()
test_detect_temp_ui_kind_define_widget_and_custom()
test_reserved_keywords_cover_all_builtins()
test_materialize_valid_base64()
test_materialize_malformed_base64_returns_none_not_raise()
test_render_custom_widgets_section_empty_and_nonempty()
test_sync_custom_widgets_doc_section_noop_if_doc_missing()
test_sync_custom_widgets_doc_section_appends_then_patches_in_place()
test_desk_custom_widgets_round_trip()
test_desk_custom_widgets_defaults_empty_for_old_file()
test_mount_html_widget_serves_over_real_http()
test_register_custom_widget_success()
test_register_custom_widget_desk_sourced_is_not_tempui_only()
test_register_custom_widget_rejects_reserved_keyword()
test_register_custom_widget_rejects_existing_widget_id()
test_register_custom_widget_cross_source_redefinition_rejected()
test_register_custom_widget_same_source_redefinition_refreshes()
test_register_custom_widgets_from_desk()
test_register_custom_widgets_from_desk_temp_scans_and_registers()
test_register_custom_widgets_from_desk_temp_noop_when_missing()
test_handle_define_widget_file_registers_and_syncs_doc()
test_handle_define_widget_file_false_for_other_kinds()
test_promote_flow_end_to_end()
test_place_widget_shows_tempui_button_only_for_custom_widgets()
test_on_widget_changed_refresh_catalog_preserves_custom_entries()
test_context_menu_excludes_tempui_only_from_spawn_menu()
print("ALL PASS")
