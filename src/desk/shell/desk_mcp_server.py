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
import json
from collections.abc import Callable
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, create_sdk_mcp_server, tool

from desk import pipeline_dsl
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
    "current Desk's own directory. Optional max_width (pixels) scales the capture down "
    "proportionally (never up) before saving -- omit it to keep native resolution. Returns "
    "whether the instance was found and the file was saved.",
    # A hand-written JSON Schema (TODO 94d2b94), not the {name: type}
    # shorthand -- same reasoning as desk_run_installed_job's own:
    # max_width must stay genuinely optional.
    {
        "type": "object",
        "properties": {
            "instance_id": {"type": "string"},
            "path": {"type": "string"},
            "max_width": {"type": "integer"},
        },
        "required": ["instance_id", "path"],
    },
)
async def _screenshot_widget(args: dict[str, Any]) -> dict[str, Any]:
    window = current_context.get_main_window()
    if window is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    try:
        ok = await _call_on_gui_thread(
            lambda: window.screenshot_widget_instance(args["instance_id"], args["path"], args.get("max_width"))
        )
    except RuntimeError as e:
        return _text_result(str(e), is_error=True)
    return _text_result(str(ok))


@tool(
    "desk_screenshot_desk",
    "Save a real PNG screenshot of the whole Workspace Canvas viewport (not any native window "
    "chrome) to path. Same path-resolution and optional max_width downsampling rules as "
    "desk_screenshot_widget.",
    {
        "type": "object",
        "properties": {"path": {"type": "string"}, "max_width": {"type": "integer"}},
        "required": ["path"],
    },
)
async def _screenshot_desk(args: dict[str, Any]) -> dict[str, Any]:
    window = current_context.get_main_window()
    if window is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    try:
        ok = await _call_on_gui_thread(lambda: window.screenshot_desk(args["path"], args.get("max_width")))
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


@tool(
    "desk_install_job",
    "Register (or re-register, if its source changed) the Installed Job at "
    "desk-installed-jobs/<name>/ -- either main.py (python kind) or a Cargo.toml + src/ (rust kind, "
    "for computationally-intensive work or GPU access via e.g. the wgpu crate; exactly one of the two "
    "must be present). Computes its version hash and persists it to the current Desk. This is the "
    "only approval point for this job: desk_run_installed_job never re-prompts. A python-kind job's "
    "own code can invoke another installed job (python or rust, uniformly) via its own "
    "RUN_INSTALLED_JOB global. See tempui-installed-jobs.md for the full picture, including "
    "job.json's optional declared desk.state.* 'needs' list.",
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
    "Run an already-installed job by name, optionally passing a config file path (a relative path "
    "resolves against the current Desk's own directory; omit to pass None). A python-kind job reads "
    "it as the CONFIG_PATH global; a rust-kind job reads it as the DESK_JOB_CONFIG_PATH environment "
    "variable, only set when given. If the job declared desk.state.* keys it needs (job.json's "
    "'needs' list), those are resolved fresh on every run and handed to the job the same way "
    "(NEEDS_PATH global / DESK_JOB_NEEDS_PATH env var). Never prompts for approval -- only "
    "desk_install_job does. Refuses to run if the on-disk source no longer matches the version that "
    "was installed (call desk_install_job again first; a rust-kind job's own target/ build output "
    "never counts as a source change). Returns {ok, stdout, stderr, traceback} as JSON -- traceback "
    "is a real Python traceback for python, or a plain exit-code note for rust.",
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
    """A thin adapter over DeskWindow.run_installed_job -- the
    validation (installed? stale hash?) and execution both live there
    now (TODO 888b537), shared with the Bridge API's own
    installedJobs.run route, rather than duplicated here. The GUI
    -thread call itself is fast (it only validates and spawns a
    background thread); the real wait is for on_result, via a plain
    asyncio.Future this handler's own event loop resolves through
    call_soon_threadsafe (on_result fires from the background thread
    run_installed_job spawned, not the GUI thread)."""
    window = current_context.get_main_window()
    if window is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    loop = asyncio.get_event_loop()
    result_future: asyncio.Future = loop.create_future()

    def _on_result(ok: bool, stdout: str, stderr: str, tb: str) -> None:
        loop.call_soon_threadsafe(result_future.set_result, (ok, stdout, stderr, tb))

    try:
        await _call_on_gui_thread(
            lambda: window.run_installed_job(args["name"], args.get("config_path") or None, _on_result)
        )
    except RuntimeError as e:
        return _text_result(str(e), is_error=True)
    except ValueError as e:
        return _text_result(str(e), is_error=True)
    ok, stdout, stderr, tb = await result_future
    return _text_result(json.dumps({"ok": ok, "stdout": stdout, "stderr": stderr, "traceback": tb}))


@tool(
    "desk_run_pipeline",
    "Run a pipe-chained verb DSL pipeline -- a "
    "single string of '|'-separated stages, each either a built-in verb call (reveal_widget "
    "<instance_id>, screenshot_widget <instance_id> <path>, screenshot_desk <path>, "
    "list_widget_instances, open_image, split_channels (splits a piped {\"path\": ...} image into "
    "a 3-item [{\"path\", \"channel\"}, ...] list, one per R/G/B channel), shell-quoted like any "
    "other command line), a 'py:' "
    "-prefixed base64-encoded Python expression escape hatch, or a map stage (`map +| verb1 | "
    "verb2 |+`, where everything between +| and |+ is itself a full sub-pipeline in this same "
    "syntax, including a nested map) that requires a list/array piped value, runs the "
    "sub-pipeline once per item, and recombines the per-item results into a new list. Every "
    "stage receives the previous stage's real output value (map's own sub-pipeline receives "
    "each item, not the outer pipeline's value); execution stops at the first stage (or map "
    "item) that raises or returns {\"ok\": false}. Returns the structured {ok, stages, value, "
    "traceback} result as JSON.",
    {"pipeline": str},
)
async def _run_pipeline(args: dict[str, Any]) -> dict[str, Any]:
    try:
        result = pipeline_dsl.run_pipeline(args["pipeline"])
    except ValueError as e:
        return _text_result(str(e), is_error=True)
    return _text_result(json.dumps(result))


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
    _run_pipeline,
]


def build_desk_mcp_server() -> McpSdkServerConfig:
    """Builds a fresh in-process MCP server instance -- called once per
    `ClaudeSession.start()` (TODO a762501), same lifecycle as the rest
    of that call's `ClaudeAgentOptions`."""
    return create_sdk_mcp_server(name=DESK_MCP_SERVER_NAME, tools=_TOOLS)
