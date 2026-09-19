"""Verifies TODO `9d52dc4`'s `WorkspaceView` drop-target delegation
(`src/desk/shell/canvas.py`): a placed widget with some descendant
that calls `setAcceptDrops(True)` gets first refusal on a local-file
drop landing on it, via Qt's own native `QGraphicsProxyWidget`
drag-and-drop forwarding, before the canvas's own long-standing
"open a new widget for this file" handling (`files_dropped`) runs.
General, not specific to the Pipeline widget that motivated it -- see
`plans/pipeline-widget.md`."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.shell.canvas import WorkspaceView  # noqa: E402

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


# QDropEvent/QDragEnterEvent don't keep their own QMimeData argument
# alive on their own -- see verify_pipeline_widget.py's own comment on
# this, confirmed the same way there. Kept alive for the rest of the
# process.
_kept_mime_data = []


def _mime_for(path) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    _kept_mime_data.append(mime)
    return mime


def _drop_event_at(view_pos: QPointF, path) -> QDropEvent:
    return QDropEvent(
        view_pos, Qt.DropAction.CopyAction, _mime_for(path), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )


def _drag_enter_event_at(view_pos: QPointF, path) -> QDragEnterEvent:
    return QDragEnterEvent(
        view_pos.toPoint(),
        Qt.DropAction.CopyAction,
        _mime_for(path),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _simulate_drop(view: WorkspaceView, view_pos: QPointF, path) -> QDropEvent:
    """A real drag delivers dragEnter, then one or more dragMove, then
    drop -- QGraphicsView's own native forwarding into an embedded
    QGraphicsProxyWidget's drag-and-drop handling depends on that
    sequence (confirmed directly: calling dropEvent alone, with no
    preceding dragEnter/dragMove on the same view, never reaches the
    embedded widget's own dropEvent at all -- silently, no exception).
    Mirrors that full sequence rather than only the final drop."""
    view.dragEnterEvent(_drag_enter_event_at(view_pos, path))
    view.dragMoveEvent(
        QDragMoveEvent(
            view_pos.toPoint(),
            Qt.DropAction.CopyAction,
            _mime_for(path),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    drop_event = _drop_event_at(view_pos, path)
    view.dropEvent(drop_event)
    return drop_event


class _RecordingDropWidget(QWidget):
    def __init__(self, accept: bool = True, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(accept)
        self.drops = []

    def dragEnterEvent(self, event) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        self.drops.append(event.mimeData().urls()[0].toLocalFile())
        event.acceptProposedAction()


def _make_view_with_widget(content: QWidget, pos=(0, 0), size=(200, 200)) -> WorkspaceView:
    view = WorkspaceView()
    view.resize(800, 600)
    view.show()
    view.add_widget(content, "Test Widget", pos=pos, size=size)
    return view


def _inside_content_view_pos(view: WorkspaceView, frame_pos=(0, 0)) -> QPointF:
    # Well below the 28px titlebar, comfortably inside the placed
    # widget's own content area.
    scene_pos = QPointF(frame_pos[0] + 50, frame_pos[1] + 100)
    return QPointF(view.mapFromScene(scene_pos))


def _empty_canvas_view_pos(view: WorkspaceView) -> QPointF:
    scene_pos = QPointF(5000, 5000)
    return QPointF(view.mapFromScene(scene_pos))


# -- A drop-accepting widget claims a drop landing on it ------------------


def test_drop_on_accepting_widget_is_delegated_not_opened_as_new_widget():
    content = _RecordingDropWidget(accept=True)
    view = _make_view_with_widget(content)
    files_dropped_calls = []
    view.files_dropped.connect(lambda paths, pos: files_dropped_calls.append(paths))

    view_pos = _inside_content_view_pos(view)
    _simulate_drop(view, view_pos, "/tmp/photo.png")

    check("the content widget's own dropEvent fired", content.drops == ["/tmp/photo.png"])
    check("the canvas did NOT also open a new widget for this drop", files_dropped_calls == [])


def test_drag_enter_on_accepting_widget_defers_to_it_too():
    content = _RecordingDropWidget(accept=True)
    view = _make_view_with_widget(content)
    view_pos = _inside_content_view_pos(view)
    event = _drag_enter_event_at(view_pos, "/tmp/photo.png")
    view.dragEnterEvent(event)
    check("dragEnterEvent delegates to the content widget (which accepts)", event.isAccepted())


# -- Empty canvas keeps the existing behavior unchanged --------------------


def test_drop_on_empty_canvas_still_opens_a_new_widget():
    content = _RecordingDropWidget(accept=True)
    view = _make_view_with_widget(content)
    files_dropped_calls = []
    view.files_dropped.connect(lambda paths, pos: files_dropped_calls.append(paths))

    view_pos = _empty_canvas_view_pos(view)
    view.dropEvent(_drop_event_at(view_pos, "/tmp/photo.png"))

    check("canvas-level handling still runs for a drop on empty canvas", len(files_dropped_calls) == 1)
    check("the unrelated placed widget's dropEvent never fired", content.drops == [])


# -- A widget that doesn't opt in never claims the drop ---------------------


def test_drop_on_a_non_accepting_widget_still_opens_a_new_widget():
    content = _RecordingDropWidget(accept=False)
    view = _make_view_with_widget(content)
    files_dropped_calls = []
    view.files_dropped.connect(lambda paths, pos: files_dropped_calls.append(paths))

    view_pos = _inside_content_view_pos(view)
    view.dropEvent(_drop_event_at(view_pos, "/tmp/photo.png"))

    check("a widget that never called setAcceptDrops(True) doesn't intercept", content.drops == [])
    check("canvas-level handling runs instead, unchanged from before this change", len(files_dropped_calls) == 1)


# -- A drop-accepting descendant nested inside the content widget -----------


def test_delegates_to_a_nested_drop_accepting_descendant():
    outer = QWidget()
    layout = QVBoxLayout(outer)
    inner = _RecordingDropWidget(accept=True)
    layout.addWidget(inner)
    view = _make_view_with_widget(outer)
    files_dropped_calls = []
    view.files_dropped.connect(lambda paths, pos: files_dropped_calls.append(paths))

    view_pos = _inside_content_view_pos(view)
    _simulate_drop(view, view_pos, "/tmp/photo.png")

    check("a nested drop-accepting descendant (not just the top-level content widget) is found", inner.drops == ["/tmp/photo.png"])
    check("canvas-level handling is skipped for it too", files_dropped_calls == [])


# -- A drop-accepting widget that itself ignores this payload rejects it, does not fall back --


def test_drop_accepting_widget_that_ignores_the_payload_falls_through_to_nothing():
    class _ImageOnlyWidget(QWidget):
        def __init__(self):
            super().__init__()
            self.setAcceptDrops(True)
            self.drops = []

        def dragEnterEvent(self, event) -> None:
            if str(event.mimeData().urls()[0].toLocalFile()).endswith(".png"):
                event.acceptProposedAction()
            else:
                event.ignore()

        def dropEvent(self, event) -> None:
            if str(event.mimeData().urls()[0].toLocalFile()).endswith(".png"):
                self.drops.append(event.mimeData().urls()[0].toLocalFile())
                event.acceptProposedAction()
            else:
                event.ignore()

    content = _ImageOnlyWidget()
    view = _make_view_with_widget(content)
    files_dropped_calls = []
    view.files_dropped.connect(lambda paths, pos: files_dropped_calls.append(paths))

    view_pos = _inside_content_view_pos(view)
    _simulate_drop(view, view_pos, "/tmp/notes.txt")

    check("the widget itself rejected the non-matching payload", content.drops == [])
    check(
        "delegation is structural, not payload-aware -- it does NOT fall back to canvas-level handling",
        files_dropped_calls == [],
    )


test_drop_on_accepting_widget_is_delegated_not_opened_as_new_widget()
test_drag_enter_on_accepting_widget_defers_to_it_too()
test_drop_on_empty_canvas_still_opens_a_new_widget()
test_drop_on_a_non_accepting_widget_still_opens_a_new_widget()
test_delegates_to_a_nested_drop_accepting_descendant()
test_drop_accepting_widget_that_ignores_the_payload_falls_through_to_nothing()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
