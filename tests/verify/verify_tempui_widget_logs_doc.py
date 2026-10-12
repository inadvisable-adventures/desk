"""TODO 51db3bd: tempui-widget-logs.md documents the log capability and MCP tools accurately."""
import sys

sys.path.insert(0, "src")

from desk import widget_logs  # noqa: E402
from desk.server.bridge_client import BRIDGE_CLIENT_TEMPLATE  # noqa: E402
from desk.shell.desk_mcp_server import _TOOLS  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    CURRENT_TAGS, SPLIT_DOC_CONTENT, WIDGET_LOGS_DOC_FILENAME, _CUSTOM_WIDGETS_DOC, _NEW_FEATURES, _PORTING_DOC,
    DOC_TEMPLATE,
)

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


doc = SPLIT_DOC_CONTENT[WIDGET_LOGS_DOC_FILENAME]
tag = next((t for t in CURRENT_TAGS if "named widget logs" in t), None)
check("filename", WIDGET_LOGS_DOC_FILENAME == "tempui-widget-logs.md")
check("tag in CURRENT_TAGS with a changelog entry linking the doc", tag in _NEW_FEATURES and "tempui-widget-logs.md" in _NEW_FEATURES[tag])
check("overview, custom-widgets and porting docs link to it", all("tempui-widget-logs.md" in d for d in (DOC_TEMPLATE, _CUSTOM_WIDGETS_DOC, _PORTING_DOC)))
check("documents the JS calls the client really declares", "desk.log.append(" in doc and "desk.log.line(" in doc and "append: (name, entries)" in BRIDGE_CLIENT_TEMPLATE and "line: (name, s)" in BRIDGE_CLIENT_TEMPLATE)
check(f"ring cap {widget_logs.MAX_ENTRIES_PER_LOG} in doc", str(widget_logs.MAX_ENTRIES_PER_LOG) in doc)
check(f"text cap {widget_logs.MAX_ENTRY_TEXT_CHARS} in doc", str(widget_logs.MAX_ENTRY_TEXT_CHARS) in doc)
check(f"log-count cap {widget_logs.MAX_LOGS} in doc", str(widget_logs.MAX_LOGS) in doc)
names = {t.name for t in _TOOLS}
check("both documented MCP tools exist", {"desk_list_widget_logs", "desk_query_widget_log"} <= names)
check("doc names both tools", "desk_list_widget_logs" in doc and "desk_query_widget_log" in doc)
check("documents inclusive bounds, order, and the python-widget path", "**inclusive**" in doc and '"desc"' in doc and "get_widget_log_store" in doc)
check("tells the widget how to get a unique suffix (no instance id in JS)", "getLocalStorage" in doc and "randomUUID" in doc)
sys.exit(1 if failed else 0)
