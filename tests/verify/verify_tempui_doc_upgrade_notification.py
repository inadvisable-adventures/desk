import os
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
from desk.temp_ui import (  # noqa: E402
    DOC_FILENAME,
    SCRATCH_DOC_FILENAME,
    TEMP_UI_DIRNAME,
    TEMPUI_DOC_VERSION,
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


def _downgrade_version(temp_dir: Path, old_version: int) -> None:
    """Simulates a pre-existing, genuinely stale .desk_temp: writes a
    fully current doc set, then rewrites just the main doc's own
    embedded version marker down to old_version -- the same "downgrade
    a real version marker" approach verify_ensure_build_widget_script
    .py already uses to simulate staleness."""
    doc_path = temp_dir / DOC_FILENAME
    text = doc_path.read_text()
    text = text.replace(f"version: {TEMPUI_DOC_VERSION} ", f"version: {old_version} ")
    doc_path.write_text(text)


# ---------- ensure_docs_current's own new (rewrote, previous_version) return value ----------


def test_ensure_docs_current_return_value():
    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)

        check("brand-new (no doc at all) -> (False, None)", ensure_docs_current(temp_dir) == (False, None))

        write_tempui_docs(temp_dir)
        check("already fully current -> (False, None)", ensure_docs_current(temp_dir) == (False, None))

        (temp_dir / SCRATCH_DOC_FILENAME).unlink()
        rewrote, previous_version = ensure_docs_current(temp_dir)
        check("current version but a missing split file -> rewrote True", rewrote is True)
        check("current version but a missing split file -> previous_version None (just a repair, not a convention change)", previous_version is None)
        check("the missing split file is actually restored", (temp_dir / SCRATCH_DOC_FILENAME).is_file())

        _downgrade_version(temp_dir, TEMPUI_DOC_VERSION - 3)
        rewrote2, previous_version2 = ensure_docs_current(temp_dir)
        check("a genuinely stale version -> rewrote True", rewrote2 is True)
        check("a genuinely stale version -> previous_version is the real old version", previous_version2 == TEMPUI_DOC_VERSION - 3)
        check("the main doc is rewritten to the current version", f"version: {TEMPUI_DOC_VERSION} " in (temp_dir / DOC_FILENAME).read_text())


test_ensure_docs_current_return_value()


# ---------- TempUiManager.provision: notification only for a real convention change ----------


def test_provision_stale_doc_notifies_and_places_a_real_scratch_widget():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        temp_dir = directory / TEMP_UI_DIRNAME
        temp_dir.mkdir()
        write_tempui_docs(temp_dir)
        old_version = TEMPUI_DOC_VERSION - 2
        _downgrade_version(temp_dir, old_version)

        mgr = TempUiManager()
        added = []
        mgr.file_added.connect(lambda p: added.append(p))

        result = mgr.provision(directory, lambda: True, lambda: True)
        check("provision returns the real temp_dir", result == temp_dir)
        check("the main doc is actually rewritten to the current version", f"version: {TEMPUI_DOC_VERSION} " in (temp_dir / DOC_FILENAME).read_text())

        pump(1.0)
        check("provision emits exactly one file_added for the upgrade notification", len(added) == 1)
        if added:
            note_path = added[0]
            check("the notification note is a real file under temp_dir", note_path.parent == temp_dir and note_path.is_file())
            note_text = note_path.read_text()
            check("the note starts with the Scratch keyword", note_text.startswith("Scratch "))
            check("the note mentions the real old version", str(old_version) in note_text)
            check("the note mentions the real new version", str(TEMPUI_DOC_VERSION) in note_text)
            check("the note points at tempui-breaking-changes.md", "tempui-breaking-changes.md" in note_text)

            # Real downstream effect, not just "the signal fired" --
            # the same _FakeWindow-with-real-_place_widget shape
            # tests/verify/verify_discuss_parking_lot_item.py already
            # uses for an equivalent notification-click check.
            current_context.set_current_desk_directory(directory)
            widget_info = WidgetInfo(
                id="scratch",
                path=Path("widgets/scratch"),
                kind="python",
                name="Scratch",
                entry="widget.py",
                capabilities=[],
                default_size=(360, 320),
            )
            win = _FakeWindow(directory, widgets={"scratch": widget_info})
            win._activate_temp_ui(note_path)
            frame = win.find_frame_by_instance_id(note_path.name)
            check("a real Scratch widget frame was actually placed for the notification", frame is not None)
            if frame is not None:
                content = frame.content.current
                check("the placed Scratch widget's label matches the note's own first line", content.label_text == "Desk's tempui conventions changed")
                check("the placed Scratch widget's body mentions both versions", str(old_version) in content.body.toPlainText() and str(TEMPUI_DOC_VERSION) in content.body.toPlainText())
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
        check("no notification for a repair-only refresh (version already current)", added == [])
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


test_provision_stale_doc_notifies_and_places_a_real_scratch_widget()
test_provision_brand_new_desk_temp_no_notification()
test_provision_current_but_missing_split_file_repairs_without_notification()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
