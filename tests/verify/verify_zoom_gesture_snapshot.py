"""TODO 19052bc: while a continuous zoom (wheel/pinch/slider) is in flight,
frames show a cached pixmap of their content instead of live content (see
plans/zoom-gesture-snapshot.md). Real WorkspaceView and frames, headless."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtGui import QWheelEvent  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit, QPlainTextEdit  # noqa: E402

app = QApplication(sys.argv)

from desk.shell.canvas import ZOOM_GESTURE_END_MS, WorkspaceView  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


view = WorkspaceView()
view.resize(900, 700)
view.show()
live = []
for i in range(3):
    label = QLabel(f"widget {i}")
    proxy = view.add_widget(label, title=f"W{i}", pos=(-400 + 250 * i, -100), size=(220, 160), instance_id=f"w{i}")
    live.append(proxy.widget())
editor = QPlainTextEdit()
focused = view.add_widget(editor, title="Focused", pos=(-400, 150), size=(300, 200), instance_id="foc").widget()
web = view.add_widget(QWebEngineView(), title="Web", pos=(0, 150), size=(300, 200), instance_id="web").widget()
pinned = view.add_widget(QLabel("pinned"), title="Pinned", pos=(350, 150), size=(200, 150), instance_id="pin").widget()
tiny = view.add_widget(QLabel("tiny"), title="Tiny", pos=(-500, -300), size=(200, 120), instance_id="tiny").widget()
app.processEvents()
editor.setFocus()
app.processEvents()
pinned.set_hud_pinned(True)
for f in view._frames:
    check(f"sanity: {f.instance_id} starts live", f._content_stack.currentIndex() == 0 and not f.zoom_snapshotted)

# -- a wheel/pinch zoom starts a gesture
view._apply_zoom(1.1)
check("the first zoom event starts a gesture", view._zoom_gesture_active)
check("an ordinary frame shows its snapshot", all(f.zoom_snapshotted and f._content_stack.currentIndex() == 1 for f in live))
check("... a real, non-empty pixmap of the live content", live[0]._snapshot_page.pixmap is not None and not live[0]._snapshot_page.pixmap.isNull() and live[0]._snapshot_page.pixmap.size().width() >= 1)
check("the keyboard-focused frame stays live", not focused.zoom_snapshotted and focused._content_stack.currentIndex() == 0)
check("a frame showing a web view stays live", not web.zoom_snapshotted)
check("a HUD-pinned frame stays live", not pinned.zoom_snapshotted)
first = live[0]._snapshot_page.pixmap.cacheKey()
view._apply_zoom(1.1)
view._apply_zoom(0.95)
check("further events in the gesture reuse the same snapshots (no re-grab)", live[0]._snapshot_page.pixmap.cacheKey() == first)
check("the chrome still rescaled with the zoom", abs(live[0]._view_scale - view._scale) < 1e-9)
check("the content stack never changed the frame's size", all(f.size().width() == 220 for f in live))

# -- the gesture ends once events stop
QTest.qWait(ZOOM_GESTURE_END_MS + 150)
check("after the debounce the gesture is over", not view._zoom_gesture_active)
check("every frame is back on live content", all(not f.zoom_snapshotted and f._content_stack.currentIndex() == 0 for f in view._frames))
check("the cached pixmaps are released", all(f._snapshot_page.pixmap is None for f in view._frames))

# -- a new gesture starts a fresh one
view._apply_zoom(1.05)
check("a later zoom starts a new gesture", view._zoom_gesture_active and live[0].zoom_snapshotted)
QTest.qWait(ZOOM_GESTURE_END_MS + 150)

# -- discrete zooms never snapshot
view.reset_zoom()
check("reset (a discrete zoom) does not snapshot", not view._zoom_gesture_active and not any(f.zoom_snapshotted for f in view._frames))
view.zoom_to_fit()
check("zoom-to-fit does not snapshot", not any(f.zoom_snapshotted for f in view._frames))
view.set_view_state(0, 0, 0.8)
check("restoring a saved view does not snapshot", not any(f.zoom_snapshotted for f in view._frames))

# -- the slider is a continuous gesture
view.zoom_control.zoom_changed.emit(1.4)
check("a slider drag is a gesture", view._zoom_gesture_active and live[0].zoom_snapshotted)
QTest.qWait(ZOOM_GESTURE_END_MS + 150)
check("... that ends too", not view._zoom_gesture_active and not live[0].zoom_snapshotted)

# -- an already-greeked frame is left alone
view.reset_zoom()
tiny.resize(60, 20)
tiny.set_view_scale(0.1)
check("sanity: the small frame is greeked", tiny.is_greeked)
view._apply_zoom(1.01)
check("a greeked frame is not snapshotted", not tiny.zoom_snapshotted)
QTest.qWait(ZOOM_GESTURE_END_MS + 150)

# -- clearing the canvas mid-gesture leaves nothing stuck
view._apply_zoom(1.02)
app.processEvents()  # let set_view_scale's deferred size reassertion run before the frames die
view.clear_widgets()
check("clearing the canvas ends the gesture", not view._zoom_gesture_active)

# -- the real wheel path goes through it
view2 = WorkspaceView()
view2.resize(600, 400)
view2.show()
f2 = view2.add_widget(QLabel("x"), title="X", pos=(-100, -100), size=(200, 150), instance_id="x").widget()
app.processEvents()
from PyQt6.QtCore import QPoint, Qt  # noqa: E402

wheel = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
view2.wheelEvent(wheel)
check("a wheel zoom over empty canvas runs the gesture", view2._zoom_gesture_active and f2.zoom_snapshotted)
QTest.qWait(ZOOM_GESTURE_END_MS + 150)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
