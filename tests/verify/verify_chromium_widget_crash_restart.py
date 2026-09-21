"""TODO 5abf5a0: a ChromiumWidget whose render process terminates shows
a "Widget crashed" overlay with a [RESTART] button (not a silent blank
view); [RESTART] reloads the page and hides the overlay."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)

from PyQt6.QtCore import QCoreApplication, QEvent, QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.server.runner import start_server  # noqa: E402
from desk.shell.chromium_widget import ChromiumWidget  # noqa: E402

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


def pump(seconds=1.0, until=None):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        if until and until():
            return True
        time.sleep(0.02)
    return until() if until else None


with tempfile.TemporaryDirectory() as d:
    widgets_dir = Path(d) / "widgets"
    wdir = widgets_dir / "crashy"
    wdir.mkdir(parents=True)
    (wdir / "widget.json").write_text(
        json.dumps({"name": "Crashy", "kind": "html", "entry": "index.html", "capabilities": []})
    )
    (wdir / "index.html").write_text("<html><body><p id='x'>hello</p></body></html>")
    handle = start_server(widgets_dir=widgets_dir)
    try:
        widget = ChromiumWidget(
            "crashy", "inst-crash", handle.widget_url("crashy"), handle.token,
            HotReloadBroker(), Path(d) / "profile",
        )
        widget.resize(400, 300)
        widget.show()
        errors = []
        widget.error_state_changed.connect(lambda on, msg: errors.append((on, msg)))
        pump(2)
        overlay = widget._crashed_overlay
        check("overlay hidden while the page is healthy", not overlay.isVisible())

        widget.page().load(QUrl("chrome://crash"))
        crashed = pump(10, until=lambda: overlay.isVisible())
        check("overlay shown after the render process terminates", bool(crashed))
        check("overlay covers the whole view", overlay.geometry() == widget.rect())
        check("error indicator raised with a crash message",
              any(on and "terminated" in msg for on, msg in errors))

        overlay._button.click()
        recovered = pump(10, until=lambda: not overlay.isVisible())
        check("[RESTART] hides the overlay", bool(recovered))
        check("[RESTART] clears the error indicator", errors and errors[-1][0] is False)

        result = {}
        pump(3)
        widget.page().runJavaScript("document.getElementById('x') && document.getElementById('x').textContent",
                                    lambda v: result.__setitem__("text", v))
        pump(2, until=lambda: "text" in result)
        check("[RESTART] reloaded the page (content is live again)", result.get("text") == "hello")
    finally:
        handle.stop()

print(f"\n{passed} passed, {failed} failed")
sys.stdout.flush()
os._exit(1 if failed else 0)
