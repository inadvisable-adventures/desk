"""TODO 48fd3e0: focus log cause attribution -- `py=native` when only the event-loop entry is on the
stack, plus `ev=` (events dispatched just before) and `painted=` (frames repainted just before) on
focus entries. Headless, real WorkspaceView.

Every step is pumped through the SAME `app.processEvents()` line: the logger strips the Python frames
beneath the event loop by (code, line), exactly as `main` calling `exec()` always sits on one line.
"""
import os
import re
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtCore import Qt, QTimer  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget  # noqa: E402

from desk import focus_logger  # noqa: E402
from desk.focus_logger import FOCUS_LOG_NAME, FocusLogger  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.widget_logs import WidgetLogStore  # noqa: E402

app = QApplication(sys.argv)
failed = 0


def check(name, ok):
    global failed
    print(("PASS" if ok else "FAIL"), name)
    failed += 0 if ok else 1


store = WidgetLogStore()
view = WorkspaceView()
view.resize(900, 700)
view.show()
a = QLineEdit()
b = QLineEdit()
proxy_a = view.add_widget(a, "A", pos=(0, 0), size=(400, 300), instance_id="aaaa0001")
view.add_widget(b, "B", pos=(420, 0), size=(400, 300), instance_id="bbbb0002")
logger = FocusLogger(view, store)
app.processEvents()


def entries():
    return [e.text for e in store.query(FOCUS_LOG_NAME, limit=10_000)]


def between(start, end):
    out = entries()
    return out[out.index(start) + 1 : out.index(end)]


def field(line, key):
    m = re.search(rf"(?:^| ){key}=(\S+)", line)
    return m.group(1) if m else None


timer = QTimer(view)
timer.setSingleShot(True)
timer.timeout.connect(b.setFocus)  # a C++ slot: no Python frame runs when it fires


def step_nothing():
    pass


def step_programmatic():
    a.setFocus(Qt.FocusReason.OtherFocusReason)


def step_native_timer():
    timer.start(0)
    time.sleep(0.02)  # let the timer come due; the pump below fires it from the loop


def step_click_driven():
    point = view.mapFromScene(proxy_a.sceneBoundingRect().center())
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)


def step_after_paint():
    a.setFocus(Qt.FocusReason.OtherFocusReason)
    view.viewport().repaint()
    b.setFocus(Qt.FocusReason.OtherFocusReason)


logger.enable()
for step in (step_nothing, step_programmatic, step_native_timer, step_click_driven, step_after_paint):
    focus_logger.note("mark", step=step.__name__)
    step()
    app.processEvents()  # the one loop line the logger's base was captured from
focus_logger.note("mark", step="end")
out = entries()


def chunk(name):
    start = next(i for i, l in enumerate(out) if l == f"mark step={name}")
    end = next((i for i, l in enumerate(out) if i > start and l.startswith("mark ")), len(out))
    return out[start + 1 : end]


check("loop base captured on the first loop turn", len(focus_logger._loop_base) > 0)

prog = [l for l in chunk("step_programmatic") if l.startswith("focus_item")]
check("a programmatic setFocus still names its Python caller (not stripped, not native)",
      len(prog) == 1 and "step_programmatic" in field(prog[0], "py") and field(prog[0], "py") != "native")

native = [l for l in chunk("step_native_timer") if l.startswith("focus_item")]
check("a focus change made by Qt alone reports py=native", len(native) == 1 and field(native[0], "py") == "native")
check("... and its ev= names the Timer that drove it", len(native) == 1 and "Timer:" in (field(native[0], "ev") or ""))
native_in = [l for l in chunk("step_native_timer") if l.startswith("focus_in")]
check("focus_in carries the same attribution", len(native_in) == 1 and field(native_in[0], "py") == "native"
      and "Timer:" in (field(native_in[0], "ev") or ""))

clicked = [l for l in chunk("step_click_driven") if l.startswith("focus_item")]
check("a click-driven change shows the press in ev=", bool(clicked) and "MouseButtonPress:" in (field(clicked[0], "ev") or ""))
check("... and is not py=native (the canvas mouse handler is on the stack)",
      bool(clicked) and "mousePressEvent" in field(clicked[0], "py"))

painted_lines = [l for l in chunk("step_after_paint") if l.startswith("focus_item") and "painted=" in l]
check("painted= names the frames that repainted just before a focus change",
      bool(painted_lines) and "aaaa0001:" in field(painted_lines[-1], "painted"))
ages = [int(p.rsplit(":", 1)[1]) for l in painted_lines for p in field(l, "painted").split(",")]
check("painted= ages are within the window", bool(ages) and all(0 <= age <= focus_logger.PAINT_WINDOW_MS for age in ages))

# --- no paints / events recorded: both fields are omitted ----------------------
logger._events.clear()
logger._painted.clear()
check("no events and no paints: neither ev= nor painted= is added", logger._cause_fields() == {})

# --- a stale paint ages out of painted= ------------------------------------
logger._painted["old0001"] = time.monotonic() - 10
check("a paint older than the window is not reported", "painted" not in logger._cause_fields())

# --- no Python frame beneath the slot at all (e.g. teardown) must not raise ----
real_getframe = sys._getframe


def boom(depth=0):
    raise ValueError("call stack is not deep enough")


sys._getframe = boom
try:
    stack = focus_logger._python_stack()
finally:
    sys._getframe = real_getframe
check("_python_stack tolerates an empty stack", stack == "native")

# --- existing fields untouched ----------------------------------------------
sample = next(l for l in out if l.startswith("focus_item"))
check("existing focus_item fields are still present", all(field(sample, k) is not None for k in ("old", "new", "reason", "widget", "py")))

# --- disable clears the new state -------------------------------------------
logger.disable()
check("disable() clears the loop base and the remembered events", focus_logger._loop_base == () and not logger._events and not logger._painted)

sys.exit(1 if failed else 0)
