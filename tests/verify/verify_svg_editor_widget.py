import importlib.util
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/Users/mphair/inadvisable-adventures/desk/src")

from PyQt6.QtCore import QPointF  # noqa: E402
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


spec = importlib.util.spec_from_file_location("svg_editor_check", REPO_ROOT / "widgets/svg_editor/widget.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def local_tag(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


# ---------- create-tool for each single-click type ----------

def test_create_each_single_click_type():
    widget = mod.SvgEditorWidget()
    for tool in ("rect", "circle", "ellipse", "line"):
        widget._create_single_click_object(tool, QPointF(100, 100))
    check("4 single-click objects created", len(widget._objects) == 4)
    tags = [local_tag(obj.element.tag) for obj in widget._objects]
    check("tags are rect/circle/ellipse/line in order", tags == ["rect", "circle", "ellipse", "line"])

    rect_obj = widget._objects[0]
    check("rect has width/height/x/y set", all(k in rect_obj.element.attrib for k in ("x", "y", "width", "height")))

    circle_obj = widget._objects[1]
    check("circle has cx/cy/r set", all(k in circle_obj.element.attrib for k in ("cx", "cy", "r")))

    ellipse_obj = widget._objects[2]
    check("ellipse has cx/cy/rx/ry set", all(k in ellipse_obj.element.attrib for k in ("cx", "cy", "rx", "ry")))

    line_obj = widget._objects[3]
    check("line has x1/y1/x2/y2 set", all(k in line_obj.element.attrib for k in ("x1", "y1", "x2", "y2")))
    widget.deleteLater()


def test_create_multiclick_types():
    widget = mod.SvgEditorWidget()
    pts = [QPointF(10, 10), QPointF(60, 10), QPointF(35, 50)]

    widget.current_tool = "polyline"
    widget._pending_points = list(pts)
    widget._finish_pending()

    widget.current_tool = "polygon"
    widget._pending_points = list(pts)
    widget._finish_pending()

    widget.current_tool = "path"
    widget._pending_points = list(pts)
    widget._finish_pending()

    check("3 multi-click objects created", len(widget._objects) == 3)
    polyline_obj, polygon_obj, path_obj = widget._objects
    check("polyline element has points", "points" in polyline_obj.element.attrib)
    check("polygon element has points", "points" in polygon_obj.element.attrib)
    check("path element has d starting with M", path_obj.element.get("d", "").startswith("M "))
    check("path element d ends with Z (closed)", path_obj.element.get("d", "").endswith("Z"))
    widget.deleteLater()


def test_create_text():
    widget = mod.SvgEditorWidget()
    import PyQt6.QtWidgets as qtw
    original = qtw.QInputDialog.getText
    qtw.QInputDialog.getText = staticmethod(lambda *a, **k: ("Hello SVG", True))
    try:
        widget._create_single_click_object("text", QPointF(20, 30))
    finally:
        qtw.QInputDialog.getText = original
    check("one text object created", len(widget._objects) == 1)
    obj = widget._objects[0]
    check("text element content set", obj.element.text == "Hello SVG")
    check("text element has font-size/fill", "font-size" in obj.element.attrib and "fill" in obj.element.attrib)
    widget.deleteLater()


test_create_each_single_click_type()
test_create_multiclick_types()
test_create_text()


# ---------- save / load round-trip, including moved/resized objects ----------

def test_save_load_roundtrip_with_move_and_resize():
    widget = mod.SvgEditorWidget()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "doc.svg"

        widget._create_single_click_object("rect", QPointF(100, 100))
        rect_obj = widget._objects[0]
        # Default rect is 80x60 placed at (60,70)-(140,130) for a
        # click at (100,100). Simulate a Shapes-tool corner drag on the
        # bottom-right corner (index 2), moving it to (300,250) --
        # new width/height = 300-60=240, 250-70=180.
        rect_obj.resize_corner(2, QPointF(300, 250))

        widget._create_single_click_object("circle", QPointF(50, 50))
        circle_obj = widget._objects[1]
        # Simulate a native Qt drag: moving the whole item via setPos.
        circle_obj.item.setPos(circle_obj.item.pos() + QPointF(40, 10))

        check("save succeeds", widget._save_to_path(path))
        check("file exists after save", path.is_file())

        # A totally fresh widget loading the saved file should reconstruct
        # both objects with the moved/resized geometry.
        widget2 = mod.SvgEditorWidget()
        widget2.set_file(path)
        check("2 objects reloaded", len(widget2._objects) == 2)
        loaded_rect = widget2._objects[0]
        loaded_rect_rect = loaded_rect.item.rect()
        check(
            "resized rect round-trips with the new width/height",
            abs(loaded_rect_rect.width() - 240) < 1.0 and abs(loaded_rect_rect.height() - 180) < 1.0,
        )
        loaded_circle = widget2._objects[1]
        check(
            "moved circle round-trips with the new position",
            abs(float(loaded_circle.element.get("cx")) - (50 + 40)) < 1.0,
        )
        widget2.deleteLater()
    widget.deleteLater()


def test_unrecognized_and_unsupported_elements_round_trip_untouched():
    widget = mod.SvgEditorWidget()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "mixed.svg"
        original = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">'
            '<defs><linearGradient id="g1"></linearGradient></defs>'
            '<rect x="10" y="10" width="50" height="40" fill="#3daee9" stroke="#000000" stroke-width="1"/>'
            '<path d="M10,10 C20,20 30,30 40,40"/>'
            "</svg>"
        )
        path.write_text(original, encoding="utf-8")
        widget.set_file(path)
        check("only the recognized rect became an editable object", len(widget._objects) == 1)
        check("save succeeds with no edits", widget._save_to_path(path))

        reparsed = ET.fromstring(path.read_bytes())
        tags = [local_tag(el.tag) for el in reparsed]
        check("defs still present after save", "defs" in tags)
        check("curved path still present after save", "path" in tags)
        curved = [el for el in reparsed if local_tag(el.tag) == "path"][0]
        check("curved path's d attribute is untouched", curved.get("d") == "M10,10 C20,20 30,30 40,40")
    widget.deleteLater()


test_save_load_roundtrip_with_move_and_resize()
test_unrecognized_and_unsupported_elements_round_trip_untouched()


# ---------- points tool ----------

def test_points_tool_moves_one_vertex_only():
    widget = mod.SvgEditorWidget()
    pts = [QPointF(10, 10), QPointF(60, 10), QPointF(35, 50)]
    widget.current_tool = "polygon"
    widget._pending_points = list(pts)
    widget._finish_pending()
    obj = widget._objects[0]

    widget.current_tool = "points"
    widget._scene.clearSelection()
    obj.item.setSelected(True)
    check("points-tool handles shown for the selected polygon", len(widget._handles) == 3)

    obj.move_point(1, QPointF(999, 999))
    positions = obj.point_positions()
    check("moved vertex updated", abs(positions[1].x() - 999) < 1.0)
    check("other vertices unaffected", abs(positions[0].x() - 10) < 1.0 and abs(positions[2].x() - 35) < 1.0)
    widget.deleteLater()


test_points_tool_moves_one_vertex_only()


# ---------- shapes tool: resize + property panel ----------

def test_shapes_tool_resize_and_property_panel():
    widget = mod.SvgEditorWidget()
    widget._create_single_click_object("rect", QPointF(100, 100))
    rect_obj = widget._objects[0]

    widget.current_tool = "shapes"
    widget._scene.clearSelection()
    rect_obj.item.setSelected(True)
    check("shapes-tool shows 4 corner handles", len(widget._handles) == 4)

    before = rect_obj.item.rect()
    rect_obj.resize_corner(2, QPointF(before.width() + 200, before.height() + 100))
    after = rect_obj.item.rect()
    check("bottom-right corner drag grows the rect", after.width() > before.width() and after.height() > before.height())

    widget._on_selection_changed()
    check("property panel enabled with a selection", widget._property_panel.isEnabled())

    rect_obj.set_fill("#ff0000")
    rect_obj.set_stroke_color("#00ff00")
    rect_obj.set_stroke_width(3.5)
    check("fill applied", rect_obj.fill_color().name() == "#ff0000")
    check("stroke color applied", rect_obj.stroke_color().name() == "#00ff00")
    check("stroke width applied", abs(rect_obj.stroke_width() - 3.5) < 0.01)

    rect_obj.sync_to_element()
    check("style synced to element", rect_obj.element.get("fill") == "#ff0000" and rect_obj.element.get("stroke") == "#00ff00")
    widget.deleteLater()


test_shapes_tool_resize_and_property_panel()


# ---------- circle stays square under resize ----------

def test_circle_resize_stays_square():
    widget = mod.SvgEditorWidget()
    widget._create_single_click_object("circle", QPointF(100, 100))
    obj = widget._objects[0]
    obj.resize_corner(2, QPointF(obj.item.rect().width() + 300, obj.item.rect().height() + 10))
    rect = obj.item.rect()
    check("circle resize keeps width == height", abs(rect.width() - rect.height()) < 0.01)
    widget.deleteLater()


test_circle_resize_stays_square()


# ---------- unsupported path grammar rejected ----------

def test_unsupported_path_grammar_rejected():
    check("curve command rejected", mod._parse_simple_path_d("M0,0 C1,1 2,2 3,3") is None)
    check("relative lowercase rejected", mod._parse_simple_path_d("m0,0 l1,1") is None)
    check("simple M/L/Z accepted", mod._parse_simple_path_d("M0,0 L10,10 Z") is not None)


test_unsupported_path_grammar_rejected()


# ---------- file_type_registry wiring ----------

from desk.file_type_registry import BUILTIN_EDIT_WIDGET_BY_SUFFIX, find_edit_handler  # noqa: E402

check("BUILTIN_EDIT_WIDGET_BY_SUFFIX maps .svg to svg_editor", BUILTIN_EDIT_WIDGET_BY_SUFFIX.get(".svg") == "svg_editor")
check(
    "find_edit_handler resolves a bare .svg to svg_editor with an empty registry",
    find_edit_handler([], Path("whatever.svg")) == "svg_editor",
)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
