"""TODO 747806b: the Areas list widget (widgets/areas)."""
import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.window  # noqa: E402,F401  (must precede QApplication)
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desk import temp_ui  # noqa: E402
from desk.desks import AREAS_CHANGED_EVENT  # noqa: E402
from desk.event_mediator import EventMediator  # noqa: E402
from desk.shell import current_context  # noqa: E402
from desk.widgets import discover_widgets  # noqa: E402

passed = failed = 0
_KEEP = []


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


spec = importlib.util.spec_from_file_location("areas_check", REPO_ROOT / "widgets" / "areas" / "widget.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class _Window:
    def __init__(self, titles):
        self.areas = [{"area_id": f"a{i}", "title": t, "x": 0.0, "y": 0.0, "width": 800.0, "height": 600.0} for i, t in enumerate(titles)]
        self.calls = []
        self.mediator = EventMediator()
        _KEEP.append(self.mediator)
        self.next = len(titles)

    def list_areas(self):
        return [dict(a) for a in self.areas]

    def view_area(self, area_id):
        self.calls.append(("view", area_id))
        return True

    def create_area(self, title=""):
        area = {"area_id": f"a{self.next}", "title": title, "x": 0.0, "y": 0.0, "width": 800.0, "height": 600.0}
        self.next += 1
        self.areas.append(area)
        self.calls.append(("create", title))
        self.mediator.publish(AREAS_CHANGED_EVENT, {"areas": self.list_areas()}, "desk")
        return dict(area)

    def update_area(self, area_id, title=None):
        self.calls.append(("update", area_id, title))
        for a in self.areas:
            if a["area_id"] == area_id and title is not None:
                a["title"] = title
        self.mediator.publish(AREAS_CHANGED_EVENT, {"areas": self.list_areas()}, "desk")

    def delete_area(self, area_id):
        self.calls.append(("delete", area_id))
        self.areas = [a for a in self.areas if a["area_id"] != area_id]
        self.mediator.publish(AREAS_CHANGED_EVENT, {"areas": self.list_areas()}, "desk")
        return True


def pump(widget):
    widget._subscription._poll()


previous = current_context.get_main_window()
win = _Window(["Inbox", "Reading"])
current_context.set_main_window(win)
try:
    w = module.build()
    w.bind_event_mediator("areas-1", win.mediator)
    check("a row per area, titled", [w._list.item(i).text() for i in range(w._list.count())] == ["Inbox", "Reading"])
    check("status counts them; rename/delete enabled", "2 area(s)" in w._status_label.text() and w._delete_button.isEnabled())
    check("tooltip carries the geometry", "800 x 600" in w._list.item(0).toolTip())

    w._list.itemClicked.emit(w._list.item(1))
    check("clicking a row views that area", win.calls == [("view", "a1")])

    w._list.setCurrentRow(1)
    win.areas[0]["title"] = "Inbox!"
    win.mediator.publish(AREAS_CHANGED_EVENT, {"areas": win.list_areas()}, "desk")
    pump(w)
    check("a change event replaces the rows", w._list.item(0).text() == "Inbox!")
    check("the selection survives a refresh", w._list.currentItem().data(module._AREA_ID_ROLE) == "a1")

    # rename (in-place edit committed)
    w._list.item(1).setText("Reading list")
    check("an edited title is written back through update_area", win.calls[-1] == ("update", "a1", "Reading list"))
    pump(w)
    w._list.item(1).setText("   ")
    check("an empty title is reverted, not saved", win.calls[-1] == ("update", "a1", "Reading list")
          and w._list.item(1).text() == "Reading list")
    n = len(win.calls)
    w._list.item(1).setText("Reading list")
    check("an unchanged title does not call update", len(win.calls) == n)

    # add
    w._add_button.click()
    check("Add creates a numbered area through create_area", win.calls[-1] == ("create", "Area 3"))
    check("the new row is listed and selected for editing", w._list.count() == 3 and w._list.currentItem().text() == "Area 3"
          and w._pending_edit is None)
    pump(w)

    # delete
    w._list.setCurrentRow(0)
    w._confirm_delete = lambda: False
    w._delete_button.click()
    check("declining the confirmation deletes nothing", not any(c[0] == "delete" for c in win.calls))
    w._confirm_delete = lambda: True
    w._delete_button.click()
    check("confirming deletes the selected area", win.calls[-1] == ("delete", "a0"))
    pump(w)
    check("the row is gone after the event", w._list.count() == 2)

    win.areas.clear()
    win.mediator.publish(AREAS_CHANGED_EVENT, {"areas": []}, "desk")
    pump(w)
    check("empty shows the empty message and disables rename/delete",
          w._status_label.text() == module.EMPTY_STATUS and not w._delete_button.isEnabled() and not w._rename_button.isEnabled())
    w._on_mediated_event("other", {"areas": [{"area_id": "q", "title": "Q"}]}, "x")
    check("unrelated events are ignored", w._list.count() == 0)

    seen = []
    previous_opener = current_context.get_popup_opener()
    current_context.set_popup_opener(lambda title, text, buttons, default: seen.append((buttons, default)) or "Yes")
    try:
        check("the confirmation goes through the desk popups service", module.AreasWidget._confirm_delete(w) is True and seen[0] == (["Yes", "No"], "No"))
    finally:
        if previous_opener is not None:
            current_context.set_popup_opener(previous_opener)
finally:
    if previous is not None:
        current_context.set_main_window(previous)

current_context.set_main_window(None)
w2 = module.build()
check("without a main window it says so and disables Add", w2._status_label.text() == module.NOT_CONNECTED_STATUS and not w2._add_button.isEnabled())

# manifest + registration + docs
widgets = discover_widgets(REPO_ROOT / "widgets")
info = widgets.get("areas")
check("discovered as a python widget named Areas", info is not None and info.kind == "python" and info.name == "Areas")
check("manifest is valid JSON with a default size", json.loads((REPO_ROOT / "widgets/areas/widget.json").read_text())["default_size"]["width"] == 300)
tag = "Areas list widget for the sidebar #632760"
check("changelog tag current, with an entry", tag in temp_ui.CURRENT_TAGS and tag in temp_ui._NEW_FEATURES)
check("the areas doc mentions the widget", "Areas` widget" in temp_ui.SPLIT_DOC_CONTENT["tempui-areas.md"])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
