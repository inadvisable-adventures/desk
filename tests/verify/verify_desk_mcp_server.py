import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.shell import current_context  # noqa: E402
from desk.shell.desk_mcp_server import (  # noqa: E402
    DESK_MCP_SERVER_NAME,
    _get_next_todo_item,
    _list_todo_items,
    _list_widget_instances,
    _reveal_widget,
    _save_desk,
    _screenshot_desk,
    _screenshot_widget,
    build_desk_mcp_server,
)

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


def run(coro):
    return asyncio.run(coro)


def _text_of(result: dict) -> str:
    return result["content"][0]["text"]


class _FakeWindow:
    def __init__(self):
        self.calls = []
        self._state = {"widgets": [{"instance_id": "abc", "widget_id": "editor"}]}
        self.saved = False

    def zoom_to_widget_by_instance_id(self, instance_id):
        self.calls.append(("zoom", instance_id))
        return instance_id == "abc"

    def screenshot_widget_instance(self, instance_id, path):
        self.calls.append(("screenshot_widget", instance_id, path))
        return instance_id == "abc"

    def screenshot_desk(self, path):
        self.calls.append(("screenshot_desk", path))
        return True

    def get_state_dict(self):
        self.calls.append(("get_state_dict",))
        return self._state

    def save_current_desk(self):
        self.calls.append(("save",))
        self.saved = True


def _register_fake_window():
    window = _FakeWindow()
    current_context.set_main_window(window)
    current_context.set_gui_thread_caller(lambda fn: fn())
    return window


def _clear_context():
    current_context.set_main_window(None)
    current_context.set_gui_thread_caller(None)
    current_context.set_current_desk_directory(None)


def test_build_desk_mcp_server_names_all_seven_tools():
    server = build_desk_mcp_server()
    check("returns a real McpSdkServerConfig-shaped dict", server.get("type") == "sdk")
    check("server named 'desk'", server.get("name") == DESK_MCP_SERVER_NAME)
    check("a real mcp.server.Server instance is present", server.get("instance") is not None)


def test_reveal_widget_found_and_not_found():
    window = _register_fake_window()
    result = run(_reveal_widget.handler({"instance_id": "abc"}))
    check("reveal found -> True", _text_of(result) == "True")
    check("routed through the fake window with the right instance id", ("zoom", "abc") in window.calls)

    result = run(_reveal_widget.handler({"instance_id": "nope"}))
    check("reveal not found -> False", _text_of(result) == "False")
    _clear_context()


def test_screenshot_widget_and_desk():
    window = _register_fake_window()
    result = run(_screenshot_widget.handler({"instance_id": "abc", "path": "shot.png"}))
    check("screenshot_widget returns True for a real instance", _text_of(result) == "True")
    check("routed through with the right args", ("screenshot_widget", "abc", "shot.png") in window.calls)

    result = run(_screenshot_desk.handler({"path": "canvas.png"}))
    check("screenshot_desk returns True", _text_of(result) == "True")
    check("routed through with the right path", ("screenshot_desk", "canvas.png") in window.calls)
    _clear_context()


def test_list_widget_instances_returns_the_real_state():
    window = _register_fake_window()
    result = run(_list_widget_instances.handler({}))
    widgets = json.loads(_text_of(result))
    check("returns the fake window's own widgets list", widgets == [{"instance_id": "abc", "widget_id": "editor"}])
    check("routed through get_state_dict", ("get_state_dict",) in window.calls)
    _clear_context()


def test_save_desk_calls_save_current_desk():
    window = _register_fake_window()
    result = run(_save_desk.handler({}))
    check("returns 'saved'", _text_of(result) == "saved")
    check("save_current_desk was really called", window.saved is True)
    _clear_context()


def test_all_handlers_report_not_ready_with_no_gui_thread_caller():
    _clear_context()
    window = _FakeWindow()
    current_context.set_main_window(window)
    # No gui_thread_caller registered at all.
    for handler, args in [
        (_reveal_widget, {"instance_id": "abc"}),
        (_screenshot_widget, {"instance_id": "abc", "path": "x.png"}),
        (_screenshot_desk, {"path": "x.png"}),
        (_list_widget_instances, {}),
        (_save_desk, {}),
    ]:
        result = run(handler.handler(args))
        check(f"{handler.name} reports not-ready, not a crash", result.get("is_error") is True)
    _clear_context()


def test_all_handlers_report_not_ready_with_no_main_window():
    _clear_context()
    for handler, args in [
        (_reveal_widget, {"instance_id": "abc"}),
        (_screenshot_widget, {"instance_id": "abc", "path": "x.png"}),
        (_screenshot_desk, {"path": "x.png"}),
        (_list_widget_instances, {}),
        (_save_desk, {}),
    ]:
        result = run(handler.handler(args))
        check(f"{handler.name} reports not-ready with no main window, not a crash", result.get("is_error") is True)


def _write_todo(directory: Path, text: str) -> Path:
    path = directory / "TODO.md"
    path.write_text(text)
    return path


_SAMPLE_TODO = """# TODO

abc1234. COMPLETED: An old, finished item.

def5678. PENDING: Blocked on an open question.

fed9876. A real actionable item, next in line.

aaa1111. Another item after that.
"""


def test_list_todo_items_reflects_real_file():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        _write_todo(directory, _SAMPLE_TODO)

        result = run(_list_todo_items.handler({}))
        items = json.loads(_text_of(result))
        check("lists all four real items", [i["item_id"] for i in items] == ["abc1234", "def5678", "fed9876", "aaa1111"])
        check("first item's status is completed", items[0]["status"] == "completed")
        check("second item's status is pending", items[1]["status"] == "pending")
        current_context.set_current_desk_directory(None)


def test_get_next_todo_item_skips_completed_and_pending():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        _write_todo(directory, _SAMPLE_TODO)

        result = run(_get_next_todo_item.handler({}))
        item = json.loads(_text_of(result))
        check("skips COMPLETED and PENDING, returns the real next item", item["item_id"] == "fed9876")
        current_context.set_current_desk_directory(None)


def test_get_next_todo_item_when_everything_is_done():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        current_context.set_current_desk_directory(directory)
        _write_todo(directory, "# TODO\n\nabc1234. COMPLETED: The only item.\n")

        result = run(_get_next_todo_item.handler({}))
        check("a clear message, not a crash, when nothing is actionable", "No actionable" in _text_of(result))
        current_context.set_current_desk_directory(None)


def test_todo_tools_report_a_clear_error_with_no_desk_directory_known():
    current_context.set_current_desk_directory(None)
    result = run(_list_todo_items.handler({}))
    check("desk_list_todo_items errors clearly with no known directory", result.get("is_error") is True)
    result = run(_get_next_todo_item.handler({}))
    check("desk_get_next_todo_item errors clearly with no known directory", result.get("is_error") is True)


test_build_desk_mcp_server_names_all_seven_tools()
test_reveal_widget_found_and_not_found()
test_screenshot_widget_and_desk()
test_list_widget_instances_returns_the_real_state()
test_save_desk_calls_save_current_desk()
test_all_handlers_report_not_ready_with_no_gui_thread_caller()
test_all_handlers_report_not_ready_with_no_main_window()
test_list_todo_items_reflects_real_file()
test_get_next_todo_item_skips_completed_and_pending()
test_get_next_todo_item_when_everything_is_done()
test_todo_tools_report_a_clear_error_with_no_desk_directory_known()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
