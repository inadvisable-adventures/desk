"""TODO 21e6e04: no raw `QComboBox` anywhere in Desk's own Python code
(`src/desk/`, `widgets/`) outside `src/desk/shell/qt_controls/`. A native
QComboBox misrenders and misplaces its popup when embedded in the
Workspace Canvas's QGraphicsProxyWidget; use
`desk.shell.qt_controls.PaintedComboBox` (see that package's docstring and
LEARNINGS.md). Mentions in comments and docstrings count too -- reword
them ("native combo box") rather than allowlist, so the check stays a
plain substring scan.

This only covers this repo; a project's own `desk_widgets/` python widgets
are out of its reach (see PARKINGLOT.md)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [ROOT / "src" / "desk", ROOT / "widgets"]
ALLOWED_DIR = ROOT / "src" / "desk" / "shell" / "qt_controls"

offenders: list[str] = []
scanned = 0
for base in SCAN_DIRS:
    for path in sorted(base.rglob("*.py")):
        if ALLOWED_DIR in path.parents:
            continue
        scanned += 1
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "QComboBox" in line:
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")

if scanned < 50:
    print(f"FAIL: scanned only {scanned} files; the scan roots look wrong")
    sys.exit(1)
if offenders:
    print("FAIL: raw QComboBox found; use desk.shell.qt_controls.PaintedComboBox:")
    for o in offenders:
        print("  " + o)
    sys.exit(1)
print(f"PASS: no raw QComboBox in {scanned} files outside qt_controls/")
