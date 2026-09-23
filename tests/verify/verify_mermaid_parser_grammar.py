# TODO 90dd6e6: desk.mermaid's parser gains stadium nodes, unpiped
# inline edge labels, and quoted labels that can contain a shape's own
# delimiter characters. No dedicated parser-only test file existed
# before this -- the two existing mermaid verify scripts only exercise
# the transform layer.
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PyQt6.QtGui import QFont, QFontMetricsF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import desk.mermaid as mermaid  # noqa: E402
from desk.mermaid import MermaidParseError, build_scene, layout, parse  # noqa: E402
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


def node_shapes(diagram):
    return {n.id: (n.label, n.shape) for n in diagram.nodes}


def edges(diagram):
    return [(e.source, e.target, e.label, e.arrow, e.dotted) for e in diagram.edges]


# ---- stadium nodes ---------------------------------------------------

d = parse("flowchart TD\nStart([Begin])\nDone([Finished])\n")
check("stadium: parses as its own shape", node_shapes(d) == {"Start": ("Begin", "stadium"), "Done": ("Finished", "stadium")})

d = parse("flowchart TD\nStart([Begin]) --> Body[Do work] --> Done([Finished])\n")
check(
    "stadium: mixes with rect in the same flowchart",
    node_shapes(d) == {"Start": ("Begin", "stadium"), "Body": ("Do work", "rect"), "Done": ("Finished", "stadium")},
)

d = parse("flowchart TD\nA(Plain rounded)\n")
check("regression: plain rounded shape (single parens) is unaffected by the new stadium alternative", node_shapes(d)["A"] == ("Plain rounded", "rounded"))

d = parse("flowchart TD\nA((Circle))\n")
check("regression: circle (double parens) is unaffected", node_shapes(d)["A"] == ("Circle", "circle"))


# ---- unpiped inline edge labels ---------------------------------------

# The feedback's own motivating case: before this fix, "Check -- yes"
# was folded into node Check's own token (a bogus id), and the error
# pointed at that token instead of recognizing an edge at all.
d = parse("flowchart TD\nCheck -- yes --> Body\n")
check("unpiped solid arrow: label lands on the edge, not folded into a node id", node_shapes(d) == {"Check": ("Check", "rect"), "Body": ("Body", "rect")})
check("unpiped solid arrow: edge has the label, is an arrow, not dotted", edges(d) == [("Check", "Body", "yes", True, False)])

d = parse("flowchart TD\nA -- side note --- B\n")
check("unpiped solid open (no arrowhead)", edges(d) == [("A", "B", "side note", False, False)])

d = parse("flowchart TD\nA -. dotted arrow .-> B\n")
check("unpiped dotted arrow", edges(d) == [("A", "B", "dotted arrow", True, True)])

d = parse("flowchart TD\nA -. dotted open .- B\nC -. another arrow .-> D\n")
check(
    "unpiped dotted open next to unpiped dotted arrow: the (?!>) lookahead disambiguates both, on adjacent lines",
    edges(d) == [("A", "B", "dotted open", False, True), ("C", "D", "another arrow", True, True)],
)

d = parse("flowchart TD\nA -- hyphenated-word --> B\n")
check("unpiped label content may itself contain a hyphen", edges(d) == [("A", "B", "hyphenated-word", True, False)])

# Regression: existing piped-label and bare-operator forms still work.
d = parse("flowchart TD\nA -->|piped| B\nC --> D\nE --- F\nG -.-> H\nI -.- J\n")
check(
    "regression: piped labels and every bare operator still parse as before",
    edges(d)
    == [
        ("A", "B", "piped", True, False),
        ("C", "D", None, True, False),
        ("E", "F", None, False, False),
        ("G", "H", None, True, True),
        ("I", "J", None, False, True),
    ],
)


# ---- quoted labels -----------------------------------------------------

d = parse('flowchart TD\nA["a [b] c"] --> B\n')
check("quoted rect label may contain its own [] delimiters", node_shapes(d)["A"] == ("a [b] c", "rect"))

d = parse('flowchart TD\nA("a (b) c") --> B\n')
check("quoted rounded label may contain its own () delimiters", node_shapes(d)["A"] == ("a (b) c", "rounded"))

d = parse('flowchart TD\nA{"a {b} c"} --> B\n')
check("quoted diamond label may contain its own {} delimiters", node_shapes(d)["A"] == ("a {b} c", "diamond"))

d = parse('flowchart TD\nA(("a (b) (c)")) --> B\n')
check("quoted circle label may contain its own () delimiters", node_shapes(d)["A"] == ("a (b) (c)", "circle"))

d = parse('flowchart TD\nA(["a (b) [c]"]) --> B\n')
check("quoted stadium label may contain both its own () and [] delimiters", node_shapes(d)["A"] == ("a (b) [c]", "stadium"))

d = parse('flowchart TD\nA[""] --> B\n')
check("an empty quoted label falls back to the node id, same as an empty unquoted one", node_shapes(d)["A"] == ("A", "rect"))

d = parse('flowchart TD\nA["no special chars"] --> B\n')
check("regression: a quoted label with nothing special still parses (quoting is optional, not required)", node_shapes(d)["A"] == ("no special chars", "rect"))


# ---- rendering smoke test (no crash) -----------------------------------

diagram = parse("flowchart TD\nStart([Begin]) -- go --> Mid[Step]\nMid --> End([Done])\n")
fm = QFontMetricsF(QFont())
result = layout(diagram, lambda text: (fm.horizontalAdvance(text), fm.height()))
scene = build_scene(diagram, result, app.palette())
check("stadium node + unpiped-label edge render without raising", len(scene.items()) > 0)


# ---- documentation -------------------------------------------------------

flat_docstring = " ".join(mermaid.__doc__.split())
check("module docstring names the stadium shape", "stadium" in flat_docstring)
check("module docstring names the unpiped/inline edge-label form", "unpiped" in flat_docstring or "inline" in flat_docstring)
check("module docstring mentions quoting", "quot" in flat_docstring)

TAG = "mermaid parser: stadium, unpiped labels, quotes #183003"
check("tag is in CURRENT_TAGS with a _NEW_FEATURES entry", TAG in CURRENT_TAGS and TAG in _NEW_FEATURES)
flat_markdown_doc = " ".join(_MARKDOWN_DOC.split())
check("tempui-markdown.md documents the stadium shape", "stadium" in flat_markdown_doc)
check("tempui-markdown.md documents unpiped edge labels", "unpiped" in flat_markdown_doc or "inline" in flat_markdown_doc)
check("tempui-markdown.md documents quoting", "quot" in flat_markdown_doc)


# ---- MermaidParseError still raised for genuinely bad syntax -----------

try:
    parse("flowchart TD\nA[[unterminated\n")
    check("genuinely malformed node syntax still raises MermaidParseError", False)
except MermaidParseError:
    check("genuinely malformed node syntax still raises MermaidParseError", True)


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
