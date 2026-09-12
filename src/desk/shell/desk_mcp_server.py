"""An in-process MCP server (TODO a762501) giving a Claude (Desk)/
`claude` session a live, queryable channel into Desk's own running
shell -- reveal/screenshot a placed widget, list what's currently
placed, force a save, and read the current project's `TODO.md` state
-- as a parallel/eventual replacement for the file-drop-and-click
-Start `Job`/`DeskProc` ceremony for these specific, agent-initiated
actions. See plans/desk-mcp-server.md.

Built with `claude_agent_sdk.create_sdk_mcp_server` (`type: "sdk"`) --
runs directly in this process, no subprocess/port to manage -- wired
into `ClaudeAgentOptions.mcp_servers` at
`desk.claude_session.ClaudeSession._connect_and_maybe_prompt`.
Confirmed directly, with a real live session against the installed
SDK, that a tool call here is gated through the exact same
`can_use_tool` hook `ClaudeSession` already implements for every other
tool -- no new approval UI needed, it surfaces through
`ClaudeDeskWidget`'s existing real approval flow automatically.

Every tool handler is a thin async wrapper over a `current_context`
hook, duplicated rather than reusing `widgets/desk_proc_runner
/widget.py`'s `DeskProcApi` -- a widget's own `widget.py` isn't meant
to be imported from outside its directory (see `CLAUDE_WIDGET_PROMPT`'s
own duplication note in `widgets/claude_desk/widget.py`), and this
server isn't itself a widget. GUI-thread marshaling reuses
`desk.server.app.run_on_gui`'s exact idiom
(`loop.run_in_executor(None, gui_thread_caller, fn)`) rather than a
raw blocking call: a tool handler is `async def`, running on this
session's own private event loop (`ClaudeSession._loop`) -- blocking
that loop synchronously while waiting for the GUI thread would stall
anything else it needs to do (e.g. a concurrent `_can_use_tool` future
resolution) for no reason.

Deliberately read-only or side-effect-bounded to actions a user could
already trigger by hand via existing UI (a titlebar button, the eye
button) -- nothing here lets an agent do something it couldn't already
do by clicking around, just without the file-drop ceremony. The
`TODO.md` tools are deliberately read-only (list/get-next, no
mark-complete/reorder) -- see TODO `a762501`'s own `TODO.md` note on
why a mutating tool would bypass this project's plan-then-verify
discipline."""

import asyncio
import contextlib
import io
import json
import sys
import threading
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, create_sdk_mcp_server, tool

from desk.installed_jobs import ENTRY_FILENAME, compute_version_hash, installed_job_dir
from desk.shell import current_context
from desk.todo_file import TodoItem, find_nearest_todo_file, parse_todo_file

DESK_MCP_SERVER_NAME = "desk"

# Referenced by desk.claude_session.ClaudeSession._can_use_tool (TODO
# 7dca383) to build the fully-qualified "mcp__desk__desk_run_installed_job"
# name its bypass branch matches against -- kept here, not duplicated
# as a literal there, so the two can never drift if this tool is ever
# renamed.
RUN_INSTALLED_JOB_TOOL_NAME = "desk_run_installed_job"

_NOT_READY_MESSAGE = "Desk's GUI thread is not reachable yet -- try again shortly."


def _text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": is_error}


async def _call_on_gui_thread(fn: Callable[[], Any]) -> Any:
    """Runs `fn()` on the GUI thread without blocking this tool
    handler's own event loop -- same idiom `desk.server.app.run_on_gui`
    already established for the identical problem (a background-thread
    caller needing a GUI-thread result), just reached from an MCP tool
    handler instead of a FastAPI route. Raises RuntimeError (caught by
    each tool handler, turned into a `_text_result(..., is_error=True)`)
    if no `current_context.get_gui_thread_caller()` is registered yet
    (e.g. Desk hasn't finished starting)."""
    caller = current_context.get_gui_thread_caller()
    if caller is None:
        raise RuntimeError(_NOT_READY_MESSAGE)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, caller, fn)


def _todo_item_dict(item: TodoItem) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "status": item.status,
        "description": item.description,
        "plan": item.plan,
    }


@tool(
    "desk_reveal_widget",
    "Zoom/pan the Workspace Canvas so a specific placed widget instance fills the view -- "
    "the same action as clicking that instance's own titlebar eye button. Returns whether a "
    "matching instance was found.",
    {"instance_id": str},
)
async def _reveal_widget(args: dict[str, Any]) -> dict[str, Any]:
    window = current_context.get_main_window()
    if window is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    try:
        found = await _call_on_gui_thread(lambda: window.zoom_to_widget_by_instance_id(args["instance_id"]))
    except RuntimeError as e:
        return _text_result(str(e), is_error=True)
    return _text_result(str(found))


@tool(
    "desk_screenshot_widget",
    "Save a real PNG screenshot of a specific placed widget instance's own frame (titlebar and "
    "content, exactly as it looks on the canvas) to path. A relative path resolves against the "
    "current Desk's own directory. Returns whether the instance was found and the file was saved.",
    {"instance_id": str, "path": str},
)
async def _screenshot_widget(args: dict[str, Any]) -> dict[str, Any]:
    window = current_context.get_main_window()
    if window is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    try:
        ok = await _call_on_gui_thread(
            lambda: window.screenshot_widget_instance(args["instance_id"], args["path"])
        )
    except RuntimeError as e:
        return _text_result(str(e), is_error=True)
    return _text_result(str(ok))


@tool(
    "desk_screenshot_desk",
    "Save a real PNG screenshot of the whole Workspace Canvas viewport (not any native window "
    "chrome) to path. Same path-resolution rules as desk_screenshot_widget.",
    {"path": str},
)
async def _screenshot_desk(args: dict[str, Any]) -> dict[str, Any]:
    window = current_context.get_main_window()
    if window is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    try:
        ok = await _call_on_gui_thread(lambda: window.screenshot_desk(args["path"]))
    except RuntimeError as e:
        return _text_result(str(e), is_error=True)
    return _text_result(str(ok))


@tool(
    "desk_list_widget_instances",
    "List the current Desk's live placed-widget layout (instance ids, widget kind, position, "
    "size) -- the same data desk.workspace.getState() already exposes to a kind:\"html\" widget "
    "with the workspace capability.",
    {},
)
async def _list_widget_instances(args: dict[str, Any]) -> dict[str, Any]:
    window = current_context.get_main_window()
    if window is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    try:
        state = await _call_on_gui_thread(lambda: window.get_state_dict())
    except RuntimeError as e:
        return _text_result(str(e), is_error=True)
    return _text_result(json.dumps(state.get("widgets", [])))


@tool(
    "desk_save",
    "Force an on-demand save of the current Desk's own widget layout/state to its .desk file, "
    "instead of waiting for a structural action (quit, Desk switch, widget removal) to trigger it.",
    {},
)
async def _save_desk(args: dict[str, Any]) -> dict[str, Any]:
    window = current_context.get_main_window()
    if window is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    try:
        await _call_on_gui_thread(lambda: window.save_current_desk())
    except RuntimeError as e:
        return _text_result(str(e), is_error=True)
    return _text_result("saved")


@tool(
    "desk_list_todo_items",
    "List the current project's TODO.md items (item_id, status, description, plan) -- read-only.",
    {},
)
async def _list_todo_items(args: dict[str, Any]) -> dict[str, Any]:
    directory = current_context.get_current_desk_directory()
    if directory is None:
        return _text_result("No current Desk directory known.", is_error=True)
    path = find_nearest_todo_file(directory)
    if path is None:
        return _text_result("No TODO.md found.", is_error=True)
    _preamble, items = parse_todo_file(path)
    return _text_result(json.dumps([_todo_item_dict(item) for item in items]))


@tool(
    "desk_get_next_todo_item",
    "The first TODO.md item that is not COMPLETED/SUPERSEDED/PENDING -- the item that should be "
    "worked next, per this project's own priority-is-position convention. Check this before "
    "starting work rather than trusting an earlier, possibly-stale read of TODO.md, since another "
    "session may have reprioritized or completed items since.",
    {},
)
async def _get_next_todo_item(args: dict[str, Any]) -> dict[str, Any]:
    directory = current_context.get_current_desk_directory()
    if directory is None:
        return _text_result("No current Desk directory known.", is_error=True)
    path = find_nearest_todo_file(directory)
    if path is None:
        return _text_result("No TODO.md found.", is_error=True)
    _preamble, items = parse_todo_file(path)
    for item in items:
        if item.status not in ("completed", "superseded", "pending"):
            return _text_result(json.dumps(_todo_item_dict(item)))
    return _text_result("No actionable TODO item found (everything is completed/superseded/pending).")


# sys.path is process-global -- serializes concurrent installed-job
# runs (each already on its own executor thread) against each other so
# one job's temporary sys.path entry can never leak into a second
# job's own import resolution if two desk_run_installed_job calls
# happen to overlap (e.g. two tool calls in the same agent turn).
# Installed Jobs are not meant to be a high-throughput concurrent
# system -- serializing here is a minimal, correct fix, not a
# performance concession that costs anything in practice.
_RUN_LOCK = threading.Lock()


def _run_installed_job(script_text: str, job_dir: Path, config_path: str | None) -> tuple[bool, str, str, str]:
    """Runs on a background thread (via loop.run_in_executor, awaited
    directly by _run_installed_job_tool below -- not the GUI thread,
    same "no Qt access from inside the job" rule a regular Job's own
    `_run_python_job` (widgets/job_runner/widget.py) already follows).
    `job_dir` is put on sys.path for the duration so main.py can import
    sibling files in its own directory; CONFIG_PATH is the documented
    way a script reads its optional config-file argument (TODO
    7dca383, see tempui-installed-jobs.md) -- None if the caller didn't
    pass one. Returns (ok, stdout, stderr, traceback) rather than
    raising, mirroring _run_python_job's own relay payload shape."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    job_dir_str = str(job_dir)
    with _RUN_LOCK:
        sys.path.insert(0, job_dir_str)
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(
                    compile(script_text, "<installed_job>", "exec"),
                    {"__name__": "__installed_job__", "CONFIG_PATH": config_path},
                )
            return True, stdout.getvalue(), stderr.getvalue(), ""
        except Exception:
            return False, stdout.getvalue(), stderr.getvalue(), traceback.format_exc()
        finally:
            with contextlib.suppress(ValueError):
                sys.path.remove(job_dir_str)


@tool(
    "desk_install_job",
    "Register (or re-register, if its source changed) the Installed Job at "
    "desk-installed-jobs/<name>/main.py -- computes its version hash and persists it to the current "
    "Desk. This is the only approval point for this job: desk_run_installed_job never re-prompts.",
    {"name": str},
)
async def _install_job(args: dict[str, Any]) -> dict[str, Any]:
    window = current_context.get_main_window()
    if window is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    try:
        ok, message = await _call_on_gui_thread(lambda: window.install_job(args["name"]))
    except RuntimeError as e:
        return _text_result(str(e), is_error=True)
    return _text_result(message, is_error=not ok)


@tool(
    RUN_INSTALLED_JOB_TOOL_NAME,
    "Run an already-installed job by name, optionally passing a config file path (available to the "
    "job's own main.py as the CONFIG_PATH global; a relative path resolves against the current Desk's "
    "own directory; omit to pass None). Never prompts for approval -- only desk_install_job does. "
    "Refuses to run if the on-disk source no longer matches the version that was installed (call "
    "desk_install_job again first). Returns {ok, stdout, stderr, traceback} as JSON.",
    # A hand-written JSON Schema, not the {name: type} shorthand
    # (SdkMcpTool._build_schema marks every shorthand key "required" --
    # config_path must stay genuinely optional, per this item's own
    # spec).
    {
        "type": "object",
        "properties": {"name": {"type": "string"}, "config_path": {"type": "string"}},
        "required": ["name"],
    },
)
async def _run_installed_job_tool(args: dict[str, Any]) -> dict[str, Any]:
    window = current_context.get_main_window()
    if window is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    name = args["name"]
    try:
        job = await _call_on_gui_thread(lambda: window.get_installed_job(name))
    except RuntimeError as e:
        return _text_result(str(e), is_error=True)
    if job is None:
        return _text_result(f"{name!r} is not installed.", is_error=True)
    directory = current_context.get_current_desk_directory()
    if directory is None:
        return _text_result("No current Desk directory known.", is_error=True)
    job_dir = installed_job_dir(directory, name)
    current_hash = compute_version_hash(job_dir)
    if current_hash != job.version_hash:
        return _text_result(
            f"{name!r}'s source on disk (version {current_hash}) no longer matches the installed "
            f"version ({job.version_hash}) -- call desk_install_job again before running it.",
            is_error=True,
        )
    raw_config_path = args.get("config_path")
    if raw_config_path:
        config_path_obj = Path(raw_config_path)
        if not config_path_obj.is_absolute():
            config_path_obj = directory / config_path_obj
        config_path: str | None = str(config_path_obj)
    else:
        config_path = None
    script_text = (job_dir / ENTRY_FILENAME).read_text()
    loop = asyncio.get_event_loop()
    ok, stdout, stderr, tb = await loop.run_in_executor(
        None, _run_installed_job, script_text, job_dir, config_path
    )
    return _text_result(json.dumps({"ok": ok, "stdout": stdout, "stderr": stderr, "traceback": tb}))


_TOOLS = [
    _reveal_widget,
    _screenshot_widget,
    _screenshot_desk,
    _list_widget_instances,
    _save_desk,
    _list_todo_items,
    _get_next_todo_item,
    _install_job,
    _run_installed_job_tool,
]


def build_desk_mcp_server() -> McpSdkServerConfig:
    """Builds a fresh in-process MCP server instance -- called once per
    `ClaudeSession.start()` (TODO a762501), same lifecycle as the rest
    of that call's `ClaudeAgentOptions`."""
    return create_sdk_mcp_server(name=DESK_MCP_SERVER_NAME, tools=_TOOLS)
