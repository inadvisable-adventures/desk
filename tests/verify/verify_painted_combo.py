"""TODO 5303de6 (and 0f2c458, ff0628a): PaintedComboBox -- QComboBox API
subset, popup placement under canvas zoom (headless: the offscreen
platform CANNOT verify real OS window placement, only that our computed
rect/placement logic is right; see LEARNINGS.md), popup has no parent,
a pan/zoom while open closes it, and picking an item doesn't crash."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

import desk.shell.widget_frame  # noqa: E402,F401  (imported before QApplication -- WebEngine ordering)
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401
from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QWidget,
)

app = QApplication(sys.argv)
from desk.shell.qt_controls import PaintedComboBox  # noqa: E402
from desk.shell.qt_controls.painted_combo import _DRIFT_POLL_MS  # noqa: E402
from desk.shell.widget_frame import WidgetFrame  # noqa: E402

failed = 0
# The offscreen platform places a popup ~2px off the requested point (a
# platform frame offset); real placement on macOS was checked against
# real screen pixels by hand (TODO 5303de6's plan), delta 0.
TOL = 3


def check(name, ok):
    global failed
    print(f"{name}: {'PASS' if ok else 'FAIL'}")
    failed += 0 if ok else 1


def make_combo():
    combo = PaintedComboBox()
    for t in ("Alpha", "Beta", "Gamma"):
        combo.addItem(t)
    return combo


def settle(ms=0):
    QTest.qWait(ms)
    app.processEvents()


# -- API subset ---------------------------------------------------------
combo = make_combo()
seen = []
combo.currentIndexChanged.connect(seen.append)
combo.setCurrentIndex(2)
check("api", combo.currentIndex() == 2 and combo.currentText() == "Gamma" and seen == [2] and combo.count() == 3)
check("itemText", combo.itemText(0) == "Alpha" and combo.itemText(9) == "")
check("renders", not combo.grab().toImage().isNull())

# -- embedded in a real WidgetFrame, sibling widgets, at several zooms --------
content = QWidget()
row = QHBoxLayout(content)
row.addWidget(QLabel("status"), stretch=1)
combo = make_combo()
row.addWidget(combo)
row.addWidget(make_combo())
frame = WidgetFrame("test", content)
frame.resize(420, 120)
scene = QGraphicsScene()
proxy = scene.addWidget(frame)
view = QGraphicsView(scene)
view.resize(700, 500)
view.show()
settle(50)

for factor in (1.0, 0.5, 0.3):
    view.resetTransform()
    view.scale(factor, factor)
    settle(50)
    rect, scale = combo._screen_rect_and_scale()
    check(f"scale {factor}: rect width tracks zoom", abs(rect.width() - combo.width() * factor) < 2 and abs(scale - factor) < 1e-6)
    combo._open_popup()
    pop = combo._popup
    check(f"scale {factor}: popup opened", pop is not None)
    if pop is not None:
        check(f"scale {factor}: popup below control", abs(pop.x() - rect.left()) < TOL and abs(pop.y() - rect.bottom()) < TOL)
        check(f"scale {factor}: popup width matches", abs(pop.width() - max(int(rect.width()), 40)) < 2)
        check(f"scale {factor}: popup has no parent (TODO 7bc07a8 origin bug)", pop.parent() is None)
        pop.close()
        settle()

# -- real click through the proxy opens the popup at the control -----------------
view.resetTransform()
settle(50)
rect, _ = combo._screen_rect_and_scale()
local = combo.mapTo(frame, QPoint(combo.width() // 2, combo.height() // 2))
scene_pt = proxy.mapToScene(local.x(), local.y())
QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(scene_pt))
settle(50)
check("real click: popup opened", combo._popup is not None)
if combo._popup is not None:
    check("real click: popup placed under control", abs(combo._popup.x() - rect.left()) < TOL and abs(combo._popup.y() - rect.bottom()) < TOL)

    # -- no false positive: an idle popup survives a watchdog tick
    settle(_DRIFT_POLL_MS * 2)
    check("idle popup survives watchdog", combo._popup is not None)

    # -- zooming while open closes it (TODO 0532852)
    view.scale(0.7, 0.7)
    settle(_DRIFT_POLL_MS * 3)
    check("zoom while open closes popup", combo._popup is None)

# -- picking an item must not crash (TODO ff0628a) ---------------------------
view.resetTransform()
settle(50)
combo2 = make_combo()
seen2 = []
combo2.currentIndexChanged.connect(seen2.append)
combo2._open_popup()
pop = combo2._popup
check("select: popup opened", pop is not None)
if pop is not None:
    item = pop.list.item(1)
    pop.list.setCurrentItem(item)
    pop._choose(item)  # same call QListWidget.itemClicked makes on a real click
    settle()
    settle()
    check("select: currentIndex updated", combo2.currentIndex() == 1)
    check("select: currentIndexChanged fired once", seen2 == [1])

sys.exit(1 if failed else 0)
