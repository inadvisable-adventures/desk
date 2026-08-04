import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from desk.shell.canvas import WorkspaceView  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

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


def test_zoom_control_visible_immediately_at_default_scale():
    view = WorkspaceView()
    view.show()
    app.processEvents()
    check("zoom control is visible right after construction, at default (100%) scale", view.zoom_control.isVisible())


def test_zoom_control_stays_visible_across_a_zoom_round_trip():
    view = WorkspaceView()
    view.show()
    app.processEvents()

    view._apply_zoom_centered(2.0)
    app.processEvents()
    check("zoom control stays visible after zooming in", view.zoom_control.isVisible())

    view._apply_zoom_centered(1.0)
    app.processEvents()
    check(
        "zoom control stays visible after zooming back to exactly 100% (previously would have hidden again)",
        view.zoom_control.isVisible(),
    )


test_zoom_control_visible_immediately_at_default_scale()
test_zoom_control_stays_visible_across_a_zoom_round_trip()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
