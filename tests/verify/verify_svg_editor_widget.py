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


# ---------- document bounds guide / Reset View / hex preview (TODO d1d176f) ----------
# see ../FEEDBACK/FEEDBACK-DESK-svg-editor-viewbox-guide-2026-07-16-1156.md


def test_document_bounds_parsing():
    root = ET.Element("svg")
    root.set("viewBox", "10 20 300 200")
    bounds = mod._document_bounds(root)
    check(
        "_document_bounds reads a normal viewBox (incl. non-zero origin)",
        (bounds.x(), bounds.y(), bounds.width(), bounds.height()) == (10.0, 20.0, 300.0, 200.0),
    )

    root2 = ET.Element("svg")
    root2.set("width", "500px")
    root2.set("height", "250px")
    bounds2 = mod._document_bounds(root2)
    check(
        "_document_bounds falls back to width/height (stripping a unit suffix) when viewBox is absent",
        (bounds2.x(), bounds2.y(), bounds2.width(), bounds2.height()) == (0.0, 0.0, 500.0, 250.0),
    )

    root3 = ET.Element("svg")
    bounds3 = mod._document_bounds(root3)
    check(
        "_document_bounds falls back to the 400x300 default when nothing usable is present",
        (bounds3.width(), bounds3.height()) == (400.0, 300.0),
    )


test_document_bounds_parsing()


def test_bounds_guide_present_after_init_and_reload():
    widget = mod.SvgEditorWidget()
    check("the bounds guide item exists right after construction", widget._bounds_guide_item is not None)

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "reload_test.svg"
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>')
        widget._load_file(path)
        check("the bounds guide item survives a full reload (_rebuild_scene_from_root)", widget._bounds_guide_item is not None)
    widget.deleteLater()


test_bounds_guide_present_after_init_and_reload()


def test_bounds_guide_and_hex_preview_never_appear_in_a_saved_file():
    widget = mod.SvgEditorWidget()
    widget._create_single_click_object("rect", QPointF(50, 50))
    widget._hex_preview_flat_button.click()

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "saved.svg"
        widget._save_to_path(path)
        saved_root = ET.fromstring(path.read_bytes())
        tags = [local_tag(el.tag) for el in saved_root]
        check(
            "the bounds guide rect never appears in a saved file",
            "rect" in tags and len(tags) == 1,
        )
    widget.deleteLater()


test_bounds_guide_and_hex_preview_never_appear_in_a_saved_file()


def test_guide_items_are_click_through():
    widget = mod.SvgEditorWidget()
    # A point inside the document bounds but with nothing real drawn there --
    # only the (always-present) bounds guide sits under it.
    check(
        "the bounds guide item doesn't accept mouse buttons (click-through)",
        widget._bounds_guide_item.acceptedMouseButtons() == mod.Qt.MouseButton.NoButton,
    )
    widget._hex_preview_pointy_button.click()
    check(
        "the hex preview item doesn't accept mouse buttons (click-through)",
        widget._hex_preview_item.acceptedMouseButtons() == mod.Qt.MouseButton.NoButton,
    )
    widget.deleteLater()


test_guide_items_are_click_through()


def test_scene_rect_bounded_generously_around_document():
    widget = mod.SvgEditorWidget()
    bounds = mod._document_bounds(widget._root)
    scene_rect = widget._scene.sceneRect()
    check(
        "the scene rect strictly contains the document bounds with room to spare on every side",
        scene_rect.left() < bounds.left()
        and scene_rect.top() < bounds.top()
        and scene_rect.right() > bounds.right()
        and scene_rect.bottom() > bounds.bottom(),
    )
    widget.deleteLater()


test_scene_rect_bounded_generously_around_document()


def test_reset_view_shows_the_document_bounds():
    widget = mod.SvgEditorWidget()
    widget.resize(400, 400)
    widget.show()
    # Pan the view far away from the document bounds.
    widget._view.centerOn(5000, 5000)
    visible = widget._view.mapToScene(widget._view.viewport().rect()).boundingRect()
    bounds = mod._document_bounds(widget._root)
    check("panning away genuinely leaves the document bounds out of view", not visible.intersects(bounds))

    widget._reset_view()
    visible_after = widget._view.mapToScene(widget._view.viewport().rect()).boundingRect()
    check("Reset View restores a transform that actually shows the document bounds", visible_after.contains(bounds))
    widget.deleteLater()


test_reset_view_shows_the_document_bounds()


def test_hex_preview_toggle_add_remove_and_persists_across_reload():
    widget = mod.SvgEditorWidget()
    check("hex preview is off by default", widget._hex_preview_item is None)
    check(
        "neither hex-orientation button is checked by default",
        not widget._hex_preview_flat_button.isChecked() and not widget._hex_preview_pointy_button.isChecked(),
    )

    widget._hex_preview_flat_button.click()
    check("clicking flat-top adds exactly one hex preview item", widget._hex_preview_item is not None)
    check("orientation state is 'flat'", widget._hex_preview_orientation == "flat")
    hex_bounds = widget._hex_preview_item.path().boundingRect()
    doc_bounds = mod._document_bounds(widget._root)
    check(
        "the hex preview's own path is bounded by the document bounds",
        doc_bounds.contains(hex_bounds) or abs(hex_bounds.width() - doc_bounds.width()) < 1.0,
    )

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "reload_hex.svg"
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>')
        widget._load_file(path)
        check("the hex preview toggle state survives a reload (re-added, not silently dropped)", widget._hex_preview_item is not None)
        check("the orientation itself also survives a reload", widget._hex_preview_orientation == "flat")

    widget._hex_preview_flat_button.click()
    check("clicking the active button again turns the mask off entirely", widget._hex_preview_item is None)
    check("orientation state is back to None (neither)", widget._hex_preview_orientation is None)
    check(
        "both buttons end up unchecked",
        not widget._hex_preview_flat_button.isChecked() and not widget._hex_preview_pointy_button.isChecked(),
    )
    widget.deleteLater()


test_hex_preview_toggle_add_remove_and_persists_across_reload()


def test_hex_preview_flat_and_pointy_are_mutually_exclusive_with_different_geometry():
    widget = mod.SvgEditorWidget()
    bounds = mod._document_bounds(widget._root)

    widget._hex_preview_flat_button.click()
    check("flat-top is checked, pointy-top is not", widget._hex_preview_flat_button.isChecked() and not widget._hex_preview_pointy_button.isChecked())

    widget._hex_preview_pointy_button.click()
    check(
        "clicking pointy-top while flat-top is active switches to pointy-top",
        widget._hex_preview_pointy_button.isChecked() and not widget._hex_preview_flat_button.isChecked(),
    )
    check("orientation state is 'pointy'", widget._hex_preview_orientation == "pointy")

    # The mask item's own boundingRect() is dominated by the outer
    # document rect (the hexagon-shaped hole doesn't touch its edges),
    # so it can't distinguish orientation -- compare the bare hexagon
    # paths' own bounding boxes instead, which genuinely differ (a
    # regular hexagon's bounding box swaps width/height between the two
    # orientations).
    flat_hex_bounds = mod._hexagon_path(bounds, flat_top=True).boundingRect()
    pointy_hex_bounds = mod._hexagon_path(bounds, flat_top=False).boundingRect()
    check(
        "flat-top and pointy-top produce genuinely different hexagon geometry for the same bounds",
        (flat_hex_bounds.width(), flat_hex_bounds.height()) != (pointy_hex_bounds.width(), pointy_hex_bounds.height()),
    )

    flat_hex = mod._hexagon_path(bounds, flat_top=True)
    pointy_hex = mod._hexagon_path(bounds, flat_top=False)
    check(
        "_hexagon_path(flat_top=True) has a vertex on the horizontal center line (flat top/bottom edges)",
        any(abs(flat_hex.elementAt(i).y - bounds.center().y()) < 0.01 for i in range(flat_hex.elementCount())),
    )
    check(
        "_hexagon_path(flat_top=False) has a vertex on the vertical center line (pointy top/bottom)",
        any(abs(pointy_hex.elementAt(i).x - bounds.center().x()) < 0.01 for i in range(pointy_hex.elementCount())),
    )
    widget.deleteLater()


test_hex_preview_flat_and_pointy_are_mutually_exclusive_with_different_geometry()


def test_hex_preview_buttons_are_grouped_in_their_own_frame():
    widget = mod.SvgEditorWidget()
    flat_parent = widget._hex_preview_flat_button.parent()
    pointy_parent = widget._hex_preview_pointy_button.parent()
    check(
        "both hex-preview buttons share the same parent frame, distinct from a plain toolbar button's parent",
        isinstance(flat_parent, mod.QFrame)
        and flat_parent is pointy_parent
        and flat_parent is not widget._toolbox.parent(),
    )
    check(
        "the hex-preview buttons have their own distinct stylesheet, unlike a plain toolbar button",
        widget._hex_preview_flat_button.styleSheet() == mod.HEX_PREVIEW_BUTTON_STYLE
        and widget._hex_preview_flat_button.styleSheet() != "",
    )
    widget.deleteLater()


test_hex_preview_buttons_are_grouped_in_their_own_frame()


def test_flat_top_hex_top_and_bottom_align_with_the_document_bounds():
    # A non-square document, so "sized off height alone" and "sized off
    # min(width, height)" would produce visibly different results if
    # this regressed back to the old (shared) sizing.
    bounds = mod.QRectF(0, 0, 400, 300)

    flat_bounds = mod._hexagon_path(bounds, flat_top=True).boundingRect()
    check(
        "the flat-top hex's vertical extent exactly matches the document's height (top/bottom aligned)",
        abs(flat_bounds.height() - bounds.height()) < 0.01,
    )
    check(
        "the flat-top hex's horizontal extent is independent of the document's width (not clamped to fit)",
        abs(flat_bounds.width() - 2 * (bounds.height() / (3 ** 0.5))) < 0.01,
    )

    pointy_bounds = mod._hexagon_path(bounds, flat_top=False).boundingRect()
    check(
        "pointy-top's own sizing is unchanged (still min(width, height) / 2 based)",
        abs(pointy_bounds.height() - min(bounds.width(), bounds.height())) < 0.01,
    )

    # Still a genuinely *regular* hexagon at the new radius -- all six
    # edges the same length, not just "the right height."
    flat_hex = mod._hexagon_path(bounds, flat_top=True)
    points = [flat_hex.elementAt(i) for i in range(flat_hex.elementCount())]
    edge_lengths = [
        ((points[i].x - points[(i + 1) % 6].x) ** 2 + (points[i].y - points[(i + 1) % 6].y) ** 2) ** 0.5
        for i in range(6)
    ]
    check(
        "the resized flat-top hex is still regular (all six edges equal length)",
        max(edge_lengths) - min(edge_lengths) < 0.01,
    )


test_flat_top_hex_top_and_bottom_align_with_the_document_bounds()


# ---------- file_type_registry wiring ----------

from desk.file_type_registry import BUILTIN_EDIT_WIDGET_BY_SUFFIX, find_edit_handler  # noqa: E402

check("BUILTIN_EDIT_WIDGET_BY_SUFFIX maps .svg to svg_editor", BUILTIN_EDIT_WIDGET_BY_SUFFIX.get(".svg") == "svg_editor")
check(
    "find_edit_handler resolves a bare .svg to svg_editor with an empty registry",
    find_edit_handler([], Path("whatever.svg")) == "svg_editor",
)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
