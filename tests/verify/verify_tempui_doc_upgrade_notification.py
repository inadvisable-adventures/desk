import os
import re
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.desks import Desk  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.temp_ui_manager import TempUiManager  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.shell.promoted_widget_source_watcher import PromotedWidgetSourceWatcher  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    CURRENT_TAGS,
    DOC_FILENAME,
    SCRATCH_DOC_FILENAME,
    TEMP_UI_DIRNAME,
    ensure_docs_current,
    write_tempui_docs,
)
from desk.widgets import WidgetInfo  # noqa: E402

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


def pump(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def poll_until(predicate, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _downgrade_tags(temp_dir: Path, has_tags: set) -> None:
    """Simulates a pre-existing, genuinely stale .desk_temp: writes a
    fully current doc set, then rewrites the main doc's own tag
    comments down to just `has_tags` -- a project that has already
    seen those tags and no others."""
    doc_path = temp_dir / DOC_FILENAME
    text = re.sub(r"<!-- desk-temporary-ui\.md tag: .+? -->\n?", "", doc_path.read_text())
    tag_lines = "\n".join(f"<!-- desk-temporary-ui.md tag: {tag} -->" for tag in has_tags)
    text = text.replace("# Temporary UI\n", f"# Temporary UI\n\n{tag_lines}\n", 1)
    doc_path.write_text(text)


# ---------- ensure_docs_current's own (rewrote, missing_tags) return value ----------


def test_ensure_docs_current_return_value():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)

        check("brand-new (no doc at all) -> (False, frozenset())", ensure_docs_current(temp_dir) == (False, frozenset()))

        write_tempui_docs(temp_dir)
        check("already fully current -> (False, frozenset())", ensure_docs_current(temp_dir) == (False, frozenset()))

        (temp_dir / SCRATCH_DOC_FILENAME).unlink()
        rewrote, missing_tags = ensure_docs_current(temp_dir)
        check("current tags but a missing split file -> rewrote True", rewrote is True)
        check("current tags but a missing split file -> missing_tags empty (just a repair, not a convention change)", missing_tags == frozenset())
        check("the missing split file is actually restored", (temp_dir / SCRATCH_DOC_FILENAME).is_file())

        has_tags = set(CURRENT_TAGS) - {"version-30", "version-40"}
        _downgrade_tags(temp_dir, has_tags)
        rewrote2, missing_tags2 = ensure_docs_current(temp_dir)
        check("genuinely missing tags -> rewrote True", rewrote2 is True)
        check("genuinely missing tags -> missing_tags is the real missing set", missing_tags2 == frozenset({"version-30", "version-40"}))
        check("the main doc is rewritten with every current tag", set(re.findall(r"<!-- desk-temporary-ui\.md tag: (.+?) -->", (temp_dir / DOC_FILENAME).read_text())) == set(CURRENT_TAGS))


test_ensure_docs_current_return_value()


# ---------- TempUiManager.provision: notification only for a real convention change ----------


def test_provision_stale_doc_notifies_and_places_a_real_markdown_widget():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / TEMP_UI_DIRNAME
        temp_dir.mkdir()
        write_tempui_docs(temp_dir)
        missing = {"version-30", "version-40"}
        _downgrade_tags(temp_dir, set(CURRENT_TAGS) - missing)

        mgr = TempUiManager()
        added = []
        mgr.file_added.connect(lambda p: added.append(p))

        result = mgr.provision(directory, lambda: True, lambda: True)
        check("provision returns the real temp_dir", result == temp_dir)
        check(
            "the main doc is actually rewritten with every current tag",
            set(re.findall(r"<!-- desk-temporary-ui\.md tag: (.+?) -->", (temp_dir / DOC_FILENAME).read_text())) == set(CURRENT_TAGS),
        )

        pump(1.0)
        check("provision emits exactly one file_added for the upgrade notification, never one per tag", len(added) == 1)
        if added:
            note_path = added[0]
            check("the notification note is a real file under temp_dir", note_path.parent == temp_dir and note_path.is_file())
            note_text = note_path.read_text()
            check("the note starts with the Markdown keyword (real content, not a plain Scratch pointer)", note_text.startswith("Markdown "))
            check("the note names both missing tags", "version-30" in note_text and "version-40" in note_text)
            check("the note does NOT mention a tag this project already had", "version-00" not in note_text)

            # Real downstream effect, not just "the signal fired" --
            # the same _FakeWindow-with-real-_place_widget shape
            # tests/verify/verify_discuss_parking_lot_item.py already
            # uses for an equivalent notification-click check. Markdown
            # notes place the real, built-in Markdown widget.
            current_context.set_current_desk_directory(directory)
            widget_info = WidgetInfo(
                id="markdown",
                path=Path("widgets/markdown"),
                kind="python",
                name="Markdown",
                entry="widget.py",
                capabilities=[],
                default_size=(900, 700),
            )
            win = _FakeWindow(directory, widgets={"markdown": widget_info})
            win._activate_temp_ui(note_path)
            frame = win.find_frame_by_instance_id(note_path.name)
            check("a real Markdown widget frame was actually placed for the notification", frame is not None)
            if frame is not None:
                content = frame.content.current
                check("the placed Markdown widget's label matches the note's own first line", content._label.text() == "Desk's tempui conventions changed")
                check(
                    "the placed Markdown widget's content mentions both missing tags",
                    "version-30" in content._tempui_content and "version-40" in content._tempui_content,
                )
            current_context.set_current_desk_directory(None)
        mgr.stop()


def test_provision_brand_new_desk_temp_no_notification():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        mgr = TempUiManager()
        added = []
        mgr.file_added.connect(lambda p: added.append(p))

        result = mgr.provision(directory, lambda: True, lambda: True)
        check("provision creates and returns a real temp_dir for a brand-new .desk_temp", result is not None and result.is_dir())

        pump(1.0)
        check("no notification for a brand-new .desk_temp (nothing was missed)", added == [])
        mgr.stop()


def test_provision_current_but_missing_split_file_repairs_without_notification():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / TEMP_UI_DIRNAME
        temp_dir.mkdir()
        write_tempui_docs(temp_dir)
        (temp_dir / SCRATCH_DOC_FILENAME).unlink()

        mgr = TempUiManager()
        added = []
        mgr.file_added.connect(lambda p: added.append(p))

        mgr.provision(directory, lambda: True, lambda: True)
        check("a missing split file is actually repaired by provision", (temp_dir / SCRATCH_DOC_FILENAME).is_file())

        pump(1.0)
        check("no notification for a repair-only refresh (tags already current)", added == [])
        mgr.stop()


def test_provision_no_tags_at_all_repairs_without_notification():
    """A doc set that predates tag-tracking entirely (no tag comments,
    no legacy version comment either) is always out of date, but there
    is nothing real to diff against -- silently topped up, same as the
    old TEMPUI_DOC_VERSION-era "no version note" case."""
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / TEMP_UI_DIRNAME
        temp_dir.mkdir()
        (temp_dir / DOC_FILENAME).write_text("# Temporary UI\n\nAncient, pre-tracking content.\n")

        mgr = TempUiManager()
        added = []
        mgr.file_added.connect(lambda p: added.append(p))

        mgr.provision(directory, lambda: True, lambda: True)
        check(
            "the doc is actually refreshed with every current tag",
            set(re.findall(r"<!-- desk-temporary-ui\.md tag: (.+?) -->", (temp_dir / DOC_FILENAME).read_text())) == set(CURRENT_TAGS),
        )

        pump(1.0)
        check("no notification for a doc with nothing to diff against", added == [])
        mgr.stop()


# ---------- _FakeWindow: same real-_place_widget shape verify_discuss_parking_lot_item.py already uses ----------


class _FakeHandle:
    def widget_url(self, widget_id):
        return f"http://fake/{widget_id}"

    token = "tok"


class _FakeWindow:
    def __init__(self, directory, widgets):
        self.current_desk = Desk(path=directory / "test.desk")
        self._widgets = widgets
        self._handle = _FakeHandle()
        self._custom_widget_definitions = {}
        self._custom_widget_sources = {}
        self._custom_widget_content_hash = {}
        # TODO 4eb3d9e: _register_custom_widget/_place_widget/
        # _on_widget_stale_clicked now also touch these.
        self._promoted_widget_source_watcher = PromotedWidgetSourceWatcher()
        self._promoted_widget_source_dirty = set()
        self.view = WorkspaceView()
        self.view.resize(800, 600)
        self.view.show()
        self._broker = HotReloadBroker()
        self._event_mediator = EventMediator()


_FakeWindow._place_widget = DeskWindow._place_widget
_FakeWindow._bind_event_mediator = DeskWindow._bind_event_mediator
_FakeWindow._bind_external_indicator = DeskWindow._bind_external_indicator
_FakeWindow._bind_error_indicator = DeskWindow._bind_error_indicator
_FakeWindow._temp_ui_widget_id_for = DeskWindow._temp_ui_widget_id_for
_FakeWindow._activate_temp_ui = DeskWindow._activate_temp_ui
_FakeWindow._bind_temp_ui_content = DeskWindow._bind_temp_ui_content
_FakeWindow.find_frame_by_instance_id = DeskWindow.find_frame_by_instance_id
_FakeWindow.open_widget = DeskWindow.open_widget
_FakeWindow.open_widget_content = DeskWindow.open_widget_content


test_provision_stale_doc_notifies_and_places_a_real_markdown_widget()
test_provision_brand_new_desk_temp_no_notification()
test_provision_current_but_missing_split_file_repairs_without_notification()
test_provision_no_tags_at_all_repairs_without_notification()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
