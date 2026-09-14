import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import claude_agent_sdk as sdk  # noqa: E402

from desk.claude_session import ClaudeSession  # noqa: E402
from desk.temp_ui import (  # noqa: E402
    NEW_FEATURES_DOC_FILENAME,
    SPLIT_DOC_CONTENT,
    TEMPUI_DOC_VERSION,
    render_static_doc,
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


# ---------- ClaudeSession (SDK-based Claude (Desk) widget) ----------


class _FakeClient:
    last_options = None

    def __init__(self, options):
        _FakeClient.last_options = options

    async def connect(self):
        pass


def _connect(session_id: str, resume: bool):
    with patch.object(sdk, "ClaudeSDKClient", _FakeClient):
        session = ClaudeSession()
        asyncio.run(session._connect_and_maybe_prompt(session_id, resume, None, "default", None, ""))
    return _FakeClient.last_options


fresh_options = _connect("fresh-instance-id", resume=False)
check(
    "fresh session: env exposes DESK_WIDGET_INSTANCE_ID as session_id",
    fresh_options.env == {"DESK_WIDGET_INSTANCE_ID": "fresh-instance-id"},
)

resumed_options = _connect("resumed-instance-id", resume=True)
check(
    "resumed session: env still exposes DESK_WIDGET_INSTANCE_ID as session_id",
    resumed_options.env == {"DESK_WIDGET_INSTANCE_ID": "resumed-instance-id"},
)

# ---------- ClaudeWidget (PTY-based claude widget) ----------


def load_widget_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


claude_mod = load_widget_module("claude_env_var_verify_mod", "widgets/claude/widget.py")


def _captured_command(session_id: str, resume: bool) -> str:
    widget = claude_mod.build()
    try:
        with patch.object(widget, "type_into_shell") as mock_type:
            widget.start_session(session_id, resume=resume)
        return mock_type.call_args[0][0]
    finally:
        widget._process.terminate()
        widget._process.wait()


fresh_command = _captured_command("abc-123", resume=False)
check(
    "fresh launch: shell command exports DESK_WIDGET_INSTANCE_ID before exec claude",
    fresh_command.startswith("DESK_WIDGET_INSTANCE_ID=abc-123 exec claude --session-id abc-123"),
)

resume_command = _captured_command("abc-123", resume=True)
check(
    "resume: shell command exports DESK_WIDGET_INSTANCE_ID before exec claude",
    resume_command.startswith("DESK_WIDGET_INSTANCE_ID=abc-123 exec claude --resume abc-123"),
)

# ---------- Docs ----------

check("TEMPUI_DOC_VERSION bumped to at least 42", TEMPUI_DOC_VERSION >= 42)

doc_template = render_static_doc()
check("main doc has a new Environment variables section", "## Environment variables" in doc_template)
check("main doc documents DESK_WIDGET_INSTANCE_ID", "DESK_WIDGET_INSTANCE_ID" in doc_template)
check(
    "Environment variables section appears after the built-in file types list",
    doc_template.index("Every file named above lives in this same directory.")
    < doc_template.index("## Environment variables"),
)

features = SPLIT_DOC_CONTENT[NEW_FEATURES_DOC_FILENAME]
check("features doc has a Version 42 entry", "## Version 42" in features)
check("features doc's Version 42 entry mentions DESK_WIDGET_INSTANCE_ID", "DESK_WIDGET_INSTANCE_ID" in features)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
