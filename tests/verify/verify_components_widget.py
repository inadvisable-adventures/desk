"""TODO 5ee7493: the Components catalog widget (widgets/components/)."""
import importlib.util
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

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk.shell import current_context  # noqa: E402

spec = importlib.util.spec_from_file_location("components_widget", REPO_ROOT / "widgets/components/widget.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def rows(widget):
    return [widget._list.item(i) for i in range(widget._list.count())]


def select(widget, name):
    for item in rows(widget):
        key = item.data(Qt.ItemDataRole.UserRole)
        if key and key[1] == name:
            widget._list.setCurrentItem(item)
            return key
    raise AssertionError(name)


manifest = json.loads((REPO_ROOT / "widgets/components/widget.json").read_text())
check("manifest: a python widget named Components", manifest["kind"] == "python" and manifest["name"] == "Components" and manifest["entry"] == "widget.py")

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    lib = root / "desk_widgets/_shared/components/pill-label"
    lib.mkdir(parents=True)
    (lib / "pill-label.ts").write_text("class PillLabel extends HTMLElement {}\n")
    (lib / "README.md").write_text("# pill-label\n\nA small pill.\n")
    w = root / "desk_widgets/demo"
    w.mkdir(parents=True)
    (w / "widget.json").write_text(json.dumps({"keyword": "K", "label": "L", "width": 1, "height": 1, "components": ["pill-label", "desk-select"]}))

    current_context.set_current_desk_directory(root)
    opened = []
    current_context.set_editor_or_scrap_opener(lambda path: opened.append(path))
    widget = module.build()
    pump(0.1)

    texts = [r.text() for r in rows(widget)]
    check("two group headers, project first, then desk-wide", texts[0].startswith("Project library (mutable) -- 1") and any(t.startswith("Desk-wide library (static)") for t in texts))
    check("headers are not selectable", all(not (r.flags() & Qt.ItemFlag.ItemIsSelectable) for r in rows(widget) if r.data(Qt.ItemDataRole.UserRole) is None))
    check("lists Desk's real components", {"desk-select", "hsv-color-picker", "document-editor-base"} <= {r.data(Qt.ItemDataRole.UserRole)[1] for r in rows(widget) if r.data(Qt.ItemDataRole.UserRole) and r.data(Qt.ItemDataRole.UserRole)[0] == "desk"})
    check("first real entry is selected by default", widget._selected() is not None and widget._selected().name == "pill-label")
    details = widget._details.toPlainText()
    check("details: summary, files and used-by", "A small pill." in details and "pill-label.ts" in details and "desk_widgets/demo" in details)
    check("a project component: no vendor button; README enabled", not widget._vendor_button.isEnabled() and widget._readme_button.isEnabled())

    select(widget, "desk-select")
    check("desk-wide details show its usage and template", "desk_widgets/demo" in widget._details.toPlainText() and "yes (injected" in widget._details.toPlainText())
    check("a desk-wide component can be copied to the project", widget._vendor_button.isEnabled())
    widget._copy_button.click()
    check("Copy entry puts the name on the clipboard", QGuiApplication.clipboard().text() == '"desk-select"')
    widget._readme_button.click()
    widget._source_button.click()
    check("README and source open through the editor opener",
          opened == [REPO_ROOT / "shared-components/desk-select/README.md", REPO_ROOT / "shared-components/desk-select/desk-select.ts"])

    widget._vendor_button.click()
    pump(0.1)
    check("Copy to project library copies it and the row is marked", (root / "desk_widgets/_shared/components/desk-select/desk-select.ts").is_file()
          and any("desk-select  (copied to project)" in r.text() for r in rows(widget)))
    check("...selection survives the refresh and the button is spent", widget._selected().name == "desk-select" and not widget._vendor_button.isEnabled())
    check("...and the status says what happened", "copied" in widget._status_label.text())

    # live updates: add a component while open
    new = root / "desk_widgets/_shared/components/zeta"
    new.mkdir()
    (new / "zeta.ts").write_text("class Zeta extends HTMLElement {}\n")
    widget._poll()
    check("a poll picks up a newly added project component", any(r.text().strip() == "zeta" for r in rows(widget)))
    check("labels are not user-selectable", widget._status_label.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction)

    current_context.set_current_desk_directory(None)
    widget.reload()
    check("no Desk directory: empty, no crash", widget._status_label.text() == "No components found." and widget._selected() is None)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
