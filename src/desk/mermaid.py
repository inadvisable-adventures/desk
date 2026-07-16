"""Bespoke, intentionally partial Mermaid diagram support.

Rather than vendoring `mermaid.js` (and the QtWebEngine round-trip that
would require), this hand-rolls a parser for a subset of Mermaid syntax,
a simplified layered auto-layout, and a native `QGraphicsScene`
renderer. Per `CLAUDE.md`'s "avoid adding dependencies, prefer bespoke
solutions" plus direct user direction (see `plans/markdown-ex-widget
.md`), this only supports:

- **Flowchart** (`flowchart`/`graph`): basic node shapes only -- rect
  `[Label]`, rounded `(Label)`, diamond `{Label}`, circle `((Label))`
  -- no extended shapes (stadium, subroutine, cylinder, hexagon, ...).
  Edge styles `-->`, `---`, `-.->`, `-.-`, with an optional `|label|`.
- **State diagram** (`stateDiagram`/`stateDiagram-v2`): flat only --
  `[*]` start/end pseudostates, `A --> B` / `A --> B : label`
  transitions, `A : label` descriptions. Composite/nested `state X {
  ... }` blocks are skipped (not an error), not rendered.

Any other diagram type (sequence, class, ER, gantt, pie, ...), or
source that doesn't match the supported grammar, raises
`MermaidParseError` -- callers should catch this and fall back to
showing the raw source as plain text rather than erroring or silently
producing a wrong diagram.

Layout is a simplified layered (Sugiyama-style) algorithm: longest-path
rank assignment (cycle-safe, but not crossing-minimized) plus
first-seen ordering within a rank -- no barycenter crossing
minimization, no orthogonal/curved edge routing. Good enough to be
readable, not a faithful reproduction of Mermaid's own layout engine.

`parse`/`layout`/`build_scene`/`render_svg` are consumed by the
`mermaid_flowchart_svg`/`mermaid_state_svg` transforms
(`desk_transforms/`, TODO `05cfccc`) -- see design-docs/transforms.md.
This module used to also host `MermaidDiagramWidget`, a `QGraphicsView`
subclass embedding a live, interactive scene directly into the Markdown
widget; retired by TODO `a9e2ba7` once the Markdown widget switched to
rendering a diagram via the transform + a shared, static `desk.svg_view
.SvgView` instead.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable

from PyQt6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPolygonF,
)
from PyQt6.QtSvg import QSvgGenerator
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)


class MermaidParseError(Exception):
    """Raised for a Mermaid diagram type/syntax this module doesn't
    support. Callers should catch this and fall back to plain text."""


# --------------------------------------------------------------------
# Diagram model
# --------------------------------------------------------------------


@dataclass
class Node:
    id: str
    label: str
    shape: str  # "rect" | "rounded" | "diamond" | "circle" | "start" | "end"


@dataclass
class Edge:
    source: str
    target: str
    label: str | None = None
    arrow: bool = True
    dotted: bool = False


@dataclass
class Diagram:
    kind: str  # "flowchart" | "state"
    direction: str  # "TD" | "TB" | "LR" | "BT" | "RL"
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


# --------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------

_FLOWCHART_HEADER = re.compile(r"^(flowchart|graph)\s+(TD|TB|LR|BT|RL)\s*$", re.IGNORECASE)
_FLOWCHART_HEADER_NO_DIR = re.compile(r"^(flowchart|graph)\s*$", re.IGNORECASE)
_STATE_HEADER = re.compile(r"^stateDiagram(-v2)?\s*$", re.IGNORECASE)

_SKIP_FLOWCHART_PREFIXES = ("subgraph", "classdef", "class ", "style ", "click ", "linkstyle")

_EDGE_RE = re.compile(r"(?P<op>-\.->|-\.-|-->|---)(?:\s*\|(?P<label>[^|]*)\|)?")

_NODE_RE = re.compile(
    r"^(?P<id>[A-Za-z0-9_]+)\s*"
    r"(?:"
    r"\(\((?P<circle>[^()]*)\)\)"
    r"|\[(?P<rect>[^\[\]]*)\]"
    r"|\((?P<rounded>[^()]*)\)"
    r"|\{(?P<diamond>[^{}]*)\}"
    r")?$"
)

_STATE_TRANSITION_RE = re.compile(
    r"^(?P<src>\[\*\]|[A-Za-z0-9_]+)\s*-->\s*(?P<dst>\[\*\]|[A-Za-z0-9_]+)"
    r"\s*(?::\s*(?P<label>.*))?$"
)
_STATE_DESC_RE = re.compile(r"^(?P<id>[A-Za-z0-9_]+)\s*:\s*(?P<label>.*)$")
_STATE_COMPOSITE_OPEN_RE = re.compile(r"^state\s+.*\{\s*$", re.IGNORECASE)


def detect_diagram_kind(text: str) -> str | None:
    """The diagram kind `parse(text)` would dispatch to (`"flowchart"`
    | `"state"`), without doing the full parse -- `None` for anything
    else (an unrecognized header, or empty content). Lets a caller
    (the Markdown widget, TODO `a9e2ba7`) decide which transform to
    invoke -- or skip straight to a plain-text fallback for a diagram
    type with no transform (yet) -- without duplicating this module's
    own header-detection regexes."""
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("%%")]
    if not lines:
        return None
    header = lines[0]
    if _FLOWCHART_HEADER.match(header) or _FLOWCHART_HEADER_NO_DIR.match(header):
        return "flowchart"
    if _STATE_HEADER.match(header):
        return "state"
    return None


def parse(text: str) -> Diagram:
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("%%")]
    if not lines:
        raise MermaidParseError("empty diagram")

    header = lines[0]
    match = _FLOWCHART_HEADER.match(header)
    if match:
        return _parse_flowchart(lines[1:], match.group(2).upper())
    if _FLOWCHART_HEADER_NO_DIR.match(header):
        return _parse_flowchart(lines[1:], "TD")
    if _STATE_HEADER.match(header):
        return _parse_state(lines[1:])
    raise MermaidParseError(f"unsupported or unrecognized diagram header: {header!r}")


def _parse_node_token(token: str) -> Node:
    match = _NODE_RE.match(token.strip())
    if not match:
        raise MermaidParseError(f"unrecognized flowchart node syntax: {token!r}")
    node_id = match.group("id")
    for shape in ("circle", "rect", "rounded", "diamond"):
        value = match.group(shape)
        if value is not None:
            return Node(node_id, value.strip() or node_id, shape)
    return Node(node_id, node_id, "rect")


def _parse_flowchart(lines: list[str], direction: str) -> Diagram:
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []

    def ensure_node(token: str) -> str:
        node = _parse_node_token(token)
        is_default = node.shape == "rect" and node.label == node.id
        if node.id not in nodes or not is_default:
            nodes.setdefault(node.id, node)
            if not is_default:
                nodes[node.id] = node
        return node.id

    for line in lines:
        if line.lower() == "end" or line.lower().startswith(_SKIP_FLOWCHART_PREFIXES):
            continue
        matches = list(_EDGE_RE.finditer(line))
        if not matches:
            ensure_node(line)
            continue
        segments = []
        pos = 0
        for m in matches:
            segments.append(line[pos : m.start()])
            pos = m.end()
        segments.append(line[pos:])
        node_ids = [ensure_node(seg) for seg in segments]
        for i, m in enumerate(matches):
            op = m.group("op")
            edges.append(
                Edge(
                    source=node_ids[i],
                    target=node_ids[i + 1],
                    label=(m.group("label") or None) and m.group("label").strip(),
                    arrow=op.endswith(">"),
                    dotted=op.startswith("-."),
                )
            )

    if not nodes:
        raise MermaidParseError("flowchart has no nodes")
    return Diagram("flowchart", direction, list(nodes.values()), edges)


def _parse_state(lines: list[str]) -> Diagram:
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    pseudo_counter = 0
    composite_depth = 0
    in_note = False

    def ensure_named(node_id: str) -> str:
        if node_id not in nodes:
            nodes[node_id] = Node(node_id, node_id, "rounded")
        return node_id

    def next_pseudo(shape: str) -> str:
        nonlocal pseudo_counter
        pseudo_counter += 1
        pseudo_id = f"__{shape}_{pseudo_counter}__"
        nodes[pseudo_id] = Node(pseudo_id, "", shape)
        return pseudo_id

    for line in lines:
        if in_note:
            if line.lower() == "end note":
                in_note = False
            continue
        if composite_depth > 0:
            if line.endswith("{"):
                composite_depth += 1
            elif line == "}":
                composite_depth -= 1
            continue
        if _STATE_COMPOSITE_OPEN_RE.match(line):
            composite_depth += 1
            continue
        if re.match(r"^note\b", line, re.IGNORECASE):
            if ":" not in line:
                in_note = True
            continue
        if line.lower().startswith("direction "):
            continue

        match = _STATE_TRANSITION_RE.match(line)
        if match:
            src_id = next_pseudo("start") if match.group("src") == "[*]" else ensure_named(match.group("src"))
            dst_id = next_pseudo("end") if match.group("dst") == "[*]" else ensure_named(match.group("dst"))
            label = match.group("label")
            edges.append(Edge(src_id, dst_id, label.strip() if label else None))
            continue

        match = _STATE_DESC_RE.match(line)
        if match:
            node_id = ensure_named(match.group("id"))
            nodes[node_id] = Node(node_id, match.group("label").strip(), nodes[node_id].shape)
            continue

        raise MermaidParseError(f"unrecognized stateDiagram line: {line!r}")

    if not nodes:
        raise MermaidParseError("state diagram has no states")
    return Diagram("state", "TD", list(nodes.values()), edges)


# --------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------

MeasureFn = Callable[[str], "tuple[float, float]"]

_RANK_GAP = 90.0
_SIBLING_GAP = 30.0
_H_PADDING = 24.0
_V_PADDING = 16.0
_PSEUDOSTATE_RADIUS = 9.0
_SCENE_MARGIN = 20.0


@dataclass
class NodeLayout:
    node: Node
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2

    @property
    def rect(self) -> QRectF:
        return QRectF(self.x, self.y, self.width, self.height)


@dataclass
class LayoutResult:
    nodes: dict[str, NodeLayout]
    width: float
    height: float


def _node_size(node: Node, measure: MeasureFn) -> tuple[float, float]:
    if node.shape in ("start", "end"):
        diameter = _PSEUDOSTATE_RADIUS * 2
        return diameter, diameter
    text_w, text_h = measure(node.label or node.id)
    width = text_w + _H_PADDING * 2
    height = text_h + _V_PADDING * 2
    if node.shape == "diamond":
        # A diamond's usable inner area is roughly half its bounding
        # box -- scale the box up so the label still fits unclipped.
        width *= 1.6
        height *= 1.6
    elif node.shape == "circle":
        side = max(width, height)
        width = height = side
    return width, height


def _assign_ranks(diagram: Diagram) -> dict[str, int]:
    node_ids = [n.id for n in diagram.nodes]
    out_edges: dict[str, list[str]] = {nid: [] for nid in node_ids}
    in_edges: dict[str, list[str]] = {nid: [] for nid in node_ids}
    in_degree: dict[str, int] = dict.fromkeys(node_ids, 0)
    for e in diagram.edges:
        if e.source in out_edges and e.target in in_degree:
            out_edges[e.source].append(e.target)
            in_edges[e.target].append(e.source)
            in_degree[e.target] += 1

    rank: dict[str, int] = {}
    remaining = dict(in_degree)
    queue = [nid for nid in node_ids if in_degree[nid] == 0]
    for nid in queue:
        rank[nid] = 0
    i = 0
    while i < len(queue):
        nid = queue[i]
        i += 1
        for target in out_edges[nid]:
            rank[target] = max(rank.get(target, 0), rank[nid] + 1)
            remaining[target] -= 1
            if remaining[target] <= 0 and target not in queue:
                queue.append(target)

    # Cycle fallback: anything left unranked is stuck in a cycle with no
    # zero-in-degree entry point. Repeatedly rank whatever now has at
    # least one ranked predecessor (or none at all left to wait for);
    # if a whole pass makes no progress (a pure, isolated cycle), force
    # -rank one node to break it and continue.
    unranked = [nid for nid in node_ids if nid not in rank]
    while unranked:
        progressed = False
        for nid in list(unranked):
            preds_ranked = [rank[p] for p in in_edges[nid] if p in rank]
            all_preds_ranked = all(p in rank for p in in_edges[nid])
            if preds_ranked or all_preds_ranked:
                rank[nid] = (max(preds_ranked) + 1) if preds_ranked else 0
                unranked.remove(nid)
                progressed = True
        if not progressed:
            nid = unranked[0]
            rank[nid] = 0
            unranked.remove(nid)
    return rank


def layout(diagram: Diagram, measure: MeasureFn) -> LayoutResult:
    if not diagram.nodes:
        return LayoutResult({}, 0.0, 0.0)

    rank = _assign_ranks(diagram)
    sizes = {n.id: _node_size(n, measure) for n in diagram.nodes}

    ranks_grouped: dict[int, list[Node]] = {}
    for n in diagram.nodes:
        ranks_grouped.setdefault(rank[n.id], []).append(n)

    horizontal = diagram.direction in ("LR", "RL")
    reverse_main = diagram.direction in ("BT", "RL")
    max_rank = max(ranks_grouped)

    rank_extent = {
        r: max((sizes[n.id][0] if horizontal else sizes[n.id][1]) for n in members)
        for r, members in ranks_grouped.items()
    }

    main_offsets: dict[int, float] = {}
    offset = 0.0
    for r in range(max_rank + 1):
        main_offsets[r] = offset
        offset += rank_extent.get(r, 0.0) + _RANK_GAP
    total_main = max(offset - _RANK_GAP, 0.0)

    layouts: dict[str, NodeLayout] = {}
    total_cross = 0.0
    for r, members in ranks_grouped.items():
        cross = 0.0
        for n in members:
            w, h = sizes[n.id]
            main_size = w if horizontal else h
            main_pos = main_offsets[r]
            if reverse_main:
                main_pos = total_main - main_pos - main_size
            if horizontal:
                x, y = main_pos, cross
            else:
                x, y = cross, main_pos
            layouts[n.id] = NodeLayout(n, x, y, w, h)
            cross += (h if horizontal else w) + _SIBLING_GAP
        total_cross = max(total_cross, cross - _SIBLING_GAP if members else 0.0)

    for nl in layouts.values():
        nl.x += _SCENE_MARGIN
        nl.y += _SCENE_MARGIN

    width = (total_main if horizontal else total_cross) + _SCENE_MARGIN * 2
    height = (total_cross if horizontal else total_main) + _SCENE_MARGIN * 2
    return LayoutResult(layouts, width, height)


# --------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------


def _boundary_point(nl: NodeLayout, other: tuple[float, float]) -> tuple[float, float]:
    """The point on `nl`'s shape boundary along the ray from its center
    toward `other` -- used to clip a straight edge to each endpoint's
    shape instead of drawing into/through it."""
    cx, cy = nl.center
    dx, dy = other[0] - cx, other[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    hw, hh = nl.width / 2, nl.height / 2
    shape = nl.node.shape
    if shape in ("circle", "start", "end"):
        dist = math.hypot(dx, dy)
        t = hw / dist
    elif shape == "diamond":
        denom = (abs(dx) / hw if hw else 0) + (abs(dy) / hh if hh else 0)
        t = 1 / denom if denom else 0
    else:  # rect / rounded
        candidates = [hw / abs(dx)] if dx else []
        candidates += [hh / abs(dy)] if dy else []
        t = min(candidates) if candidates else 0
    t = min(t, 1.0)
    return cx + dx * t, cy + dy * t


def _make_node_item(nl: NodeLayout, pen: QPen, fill: QColor, text_color: QColor):
    shape = nl.node.shape
    rect = nl.rect

    if shape == "start":
        item = QGraphicsEllipseItem(rect)
        item.setBrush(QBrush(text_color))
        item.setPen(pen)
        return item
    if shape == "end":
        outer = QGraphicsEllipseItem(rect)
        outer.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        outer.setPen(pen)
        margin = rect.width() * 0.25
        inner = QGraphicsEllipseItem(rect.adjusted(margin, margin, -margin, -margin), outer)
        inner.setBrush(QBrush(text_color))
        inner.setPen(QPen(Qt.PenStyle.NoPen))
        return outer

    if shape == "diamond":
        poly = QPolygonF(
            [
                QPointF(rect.center().x(), rect.top()),
                QPointF(rect.right(), rect.center().y()),
                QPointF(rect.center().x(), rect.bottom()),
                QPointF(rect.left(), rect.center().y()),
            ]
        )
        item = QGraphicsPolygonItem(poly)
    elif shape == "circle":
        item = QGraphicsEllipseItem(rect)
    elif shape == "rounded":
        path = QPainterPath()
        radius = min(rect.width(), rect.height()) * 0.3
        path.addRoundedRect(rect, radius, radius)
        item = QGraphicsPathItem(path)
    else:  # "rect"
        item = QGraphicsRectItem(rect)
    item.setBrush(QBrush(fill))
    item.setPen(pen)

    text = QGraphicsSimpleTextItem(nl.node.label, item)
    text.setBrush(QBrush(text_color))
    tb = text.boundingRect()
    text.setPos(rect.center().x() - tb.width() / 2, rect.center().y() - tb.height() / 2)
    return item


def _arrowhead(tip: tuple[float, float], from_point: tuple[float, float], color: QColor, size: float = 9.0):
    angle = math.atan2(tip[1] - from_point[1], tip[0] - from_point[0])
    spread = math.radians(28)
    left = (tip[0] - size * math.cos(angle - spread), tip[1] - size * math.sin(angle - spread))
    right = (tip[0] - size * math.cos(angle + spread), tip[1] - size * math.sin(angle + spread))
    poly = QPolygonF([QPointF(*tip), QPointF(*left), QPointF(*right)])
    item = QGraphicsPolygonItem(poly)
    item.setBrush(QBrush(color))
    item.setPen(QPen(color))
    return item


def _add_edge_label(scene: QGraphicsScene, pos: tuple[float, float], text: str, color: QColor, bg_color: QColor) -> None:
    label = QGraphicsSimpleTextItem(text)
    label.setBrush(QBrush(color))
    tb = label.boundingRect()
    bg = QGraphicsRectItem(tb.adjusted(-3, -1, 3, 1))
    bg.setBrush(QBrush(bg_color))
    bg.setPen(QPen(Qt.PenStyle.NoPen))
    bg.setPos(pos[0] - tb.width() / 2 - 3, pos[1] - tb.height() / 2 - 1)
    label.setPos(pos[0] - tb.width() / 2, pos[1] - tb.height() / 2)
    scene.addItem(bg)
    scene.addItem(label)


def _add_edge(scene: QGraphicsScene, src: NodeLayout, tgt: NodeLayout, edge: Edge, color: QColor, bg_color: QColor) -> None:
    pen = QPen(color)
    pen.setWidthF(1.3)
    if edge.dotted:
        pen.setStyle(Qt.PenStyle.DashLine)

    if edge.source == edge.target:
        # A straight line has zero length for a self-loop -- draw a
        # small bulging loop off the node's right edge instead.
        x0 = src.x + src.width
        y0 = src.y + src.height * 0.3
        y1 = src.y + src.height * 0.7
        loop_out = 40.0
        path = QPainterPath()
        path.moveTo(x0, y0)
        path.cubicTo(x0 + loop_out, y0 - 10, x0 + loop_out, y1 + 10, x0, y1)
        item = QGraphicsPathItem(path)
        item.setPen(pen)
        scene.addItem(item)
        if edge.arrow:
            scene.addItem(_arrowhead((x0, y1), (x0 + loop_out * 0.3, y1 + 8), color))
        if edge.label:
            _add_edge_label(scene, (x0 + loop_out * 0.7, (y0 + y1) / 2), edge.label, color, bg_color)
        return

    p1 = _boundary_point(src, tgt.center)
    p2 = _boundary_point(tgt, src.center)
    path = QPainterPath()
    path.moveTo(*p1)
    path.lineTo(*p2)
    item = QGraphicsPathItem(path)
    item.setPen(pen)
    scene.addItem(item)
    if edge.arrow:
        scene.addItem(_arrowhead(p2, p1, color))
    if edge.label:
        _add_edge_label(scene, ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2), edge.label, color, bg_color)


def build_scene(diagram: Diagram, result: LayoutResult, palette: QPalette) -> QGraphicsScene:
    scene = QGraphicsScene(0, 0, max(result.width, 1.0), max(result.height, 1.0))

    fill = palette.color(QPalette.ColorRole.Button)
    border = palette.color(QPalette.ColorRole.Text)
    text_color = palette.color(QPalette.ColorRole.ButtonText)
    bg_color = palette.color(QPalette.ColorRole.Base)

    pen = QPen(border)
    pen.setWidthF(1.4)

    for nl in result.nodes.values():
        scene.addItem(_make_node_item(nl, pen, fill, text_color))

    for edge in diagram.edges:
        src = result.nodes.get(edge.source)
        tgt = result.nodes.get(edge.target)
        if src is None or tgt is None:
            continue
        _add_edge(scene, src, tgt, edge, border, bg_color)

    return scene


def render_svg(scene: QGraphicsScene) -> str:
    """Serializes `scene` to a real SVG string (TODO `05cfccc`) --
    genuinely new: nothing in this module previously ever produced an
    SVG, only a live `QGraphicsScene` rendered directly by the
    (now-retired) `MermaidDiagramWidget`, with no serialization step at
    all. Used by the `mermaid_flowchart_svg`/`mermaid_state_svg`
    transforms (`desk_transforms/`)."""
    rect = scene.sceneRect()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    generator = QSvgGenerator()
    generator.setOutputDevice(buffer)
    generator.setSize(rect.size().toSize())
    generator.setViewBox(rect)
    painter = QPainter(generator)
    scene.render(painter, target=QRectF(0, 0, rect.width(), rect.height()), source=rect)
    painter.end()
    buffer.close()
    return bytes(buffer.data()).decode("utf-8")
