"""Bespoke, intentionally partial Mermaid diagram support.

Rather than vendoring `mermaid.js` (and the QtWebEngine round-trip that
would require), this hand-rolls a parser for a subset of Mermaid syntax,
a simplified layered auto-layout, and a native `QGraphicsScene`
renderer. Per `CLAUDE.md`'s "avoid adding dependencies, prefer bespoke
solutions" plus direct user direction (see `plans/markdown-ex-widget
.md`), this only supports:

- **Flowchart** (`flowchart`/`graph`): `subgraph ... end` boxes (nestable;
  TODO a8931c8) and `classDef`/`class`/`:::`/`style` node styling (TODO
  a509077) -- `linkStyle`/`click` are still skipped, and an edge to a
  subgraph itself is a `MermaidParseError`. Five node shapes -- rect
  `[Label]`, rounded `(Label)`, diamond `{Label}`, circle `((Label))`,
  stadium `([Label])` -- no other extended shapes (subroutine,
  cylinder, hexagon, ...). Edge styles `-->`, `---`, `-.->`, `-.-`,
  with a label either piped (`-->|label|`) or unpiped/inline
  (`-- label -->`, `-. label .->`, and the arrow-less equivalents).
  Any label -- inside a shape or on an edge -- may be double-quoted
  (`id["a [b] c"]`) so it can contain its own shape's delimiter
  characters literally; there is no other escaping mechanism (no
  backslash escapes, no HTML entities).
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
    shape: str  # "rect" | "rounded" | "diamond" | "circle" | "stadium" | "start" | "end"
    # TODO a509077: `classDef`/`class`/`:::`/`style` support. `classes` is
    # the ordered list of class names assigned to this node; `style` is
    # the fully resolved property map (default class, then each assigned
    # class in order, then an explicit `style` line), filled in at the
    # end of parsing -- see `_resolve_node_styles`.
    classes: list[str] = field(default_factory=list)
    style: dict[str, str] = field(default_factory=dict)


@dataclass
class Edge:
    source: str
    target: str
    label: str | None = None
    arrow: bool = True
    dotted: bool = False


@dataclass
class Subgraph:
    """TODO a8931c8: a `subgraph <id> [title] ... end` block. `members`
    are the node ids first mentioned directly inside it (not inside a
    nested subgraph); `parent` is the enclosing subgraph's id, if any."""

    id: str
    title: str
    parent: str | None = None
    members: list[str] = field(default_factory=list)


@dataclass
class Diagram:
    kind: str  # "flowchart" | "state"
    direction: str  # "TD" | "TB" | "LR" | "BT" | "RL"
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    subgraphs: list[Subgraph] = field(default_factory=list)  # outer before inner


# --------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------

_FLOWCHART_HEADER = re.compile(r"^(flowchart|graph)\s+(TD|TB|LR|BT|RL)\s*$", re.IGNORECASE)
_FLOWCHART_HEADER_NO_DIR = re.compile(r"^(flowchart|graph)\s*$", re.IGNORECASE)
_STATE_HEADER = re.compile(r"^stateDiagram(-v2)?\s*$", re.IGNORECASE)

# TODO a509077/a8931c8: `subgraph`/`end`/`classDef`/`class`/`style` are
# now handled; the rest of these are still skipped (not rendered).
# `direction XX` inside a subgraph is accepted and ignored too.
_SKIP_FLOWCHART_PREFIXES = ("click ", "linkstyle", "direction ")
_SUBGRAPH_RE = re.compile(r"^subgraph(?:\s+(?P<rest>.*))?$", re.IGNORECASE)
_SUBGRAPH_ID_TITLE_RE = re.compile(
    r'^(?P<id>[A-Za-z0-9_]+)\s*\[\s*(?:"(?P<tq>[^"]*)"|(?P<t>[^\]]*))\s*\]$'
)
_CLASSDEF_RE = re.compile(r"^classDef\s+(?P<names>[\w\-]+(?:\s*,\s*[\w\-]+)*)\s+(?P<styles>.+?)\s*;?$", re.IGNORECASE)
_CLASS_RE = re.compile(r"^class\s+(?P<ids>\w+(?:\s*,\s*\w+)*)\s+(?P<name>[\w\-]+)\s*;?$", re.IGNORECASE)
_STYLE_RE = re.compile(r"^style\s+(?P<id>\w+)\s+(?P<styles>.+?)\s*;?$", re.IGNORECASE)
# Splits `fill:#f9f,stroke:#333` on commas that aren't inside parens
# (so `fill:rgb(1,2,3)` survives).
_STYLE_SPLIT_RE = re.compile(r",(?![^()]*\))")

# TODO 90dd6e6: unpiped inline edge labels (`A -- text --> B`, standard
# Mermaid alongside the piped `A -->|text| B` form) sit between an
# opening and closing token rather than after a literal operator --
# one alternative per operator family, each with its own uniquely
# -named group pair (Python's `re` disallows reusing a group name
# across alternatives). Tried before the plain literal-operator
# alternative so a label is never mistaken for part of a node id (the
# bug this fixes: without this, `A -- text --> B`'s "-- text" was
# folded into node A's own token instead of recognized as an edge).
# The dotted-open alternative's `(?!>)` keeps it from also matching a
# dotted-arrow-with-label's own `.->` closing sequence.
_EDGE_RE = re.compile(
    r"(?:--\s+(?P<arrow_label>.+?)\s+-->)"
    r"|(?:--\s+(?P<open_label>.+?)\s+---)"
    r"|(?:-\.\s*(?P<dotted_arrow_label>.+?)\s*\.->)"
    r"|(?:-\.\s*(?P<dotted_open_label>.+?)\s*\.-(?!>))"
    r"|(?P<op>-\.->|-\.-|-->|---)(?:\s*\|(?P<label>[^|]*)\|)?"
)

# TODO 90dd6e6: every shape's content is either double-quoted (any
# character except a literal `"`, so a label can contain its own
# shape's delimiter characters -- standard Mermaid, e.g. `id["a [b]
# c"]`) or the existing unquoted class -- tried unquoted first (the
# common case), falling back to the quoted alternative via ordinary
# regex backtracking when the unquoted class can't reach the shape's
# own closing delimiter. Stadium `([...])` is ordered *before* rounded
# `(...)`: rounded's own class allows brackets, so tried first it would
# otherwise consume `([label])` whole as a rounded node with the
# literal label `[label]` -- alternation tries branches in order and
# takes the first one that lets the *overall* pattern match, not the
# most specific one. Circle already precedes rect for the equivalent
# reason (`((` vs `[`), unaffected.
_NODE_RE = re.compile(
    r"^(?P<id>[A-Za-z0-9_]+)\s*"
    r"(?:"
    r'\(\((?:"(?P<circle_q>[^"]*)"|(?P<circle>[^()]*))\)\)'
    r'|\[(?:"(?P<rect_q>[^"]*)"|(?P<rect>[^\[\]]*))\]'
    r'|\(\[(?:"(?P<stadium_q>[^"]*)"|(?P<stadium>[^\[\]()]*))\]\)'
    r'|\((?:"(?P<rounded_q>[^"]*)"|(?P<rounded>[^()]*))\)'
    r'|\{(?:"(?P<diamond_q>[^"]*)"|(?P<diamond>[^{}]*))\}'
    r")?"
    # TODO a509077: the `A:::className` class shorthand.
    r"(?::::(?P<cls>[A-Za-z0-9_\-]+))?$"
)

_NODE_SHAPES = ("circle", "rect", "stadium", "rounded", "diamond")

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
    for shape in _NODE_SHAPES:
        # TODO 90dd6e6: `is None`, not falsy -- an intentionally empty
        # quoted label (`id[""]`) must not be skipped in favor of the
        # (unmatched, also None) plain group.
        value = match.group(f"{shape}_q")
        if value is None:
            value = match.group(shape)
        if value is not None:
            return Node(node_id, value.strip() or node_id, shape, _shorthand_classes(match))
    return Node(node_id, node_id, "rect", _shorthand_classes(match))


def _shorthand_classes(match: re.Match) -> list[str]:
    cls = match.group("cls")
    return [cls] if cls else []


def _parse_style_props(text: str) -> dict[str, str]:
    """`fill:#f9f,stroke:#333,stroke-width:4px` -> a property map (keys
    lowercased; a trailing `;` and malformed pieces are dropped)."""
    props: dict[str, str] = {}
    for piece in _STYLE_SPLIT_RE.split(text.strip().rstrip(";")):
        key, sep, value = piece.partition(":")
        key, value = key.strip().lower(), value.strip().rstrip(";").strip()
        if sep and key and value:
            props[key] = value
    return props


def _edge_match_info(m: re.Match) -> tuple[str, str | None]:
    """TODO 90dd6e6: normalizes an `_EDGE_RE` match -- whichever
    unpiped-label alternative matched (if any), or the plain literal
    -operator alternative -- into the `(op, label)` shape
    `_parse_flowchart`'s own edge-construction logic already expects,
    unchanged since before this TODO."""
    for op, group in (
        ("-->", "arrow_label"),
        ("---", "open_label"),
        ("-.->", "dotted_arrow_label"),
        ("-.-", "dotted_open_label"),
    ):
        label = m.group(group)
        if label is not None:
            return op, label
    return m.group("op"), m.group("label")


def _parse_flowchart(lines: list[str], direction: str) -> Diagram:
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    subgraphs: dict[str, Subgraph] = {}
    sg_stack: list[Subgraph] = []
    member_of: set[str] = set()
    class_defs: dict[str, dict[str, str]] = {}
    pending_classes: list[tuple[str, str]] = []  # (node id, class name)
    node_styles: dict[str, dict[str, str]] = {}

    def ensure_node(token: str) -> str:
        node = _parse_node_token(token)
        for cls in node.classes:
            pending_classes.append((node.id, cls))
        node.classes = []
        is_default = node.shape == "rect" and node.label == node.id
        if node.id not in nodes or not is_default:
            nodes.setdefault(node.id, node)
            if not is_default:
                nodes[node.id] = node
        if sg_stack and node.id not in member_of:
            # A node belongs to the innermost subgraph it is first
            # mentioned in; a later mention elsewhere doesn't move it.
            member_of.add(node.id)
            sg_stack[-1].members.append(node.id)
        return node.id

    for line in lines:
        lowered = line.lower()
        if lowered == "end":
            if sg_stack:
                sg_stack.pop()
            continue
        sg_match = _SUBGRAPH_RE.match(line)
        if sg_match:
            sg = _open_subgraph(sg_match.group("rest"), sg_stack, subgraphs)
            sg_stack.append(sg)
            continue
        if lowered.startswith(_SKIP_FLOWCHART_PREFIXES):
            continue
        m = _CLASSDEF_RE.match(line)
        if m:
            props = _parse_style_props(m.group("styles"))
            for name in m.group("names").split(","):
                class_defs.setdefault(name.strip(), {}).update(props)
            continue
        m = _CLASS_RE.match(line)
        if m:
            for node_id in m.group("ids").split(","):
                pending_classes.append((node_id.strip(), m.group("name")))
            continue
        m = _STYLE_RE.match(line)
        if m:
            node_styles.setdefault(m.group("id"), {}).update(_parse_style_props(m.group("styles")))
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
            op, label = _edge_match_info(m)
            edges.append(
                Edge(
                    source=node_ids[i],
                    target=node_ids[i + 1],
                    label=(label or None) and label.strip(),
                    arrow=op.endswith(">"),
                    dotted=op.startswith("-."),
                )
            )

    if not nodes:
        raise MermaidParseError("flowchart has no nodes")
    for sg_id in subgraphs:
        if sg_id in nodes:
            raise MermaidParseError(
                f"{sg_id!r} is a subgraph id used as an edge endpoint or node -- "
                "edges to/from a subgraph itself aren't supported"
            )
    _resolve_node_styles(nodes, class_defs, pending_classes, node_styles)
    return Diagram("flowchart", direction, list(nodes.values()), edges, list(subgraphs.values()))


def _open_subgraph(rest: str | None, stack: list[Subgraph], subgraphs: dict[str, Subgraph]) -> Subgraph:
    """TODO a8931c8: `subgraph id [Title]`, `subgraph id["Title"]`, or
    `subgraph Title` (the title doubles as the id)."""
    rest = (rest or "").strip()
    if not rest:
        raise MermaidParseError("subgraph needs an id or title")
    m = _SUBGRAPH_ID_TITLE_RE.match(rest)
    if m:
        sg_id = m.group("id")
        title = m.group("tq") if m.group("tq") is not None else m.group("t")
        title = title.strip() or sg_id
    else:
        title = rest[1:-1] if len(rest) >= 2 and rest[0] == rest[-1] == '"' else rest
        sg_id = title
    if sg_id in subgraphs:
        raise MermaidParseError(f"duplicate subgraph id: {sg_id!r}")
    sg = Subgraph(sg_id, title, stack[-1].id if stack else None)
    subgraphs[sg_id] = sg
    return sg


def _resolve_node_styles(
    nodes: dict[str, Node],
    class_defs: dict[str, dict[str, str]],
    pending_classes: list[tuple[str, str]],
    node_styles: dict[str, dict[str, str]],
) -> None:
    """TODO a509077: fills each node's `classes` and `style` -- done once
    at the end so `class`/`style` lines may come before or after the
    nodes and `classDef`s they refer to. A class with no `classDef` and
    a `class`/`style` naming an unknown node are silently ignored (as in
    Mermaid)."""
    for node_id, cls in pending_classes:
        node = nodes.get(node_id)
        if node is not None and cls not in node.classes:
            node.classes.append(cls)
    for node in nodes.values():
        style = dict(class_defs.get("default", {}))
        for cls in node.classes:
            style.update(class_defs.get(cls, {}))
        style.update(node_styles.get(node.id, {}))
        node.style = style


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
_SUBGRAPH_PADDING = 14.0


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
class SubgraphLayout:
    """TODO a8931c8: the bounding box drawn around a subgraph's nodes."""

    subgraph: Subgraph
    rect: QRectF


@dataclass
class LayoutResult:
    nodes: dict[str, NodeLayout]
    width: float
    height: float
    subgraphs: dict[str, SubgraphLayout] = field(default_factory=dict)


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
    order_index = {n.id: i for i, n in enumerate(diagram.nodes)}

    horizontal = diagram.direction in ("LR", "RL")
    reverse_main = diagram.direction in ("BT", "RL")

    # ---- subgraph bookkeeping (TODO a8931c8) -------------------------
    sgs = {sg.id: sg for sg in diagram.subgraphs}
    children: dict[str | None, list[str]] = {}
    for sg in diagram.subgraphs:
        children.setdefault(sg.parent, []).append(sg.id)
    desc: dict[str, list[str]] = {}

    def descendants(sg_id: str) -> list[str]:
        if sg_id not in desc:
            ids = [m for m in sgs[sg_id].members if m in sizes]
            for child in children.get(sg_id, []):
                ids += descendants(child)
            desc[sg_id] = ids
        return desc[sg_id]

    # Empty subgraphs (no nodes anywhere inside) draw nothing.
    live_children = {
        parent: [c for c in kids if descendants(c)] for parent, kids in children.items()
    }
    live = [sg.id for sg in diagram.subgraphs if descendants(sg.id)]
    member_of = {m for sg_id in live for m in sgs[sg_id].members if m in sizes}
    title_h = (measure("Ag")[1] + 4.0) if live else 0.0
    pad = _SUBGRAPH_PADDING

    def depth(sg_id: str) -> int:
        return 1 + max((depth(c) for c in live_children.get(sg_id, [])), default=0)

    rank_gap = _RANK_GAP
    if live:
        max_depth = max(depth(sg_id) for sg_id in live if sgs[sg_id].parent is None)
        rank_gap = max(_RANK_GAP, max_depth * (2 * pad + title_h) + 36.0)

    # ---- cross-axis packing ------------------------------------------
    # Items are nodes ("n", id) and subgraph blocks ("s", id). Each is
    # placed at the first cross offset clear of everything already placed
    # in *every rank it spans* -- so a subgraph reserves one contiguous
    # cross-axis lane across all its ranks, and a non-member in a rank in
    # the middle of its span is pushed past the lane instead of landing
    # inside the box. With no subgraphs every item spans exactly one rank
    # and this is the plain left-to-right packing per rank.
    block_cache: dict[str, tuple[dict, float]] = {}

    def span(item):
        kind, ident = item
        if kind == "n":
            return rank[ident], rank[ident]
        ranks = [rank[n] for n in descendants(ident)]
        return min(ranks), max(ranks)

    def order(item):
        kind, ident = item
        return order_index[ident] if kind == "n" else min(order_index[n] for n in descendants(ident))

    def cross_size(item):
        kind, ident = item
        if kind == "n":
            w, h = sizes[ident]
            return h if horizontal else w
        return pack(ident)[1]

    def pack(container: str | None):
        if container is not None and container in block_cache:
            return block_cache[container]
        if container is None:
            start_pad = end_pad = 0.0
            items = [("n", n.id) for n in diagram.nodes if n.id not in member_of]
        else:
            # In a horizontal layout the cross axis is vertical, so the
            # title strip (drawn at the box's top) lives in the start pad.
            start_pad = pad + (title_h if horizontal else 0.0)
            end_pad = pad
            items = [("n", m) for m in sgs[container].members if m in sizes]
        items += [("s", c) for c in live_children.get(container, [])]
        items.sort(key=order)
        edge: dict[int, float] = {}
        offsets: dict[tuple[str, str], float] = {}
        for item in items:
            lo, hi = span(item)
            size = cross_size(item)
            off = max(edge.get(r, start_pad) for r in range(lo, hi + 1))
            offsets[item] = off
            for r in range(lo, hi + 1):
                edge[r] = off + size + _SIBLING_GAP
        total = (max(edge.values()) - _SIBLING_GAP if edge else start_pad) + end_pad
        if container is not None and not horizontal:
            total = max(total, measure(sgs[container].title)[0] + 2 * pad)
        result = (offsets, total)
        if container is not None:
            block_cache[container] = result
        return result

    cross_pos: dict[str, float] = {}
    block_pos: dict[str, float] = {}

    def place(container: str | None, base: float) -> None:
        offsets, _ = pack(container)
        for (kind, ident), off in offsets.items():
            if kind == "n":
                cross_pos[ident] = base + off
            else:
                block_pos[ident] = base + off
                place(ident, base + off)

    place(None, 0.0)
    total_cross = pack(None)[1]

    # ---- main-axis ranks ---------------------------------------------
    ranks_grouped: dict[int, list[Node]] = {}
    for n in diagram.nodes:
        ranks_grouped.setdefault(rank[n.id], []).append(n)
    max_rank = max(ranks_grouped)

    rank_extent = {
        r: max((sizes[n.id][0] if horizontal else sizes[n.id][1]) for n in members)
        for r, members in ranks_grouped.items()
    }

    main_offsets: dict[int, float] = {}
    offset = 0.0
    for r in range(max_rank + 1):
        main_offsets[r] = offset
        offset += rank_extent.get(r, 0.0) + rank_gap
    total_main = max(offset - rank_gap, 0.0)

    layouts: dict[str, NodeLayout] = {}
    for n in (n for members in ranks_grouped.values() for n in members):
        w, h = sizes[n.id]
        main_size = w if horizontal else h
        main_pos = main_offsets[rank[n.id]]
        if reverse_main:
            main_pos = total_main - main_pos - main_size
        cross = cross_pos[n.id]
        x, y = (main_pos, cross) if horizontal else (cross, main_pos)
        layouts[n.id] = NodeLayout(n, x, y, w, h)

    # ---- subgraph boxes ----------------------------------------------
    # Cross extent is the lane reserved above; main extent hugs the
    # contained nodes / child boxes (computed bottom-up so a parent
    # strictly encloses its children).
    boxes: dict[str, QRectF] = {}

    def box(sg_id: str) -> QRectF:
        if sg_id in boxes:
            return boxes[sg_id]
        rects = [layouts[m].rect for m in sgs[sg_id].members if m in layouts]
        rects += [box(c) for c in live_children.get(sg_id, [])]
        union = rects[0]
        for r in rects[1:]:
            union = union.united(r)
        lane_start, lane = block_pos[sg_id], pack(sg_id)[1]
        if horizontal:
            rect = QRectF(union.left() - pad, lane_start, union.width() + 2 * pad, lane)
        else:
            top = union.top() - pad - title_h
            rect = QRectF(lane_start, top, lane, union.bottom() + pad - top)
        boxes[sg_id] = rect
        return rect

    for sg_id in live:
        box(sg_id)

    # Boxes may extend past the nodes (negative coordinates); shift
    # everything so the whole drawing starts at the scene margin.
    all_rects = [nl.rect for nl in layouts.values()] + list(boxes.values())
    min_x = min(r.left() for r in all_rects)
    min_y = min(r.top() for r in all_rects)
    max_x = max(r.right() for r in all_rects)
    max_y = max(r.bottom() for r in all_rects)
    dx, dy = _SCENE_MARGIN - min_x, _SCENE_MARGIN - min_y
    for nl in layouts.values():
        nl.x += dx
        nl.y += dy
    sg_layouts = {
        sg_id: SubgraphLayout(sgs[sg_id], boxes[sg_id].translated(dx, dy)) for sg_id in live
    }

    width = max_x - min_x + _SCENE_MARGIN * 2
    height = max_y - min_y + _SCENE_MARGIN * 2
    return LayoutResult(layouts, width, height, sg_layouts)


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


_RGB_RE = re.compile(r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$", re.IGNORECASE)


def _parse_color(value: str) -> QColor | None:
    """TODO a509077: a CSS-ish color from a `classDef`/`style` value --
    `#rgb`/`#rrggbb`, a named color, or `rgb(r,g,b)`/`rgba(r,g,b,a)`.
    `None` for anything else (including `none`), which callers treat as
    'leave the default'."""
    value = value.strip()
    m = _RGB_RE.match(value)
    if m:
        r, g, b = (min(int(m.group(i)), 255) for i in (1, 2, 3))
        alpha = min(float(m.group(4)), 1.0) if m.group(4) else 1.0
        return QColor(r, g, b, round(alpha * 255))
    color = QColor(value)
    return color if color.isValid() else None


def _styled(node: Node, pen: QPen, fill: QColor, text_color: QColor) -> tuple[QPen, QColor, QColor]:
    """TODO a509077: the node's own pen/fill/text color after applying its
    resolved `classDef`/`style` properties -- `fill`, `stroke`,
    `stroke-width`, `stroke-dasharray`, `color`. Other properties
    (font-size, rx, ...) are accepted by the parser but not drawn."""
    style = node.style
    if not style:
        return pen, fill, text_color
    pen = QPen(pen)
    if "fill" in style:
        fill = _parse_color(style["fill"]) or fill
    if "stroke" in style:
        stroke = _parse_color(style["stroke"])
        if stroke is not None:
            pen.setColor(stroke)
    if "stroke-width" in style:
        try:
            pen.setWidthF(max(float(style["stroke-width"].lower().removesuffix("px")), 0.0))
        except ValueError:
            pass
    if "stroke-dasharray" in style:
        pen.setStyle(Qt.PenStyle.DashLine)
    if "color" in style:
        text_color = _parse_color(style["color"]) or text_color
    return pen, fill, text_color


def _make_node_item(nl: NodeLayout, pen: QPen, fill: QColor, text_color: QColor):
    shape = nl.node.shape
    rect = nl.rect
    pen, fill, text_color = _styled(nl.node, pen, fill, text_color)

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
    elif shape == "stadium":
        # TODO 90dd6e6: a true pill/capsule -- radius = height / 2 fully
        # rounds the short ends -- distinct from "rounded"'s own more
        # moderate corner rounding above.
        path = QPainterPath()
        radius = rect.height() / 2
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


def _add_subgraph_box(scene: QGraphicsScene, sl: SubgraphLayout, border: QColor, text_color: QColor) -> None:
    fill = QColor(border)
    fill.setAlpha(22)
    edge = QColor(border)
    edge.setAlpha(150)
    pen = QPen(edge)
    pen.setWidthF(1.0)
    path = QPainterPath()
    path.addRoundedRect(sl.rect, 6, 6)
    item = QGraphicsPathItem(path)
    item.setBrush(QBrush(fill))
    item.setPen(pen)
    scene.addItem(item)
    title = QGraphicsSimpleTextItem(sl.subgraph.title)
    title.setBrush(QBrush(text_color))
    available = max(sl.rect.width() - 16.0, 8.0)
    title.setText(QFontMetricsF(title.font()).elidedText(sl.subgraph.title, Qt.TextElideMode.ElideRight, available))
    title.setPos(sl.rect.left() + 8.0, sl.rect.top() + 4.0)
    scene.addItem(title)


def build_scene(diagram: Diagram, result: LayoutResult, palette: QPalette) -> QGraphicsScene:
    scene = QGraphicsScene(0, 0, max(result.width, 1.0), max(result.height, 1.0))

    fill = palette.color(QPalette.ColorRole.Button)
    border = palette.color(QPalette.ColorRole.Text)
    text_color = palette.color(QPalette.ColorRole.ButtonText)
    bg_color = palette.color(QPalette.ColorRole.Base)

    pen = QPen(border)
    pen.setWidthF(1.4)

    # TODO a8931c8: subgraph boxes first, so they sit behind everything.
    # `result.subgraphs` is outer-before-inner, so a nested box draws on
    # top of its parent's.
    for sl in result.subgraphs.values():
        _add_subgraph_box(scene, sl, border, text_color)

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
