"""TODO b4d99a1: the focus logger (desk.focus_logger) with a real WorkspaceView,
close/overlapping frames and a real WidgetLogStore. Headless."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtCore import Qt  # noqa: E402
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


class MultiField(QWidget):
    def __init__(self):
        super().__init__()
        self.field1 = QLineEdit()
        self.field1.setObjectName("one")
        self.field2 = QLineEdit()
        self.field2.setObjectName("two")
        layout = QVBoxLayout(self)
        layout.addWidget(self.field1)
        layout.addWidget(self.field2)


def lines(store):
    return [e.text for e in store.query(FOCUS_LOG_NAME, limit=10_000)]


def kinds(store):
    return [line.split(" ", 1)[0] for line in lines(store)]


def build():
    store = WidgetLogStore()
    view = WorkspaceView()
    view.resize(900, 700)
    view.show()
    a = MultiField()
    b = QLineEdit()
    proxy_a = view.add_widget(a, "A", pos=(0, 0), size=(400, 300), instance_id="aaaa0001")
    proxy_b = view.add_widget(b, "B", pos=(420, 0), size=(400, 300), instance_id="bbbb0002")  # 20 units apart
    logger = FocusLogger(view, store)
    app.processEvents()  # let the initial window-activation focus settle before anything is recorded
    return store, view, logger, a, b, proxy_a, proxy_b


# --- off by default, nothing attached ---------------------------------
store, view, logger, a, b, pa, pb = build()
a.field1.setFocus(Qt.FocusReason.MouseFocusReason)
QTest.keyClicks(a.field1, "hello")
app.processEvents()
check("off by default: nothing logged", lines(store) == [] and not logger.is_enabled())
check("note() is a no-op when off", focus_logger.note("x") is None and lines(store) == [])

# --- scene focus change, intra-frame move, gap ---------------------------
logger.enable(tag="rec-test-1")
check("session_start recorded with tag", lines(store)[0] == "session_start rec=rec-test-1")
b.setFocus(Qt.FocusReason.MouseFocusReason)
app.processEvents()
out = lines(store)
item = next((l for l in out if l.startswith("focus_item") and "reason=MouseFocusReason" in l), "")
check("focus_item names old/new frames and reason", "old=aaaa0001" in item and "new=bbbb0002" in item and "reason=MouseFocusReason" in item)
check("focus_item reports the neighbour gap (20 units)", "gap=20.0" in item and "nbr=aaaa0001" in item and "overlap=0" in item)
check("focus_item carries the rec tag", item.endswith("rec=rec-test-1"))
check("a Python setFocus caller shows in py=", "py=" in item and "verify_focus_logger.py" in item)

a.field1.setFocus(Qt.FocusReason.MouseFocusReason)
app.processEvents()
a.field2.setFocus(Qt.FocusReason.OtherFocusReason)
app.processEvents()
out = lines(store)
moved = [l for l in out if l.startswith("focus_in") and "frame=aaaa0001" in l and "widget=QLineEdit#two" in l]
check("intra-frame focus move is logged (no scene signal fires for it)", len(moved) == 1 and "from=QLineEdit#one" in moved[0] and "reason=OtherFocusReason" in moved[0])

check("no scene-level focus_item fires for an intra-frame move", not any(l.startswith("focus_item") for l in out[out.index(moved[0]) - 2:]))

# --- typing never leaks characters --------------------------------------
store.clear()
a.field1.setFocus(Qt.FocusReason.MouseFocusReason)
app.processEvents()
store.clear()
QTest.keyClicks(view, "SECRETpassword")
QTest.keyClick(view, Qt.Key.Key_Tab)
app.processEvents()
text = "\n".join(lines(store))
check("typed characters never appear in the log", "SECRET" not in text.upper().replace("SESSION", "") and "password" not in text.lower())
check("printable keys are counted and coalesced before the Tab key", any(l.startswith("typing n=14") for l in lines(store)))
check("non-printable key is named", any(l.startswith("key key=Key_Tab mods=none") for l in lines(store)))
ks = kinds(store)
check("typing flushed before the key entry, in order", ks.index("typing") < ks.index("key"))
check("Tab navigation recorded", "tab_nav" in ks and "tab_reclaim" in ks)

# --- mouse press: stack and gap ----------------------------------------
store.clear()
overlap_proxy = view.add_widget(QLineEdit(), "C", pos=(300, 100), size=(300, 200), instance_id="cccc0003")  # overlaps A and B
app.processEvents()
store.clear()
view_point = view.mapFromScene(overlap_proxy.sceneBoundingRect().center())
QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view_point)
app.processEvents()
press = next((l for l in lines(store) if l.startswith("mouse_press")), "")
check("mouse_press names the frame and chrome part", "frame=cccc0003" in press and "chrome=content" in press and "button=LeftButton" in press)
check("mouse_press lists the stack front to back", "stack=cccc0003>" in press)
check("mouse_press reports overlap with a neighbour", "overlap=1" in press)

# --- z-order notes and chrome -------------------------------------------
store.clear()
view.send_to_back(pa.widget())
view.bring_to_front(pa.widget())
ks = kinds(store)
check("send_to_back/bring_to_front noted", ks == ["send_to_back", "bring_to_front"])

# --- disable detaches everything -----------------------------------------
logger.disable()
store.clear()
a.field2.setFocus(Qt.FocusReason.MouseFocusReason)
QTest.keyClicks(view, "zzz")
QTest.keyClick(view, Qt.Key.Key_Tab)
view.bring_to_front(pb.widget())
focus_logger.note("after_disable")
app.processEvents()
check("disabled: nothing further recorded (filters and signals detached)", lines(store) == [])
logger.enable()
check("re-enable works", lines(store)[-1] == "session_start")
logger.disable()
check("session_stop is the last entry of a session", lines(store)[-1] == "session_stop")

sys.exit(1 if failed else 0)
