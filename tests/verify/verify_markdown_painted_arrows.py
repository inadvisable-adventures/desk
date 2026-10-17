"""TODO 333bebf: Markdown TOC branch arrows and section-toggle arrows are
painted by us (not native style) and the section arrow scales with level."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.shell.qt_controls.painted_branches import PaintedBranchTreeWidget  # noqa: E402
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("md_widget", "widgets/markdown/widget.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
from pathlib import Path  # noqa: E402

failed = 0


def check(name, ok):
    global failed
    print(f"{name}: {'PASS' if ok else 'FAIL'}")
    failed += 0 if ok else 1


def section(level):
    return mod._Section(title="T", level=level)


s1 = mod._SectionWidget(section(1), Path("."))
s2 = mod._SectionWidget(section(2), Path("."))
check("section arrow is not native", s1.toggle.arrowType().name == "NoArrow")
check("arrow icon present", not s1.toggle.icon().isNull())
check("H1 arrow >= H2 arrow", s1.toggle.iconSize().width() >= s2.toggle.iconSize().width())
check("H1 arrow > H2 arrow strictly", s1.toggle.iconSize().width() > s2.toggle.iconSize().width())
s1.set_expanded(False)
check("collapsed icon present", not s1.toggle.icon().isNull() and not s1.body.isVisibleTo(s1))

w = mod.MarkdownWidget()
check("TOC is painted-branch tree", isinstance(w._toc, PaintedBranchTreeWidget))
from PyQt6.QtWidgets import QTreeWidgetItem  # noqa: E402

top = QTreeWidgetItem(["a"])
w._toc.addTopLevelItem(top)
top.addChild(QTreeWidgetItem(["b"]))
w._toc.expandAll()
w._toc.resize(200, 200)
w._toc.show()
img = w._toc.grab().toImage()
check("TOC renders", not img.isNull())
sys.exit(1 if failed else 0)
