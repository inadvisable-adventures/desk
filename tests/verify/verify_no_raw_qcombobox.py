"""TODO 21e6e04: no raw `QComboBox` anywhere in Desk's own Python code
(`src/desk/`, `widgets/`) outside `src/desk/shell/qt_controls/`. A native
QComboBox misrenders and misplaces its popup when embedded in the
Workspace Canvas's QGraphicsProxyWidget; use
`desk.shell.qt_controls.PaintedComboBox` (see that package's docstring and
LEARNINGS.md). The scan is AST-based: it flags real
uses (a name, an attribute, an import), and ignores comments and string
literals, so prose that names the class (e.g. `temp_ui.py`'s agent-facing
docs) is not a false positive (TODO 118d5ab).

This only covers this repo; a project's own `desk_widgets/` python widgets
are out of its reach (see PARKINGLOT.md)."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [ROOT / "src" / "desk", ROOT / "widgets"]
ALLOWED_DIR = ROOT / "src" / "desk" / "shell" / "qt_controls"


def raw_uses(source: str) -> list[int]:
    """Line numbers of real `QComboBox` names, attributes and imports."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id == "QComboBox":
            lines.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == "QComboBox":
            lines.append(node.lineno)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            lines += [node.lineno for a in node.names if a.name.split(".")[-1] == "QComboBox"]
    return lines


offenders: list[str] = []
scanned = 0
for base in SCAN_DIRS:
    for path in sorted(base.rglob("*.py")):
        if ALLOWED_DIR in path.parents:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8")
        src_lines = text.splitlines()
        for lineno in sorted(set(raw_uses(text))):
            offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {src_lines[lineno - 1].strip()}")

if scanned < 50:
    print(f"FAIL: scanned only {scanned} files; the scan roots look wrong")
    sys.exit(1)
if offenders:
    print("FAIL: raw QComboBox found; use desk.shell.qt_controls.PaintedComboBox:")
    for o in offenders:
        print("  " + o)
    sys.exit(1)
print(f"PASS: no raw QComboBox in {scanned} files outside qt_controls/")

# Sanity: the scanner must catch real uses and ignore prose.
assert raw_uses("from PyQt6.QtWidgets import QComboBox\nc = QComboBox()") == [1, 2]
assert raw_uses("import PyQt6.QtWidgets as w\nc = w.QComboBox()") == [2]
assert raw_uses('# QComboBox\nx = "use not QComboBox"\n"""QComboBox"""') == []
print("PASS: scanner catches planted uses and ignores prose")
