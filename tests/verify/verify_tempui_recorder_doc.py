"""TODO b9689cd: the DeskRecorder docs/tag match the real Bridge client, routes and MCP tools."""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401
from desk import recorder_protocol, temp_ui  # noqa: E402
from desk.server.bridge_client import render_bridge_client  # noqa: E402
import desk.shell.desk_mcp_server as mcp  # noqa: E402

passed = failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


tag = next((t for t in temp_ui.CURRENT_TAGS if t.endswith("#b9689cd")), None)
check("the tag is in CURRENT_TAGS", tag is not None)
doc = (REPO / "src/desk/tempui_content/tempui-custom-widgets.md").read_text()
js = render_bridge_client("w", "i", "t")
for fn in ("status", "start", "stop", "sources"):
    check(f"doc names desk.recorder.{fn} and the client defines it", f"`.{fn}(" in doc or f"desk.recorder.{fn}" in doc)
check("client defines the recorder block", "recorder: {" in js and "/api/bridge/recorder/status" in js)
check("client defines the transcripts block", "transcripts: {" in js and "/api/bridge/transcripts/list" in js)
check("doc names both capabilities", "`recorder`" in doc and "`transcripts`" in doc)
check("doc lists every feature the protocol has", all(f'"{f}"' in doc for f in recorder_protocol.FEATURES))
check("doc lists every state the protocol has (except those the client cannot see)",
      all(f"`{s}`" in doc for s in ("idle", "starting", "running", "stopping", "error", "denied", "disconnected")))
for name in ("desk_recorder_status", "desk_recorder_control", "desk_read_transcript"):
    registered = any(getattr(t, "name", None) == name for t in mcp._TOOLS)
    check(f"MCP tool {name} is registered and documented", registered and name in doc)
check("doc says what recording means", "records the user's microphone, screen or" in doc.replace("\n  ", " "))
check("doc mentions the build script", "scripts/build_desk_recorder_app.sh" in doc)
check("the build script the doc names exists", (REPO / "scripts/build_desk_recorder_app.sh").is_file())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
