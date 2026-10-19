"""TODO 0593797: .gitignore questions are non-blocking notifications."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QMessageBox

from desk.shell.temp_ui_notifications import TempUiNotificationStack
from desk.shell.window import DeskWindow
from desk.temp_ui import INSTALLED_JOBS_RUST_TARGET_GITIGNORE_ENTRY, installed_jobs_gitignore_pending

app = QApplication.instance() or QApplication(sys.argv)
passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def buttons(banner):
    return {b.text(): b for b in banner.findChildren(type(banner.accept_button))}


stack = TempUiNotificationStack()
accepted = []
stack.notify_prompt(Path("k"), "Update .gitignore?", "details here", "Yes", lambda: accepted.append(1))
banner = stack._banners[Path("k")]
stack.show()
check("prompt banner has Yes and More info buttons", {"Yes", "More info"} <= set(buttons(banner)))
check("✕ dismiss button still present", "✕" in buttons(banner))
check("detail hidden initially", not banner._detail_label.isVisible())
before = stack.sizeHint().height()
buttons(banner)["More info"].click()
check("More info reveals detail", banner._detail_label.isVisible())
check("stack grows to fit", stack.sizeHint().height() > before)
resized = []
stack.resized.connect(lambda: resized.append(1))
buttons(banner)["More info"].click()
check("More info toggles and signals a resize", not banner._detail_label.isVisible() and resized)
check("accepting does not happen on body click", not accepted)
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent

banner.mousePressEvent(
    QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(2, 2), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
)
check("body click does nothing on a prompt", not accepted and Path("k") in stack._banners)
buttons(banner)["Yes"].click()
check("Yes runs the callback and removes the banner", accepted == [1] and Path("k") not in stack._banners)

stack.notify_prompt(Path("k"), "a", "d", "Yes", lambda: None)
stack.notify_prompt(Path("k"), "b", "d", "Yes", lambda: None)
check("same key replaces rather than stacks", len(stack._banners) == 1)
buttons(stack._banners[Path("k")])["✕"].click()
check("✕ dismisses", not stack._banners)

# Window wiring: no modal, nothing written until Yes.
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    directory = Path(d)
    subprocess.run(["git", "init", "-q", str(directory)], check=True)
    (directory / "desk-installed-jobs").mkdir()
    prompts = []

    class W:
        view = type("V", (), {"notify_temp_ui_prompt": lambda v, key, text, detail, label, cb: prompts.append(cb)})()

        def _confirm_fn(self, *a):
            raise AssertionError("modal confirm must not be used")

    QMessageBox.question = staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("modal")))
    DeskWindow._offer_gitignore_entry(W(), "installed_jobs", directory)
    check("pending -> one prompt offered, nothing written", len(prompts) == 1 and not (directory / ".gitignore").exists())
    prompts[0]()
    check("Yes writes the entry", INSTALLED_JOBS_RUST_TARGET_GITIGNORE_ENTRY in (directory / ".gitignore").read_text())
    check("no longer pending", not installed_jobs_gitignore_pending(directory))
    DeskWindow._offer_gitignore_entry(W(), "installed_jobs", directory)
    check("not pending -> no further prompt", len(prompts) == 1)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
