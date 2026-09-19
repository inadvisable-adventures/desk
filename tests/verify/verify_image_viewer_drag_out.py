"""Verifies TODO `8b88ec2`: the Image Viewer widget's loaded image can
be dragged back out of it -- a `QDrag` carrying the loaded file's own
local-file URL. See `plans/image-viewer-drag-out.md`.

`_start_drag`'s real `QDrag.exec()` is never invoked here (it would
block on a native drag loop) -- covered via `_drag_mime_data()`
directly, and via patching `_start_drag` itself to confirm the
event-filter gesture-detection logic (press, then move past the
threshold) calls it at the right moment."""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

_spec = importlib.util.spec_from_file_location(
    "image_viewer_drag_out_check", REPO_ROOT / "widgets/image_viewer/widget.py"
)
image_viewer_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(image_viewer_module)

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


def make_png(path: Path) -> None:
    image = QImage(20, 10, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    image.save(str(path), "PNG")


SVG_CONTENT = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<circle cx="50" cy="50" r="40" fill="teal"/></svg>'
)


def _mouse_event(kind: QEvent.Type, pos: QPoint, button=Qt.MouseButton.LeftButton) -> QMouseEvent:
    buttons = button if kind == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton
    return QMouseEvent(kind, QPointF(pos), QPointF(pos), button, buttons, Qt.KeyboardModifier.NoModifier)


# -- _drag_mime_data ---------------------------------------------------


def test_no_mime_data_with_no_file_loaded():
    widget = image_viewer_module.ImageViewerWidget()
    check("no file loaded -> no drag mime data", widget._drag_mime_data() is None)


def test_no_mime_data_if_file_no_longer_exists():
    widget = image_viewer_module.ImageViewerWidget()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "photo.png"
        make_png(path)
        widget.set_file(path)
        path.unlink()
        check("loaded file deleted afterward -> no drag mime data", widget._drag_mime_data() is None)


def test_mime_data_carries_the_loaded_raster_files_own_url():
    widget = image_viewer_module.ImageViewerWidget()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "photo.png"
        make_png(path)
        widget.set_file(path)
        mime = widget._drag_mime_data()
        check("mime data was built", mime is not None)
        check("mime data's urls() is exactly the loaded file's own local-file URL", [u.toLocalFile() for u in mime.urls()] == [str(path)])


def test_mime_data_carries_the_loaded_vector_files_own_url():
    widget = image_viewer_module.ImageViewerWidget()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "shape.svg"
        path.write_text(SVG_CONTENT)
        widget.set_file(path)
        mime = widget._drag_mime_data()
        check("mime data was built for a loaded SVG too", mime is not None)
        check("mime data's urls() is exactly the loaded SVG's own local-file URL", [u.toLocalFile() for u in mime.urls()] == [str(path)])


# -- Event-filter gesture detection -----------------------------------


def test_small_move_does_not_start_a_drag():
    widget = image_viewer_module.ImageViewerWidget()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "photo.png"
        make_png(path)
        widget.set_file(path)
        with patch.object(widget, "_start_drag") as start_drag:
            widget.eventFilter(widget._view_container, _mouse_event(QEvent.Type.MouseButtonPress, QPoint(10, 10)))
            widget.eventFilter(widget._view_container, _mouse_event(QEvent.Type.MouseMove, QPoint(11, 10)))
            check("a sub-threshold move doesn't start a drag", start_drag.call_count == 0)


def test_crossing_the_threshold_starts_exactly_one_drag():
    widget = image_viewer_module.ImageViewerWidget()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "photo.png"
        make_png(path)
        widget.set_file(path)
        threshold = QApplication.startDragDistance()
        with patch.object(widget, "_start_drag") as start_drag:
            widget.eventFilter(widget._view_container, _mouse_event(QEvent.Type.MouseButtonPress, QPoint(10, 10)))
            widget.eventFilter(
                widget._view_container, _mouse_event(QEvent.Type.MouseMove, QPoint(10 + threshold + 5, 10))
            )
            check("crossing the threshold starts a drag", start_drag.call_count == 1)
            # Further move events after the drag has already started
            # don't start a second one -- _drag_press_pos was cleared.
            widget.eventFilter(
                widget._view_container, _mouse_event(QEvent.Type.MouseMove, QPoint(10 + threshold + 20, 10))
            )
            check("no second drag from further movement mid-drag", start_drag.call_count == 1)


def test_release_before_threshold_resets_tracking():
    widget = image_viewer_module.ImageViewerWidget()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "photo.png"
        make_png(path)
        widget.set_file(path)
        with patch.object(widget, "_start_drag") as start_drag:
            widget.eventFilter(widget._view_container, _mouse_event(QEvent.Type.MouseButtonPress, QPoint(10, 10)))
            widget.eventFilter(
                widget._view_container, _mouse_event(QEvent.Type.MouseButtonRelease, QPoint(11, 10), Qt.MouseButton.LeftButton)
            )
            check("release before threshold clears the tracked press", widget._drag_press_pos is None)
            # A move now (as if from an unrelated later mouse event with
            # no button held) must not be mistaken for an in-progress drag.
            widget.eventFilter(widget._view_container, _mouse_event(QEvent.Type.MouseMove, QPoint(500, 500)))
            check("no drag starts from a move with no tracked press", start_drag.call_count == 0)


def test_events_on_a_different_object_are_ignored():
    widget = image_viewer_module.ImageViewerWidget()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "photo.png"
        make_png(path)
        widget.set_file(path)
        other = image_viewer_module.QWidget()
        with patch.object(widget, "_start_drag") as start_drag:
            widget.eventFilter(other, _mouse_event(QEvent.Type.MouseButtonPress, QPoint(10, 10)))
            widget.eventFilter(other, _mouse_event(QEvent.Type.MouseMove, QPoint(500, 500)))
            check("events on an unrelated object never start a drag", start_drag.call_count == 0)


test_no_mime_data_with_no_file_loaded()
test_no_mime_data_if_file_no_longer_exists()
test_mime_data_carries_the_loaded_raster_files_own_url()
test_mime_data_carries_the_loaded_vector_files_own_url()
test_small_move_does_not_start_a_drag()
test_crossing_the_threshold_starts_exactly_one_drag()
test_release_before_threshold_resets_tracking()
test_events_on_a_different_object_are_ignored()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
