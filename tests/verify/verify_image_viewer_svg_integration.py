import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtGui import QImage, QColor  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

REPO_ROOT = Path("/Users/mphair/inadvisable-adventures/desk")

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


spec = importlib.util.spec_from_file_location(
    "image_viewer_svg_check", REPO_ROOT / "widgets/image_viewer/widget.py"
)
image_viewer_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image_viewer_module)

check("widgets/svg_viewer/ no longer exists", not (REPO_ROOT / "widgets" / "svg_viewer").exists())
check("IMAGE_FILTER includes .svg", "*.svg" in image_viewer_module.IMAGE_FILTER)
check("IMAGE_FILTER includes .svgz", "*.svgz" in image_viewer_module.IMAGE_FILTER)


def make_png(path: Path) -> None:
    image = QImage(20, 10, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    image.save(str(path), "PNG")


SVG_CONTENT = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<circle cx="50" cy="50" r="40" fill="teal"/></svg>'
)


def test_raster_and_vector_dispatch():
    widget = image_viewer_module.ImageViewerWidget()
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)

        png_path = directory / "photo.png"
        make_png(png_path)
        widget.set_file(png_path)
        check("raster file shows the raster page", widget._stack.currentWidget() is widget._raster_view)
        check("raster view loaded successfully", widget._raster_view.is_valid())
        check("raster label shows filename", widget._label.text() == "photo.png")

        svg_path = directory / "shape.svg"
        svg_path.write_text(SVG_CONTENT)
        widget.set_file(svg_path)
        check("svg file shows the vector page", widget._stack.currentWidget() is widget._vector_view)
        check("vector view loaded successfully", widget._vector_view.is_valid())
        check("svg label shows filename", widget._label.text() == "shape.svg")

        real_svg = REPO_ROOT / "diagram-assets" / "circle-square.svg"
        widget.set_file(real_svg)
        check("real repo SVG fixture loads", widget._vector_view.is_valid())

        # Switch back to raster to confirm the stack really swaps both ways,
        # not just forward.
        widget.set_file(png_path)
        check("switching back to raster re-shows the raster page", widget._stack.currentWidget() is widget._raster_view)

        # Invalid content of each kind shows an error label, not a crash.
        bad_svg = directory / "bad.svg"
        bad_svg.write_text("not an svg at all { } <<<")
        widget.set_file(bad_svg)
        check("invalid svg shows an error label", "not a valid image file" in widget._label.text())

        bad_png = directory / "bad.png"
        bad_png.write_bytes(b"not a real png")
        widget.set_file(bad_png)
        check("invalid raster shows an error label", "not a valid image file" in widget._label.text())

    widget.deleteLater()


def test_svgz_dispatches_to_vector():
    widget = image_viewer_module.ImageViewerWidget()
    check("svgz dispatches to vector view", image_viewer_module._is_vector(Path("x.svgz")))
    check("svg dispatches to vector view", image_viewer_module._is_vector(Path("x.SVG")))
    check("png does not dispatch to vector view", not image_viewer_module._is_vector(Path("x.png")))
    widget.deleteLater()


test_raster_and_vector_dispatch()
test_svgz_dispatches_to_vector()


# ---------- file_type_registry ----------

from desk.file_type_registry import BUILTIN_VIEW_WIDGET_BY_SUFFIX, find_view_handler  # noqa: E402

check("BUILTIN_VIEW_WIDGET_BY_SUFFIX no longer references svg_viewer", "svg_viewer" not in BUILTIN_VIEW_WIDGET_BY_SUFFIX.values())
check(".svg resolves to image_viewer", BUILTIN_VIEW_WIDGET_BY_SUFFIX[".svg"] == "image_viewer")
check(".svgz resolves to image_viewer", BUILTIN_VIEW_WIDGET_BY_SUFFIX.get(".svgz") == "image_viewer")
check(
    "find_view_handler resolves a bare .svg path to image_viewer with an empty registry",
    find_view_handler([], Path("whatever.svg")) == "image_viewer",
)


# ---------- window.py source-level checks ----------

window_src = (REPO_ROOT / "src/desk/shell/window.py").read_text()
check("window.py no longer defines SVG_VIEWER_WIDGET_ID", "SVG_VIEWER_WIDGET_ID" not in window_src)
check("window.py's EXTERNAL_DROP_WIDGET_BY_SUFFIX routes .svg to IMAGE_VIEWER_WIDGET_ID", '".svg": IMAGE_VIEWER_WIDGET_ID' in window_src)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
