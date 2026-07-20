"""SVG Editor (TODO 7076af5) -- a basic toolbox editor for SVG's
"supported element types" (see design-docs/svg-viewing-and-editing.md):
rect/circle/ellipse/line/polyline/polygon/path/text. A create-tool per
type, plus two editing tools -- Points (drag a path/polyline/polygon's
individual vertices) and Shapes (move/resize a whole object as a unit,
plus a fill/stroke/stroke-width property panel).

Document model: xml.etree.ElementTree is the single source of truth.
Each recognized element becomes a wrapper object (SvgObject subclass)
pairing a QGraphicsItem with the live ET.Element it was parsed from;
anything unrecognized (comments, <defs>, an unsupported <path> -- see
PathObject) is simply never touched, so it round-trips verbatim on save
with no separate bookkeeping needed. See plans/svg-editor-widget.md."""

import logging
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.file_watch import SingleFileWatcher
from desk.shell import current_context

logger = logging.getLogger(__name__)

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

SVG_FILTER = "SVG (*.svg);;All files (*)"

DEFAULT_FILL = "#3daee9"
DEFAULT_STROKE = "#000000"
DEFAULT_STROKE_WIDTH = 1.0

HANDLE_SIZE = 8.0

# TODO 9874bc3: same shape/rationale as widgets/todo/widget.py's own
# FILTER_BUTTON_STYLE -- a plain QPushButton(checkable=True) looks
# nearly identical checked vs. unchecked on some platform styles
# (macOS's native style included), so this makes the toggle state
# unambiguous, and also visually distinguishes these two buttons from
# the plain toolbar buttons (Open/Save/Save As/Reset View) even when
# unchecked. QSS on a native Qt widget, not browser CSS.
HEX_PREVIEW_BUTTON_STYLE = """
QPushButton {
    padding: 3px 10px;
    border: 1px solid #888;
    border-radius: 3px;
    background-color: #3a3d42;
}
QPushButton:checked {
    background-color: #3daee9;
    color: white;
    border-color: #2a8cc4;
}
"""

SINGLE_CLICK_TOOLS = {"rect", "circle", "ellipse", "line", "text"}
MULTI_CLICK_TOOLS = {"polyline", "polygon", "path"}

TOOL_LABELS = [
    ("rect", "Rectangle"),
    ("circle", "Circle"),
    ("ellipse", "Ellipse"),
    ("line", "Line"),
    ("polyline", "Polyline"),
    ("polygon", "Polygon"),
    ("path", "Path"),
    ("text", "Text"),
    ("shapes", "Shapes"),
    ("points", "Points"),
]


def _qn(tag: str) -> str:
    return f"{{{SVG_NS}}}{tag}"


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _fmt(value: float) -> str:
    return f"{round(value, 2):g}"


def _parse_points(text: str) -> list[QPointF]:
    nums = [float(n) for n in re.split(r"[,\s]+", text.strip()) if n]
    return [QPointF(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]


def _format_points(points: list[QPointF]) -> str:
    return " ".join(f"{_fmt(p.x())},{_fmt(p.y())}" for p in points)


_PATH_TOKEN_RE = re.compile(r"([MLZ])([^MLZ]*)")


def _parse_simple_path_d(d: str) -> tuple[list[QPointF], bool] | None:
    """Only M/L/Z with absolute, comma-or-space-separated coordinates --
    anything else (lowercase/relative commands, curves, arcs) returns
    None so the caller leaves the element untouched rather than
    misrepresenting it. See plans/svg-editor-widget.md's "<path> scope"
    section."""
    d = d.strip()
    if not d:
        return None
    letters = {ch for ch in d if ch.isalpha()}
    if not letters or not letters <= {"M", "L", "Z"}:
        return None
    points: list[QPointF] = []
    closed = False
    for cmd, args in _PATH_TOKEN_RE.findall(d):
        if cmd == "Z":
            closed = True
            continue
        nums = [float(n) for n in re.split(r"[,\s]+", args.strip()) if n]
        if len(nums) % 2 != 0:
            return None
        for i in range(0, len(nums), 2):
            points.append(QPointF(nums[i], nums[i + 1]))
    if not points:
        return None
    return points, closed


def _format_simple_path_d(points: list[QPointF], closed: bool) -> str:
    parts = [f"M {_fmt(points[0].x())},{_fmt(points[0].y())}"]
    for p in points[1:]:
        parts.append(f"L {_fmt(p.x())},{_fmt(p.y())}")
    if closed:
        parts.append("Z")
    return " ".join(parts)


def _apply_default_style(item) -> None:
    if hasattr(item, "setBrush"):
        item.setBrush(QBrush(QColor(DEFAULT_FILL)))
    if hasattr(item, "setPen"):
        item.setPen(QPen(QColor(DEFAULT_STROKE), DEFAULT_STROKE_WIDTH))


def _style_from_element(item, element) -> None:
    fill = element.get("fill")
    stroke = element.get("stroke")
    stroke_width = element.get("stroke-width")
    if hasattr(item, "setBrush"):
        if fill == "none":
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        else:
            item.setBrush(QBrush(QColor(fill or DEFAULT_FILL)))
    if hasattr(item, "setPen"):
        width = float(stroke_width) if stroke_width else DEFAULT_STROKE_WIDTH
        item.setPen(QPen(QColor(stroke or DEFAULT_STROKE), width))


def _style_to_element(item, element) -> None:
    if hasattr(item, "brush"):
        brush = item.brush()
        if brush.style() == Qt.BrushStyle.NoBrush:
            element.set("fill", "none")
        else:
            element.set("fill", brush.color().name())
    if hasattr(item, "pen"):
        pen = item.pen()
        element.set("stroke", pen.color().name())
        element.set("stroke-width", _fmt(pen.widthF() or DEFAULT_STROKE_WIDTH))


def _resize_rect_like(item, corner_index: int, scene_pos: QPointF) -> None:
    rect = item.rect()
    top_left = item.mapToScene(rect.topLeft())
    bottom_right = item.mapToScene(rect.bottomRight())
    if corner_index == 0:
        top_left = scene_pos
    elif corner_index == 1:
        top_left = QPointF(top_left.x(), scene_pos.y())
        bottom_right = QPointF(scene_pos.x(), bottom_right.y())
    elif corner_index == 2:
        bottom_right = scene_pos
    elif corner_index == 3:
        top_left = QPointF(scene_pos.x(), top_left.y())
        bottom_right = QPointF(bottom_right.x(), scene_pos.y())
    w = max(4.0, bottom_right.x() - top_left.x())
    h = max(4.0, bottom_right.y() - top_left.y())
    item.setPos(top_left)
    item.setRect(0, 0, w, h)


class _UnsupportedPathData(Exception):
    """Raised by PathObject.from_element for a <path> whose `d` isn't
    the supported M/L/Z-only grammar -- caught by the loader, which
    leaves that element in the tree untouched (see module docstring)."""


class _PolylineItem(QGraphicsPathItem):
    """An open point-sequence (unlike QGraphicsPolygonItem, which always
    closes the shape) -- backs both PolylineObject and an open
    PathObject."""

    def __init__(self, points: list[QPointF]) -> None:
        super().__init__()
        self._points = list(points)
        self._rebuild()

    def _rebuild(self) -> None:
        path = QPainterPath()
        if self._points:
            path.moveTo(self._points[0])
            for p in self._points[1:]:
                path.lineTo(p)
        self.setPath(path)

    def points(self) -> list[QPointF]:
        return list(self._points)

    def set_point(self, index: int, pos: QPointF) -> None:
        self._points[index] = pos
        self._rebuild()


class _Handle(QGraphicsRectItem):
    """A small, purely visual square handle -- dragging is tracked
    centrally by _EditorView (mirrors WorkspaceView's own "hit-test at
    the view level" resize-handle pattern, design-docs/widget-ux.md's
    "Zoom-Correct Dragging" section), not by the handle item itself."""

    def __init__(self) -> None:
        super().__init__(-HANDLE_SIZE / 2, -HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE)
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#000000")))
        self.setZValue(1000)


class SvgObject:
    """Base for one editable SVG object: pairs a QGraphicsItem with the
    live ET.Element it was parsed from / will be serialized into.
    fill/stroke/stroke-width are generic (hasattr-based) since every
    supported Qt item type except QGraphicsLineItem exposes both
    brush() and pen()."""

    tag: str = ""

    def __init__(self, element: ET.Element, item) -> None:
        self.element = element
        self.item = item

    @classmethod
    def create_default(cls, *args):
        raise NotImplementedError

    @classmethod
    def from_element(cls, element: ET.Element) -> "SvgObject":
        raise NotImplementedError

    def sync_to_element(self) -> None:
        raise NotImplementedError

    def point_positions(self) -> list[QPointF]:
        return []

    def move_point(self, index: int, scene_pos: QPointF) -> None:
        pass

    def resize_corner(self, corner_index: int, scene_pos: QPointF) -> None:
        pass

    def fill_color(self) -> QColor:
        if hasattr(self.item, "brush"):
            return self.item.brush().color()
        return QColor(DEFAULT_FILL)

    def stroke_color(self) -> QColor:
        if hasattr(self.item, "pen"):
            return self.item.pen().color()
        return QColor(DEFAULT_STROKE)

    def stroke_width(self) -> float:
        if hasattr(self.item, "pen"):
            return self.item.pen().widthF()
        return DEFAULT_STROKE_WIDTH

    def set_fill(self, color: str) -> None:
        if hasattr(self.item, "setBrush"):
            self.item.setBrush(QBrush(QColor(color)))

    def set_stroke_color(self, color: str) -> None:
        if hasattr(self.item, "setPen"):
            pen = self.item.pen()
            pen.setColor(QColor(color))
            self.item.setPen(pen)

    def set_stroke_width(self, width: float) -> None:
        if hasattr(self.item, "setPen"):
            pen = self.item.pen()
            pen.setWidthF(width)
            self.item.setPen(pen)


class RectObject(SvgObject):
    tag = "rect"

    @classmethod
    def create_default(cls, scene_pos: QPointF) -> "RectObject":
        item = QGraphicsRectItem(0, 0, 80, 60)
        item.setPos(scene_pos.x() - 40, scene_pos.y() - 30)
        _apply_default_style(item)
        obj = cls(ET.Element(_qn("rect")), item)
        obj.sync_to_element()
        return obj

    @classmethod
    def from_element(cls, element: ET.Element) -> "RectObject":
        x = float(element.get("x", 0))
        y = float(element.get("y", 0))
        w = float(element.get("width", 0))
        h = float(element.get("height", 0))
        item = QGraphicsRectItem(0, 0, w, h)
        item.setPos(x, y)
        _style_from_element(item, element)
        return cls(element, item)

    def sync_to_element(self) -> None:
        rect = self.item.rect()
        top_left = self.item.mapToScene(rect.topLeft())
        self.element.set("x", _fmt(top_left.x()))
        self.element.set("y", _fmt(top_left.y()))
        self.element.set("width", _fmt(rect.width()))
        self.element.set("height", _fmt(rect.height()))
        _style_to_element(self.item, self.element)

    def resize_corner(self, corner_index: int, scene_pos: QPointF) -> None:
        _resize_rect_like(self.item, corner_index, scene_pos)


class EllipseObject(SvgObject):
    tag = "ellipse"

    @classmethod
    def create_default(cls, scene_pos: QPointF) -> "EllipseObject":
        item = QGraphicsEllipseItem(0, 0, 80, 50)
        item.setPos(scene_pos.x() - 40, scene_pos.y() - 25)
        _apply_default_style(item)
        obj = cls(ET.Element(_qn("ellipse")), item)
        obj.sync_to_element()
        return obj

    @classmethod
    def from_element(cls, element: ET.Element) -> "EllipseObject":
        cx = float(element.get("cx", 0))
        cy = float(element.get("cy", 0))
        rx = float(element.get("rx", 0))
        ry = float(element.get("ry", 0))
        item = QGraphicsEllipseItem(0, 0, rx * 2, ry * 2)
        item.setPos(cx - rx, cy - ry)
        _style_from_element(item, element)
        return cls(element, item)

    def sync_to_element(self) -> None:
        rect = self.item.rect()
        top_left = self.item.mapToScene(rect.topLeft())
        self.element.set("cx", _fmt(top_left.x() + rect.width() / 2))
        self.element.set("cy", _fmt(top_left.y() + rect.height() / 2))
        self.element.set("rx", _fmt(rect.width() / 2))
        self.element.set("ry", _fmt(rect.height() / 2))
        _style_to_element(self.item, self.element)

    def resize_corner(self, corner_index: int, scene_pos: QPointF) -> None:
        _resize_rect_like(self.item, corner_index, scene_pos)


class CircleObject(SvgObject):
    tag = "circle"

    @classmethod
    def create_default(cls, scene_pos: QPointF) -> "CircleObject":
        item = QGraphicsEllipseItem(0, 0, 60, 60)
        item.setPos(scene_pos.x() - 30, scene_pos.y() - 30)
        _apply_default_style(item)
        obj = cls(ET.Element(_qn("circle")), item)
        obj.sync_to_element()
        return obj

    @classmethod
    def from_element(cls, element: ET.Element) -> "CircleObject":
        cx = float(element.get("cx", 0))
        cy = float(element.get("cy", 0))
        r = float(element.get("r", 0))
        item = QGraphicsEllipseItem(0, 0, r * 2, r * 2)
        item.setPos(cx - r, cy - r)
        _style_from_element(item, element)
        return cls(element, item)

    def sync_to_element(self) -> None:
        rect = self.item.rect()
        top_left = self.item.mapToScene(rect.topLeft())
        r = rect.width() / 2
        self.element.set("cx", _fmt(top_left.x() + r))
        self.element.set("cy", _fmt(top_left.y() + r))
        self.element.set("r", _fmt(r))
        _style_to_element(self.item, self.element)

    def resize_corner(self, corner_index: int, scene_pos: QPointF) -> None:
        # Constrains rx==ry so a Circle stays a true circle -- switch it
        # to an Ellipse object first if independent axes are wanted.
        _resize_rect_like(self.item, corner_index, scene_pos)
        rect = self.item.rect()
        side = max(rect.width(), rect.height())
        self.item.setRect(0, 0, side, side)


class LineObject(SvgObject):
    tag = "line"

    @classmethod
    def create_default(cls, scene_pos: QPointF) -> "LineObject":
        item = QGraphicsLineItem(-40, 0, 40, 0)
        item.setPos(scene_pos)
        _apply_default_style(item)
        obj = cls(ET.Element(_qn("line")), item)
        obj.sync_to_element()
        return obj

    @classmethod
    def from_element(cls, element: ET.Element) -> "LineObject":
        x1 = float(element.get("x1", 0))
        y1 = float(element.get("y1", 0))
        x2 = float(element.get("x2", 0))
        y2 = float(element.get("y2", 0))
        item = QGraphicsLineItem(0, 0, x2 - x1, y2 - y1)
        item.setPos(x1, y1)
        _style_from_element(item, element)
        return cls(element, item)

    def sync_to_element(self) -> None:
        line = self.item.line()
        p1 = self.item.mapToScene(line.p1())
        p2 = self.item.mapToScene(line.p2())
        self.element.set("x1", _fmt(p1.x()))
        self.element.set("y1", _fmt(p1.y()))
        self.element.set("x2", _fmt(p2.x()))
        self.element.set("y2", _fmt(p2.y()))
        _style_to_element(self.item, self.element)

    def point_positions(self) -> list[QPointF]:
        line = self.item.line()
        return [self.item.mapToScene(line.p1()), self.item.mapToScene(line.p2())]

    def move_point(self, index: int, scene_pos: QPointF) -> None:
        local = self.item.mapFromScene(scene_pos)
        line = self.item.line()
        p1, p2 = line.p1(), line.p2()
        if index == 0:
            p1 = local
        else:
            p2 = local
        self.item.setLine(p1.x(), p1.y(), p2.x(), p2.y())

    def resize_corner(self, corner_index: int, scene_pos: QPointF) -> None:
        # The Shapes tool's 4 bounding-box corners collapse to this
        # line's 2 endpoints -- same handles Points would show for it.
        self.move_point(0 if corner_index in (0, 3) else 1, scene_pos)


class PolylineObject(SvgObject):
    tag = "polyline"

    @classmethod
    def create_default(cls, points: list[QPointF]) -> "PolylineObject":
        item = _PolylineItem(points)
        _apply_default_style(item)
        obj = cls(ET.Element(_qn("polyline")), item)
        obj.sync_to_element()
        return obj

    @classmethod
    def from_element(cls, element: ET.Element) -> "PolylineObject":
        item = _PolylineItem(_parse_points(element.get("points", "")))
        _style_from_element(item, element)
        return cls(element, item)

    def sync_to_element(self) -> None:
        pts = [self.item.mapToScene(p) for p in self.item.points()]
        self.element.set("points", _format_points(pts))
        _style_to_element(self.item, self.element)

    def point_positions(self) -> list[QPointF]:
        return [self.item.mapToScene(p) for p in self.item.points()]

    def move_point(self, index: int, scene_pos: QPointF) -> None:
        self.item.set_point(index, self.item.mapFromScene(scene_pos))


class PolygonObject(SvgObject):
    tag = "polygon"

    @classmethod
    def create_default(cls, points: list[QPointF]) -> "PolygonObject":
        item = QGraphicsPolygonItem(QPolygonF(points))
        _apply_default_style(item)
        obj = cls(ET.Element(_qn("polygon")), item)
        obj.sync_to_element()
        return obj

    @classmethod
    def from_element(cls, element: ET.Element) -> "PolygonObject":
        item = QGraphicsPolygonItem(QPolygonF(_parse_points(element.get("points", ""))))
        _style_from_element(item, element)
        return cls(element, item)

    def sync_to_element(self) -> None:
        pts = [self.item.mapToScene(p) for p in self.item.polygon()]
        self.element.set("points", _format_points(pts))
        _style_to_element(self.item, self.element)

    def point_positions(self) -> list[QPointF]:
        return [self.item.mapToScene(p) for p in self.item.polygon()]

    def move_point(self, index: int, scene_pos: QPointF) -> None:
        poly = QPolygonF(self.item.polygon())
        poly[index] = self.item.mapFromScene(scene_pos)
        self.item.setPolygon(poly)


class PathObject(SvgObject):
    """First pass: only straight-line path data (M/L/Z) -- see
    _parse_simple_path_d and plans/svg-editor-widget.md's "<path>
    scope" section."""

    tag = "path"

    def __init__(self, element: ET.Element, item, closed: bool) -> None:
        super().__init__(element, item)
        self._closed = closed

    @classmethod
    def create_default(cls, points: list[QPointF]) -> "PathObject":
        item = QGraphicsPolygonItem(QPolygonF(points))
        _apply_default_style(item)
        obj = cls(ET.Element(_qn("path")), item, closed=True)
        obj.sync_to_element()
        return obj

    @classmethod
    def from_element(cls, element: ET.Element) -> "PathObject":
        parsed = _parse_simple_path_d(element.get("d", ""))
        if parsed is None:
            raise _UnsupportedPathData
        points, closed = parsed
        item = QGraphicsPolygonItem(QPolygonF(points)) if closed else _PolylineItem(points)
        _style_from_element(item, element)
        return cls(element, item, closed)

    def _local_points(self) -> list[QPointF]:
        if isinstance(self.item, QGraphicsPolygonItem):
            return list(self.item.polygon())
        return self.item.points()

    def sync_to_element(self) -> None:
        pts = [self.item.mapToScene(p) for p in self._local_points()]
        self.element.set("d", _format_simple_path_d(pts, self._closed))
        _style_to_element(self.item, self.element)

    def point_positions(self) -> list[QPointF]:
        return [self.item.mapToScene(p) for p in self._local_points()]

    def move_point(self, index: int, scene_pos: QPointF) -> None:
        local = self.item.mapFromScene(scene_pos)
        if isinstance(self.item, QGraphicsPolygonItem):
            poly = QPolygonF(self.item.polygon())
            poly[index] = local
            self.item.setPolygon(poly)
        else:
            self.item.set_point(index, local)


class TextObject(SvgObject):
    tag = "text"

    @classmethod
    def create_default(cls, scene_pos: QPointF) -> "TextObject":
        text, ok = QInputDialog.getText(None, "Text", "Content:")
        if not ok or not text:
            text = "Text"
        item = QGraphicsSimpleTextItem(text)
        item.setPos(scene_pos)
        item.setBrush(QBrush(QColor(DEFAULT_FILL)))
        font = item.font()
        font.setPointSize(16)
        item.setFont(font)
        obj = cls(ET.Element(_qn("text")), item)
        obj.sync_to_element()
        return obj

    @classmethod
    def from_element(cls, element: ET.Element) -> "TextObject":
        x = float(element.get("x", 0))
        y = float(element.get("y", 0))
        size = float(element.get("font-size", 16))
        item = QGraphicsSimpleTextItem(element.text or "")
        item.setPos(x, y - size)
        font = item.font()
        font.setPointSize(max(1, int(size)))
        item.setFont(font)
        fill = element.get("fill")
        item.setBrush(QBrush(QColor(fill if fill and fill != "none" else DEFAULT_FILL)))
        return cls(element, item)

    def sync_to_element(self) -> None:
        pos = self.item.pos()
        size = self.item.font().pointSize()
        self.element.set("x", _fmt(pos.x()))
        self.element.set("y", _fmt(pos.y() + size))
        self.element.set("font-size", _fmt(size))
        self.element.set("fill", self.item.brush().color().name())
        self.element.text = self.item.text()

    def resize_corner(self, corner_index: int, scene_pos: QPointF) -> None:
        rect = self.item.sceneBoundingRect()
        old_h = max(1.0, rect.height())
        new_h = (rect.bottom() - scene_pos.y()) if corner_index in (0, 1) else (scene_pos.y() - rect.top())
        new_h = max(6.0, new_h)
        font = self.item.font()
        font.setPointSize(max(4, int(font.pointSize() * (new_h / old_h))))
        self.item.setFont(font)


TAG_TO_CLASS = {
    "rect": RectObject,
    "circle": CircleObject,
    "ellipse": EllipseObject,
    "line": LineObject,
    "polyline": PolylineObject,
    "polygon": PolygonObject,
    "path": PathObject,
    "text": TextObject,
}


def _new_empty_root() -> ET.Element:
    root = ET.Element(_qn("svg"))
    root.set("viewBox", "0 0 400 300")
    root.set("width", "400")
    root.set("height", "300")
    return root


_DEFAULT_BOUNDS = QRectF(0, 0, 400, 300)
_UNIT_SUFFIX_RE = re.compile(r"[a-zA-Z%]+$")


def _document_bounds(root: ET.Element) -> QRectF:
    """The document's real, exportable bounds -- what any real SVG
    consumer (a browser, an `<img>`/`<image>` tag) clips to, unlike
    this editor itself, which never clips while editing (TODO
    `d1d176f` -- see FEEDBACK-DESK-svg-editor-viewbox-guide
    -2026-07-16-1156.md). `viewBox` (`min-x min-y width height`) is the
    primary, authoritative source; falls back to a `0,0,width,height`
    rect from the `width`/`height` attributes (stripping a trailing
    unit suffix, e.g. `"400px"`) if `viewBox` is absent/unparseable --
    a hand-authored or externally-produced `.svg` opened via
    `_load_file` isn't guaranteed to have a clean, unitless `viewBox`.
    Falls back to `_new_empty_root`'s own default size if neither
    attribute is usable at all."""
    view_box = root.get("viewBox")
    if view_box:
        parts = view_box.split()
        if len(parts) == 4:
            try:
                min_x, min_y, width, height = (float(p) for p in parts)
                return QRectF(min_x, min_y, width, height)
            except ValueError:
                pass
    width_attr = root.get("width")
    height_attr = root.get("height")
    if width_attr and height_attr:
        try:
            width = float(_UNIT_SUFFIX_RE.sub("", width_attr))
            height = float(_UNIT_SUFFIX_RE.sub("", height_attr))
            return QRectF(0, 0, width, height)
        except ValueError:
            pass
    return QRectF(_DEFAULT_BOUNDS)


def _hexagon_path(bounds: QRectF, flat_top: bool) -> QPainterPath:
    """A regular hexagon centered in `bounds` -- the shape a hex-tile
    consumer (e.g. `necro-4x`'s terrain art pipeline) actually clips
    artwork to via an SVG `<clipPath>`. `flat_top`: a flat edge (not a
    vertex) at the top/bottom -- vertices at 0/60/120/180/240/300
    degrees, vs. pointy-top's -90/-30/30/90/150/210 (a vertex straight
    up/down, the `-90` angle offset).

    Sizing (TODO `9874bc3`) differs by orientation. Pointy-top:
    `min(width, height) / 2` -- the largest that fits without touching
    the shorter edge, unchanged from before this TODO. Flat-top:
    `bounds.height() / sqrt(3)` -- for a regular hexagon with
    circumradius R, the flat-to-flat distance (here, top-to-bottom,
    since the flat edges are on top/bottom in this orientation) is `R *
    sqrt(3)`; solving for R so that distance exactly equals
    `bounds.height()` lands the hex's own top/bottom edges exactly on
    the document bounds. This can legitimately make the hex *wider*
    than the document (vertex-to-vertex width is `2R`, independent of
    `bounds.width()`) -- accepted deliberately: real flat-top hex-tile
    art conventionally spans the tile's full height and overlaps
    horizontally in an actual tessellated grid, which is exactly what
    this preview is trying to show."""
    cx, cy = bounds.center().x(), bounds.center().y()
    if flat_top:
        radius = bounds.height() / math.sqrt(3)
    else:
        radius = min(bounds.width(), bounds.height()) / 2
    angle_offset = 0 if flat_top else -90
    polygon = QPolygonF()
    for i in range(6):
        angle = math.radians(60 * i + angle_offset)
        polygon.append(QPointF(cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    path = QPainterPath()
    path.addPolygon(polygon)
    path.closeSubpath()
    return path


class _EditorView(QGraphicsView):
    """Hit-tests handles/create-tool clicks at the view level -- same
    "centralize drag tracking in the view, keep the item itself purely
    visual" shape WorkspaceView's own resize handles already use (see
    design-docs/widget-ux.md's "Zoom-Correct Dragging"). Falls through
    to Qt's own default QGraphicsView select/move handling for a plain
    click with no create-tool armed and no handle hit -- items already
    carry ItemIsSelectable/ItemIsMovable, so no extra code is needed for
    that path."""

    def __init__(self, editor: "SvgEditorWidget", scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self._editor = editor
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.pos())
            hit = self._editor._hit_test_handle(pos)
            if hit is not None:
                self._editor._begin_handle_drag(hit[1])
                return
            tool = self._editor.current_tool
            if tool in SINGLE_CLICK_TOOLS:
                self._editor._create_single_click_object(tool, pos)
                return
            if tool in MULTI_CLICK_TOOLS:
                self._editor._add_pending_point(pos)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._editor.is_dragging_handle():
            self._editor._update_handle_drag(self.mapToScene(event.pos()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._editor.is_dragging_handle():
            self._editor._end_handle_drag()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self._editor.current_tool in MULTI_CLICK_TOOLS and self._editor.has_pending_points():
            self._editor._finish_pending()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._editor.has_pending_points():
            self._editor._finish_pending()
            return
        super().keyPressEvent(event)


class SvgEditorWidget(QWidget):
    """Toolbox SVG editor -- see the module docstring and
    plans/svg-editor-widget.md."""

    external_path_changed = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_path: Path | None = None
        self._last_dir = current_context.get_current_desk_directory() or Path.home()
        self._root = _new_empty_root()
        self._objects: list[SvgObject] = []
        self._selected_object: SvgObject | None = None
        self._handles: list[tuple[_Handle, int]] = []
        self._dragging_handle_index: int | None = None
        self._pending_points: list[QPointF] | None = None
        self._pending_preview_items: list = []
        self.current_tool = "shapes"
        # TODO d1d176f: purely visual, never touch self._root/self._objects
        # (see _document_bounds/_refresh_document_guides) -- excluded from
        # the saved file automatically, the same way _Handle already is,
        # since _save_to_path only ever serializes self._objects.
        self._bounds_guide_item = None
        self._hex_preview_item = None
        # TODO 1c7d5b9: "flat", "pointy", or None (off) -- flat-top and
        # pointy-top are mutually exclusive, but neither selected is
        # also a valid state, so this isn't a plain bool anymore.
        self._hex_preview_orientation = None

        self._scene = QGraphicsScene(self)
        self._scene.selectionChanged.connect(self._on_selection_changed)
        self._view = _EditorView(self, self._scene)

        self._label = QLabel()
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        open_button = QPushButton("Open")
        open_button.clicked.connect(self._open_file)
        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)
        save_as_button = QPushButton("Save As")
        save_as_button.clicked.connect(self._save_as)
        reset_view_button = QPushButton("Reset View")
        reset_view_button.clicked.connect(self._reset_view)
        # TODO 1c7d5b9: two independent checkable buttons, not a
        # QButtonGroup(exclusive=True) -- that enforces "at most one
        # checked," but whether it lets the user manually uncheck the
        # currently-checked one (clicking it again) isn't something to
        # lean on without verifying; explicit mutual exclusion via
        # _set_hex_preview_orientation is simpler to reason about and
        # test, and makes "neither" unambiguously reachable.
        self._hex_preview_flat_button = QPushButton("Hex (Flat-top) Preview")
        self._hex_preview_flat_button.setCheckable(True)
        self._hex_preview_flat_button.setStyleSheet(HEX_PREVIEW_BUTTON_STYLE)
        self._hex_preview_flat_button.clicked.connect(
            lambda checked: self._set_hex_preview_orientation("flat" if checked else None)
        )
        self._hex_preview_pointy_button = QPushButton("Hex (Pointy-top) Preview")
        self._hex_preview_pointy_button.setCheckable(True)
        self._hex_preview_pointy_button.setStyleSheet(HEX_PREVIEW_BUTTON_STYLE)
        self._hex_preview_pointy_button.clicked.connect(
            lambda checked: self._set_hex_preview_orientation("pointy" if checked else None)
        )
        # TODO 9874bc3: framed and spaced apart from the plain toolbar
        # buttons -- same shape as widgets/todo/widget.py's own
        # filter_frame (a QFrame(StyledPanel) grouping its own set of
        # related checkable buttons).
        hex_preview_frame = QFrame()
        hex_preview_frame.setFrameShape(QFrame.Shape.StyledPanel)
        hex_preview_layout = QHBoxLayout(hex_preview_frame)
        hex_preview_layout.setContentsMargins(4, 4, 4, 4)
        hex_preview_layout.setSpacing(4)
        hex_preview_layout.addWidget(self._hex_preview_flat_button)
        hex_preview_layout.addWidget(self._hex_preview_pointy_button)

        top_toolbar = QHBoxLayout()
        top_toolbar.addWidget(open_button)
        top_toolbar.addWidget(save_button)
        top_toolbar.addWidget(save_as_button)
        top_toolbar.addWidget(reset_view_button)
        top_toolbar.addSpacing(12)
        top_toolbar.addWidget(hex_preview_frame)
        top_toolbar.addStretch()
        top_toolbar.addWidget(self._label)

        self._toolbox = self._build_toolbox()
        self._property_panel = self._build_property_panel()

        middle = QHBoxLayout()
        middle.addWidget(self._toolbox)
        middle.addWidget(self._view, stretch=1)
        middle.addWidget(self._property_panel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top_toolbar)
        layout.addLayout(middle, stretch=1)

        self._watcher = SingleFileWatcher(self)
        self._watcher.changed.connect(self._on_external_change)
        watcher = self._watcher
        self.destroyed.connect(lambda: watcher.stop())

        self._refresh_document_guides()
        # fitInView needs the view's real viewport size, not yet available
        # here (before this widget has actually been laid out/shown) --
        # deferred to the next event-loop iteration, a well-known Qt
        # gotcha, not specific to this codebase.
        QTimer.singleShot(0, self._reset_view)

        self._update_label()

    # --- toolbox / property panel construction -------------------------

    def _build_toolbox(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        group = QButtonGroup(panel)
        group.setExclusive(True)
        for tool_id, label in TOOL_LABELS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda checked, t=tool_id: self._set_tool(t))
            group.addButton(button)
            layout.addWidget(button)
            if tool_id == "shapes":
                button.setChecked(True)
        layout.addStretch()
        self._tool_group = group
        return panel

    def _build_property_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self._fill_button = QPushButton("Fill")
        self._fill_button.clicked.connect(self._pick_fill)
        self._stroke_button = QPushButton("Stroke")
        self._stroke_button.clicked.connect(self._pick_stroke)
        self._stroke_width_spin = QDoubleSpinBox()
        self._stroke_width_spin.setRange(0.0, 50.0)
        self._stroke_width_spin.setSingleStep(0.5)
        self._stroke_width_spin.valueChanged.connect(self._on_stroke_width_changed)
        layout.addWidget(QLabel("Style"))
        layout.addWidget(self._fill_button)
        layout.addWidget(self._stroke_button)
        layout.addWidget(QLabel("Stroke width"))
        layout.addWidget(self._stroke_width_spin)
        layout.addStretch()
        panel.setEnabled(False)
        return panel

    # --- tool state ------------------------------------------------------

    def _set_tool(self, tool_id: str) -> None:
        self._cancel_pending()
        self.current_tool = tool_id
        self._refresh_handles()

    def is_dragging_handle(self) -> bool:
        return self._dragging_handle_index is not None

    def has_pending_points(self) -> bool:
        return bool(self._pending_points)

    # --- handles ---------------------------------------------------------

    def _hit_test_handle(self, scene_pos: QPointF):
        for handle, index in self._handles:
            if handle.sceneBoundingRect().contains(scene_pos):
                return (handle, index)
        return None

    def _refresh_handles(self) -> None:
        for handle, _ in self._handles:
            self._scene.removeItem(handle)
        self._handles = []
        if self._selected_object is None:
            return
        if self.current_tool == "shapes":
            rect = self._selected_object.item.sceneBoundingRect()
            corners = [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]
            for index, point in enumerate(corners):
                self._add_handle(point, index)
        elif self.current_tool == "points":
            for index, point in enumerate(self._selected_object.point_positions()):
                self._add_handle(point, index)

    def _add_handle(self, scene_pos: QPointF, index: int) -> None:
        handle = _Handle()
        handle.setPos(scene_pos)
        self._scene.addItem(handle)
        self._handles.append((handle, index))

    def _begin_handle_drag(self, index: int) -> None:
        self._dragging_handle_index = index

    def _update_handle_drag(self, scene_pos: QPointF) -> None:
        if self._selected_object is None or self._dragging_handle_index is None:
            return
        if self.current_tool == "shapes":
            self._selected_object.resize_corner(self._dragging_handle_index, scene_pos)
        elif self.current_tool == "points":
            self._selected_object.move_point(self._dragging_handle_index, scene_pos)
        self._refresh_handles()

    def _end_handle_drag(self) -> None:
        self._dragging_handle_index = None

    # --- selection / property panel --------------------------------------

    def _on_selection_changed(self) -> None:
        # Wrapped defensively (TODO 810a5d6): a Qt-signal-invoked slot
        # chain where an uncaught exception is fatal to the whole
        # process in this PyQt6 setup -- can fire once more during
        # widget teardown after self._scene's C++ object is already
        # gone (RuntimeError), same class of issue documented in
        # LEARNINGS.md for other Qt-signal-invoked slots here.
        try:
            selected = self._scene.selectedItems()
        except RuntimeError:
            return
        self._selected_object = self._object_for_item(selected[0]) if len(selected) == 1 else None
        self._refresh_handles()
        self._refresh_property_panel()

    def _object_for_item(self, item) -> SvgObject | None:
        for obj in self._objects:
            if obj.item is item:
                return obj
        return None

    def _refresh_property_panel(self) -> None:
        obj = self._selected_object
        self._property_panel.setEnabled(obj is not None)
        if obj is None:
            return
        self._fill_button.setStyleSheet(f"background-color: {obj.fill_color().name()};")
        self._stroke_button.setStyleSheet(f"background-color: {obj.stroke_color().name()};")
        self._stroke_width_spin.blockSignals(True)
        self._stroke_width_spin.setValue(obj.stroke_width())
        self._stroke_width_spin.blockSignals(False)

    def _pick_fill(self) -> None:
        if self._selected_object is None:
            return
        color = QColorDialog.getColor(self._selected_object.fill_color(), self)
        if color.isValid():
            self._selected_object.set_fill(color.name())
            self._refresh_property_panel()

    def _pick_stroke(self) -> None:
        if self._selected_object is None:
            return
        color = QColorDialog.getColor(self._selected_object.stroke_color(), self)
        if color.isValid():
            self._selected_object.set_stroke_color(color.name())
            self._refresh_property_panel()

    def _on_stroke_width_changed(self, value: float) -> None:
        if self._selected_object is not None:
            self._selected_object.set_stroke_width(value)

    # --- creating objects --------------------------------------------------

    def _create_single_click_object(self, tool: str, pos: QPointF) -> None:
        obj = TAG_TO_CLASS[tool].create_default(pos)
        self._add_object(obj)

    def _add_pending_point(self, pos: QPointF) -> None:
        if self._pending_points is None:
            self._pending_points = []
        self._pending_points.append(pos)
        self._refresh_pending_preview()

    def _clear_preview_items(self) -> None:
        for item in self._pending_preview_items:
            self._scene.removeItem(item)
        self._pending_preview_items = []

    def _refresh_pending_preview(self) -> None:
        self._clear_preview_items()
        points = self._pending_points or []
        pen = QPen(QColor(DEFAULT_FILL))
        brush = QBrush(QColor(DEFAULT_FILL))
        for p in points:
            dot = self._scene.addEllipse(p.x() - 3, p.y() - 3, 6, 6, pen, brush)
            self._pending_preview_items.append(dot)
        for a, b in zip(points, points[1:]):
            line = self._scene.addLine(a.x(), a.y(), b.x(), b.y(), pen)
            self._pending_preview_items.append(line)

    def _cancel_pending(self) -> None:
        self._clear_preview_items()
        self._pending_points = None

    def _finish_pending(self) -> None:
        points = self._pending_points
        tool = self.current_tool
        self._clear_preview_items()
        self._pending_points = None
        if points is None or len(points) < 2:
            return
        obj = TAG_TO_CLASS[tool].create_default(points)
        self._add_object(obj)

    def _add_object(self, obj: SvgObject) -> None:
        obj.item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        obj.item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self._scene.addItem(obj.item)
        self._root.append(obj.element)
        self._objects.append(obj)
        self._scene.clearSelection()
        obj.item.setSelected(True)

    # --- file I/O ----------------------------------------------------------

    def _update_label(self) -> None:
        if self._current_path is None:
            self._label.setText("(no file — Open or Save As to choose one)")
        else:
            self._label.setText(self._current_path.name)

    def _open_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Open SVG File", str(self._last_dir), SVG_FILTER)
        if filename:
            self._load_file(Path(filename))

    def set_file(self, path: Path) -> None:
        """Public so other widgets/services can open a file here
        programmatically (TODO 7076af5 registers this widget as the
        built-in `.svg` edit handler, so Image Viewer's Edit button
        reaches this via current_context.get_editor_or_scrap_opener)."""
        self._load_file(path)

    def _load_file(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError as error:
            self._label.setText(f"Could not read `{path.name}`: {error}.")
            return
        try:
            root = ET.fromstring(data)
        except ET.ParseError as error:
            self._label.setText(f"`{path.name}` is not valid XML: {error}.")
            return
        self._root = root
        self._current_path = path
        self._last_dir = path.parent
        self._rebuild_scene_from_root()
        self._watcher.watch(path)
        self.refresh_external_path_status()
        self._update_label()
        self._reset_view()

    def _rebuild_scene_from_root(self) -> None:
        # _scene.clear() deletes every scene item, including the guide/
        # hex-preview items (TODO d1d176f) -- clear these references too
        # (same reason _handles is reset alongside it) so
        # _refresh_document_guides() below doesn't try to remove an
        # already-deleted item.
        self._scene.clear()
        self._objects = []
        self._selected_object = None
        self._handles = []
        self._pending_points = None
        self._pending_preview_items = []
        self._bounds_guide_item = None
        self._hex_preview_item = None
        for element in list(self._root):
            cls = TAG_TO_CLASS.get(_local_tag(element.tag))
            if cls is None:
                continue
            try:
                obj = cls.from_element(element)
            except _UnsupportedPathData:
                continue
            obj.item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            obj.item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            self._scene.addItem(obj.item)
            self._objects.append(obj)
        self._refresh_document_guides()

    # --- document bounds guide / hex preview mask (TODO d1d176f) --------

    def _refresh_document_guides(self) -> None:
        """(Re-)builds the document-bounds guide rect, the scene's own
        bounded rect, and (if enabled) the hex preview mask -- called
        whenever bounds might have changed: __init__, and after
        _rebuild_scene_from_root's _scene.clear() (nothing here
        survives a scene clear)."""
        bounds = _document_bounds(self._root)
        self._refresh_bounds_guide(bounds)
        # Generous, not exact -- drawing slightly outside the canvas
        # mid-edit, before trimming, is reasonable (see the feedback
        # this TODO comes from); just no longer effectively unbounded.
        # Proportional to the document's own size so a small document
        # gets a modest margin and a much larger one gets a
        # proportionally larger one.
        margin = max(bounds.width(), bounds.height())
        self._scene.setSceneRect(bounds.adjusted(-margin, -margin, margin, margin))
        self._refresh_hex_preview(bounds)

    def _refresh_bounds_guide(self, bounds: QRectF) -> None:
        if self._bounds_guide_item is not None:
            self._scene.removeItem(self._bounds_guide_item)
            self._bounds_guide_item = None
        pen = QPen(QColor(DEFAULT_FILL))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidthF(1.5)
        item = QGraphicsRectItem(bounds)
        item.setPen(pen)
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setZValue(-1000)  # always behind real content
        # Click-through: Qt's own mechanism for "receive/paint this item,
        # but never intercept mouse events meant for whatever's beneath
        # it" -- editing must work identically with the guide present.
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._scene.addItem(item)
        self._bounds_guide_item = item

    def _set_hex_preview_orientation(self, orientation: str | None) -> None:
        self._hex_preview_orientation = orientation
        # .setChecked() doesn't re-emit clicked (only toggled, which
        # nothing here is connected to), so syncing both buttons this
        # way can't cause a feedback loop back into this method.
        self._hex_preview_flat_button.setChecked(orientation == "flat")
        self._hex_preview_pointy_button.setChecked(orientation == "pointy")
        self._refresh_hex_preview()

    def _refresh_hex_preview(self, bounds: QRectF | None = None) -> None:
        if self._hex_preview_item is not None:
            self._scene.removeItem(self._hex_preview_item)
            self._hex_preview_item = None
        if self._hex_preview_orientation is None:
            return
        if bounds is None:
            bounds = _document_bounds(self._root)
        full_rect_path = QPainterPath()
        full_rect_path.addRect(bounds)
        hex_path = _hexagon_path(bounds, flat_top=(self._hex_preview_orientation == "flat"))
        path = full_rect_path.subtracted(hex_path)
        item = QGraphicsPathItem(path)
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setBrush(QBrush(QColor(0, 0, 0, 140)))
        item.setZValue(2000)  # always on top, including over handles
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._scene.addItem(item)
        self._hex_preview_item = item

    def _reset_view(self) -> None:
        self._view.fitInView(_document_bounds(self._root), Qt.AspectRatioMode.KeepAspectRatio)

    def _on_external_change(self) -> None:
        if self._current_path is not None:
            self._load_file(self._current_path)

    def _save(self) -> bool:
        if self._current_path is None:
            return self._save_as()
        return self._save_to_path(self._current_path)

    def _save_as(self) -> bool:
        filename, _ = QFileDialog.getSaveFileName(self, "Save As", str(self._last_dir), SVG_FILTER)
        if not filename:
            return False
        path = Path(filename)
        if not self._save_to_path(path):
            return False
        self._current_path = path
        self._last_dir = path.parent
        self._watcher.watch(path)
        self._update_label()
        return True

    def _save_to_path(self, path: Path) -> bool:
        for obj in self._objects:
            obj.sync_to_element()
        data = ET.tostring(self._root, encoding="utf-8", xml_declaration=True)
        try:
            path.write_bytes(data)
        except OSError as error:
            opener = current_context.get_popup_opener()
            if opener is not None:
                opener("Save", f"Could not save: {error}", ["OK"], "OK")
            return False
        self._watcher.record_own_write(data.decode("utf-8"))
        return True

    def refresh_external_path_status(self) -> None:
        """See TODO a053e3a / TODO 810a5d6 -- same pattern as every
        other file-backed widget here (e.g. widgets/image_viewer)."""
        try:
            is_external = self._current_path is not None and current_context.path_is_external(
                self._current_path
            )
        except Exception:
            logger.error("Failed to compute external-path status for %s", self._current_path, exc_info=True)
            return
        self.external_path_changed.emit(is_external)


def build() -> QWidget:
    return SvgEditorWidget()
