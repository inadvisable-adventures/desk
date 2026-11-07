# TODOs a509077 (classDef/class/style/::: node styling) and a8931c8
# (subgraph containment boxes): desk.mermaid parses and renders both.
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtGui import QFont, QFontMetricsF, QPalette  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.mermaid import MermaidParseError, build_scene, layout, parse, render_svg  # noqa: E402
from desk.temp_ui import CURRENT_TAGS, _MARKDOWN_DOC, _NEW_FEATURES  # noqa: E402

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


def measure(text):
    m = QFontMetricsF(QFont())
    return m.horizontalAdvance(text), m.height()


def styles(d):
    return {n.id: n.style for n in d.nodes}


# ---- classDef / class / ::: / style ------------------------------------

d = parse(
    "flowchart TD\n"
    "A --> B --> C\n"
    "classDef hot fill:#f96,stroke:#333,stroke-width:4px;\n"
    "class A,B hot\n"
)
check("classDef + class (comma list): both nodes get the style", styles(d)["A"] == styles(d)["B"] == {"fill": "#f96", "stroke": "#333", "stroke-width": "4px"})
check("class: unassigned node unstyled", styles(d)["C"] == {})
check("class: node records its class names", d.nodes[0].classes == ["hot"])

d = parse("flowchart TD\nclass A hot\nA --> B\nclassDef hot fill:#0f0\n")
check("class/classDef order doesn't matter (resolved at the end)", styles(d)["A"] == {"fill": "#0f0"})

d = parse("flowchart TD\nA:::hot --> B[Bee]:::hot\nclassDef hot fill:#00f\n")
check("`:::` shorthand on bare and shaped nodes", styles(d)["A"] == {"fill": "#00f"} and styles(d)["B"] == {"fill": "#00f"})
check("`:::` keeps the node's label/shape", [(n.label, n.shape) for n in d.nodes] == [("A", "rect"), ("Bee", "rect")])

d = parse("flowchart TD\nA --> B\nclassDef default fill:#111\nclassDef x stroke:#222\nclass B x\nstyle B fill:#333\n")
check("default class applies to all nodes", styles(d)["A"] == {"fill": "#111"})
check("order: default, then classes, then `style` line wins", styles(d)["B"] == {"fill": "#333", "stroke": "#222"})

d = parse("flowchart TD\nA\nclassDef a,b fill:rgb(1,2,3),color:#fff\nclass A b\n")
check("multi-name classDef; commas inside rgb() don't split", styles(d)["A"] == {"fill": "rgb(1,2,3)", "color": "#fff"})

d = parse("flowchart TD\nA\nclass Ghost nope\nstyle Ghost fill:#fff\nclass A undefinedClass\n")
check("unknown node / undefined class are ignored, not errors", styles(d) == {"A": {}})

d = parse("flowchart TD\nclick A callback\nlinkStyle 0 stroke:#f00\nA --> B\n")
check("click/linkStyle still skipped", len(d.nodes) == 2 and len(d.edges) == 1)

# ---- rendering of styles ----------------------------------------------

d = parse("flowchart TD\nA[Alpha] --> B[Beta]\nclassDef hot fill:#ff0000,stroke:#00ff00,stroke-width:5px,color:#0000ff\nclass A hot\n")
svg = render_svg(build_scene(d, layout(d, measure), QPalette()))
check("svg carries the custom fill", "#ff0000" in svg.lower())
check("svg carries the custom stroke", "#00ff00" in svg.lower())
check("svg carries the custom text color", "#0000ff" in svg.lower())
plain = parse("flowchart TD\nA[Alpha] --> B[Beta]\n")
check("unstyled diagram has none of those colors", "#ff0000" not in render_svg(build_scene(plain, layout(plain, measure), QPalette())).lower())

# ---- subgraph parsing -------------------------------------------------

d = parse(
    "flowchart TD\n"
    "subgraph one [First Group]\n"
    "  direction LR\n"
    "  A --> B\n"
    "end\n"
    'subgraph two["Second"]\n'
    "  C\n"
    "  subgraph inner\n"
    "    D\n"
    "  end\n"
    "end\n"
    "B --> C\n"
)
sg = {s.id: s for s in d.subgraphs}
check("subgraph id [title]", sg["one"].title == "First Group" and sg["one"].members == ["A", "B"])
check('subgraph id["quoted title"]', sg["two"].title == "Second")
check("nested subgraph: parent recorded, members direct-only", sg["inner"].parent == "two" and sg["inner"].members == ["D"] and sg["two"].members == ["C"])
check("subgraph without brackets: title doubles as id", sg["inner"].title == "inner")
check("outer-before-inner ordering", [s.id for s in d.subgraphs] == ["one", "two", "inner"])
check("a later top-level mention doesn't move a node", [n.id for n in d.nodes] == ["A", "B", "C", "D"] and sg["one"].members == ["A", "B"])

d = parse("flowchart TD\nsubgraph s\nA\nend\nsubgraph t\nA --> B\nend\n")
check("first-mention-wins membership", {s.id: s.members for s in d.subgraphs} == {"s": ["A"], "t": ["B"]})

for bad, why in (
    ("flowchart TD\nsubgraph s\nA\nend\nA --> s\n", "edge to a subgraph id"),
    ("flowchart TD\nsubgraph s\nA\nend\nsubgraph s\nB\nend\n", "duplicate subgraph id"),
    ("flowchart TD\nsubgraph\nA\nend\n", "subgraph with no id/title"),
):
    try:
        parse(bad)
        check(f"MermaidParseError: {why}", False)
    except MermaidParseError:
        check(f"MermaidParseError: {why}", True)

d = parse("flowchart TD\nsubgraph s\nA\n")
check("unclosed subgraph is tolerated", len(d.subgraphs) == 1)
d = parse("flowchart TD\nA\nend\nB\n")
check("stray `end` is tolerated", len(d.nodes) == 2)

# ---- subgraph layout --------------------------------------------------


def overlaps(a, b):
    return a.intersects(b) and not (a.contains(b) or b.contains(a))


for direction in ("TD", "BT", "LR", "RL"):
    d = parse(
        f"flowchart {direction}\n"
        "Start --> A\n"
        "subgraph g1 [Group One]\n"
        "  A --> B --> C\n"
        "  subgraph g2 [Nested]\n"
        "    D\n"
        "  end\n"
        "end\n"
        "A --> X\n"
        "X --> Y --> Z\n"
        "B --> D\n"
        "C --> End\n"
        "subgraph g3 [Other]\n"
        "  P --> Q\n"
        "end\n"
        "Start --> P\n"
    )
    r = layout(d, measure)
    members = {"g1": {"A", "B", "C", "D"}, "g2": {"D"}, "g3": {"P", "Q"}}
    boxes = {k: v.rect for k, v in r.subgraphs.items()}
    check(f"{direction}: one box per non-empty subgraph", set(boxes) == {"g1", "g2", "g3"})
    check(
        f"{direction}: each box contains all its members",
        all(boxes[g].contains(r.nodes[n].rect) for g, ns in members.items() for n in ns),
    )
    check(
        f"{direction}: no non-member node intersects a box",
        all(
            not boxes[g].intersects(r.nodes[n].rect)
            for g, ns in members.items()
            for n in r.nodes
            if n not in ns
        ),
    )
    check(f"{direction}: nested box is inside its parent", boxes["g1"].contains(boxes["g2"]))
    check(f"{direction}: sibling boxes don't overlap", not boxes["g1"].intersects(boxes["g3"]))
    check(
        f"{direction}: everything is inside the scene",
        all(b.left() >= 0 and b.top() >= 0 and b.right() <= r.width and b.bottom() <= r.height for b in boxes.values())
        and all(n.x >= 0 and n.y >= 0 and n.x + n.width <= r.width and n.y + n.height <= r.height for n in r.nodes.values()),
    )

# Empty subgraph draws nothing.
d = parse("flowchart TD\nsubgraph s [Empty]\nend\nA --> B\n")
check("empty subgraph produces no box", layout(d, measure).subgraphs == {})

# Diagram with no subgraphs: result carries none.
check("no subgraphs -> empty subgraphs map", layout(plain, measure).subgraphs == {})

d = parse("flowchart LR\nsubgraph s [A Rather Long Subgraph Title Indeed]\nA\nend\n")
svg = render_svg(build_scene(d, layout(d, measure), QPalette()))
check("svg renders a subgraph (smoke)", svg.startswith("<?xml") and "<svg" in svg)

# ---- docs and tags ----------------------------------------------------

check("node-styling tag registered", "mermaid classDef/class node styling #200895" in CURRENT_TAGS)
check("subgraph tag registered", "mermaid subgraph containment boxes #200896" in CURRENT_TAGS)
check("changelog entries exist", all(t in _NEW_FEATURES for t in ("mermaid classDef/class node styling #200895", "mermaid subgraph containment boxes #200896")))
check("tempui-markdown mentions subgraph and classDef", "subgraph" in _MARKDOWN_DOC and "classDef" in _MARKDOWN_DOC)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
