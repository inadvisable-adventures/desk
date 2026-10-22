"""TODO 2016312: the Scratch widget's "Send to agent" button and
DeskWindow.send_text_to_agent (plans/send-scratch-to-agent.md)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.shell.canvas import WorkspaceView  # noqa: E402
from desk.shell.python_widget import PythonWidgetHost  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("scratch_widget", REPO_ROOT / "widgets" / "scratch" / "widget.py")
scratch_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scratch_mod)

popups: list[str] = []
sent: list[tuple] = []
current_context.set_popup_opener(lambda title, message, buttons, default: popups.append(message))
current_context.set_scratch_agent_sender(lambda w, label, text: sent.append((w, label, text)))

# ---- widget side ----
w = scratch_mod.ScratchWidget()
check("button exists with its label", w._send_button.text() == "Send to agent")
w.send_to_agent()
check("empty Scratch: popup, nothing sent", len(popups) == 1 and "empty" in popups[0] and not sent)
w.body.setPlainText("   \n ")
w.send_to_agent()
check("whitespace-only Scratch counts as empty", len(popups) == 2 and not sent)
w.body.setPlainText("x" * (scratch_mod.MAX_SCRATCH_SEND_CHARS + 1))
w.send_to_agent()
check("over the cap: popup naming the limit, nothing sent", len(popups) == 3 and "400,000" in popups[2] and not sent)
text = "Line one\n  indented 'quote' \"dq\" {braces}\n\nlast"
w.body.setPlainText(text)
w.set_label("notes")
w._send_button.click()
check("normal: sender gets widget, label and exact text", sent == [(w, "notes", text)])
current_context.set_scratch_agent_sender(lambda *a: "boom")
w.send_to_agent()
check("sender error is shown", popups[-1] == "boom")

# ---- window side (real _place_widget replaced by a recorder; real frame geometry) ----
broker = HotReloadBroker()
view = WorkspaceView()
view.resize(900, 600)
view.show()
host = PythonWidgetHost("scratch", REPO_ROOT / "widgets" / "scratch", "widget.py", broker)
proxy = view.add_widget(host, title="Scratch", pos=(100, 50), size=(300, 200), instance_id="scr1")
source = host.current


class _FakeWin:
    def __init__(self, with_widget=True):
        self._widgets = {"claude_desk": type("W", (), {"default_size": (400, 300)})()} if with_widget else {}
        self.view = view
        self.placed = []

    def _place_widget(self, *a, **k):
        self.placed.append((a, k))
        return object()


_FakeWin.send_text_to_agent = DeskWindow.send_text_to_agent
win = _FakeWin()
err = win.send_text_to_agent(source, "notes", text)  # positional, as the hook calls it
args, kwargs = win.placed[0]
rect = proxy.sceneBoundingRect()
check("returns None on success", err is None)
check("places a claude_desk widget", args[0] == "claude_desk")
check("positioned just right of the Scratch frame", args[2] == (rect.right() + 24, rect.top()), str(args[2]))
extra = kwargs["claude_extra_instructions"]
check("extra instructions end with the verbatim text", extra.endswith("\n\n" + text))
check("no widget-chat instructions or file pointer", "Read the file" not in extra and "widget-chat" not in extra.lower())
check("not in answer-question mode", not kwargs.get("claude_answer_question", False))
check("missing widget kind returns an error", _FakeWin(False).send_text_to_agent(source, "n", "t") is not None)

check("registered with DeskWindow's hook", "set_scratch_agent_sender(self.send_text_to_agent)" in
      (REPO_ROOT / "src/desk/shell/window.py").read_text())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
