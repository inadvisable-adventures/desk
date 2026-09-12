import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import claude_agent_sdk as sdk  # noqa: E402

from desk.claude_session import ClaudeSession  # noqa: E402

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


async def _run_gated(session: ClaudeSession, tool_name: str):
    """Sets up self._loop the same way ClaudeSession's own
    _connect_and_maybe_prompt would (via the running loop, TODO
    a596dbf), auto-approves the first permission request that arrives
    (so a genuinely gated call resolves instead of hanging this test),
    and returns (result, [captured (request_id, tool_name, input)])."""
    session._loop = asyncio.get_running_loop()
    captured = []

    def _on_permission_request(request_id, name, tool_input):
        captured.append((request_id, name, tool_input))
        session.respond_to_permission(request_id, True)

    session.permission_request.connect(_on_permission_request)
    result = await session._can_use_tool(tool_name, {}, None)
    return result, captured


def test_desk_run_installed_job_is_bypassed():
    session = ClaudeSession()
    captured = []
    session.permission_request.connect(lambda *args: captured.append(args))

    result = asyncio.run(session._can_use_tool("mcp__desk__desk_run_installed_job", {}, None))
    check("returns PermissionResultAllow immediately", isinstance(result, sdk.PermissionResultAllow))
    check("no permission_request was ever emitted", captured == [])
    check("no pending permission future was ever created", session._pending_permissions == {})


def test_desk_install_job_is_not_bypassed():
    session = ClaudeSession()
    result, captured = asyncio.run(_run_gated(session, "mcp__desk__desk_install_job"))
    check("desk_install_job still creates a real pending permission request", len(captured) == 1)
    check("its tool_name is passed through unchanged", captured[0][1] == "mcp__desk__desk_install_job")
    check("once approved, it resolves through the normal allow path", isinstance(result, sdk.PermissionResultAllow))
    check("the pending future was cleaned up after resolving", session._pending_permissions == {})


def test_an_unrelated_tool_is_also_not_bypassed():
    session = ClaudeSession()
    result, captured = asyncio.run(_run_gated(session, "Write"))
    check("an ordinary tool (Write) still goes through the normal gate", len(captured) == 1)
    check("it resolves normally once approved", isinstance(result, sdk.PermissionResultAllow))


test_desk_run_installed_job_is_bypassed()
test_desk_install_job_is_not_bypassed()
test_an_unrelated_tool_is_also_not_bypassed()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
