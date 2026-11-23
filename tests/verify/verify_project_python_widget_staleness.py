"""TODO f143ce4 -- see plans/project-python-widget-staleness.md.
Cites ../FEEDBACK/FEEDBACK-DESK-a-placed-instance-of-a-kind-python-project-widget-desk-widge-2026-11-20-1706.md.

A project (desk_widgets/<name>/) python widget no longer auto-reloads: a
content hash of its directory drives [STALE], and accepting it rebuilds."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

import desk.temp_ui as temp_ui  # noqa: E402
from desk.hotreload import HotReloadBroker  # noqa: E402
from desk.shell.python_widget import PythonWidgetHost  # noqa: E402
from desk.shell.widget_frame import WidgetFrame  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk.widgets import project_widget_content_hash  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


SRC = "from PyQt6.QtWidgets import QLabel\ndef build():\n    return QLabel(%r)\n"


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def make_widget(project, name="vp", text="v1"):
    d = project / temp_ui.PROMOTED_WIDGET_SRC_DIRNAME / name
    d.mkdir(parents=True)
    (d / "widget.json").write_text(json.dumps({"name": name, "kind": "python"}))
    (d / "widget.py").write_text(SRC % text)
    return d


# ---------- the hash ----------
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
    d = make_widget(Path(t))
    h1 = project_widget_content_hash(d)
    check("hash is stable", h1 == project_widget_content_hash(d))
    (d / "__pycache__").mkdir()
    (d / "__pycache__" / "widget.cpython-312.pyc").write_bytes(b"junk")
    (d / ".DS_Store").write_bytes(b"junk")
    check("pycache and dotfiles ignored", project_widget_content_hash(d) == h1)
    (d / "widget.py").write_text(SRC % "v2")
    h2 = project_widget_content_hash(d)
    check("source edit changes the hash", h2 != h1)
    (d / "widget.py").write_text(SRC % "v1")
    check("reverting restores the hash", project_widget_content_hash(d) == h1)
    (d / "helper.py").write_text("x = 1\n")
    check("a new file in the directory changes the hash", project_widget_content_hash(d) != h1)

# ---------- PythonWidgetHost auto_reload ----------
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
    d = make_widget(Path(t))
    broker = HotReloadBroker()
    manual = PythonWidgetHost("vp", d, "widget.py", broker, auto_reload=False)
    auto = PythonWidgetHost("vp", d, "widget.py", broker)
    (d / "widget.py").write_text(SRC % "v2")
    broker.widget_changed.emit("vp")
    pump(0.2)
    check("auto_reload=True host swaps on widget_changed", auto.current.text() == "v2")
    check("auto_reload=False host does NOT swap on widget_changed", manual.current.text() == "v1")
    manual.rebuild()
    check("rebuild() swaps it", manual.current.text() == "v2")

# ---------- DeskWindow plumbing, with the real methods bound to a stand-in ----------


class _View:
    def __init__(self):
        self._frames = []

    def set_widget_catalog(self, catalog):
        pass


class _Win:
    def __init__(self):
        self._widgets = {}
        self._widgets_dir = Path(".")
        self._broker = HotReloadBroker()
        self._project_widget_ids = set()
        self._project_widget_watcher = None
        self._custom_widget_content_hash = {}
        self._promoted_widget_source_dirty = set()
        self.view = _View()


for name in ("_load_project_widgets", "_refresh_stale_indicators_for", "_reload_stale_frame"):
    setattr(_Win, name, getattr(DeskWindow, name))

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
    project = Path(t)
    d = make_widget(project)
    win = _Win()
    desk = type("D", (), {"directory": project})()
    win._load_project_widgets(desk)
    h1 = win._custom_widget_content_hash.get("vp")
    check("project widget gets a content hash", h1 == project_widget_content_hash(d))

    host = PythonWidgetHost("vp", d, "widget.py", win._broker, auto_reload=False)
    frame = WidgetFrame("vp", host)
    win.view._frames.append(frame)
    frame.placed_content_hash = h1
    frame.set_stale(False)

    (d / "widget.py").write_text(SRC % "v2")
    win._load_project_widgets(desk)  # what each debounced widget_changed does
    check("edit -> hash changes", win._custom_widget_content_hash["vp"] != h1)
    check("edit -> placed instance marked [STALE]", frame.is_stale())
    check("edit -> running instance untouched", host.current.text() == "v1")

    win._confirm_stale_reload = lambda placed, current: True
    win._on_widget_stale_clicked = DeskWindow._on_widget_stale_clicked.__get__(win)
    win._on_widget_stale_clicked(frame)
    check("accepting rebuilds the instance", host.current.text() == "v2")
    check("accepting clears [STALE]", not frame.is_stale())
    check("accepting adopts the new hash", frame.placed_content_hash == win._custom_widget_content_hash["vp"])

    (d / "widget.py").write_text(SRC % "v1")
    win._load_project_widgets(desk)
    check("reverting an edit after placement is stale vs. the rebuilt instance", frame.is_stale())
    win._project_widget_watcher.stop()

# ---------- wiring in the real source ----------
import inspect  # noqa: E402

src = inspect.getsource(DeskWindow._place_widget)
check("_place_widget turns auto_reload off for project widgets", "auto_reload=widget_id not in self._project_widget_ids" in src)
check("changelog tag registered", any("Project python widgets go [STALE]" in t for t in temp_ui.CURRENT_TAGS))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
