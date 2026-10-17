"""TODO d4c0d68: the PaintedComboBox rule is documented in the root conventions doc, referenced from CLAUDE.md,
and reaches agents in other projects via the tempui docs and the changelog."""
import sys
from pathlib import Path

sys.path.insert(0, "src")
from desk import temp_ui  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
failed = 0


def check(name, ok):
    global failed
    print(f"{name}: {'PASS' if ok else 'FAIL'}")
    failed += 0 if ok else 1


doc = (ROOT / "python-widget-conventions.md").read_text()
check("conventions doc names PaintedComboBox + qt_controls", "PaintedComboBox" in doc and "qt_controls" in doc)
check("CLAUDE.md references it", "./python-widget-conventions.md" in (ROOT / "CLAUDE.md").read_text())

tag = "python widgets use qt_controls, not QComboBox #514695"
check("tag in CURRENT_TAGS", tag in temp_ui.CURRENT_TAGS)
check("new-features entry", tag in temp_ui._NEW_FEATURES and "PaintedComboBox" in temp_ui._NEW_FEATURES[tag])
check("changelog doc renders the entry", tag in temp_ui._NEW_FEATURES_DOC)
check("main doc Project widgets section is self-contained", "desk.shell.qt_controls" in temp_ui.__dict__.get("TEMPUI_DOC", "") or any("desk.shell.qt_controls" in v for v in vars(temp_ui).values() if isinstance(v, str) and "## Project widgets" in v))
sys.exit(1 if failed else 0)
