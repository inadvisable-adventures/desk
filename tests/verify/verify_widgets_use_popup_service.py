"""TODO 5242aeb: a real, automated regression guard -- a widget-content
QMessageBox (parented to a widget's own content, embedded in a
QGraphicsProxyWidget on the canvas, not a real top-level window) renders
as a detached macOS window (TODO 359684f). Scans every real
widgets/*/widget.py for a live QMessageBox.(question|warning|
information|critical)(...) call -- a plain regex, not an AST-aware
check, deliberately simple and fast. A widget should use
current_context.get_popup_opener() (desk_services.popups) instead. Does
not scan src/desk/shell/window.py itself: DeskWindow is a real
top-level QMainWindow, never embedded in a QGraphicsProxyWidget, so its
own QMessageBox usage was never subject to this bug.
"""

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


REPO_ROOT = Path(__file__).resolve().parents[2]
WIDGETS_DIR = REPO_ROOT / "widgets"
LIVE_CALL_RE = re.compile(r"QMessageBox\.(question|warning|information|critical)\s*\(")


def test_no_widget_calls_qmessagebox_directly():
    offenders = []
    for widget_py in sorted(WIDGETS_DIR.glob("*/widget.py")):
        text = widget_py.read_text()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if LIVE_CALL_RE.search(line):
                offenders.append(f"{widget_py.relative_to(WIDGETS_DIR.parent)}:{lineno}: {line.strip()}")
    check(
        "no widgets/*/widget.py calls QMessageBox.(question|warning|information|critical)(...) directly"
        + ("" if not offenders else " -- " + "; ".join(offenders)),
        not offenders,
    )


def test_the_check_itself_actually_catches_a_real_offender():
    # A same-shape sanity check on the regex itself, so this guard
    # can't silently stop working (e.g. from a refactor of the regex)
    # without a test noticing -- mirrors this project's own "verify the
    # verifier" precedent for other scanning-based checks.
    sample = 'QMessageBox.warning(self, "title", "message")'
    check("the regex matches the exact pattern this bug looks like", LIVE_CALL_RE.search(sample) is not None)
    check(
        "the regex does not false-positive on a comment mentioning QMessageBox by name",
        LIVE_CALL_RE.search("# not a QMessageBox parented to self") is None,
    )


test_no_widget_calls_qmessagebox_directly()
test_the_check_itself_actually_catches_a_real_offender()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
