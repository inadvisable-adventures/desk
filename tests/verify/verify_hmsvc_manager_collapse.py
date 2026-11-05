import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "widgets" / "hmsvc_manager"))

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.shell import current_context  # noqa: E402

import widget as mgr  # noqa: E402

failed = 0


def check(name, cond):
    global failed
    print(("PASS: " if cond else "FAIL: ") + name)
    failed += 0 if cond else 1


def svc(name):
    return {"name": name, "status": "running", "port": 1234, "pid": 9, "exit_code": None,
            "url": "http://127.0.0.1:1234/", "description": "DESCTEXT"}


class FakeManager:
    def list_services(self):
        return [svc("alpha"), svc("beta")]

    def get_logs(self, name, n):
        return []


current_context.set_hmsvc_manager(FakeManager())
w = mgr.build()


def row(i):
    return w._list.itemWidget(w._list.item(i))


def texts(r):
    return [b.text() for b in r.findChildren(QPushButton)], " ".join(l.text() for l in r.findChildren(QLabel))


buttons, label = texts(row(0))
check("expanded shows description", "DESCTEXT" in label and "Collapse" in buttons)
next(b for b in row(0).findChildren(QPushButton) if b.text() == "Collapse").click()
buttons, label = texts(row(0))
check("collapsed hides details", "DESCTEXT" not in label and "127.0.0.1" not in label)
check("collapsed keeps name+status", "alpha" in label and "running" in label)
check("collapsed keeps buttons + Expand", all(t in buttons for t in ("Start", "Stop", "Restart", "Logs", "Source", "Expand")))
check("other entry unaffected", "DESCTEXT" in texts(row(1))[1])
w._on_mediated_event(mgr.HMSVC_CHANGED_EVENT, {"services": [svc("alpha"), svc("beta")]}, "x")
check("collapse survives repopulate", "DESCTEXT" not in texts(row(0))[1])
next(b for b in row(0).findChildren(QPushButton) if b.text() == "Expand").click()
check("expand restores", "DESCTEXT" in texts(row(0))[1])
sys.exit(1 if failed else 0)
