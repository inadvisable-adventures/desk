"""TODO 1746166: desk_place_widget MCP tool + DeskWindow.place_widget_by_id."""
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.shell import current_context  # noqa: E402
from desk.shell.desk_mcp_server import _TOOLS, _place_widget_tool  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402
from desk import temp_ui  # noqa: E402

passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


class _Frame:
    instance_id = "new-1"


class _Win:
    def __init__(self, fail=False):
        self._widgets = {"kanban": type("W", (), {"default_size": (400, 300)})()}
        self.placed = []
        self.bound = []
        self.kwargs = {}
        self.fail = fail
        self.view = type("V", (), {
            "mapToScene": lambda s, p: type("P", (), {"x": lambda s: 1000.0, "y": lambda s: 500.0})(),
            "viewport": lambda s: type("VP", (), {"rect": lambda s: type("R", (), {"center": lambda s: None})()})(),
        })()

    def _bind_widget_local_storage(self, frame, data):
        self.bound.append(data)

    def _place_widget(self, widget_id, widget, pos, size, **k):
        self.kwargs = k
        self.placed.append((widget_id, pos, size))
        return None if self.fail else _Frame()


_Win.place_widget_by_id = DeskWindow.place_widget_by_id

w = _Win()


def _raises_state(win):
    try:
        win.place_widget_by_id("kanban", state=[1])
    except ValueError:
        return True
    return False


check("returns instance_id", w.place_widget_by_id("kanban") == "new-1")
check("default: centered in view using default size", w.placed[-1] == ("kanban", (800.0, 350.0), (400, 300)))
w.place_widget_by_id("kanban", 10, 20, 300, 200)
check("explicit x/y is top-left, explicit size used", w.placed[-1] == ("kanban", (10.0, 20.0), (300, 200)))


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


check("no state: nothing seeded", w.kwargs == {"local_storage_data": None} and w.bound == [])
w.place_widget_by_id("kanban", state={"tab": "b"})
check("state seeds local storage at placement and is bound", w.kwargs == {"local_storage_data": {"tab": "b"}} and w.bound == [{"tab": "b"}])
check("non-dict state raises", _raises_state(w))
check("unknown widget id raises ValueError", raises(lambda: w.place_widget_by_id("nope")))
check("x without y raises", raises(lambda: w.place_widget_by_id("kanban", 1, None)))
check("width without height raises", raises(lambda: w.place_widget_by_id("kanban", None, None, 5, None)))
check("failed placement raises", raises(lambda: _Win(fail=True).place_widget_by_id("kanban")))

# ---- MCP handler ----
check("tool registered", _place_widget_tool in _TOOLS and _place_widget_tool.name == "desk_place_widget")
current_context.set_gui_thread_caller(lambda fn: fn())
current_context.set_main_window(_Win())
res = asyncio.run(_place_widget_tool.handler({"widget_id": " kanban ", "x": 1, "y": 2}))
check("handler returns instance_id", not res.get("is_error") and res["content"][0]["text"] == "new-1")
_seen = {}
current_context.set_main_window(type("W", (), {"place_widget_by_id": lambda s, *a: _seen.setdefault("a", a) and "i2"})())
res = asyncio.run(_place_widget_tool.handler({"widget_id": "k", "state": {"a": 1}}))
check("handler forwards state", _seen["a"][-1] == {"a": 1} and res["content"][0]["text"] == "i2")
current_context.set_main_window(_Win())
res = asyncio.run(_place_widget_tool.handler({"widget_id": "nope"}))
check("handler reports unknown id as error", res["is_error"] is True)
res = asyncio.run(_place_widget_tool.handler({"widget_id": ""}))
check("handler rejects empty id", res["is_error"] is True)
current_context.set_main_window(None)

tag = "desk_place_widget MCP places a registered widget #800488"
check("changelog tag current and has entry", tag in temp_ui.CURRENT_TAGS and tag in temp_ui._NEW_FEATURES)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
