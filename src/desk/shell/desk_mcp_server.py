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
do by clicking around, just without the file-drop ceremony. The one
exception is `desk_git_commit` (TODO `c33657f`), which mirrors no GUI
button: it grants no capability the Bash tool doesn't already have
(same `can_use_tool` approval), it only changes how a commit message
travels -- a structured parameter fed to git on stdin, never a shell
string (see TODO `8e8db18` for the quoting hazard that avoids). The
`TODO.md` tools are deliberately read-only (list/get-next, no
mark-complete/reorder) -- see TODO `a762501`'s own `TODO.md` note on
why a mutating tool would bypass this project's plan-then-verify
discipline."""

import asyncio
import json
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from pathlib import Path
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, create_sdk_mcp_server, tool

from desk import pipeline_dsl
from desk.event_mediator import MediatedEvent
from desk.widget_logs import RECORDING_EVENT, STOPPED_RECORDING_EVENT, format_time_iso, parse_time_ms
from desk.shell import current_context
from desk.todo_file import TodoItem, find_nearest_todo_file, parse_todo_file

DESK_MCP_SERVER_NAME = "desk"

# Referenced by desk.claude_session.ClaudeSession._can_use_tool (TODO
# 7dca383) to build the fully-qualified "mcp__desk__desk_run_installed_job"
# name its bypass branch matches against -- kept here, not duplicated
# as a literal there, so the two can never drift if this tool is ever
# renamed.
RUN_INSTALLED_JOB_TOOL_NAME = "desk_run_installed_job"

# The sender id an agent-raised desk event is published under (TODO
# 71d11da). Never a subscribed widget instance, so the mediator's
# "sender never receives its own publish" rule skips nobody, and the Event
# Log's sender column shows plainly where the event came from.
AGENT_EVENT_SENDER_ID = "agent"

# Names an agent may not raise: the `desk.` namespace is Desk's own
# (`desk.state.changed`, ...), and the recording events are published by
# Claude (Desk)'s record button -- forging either would make widgets act
# on something Desk never did.
RESERVED_EVENT_NAME_PREFIX = "desk."
RESERVED_EVENT_NAMES = frozenset({RECORDING_EVENT, STOPPED_RECORDING_EVENT})
MAX_EVENT_NAME_CHARS = 200
# Hard backstop only: every subscriber's queue and the event log hold the
# payload. The documented guidance is much lower (use a file past ~1 KiB).
MAX_EVENT_PAYLOAD_BYTES = 64 * 1024

# TODO 30069f6: desk_wait_for_event blocks for as long as it takes an event
# to arrive, so it is meant for a background sub-agent. Referenced by
# desk.claude_session.ClaudeSession's PreToolUse hook to build the
# fully-qualified "mcp__desk__desk_wait_for_event" matcher (same no-drift
# reasoning as RUN_INSTALLED_JOB_TOOL_NAME above).
WAIT_FOR_EVENT_TOOL_NAME = "desk_wait_for_event"
EVENT_LISTENER_ID_PREFIX = "agent-listener:"
# EventMediator.poll() clamps to 30 s, and a blocked thread cannot be
# interrupted, so the wait polls in slices this long and checks a cancel flag
# in between: the longest a cancelled/ended wait lingers.
EVENT_WAIT_SLICE_SECONDS = 1.0
# A dedicated pool, so listeners can never starve the default executor that
# GUI-thread hops (_call_on_gui_thread) share.
MAX_CONCURRENT_EVENT_LISTENERS = 8
_listener_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_EVENT_LISTENERS, thread_name_prefix="desk-event-wait")
_active_listeners = 0
_active_listeners_lock = threading.Lock()

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
    "with the workspace capability. Each entry's stale is true when that instance is showing "
    "the titlebar [STALE] badge (its placed content no longer matches what's currently "
    "registered/on disk) -- check it before trusting a just-edited widget's behavior; a stale "
    "instance is still running its own pre-edit code.",
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
    "desk_list_widget_logs",
    "List the named, time-stamped logs widgets have appended to (TODO 1f74c27) -- name, entry "
    "count, and first/last entry time (ISO-8601, local zone). Read-only. Call this to discover "
    "what desk_query_widget_log can be asked about; log names are chosen by the widgets, "
    "conventionally a short descriptive name followed by a unique suffix.",
    {},
)
async def _list_widget_logs(args: dict[str, Any]) -> dict[str, Any]:
    store = current_context.get_widget_log_store()
    if store is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    logs = [
        {
            "name": log.name,
            "count": log.count,
            "first": format_time_iso(log.first_t) if log.first_t is not None else None,
            "last": format_time_iso(log.last_t) if log.last_t is not None else None,
        }
        for log in store.list_logs()
    ]
    return _text_result(json.dumps(logs))


@tool(
    "desk_query_widget_log",
    "Time-range query of one named widget log (see desk_list_widget_logs). start and end are "
    "optional and INCLUSIVE; each is an ISO-8601 datetime (no zone = the Desk machine's local "
    "time; a trailing Z = UTC) or epoch milliseconds. limit (default 200) caps the result: with "
    "order \"asc\" (default) you get the first `limit` entries in range, oldest first; with "
    "\"desc\" the newest `limit`, newest first. Output is one `<ISO-time>\\t<text>` line per "
    "entry, plus a trailing note if the range held more than limit. Read-only. Pair with a "
    "timecoded transcript's absolute start time to correlate a widget's log with what was said.",
    {
        "type": "object",
        "properties": {
            "log_name": {"type": "string"},
            "start": {"type": ["string", "integer"]},
            "end": {"type": ["string", "integer"]},
            "limit": {"type": "integer"},
            "order": {"type": "string", "enum": ["asc", "desc"]},
        },
        "required": ["log_name"],
    },
)
async def _query_widget_log(args: dict[str, Any]) -> dict[str, Any]:
    store = current_context.get_widget_log_store()
    if store is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    try:
        start = parse_time_ms(args["start"]) if args.get("start") is not None else None
        end = parse_time_ms(args["end"]) if args.get("end") is not None else None
    except ValueError as e:
        return _text_result(str(e), is_error=True)
    limit = args.get("limit", 200)
    if not isinstance(limit, int) or limit < 1:
        return _text_result("limit must be a positive integer", is_error=True)
    newest_first = args.get("order", "asc") == "desc"
    # One extra entry only to learn whether the range held more than limit.
    entries = store.query(args["log_name"], start, end, limit + 1, newest_first)
    truncated = len(entries) > limit
    lines = [f"{format_time_iso(entry.t)}\t{entry.text}" for entry in entries[:limit]]
    if truncated:
        lines.append(f"[more entries in range; showing {limit} -- narrow start/end or raise limit]")
    elif not entries and not any(log.name == args["log_name"] for log in store.list_logs()):
        return _text_result(f"No such log: {args['log_name']!r} (see desk_list_widget_logs)", is_error=True)
    if not lines:
        return _text_result("(no entries in range)")
    return _text_result("\n".join(lines))


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


GIT_COMMIT_TIMEOUT_SECONDS = 300  # a pre-commit hook can legitimately be slow


def run_git_commit(directory: Path, message: str, files: list[str] | None) -> tuple[bool, str]:
    """TODO c33657f: the whole of `desk_git_commit`, synchronous and free
    of any MCP/GUI machinery so it is directly testable against a real
    repo. The message goes to `git commit -F -` on stdin and every
    command is an argv list with `shell=False`, so no shell (and no
    argv parsing of the message) ever sees it. Deliberately no
    blanket-add, amend, or --no-verify: `files` is exact paths only,
    each of which must resolve inside `directory`. Returns (ok, text);
    on failure text is git's own combined output so the caller can react
    (fix a hook failure and retry, etc.)."""
    if not message.strip():
        return False, "Commit message is empty."
    root = directory.resolve()
    to_add: list[str] = []
    for name in files or []:
        resolved = (root / name).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            return False, f"Refusing to stage {name!r}: it resolves outside the project directory ({root})."
        to_add.append(str(resolved))

    def _git(argv: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *argv],
            cwd=root,
            input=stdin,
            capture_output=True,
            text=True,
            shell=False,
            timeout=GIT_COMMIT_TIMEOUT_SECONDS,
        )

    def _output(proc: subprocess.CompletedProcess) -> str:
        return "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)

    try:
        if to_add:
            added = _git(["add", "--", *to_add])
            if added.returncode != 0:
                return False, f"git add failed:\n{_output(added)}"
        committed = _git(["commit", "-F", "-"], stdin=message)
        if committed.returncode != 0:
            return False, f"git commit failed (exit {committed.returncode}):\n{_output(committed)}"
        head = _git(["rev-parse", "--short", "HEAD"])
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"git could not be run: {e}"
    return True, f"commit {head.stdout.strip()}\n{_output(committed)}"


@tool(
    "desk_git_commit",
    "Create a git commit in the current project, passing the commit message as a structured "
    "parameter. Prefer this over a Bash `git commit -m \"$(cat <<EOF ...)\"` heredoc: the message "
    "never goes through shell quoting, so apostrophes, backticks, `$(...)`, double quotes and "
    "newlines all work verbatim with no escaping. `files` is an optional list of exact paths "
    "(relative to the current project directory) to `git add` first; there is deliberately no "
    "add-everything option. If omitted, commits whatever is already staged. No amend, no "
    "--no-verify (hooks always run). Returns the short commit hash and git's output, or git's "
    "real error output (nothing staged, a hook failing, not a repository, ...).",
    # Hand-written JSON Schema: `files` must stay genuinely optional (see
    # _run_installed_job_tool's note on the {name: type} shorthand).
    {
        "type": "object",
        "properties": {"message": {"type": "string"}, "files": {"type": "array", "items": {"type": "string"}}},
        "required": ["message"],
    },
)
async def _git_commit(args: dict[str, Any]) -> dict[str, Any]:
    directory = current_context.get_current_desk_directory()
    if directory is None:
        return _text_result("No current Desk directory known.", is_error=True)
    ok, text = await asyncio.to_thread(run_git_commit, directory, args["message"], args.get("files"))
    return _text_result(text, is_error=not ok)


@tool(
    "desk_raise_event",
    "Raise a named desk event, with an optional JSON payload, on the same channel widgets use "
    "(`desk.events`), so any widget instance subscribed to that name receives it immediately -- "
    "no file to drop or poll. A payload may be omitted for a bare signal (\"I updated the "
    "file\"), or carry the data a file would otherwise hold; keep it small (a message over about "
    "1 KB should usually be a file, with the event just announcing it; hard limit 64 KiB). "
    "Names starting with `desk.` and the names `recording`/`stopped_recording` are reserved for "
    "Desk itself. Returns how many widget instances were subscribed to the name at the moment of "
    "publishing (0 means nobody was listening; the event is still logged).",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "payload": {},
        },
        "required": ["name"],
    },
)
async def _raise_event(args: dict[str, Any]) -> dict[str, Any]:
    name = args.get("name")
    if not isinstance(name, str) or not name.strip():
        return _text_result("name must be a non-empty string.", is_error=True)
    if len(name) > MAX_EVENT_NAME_CHARS:
        return _text_result(f"name is longer than {MAX_EVENT_NAME_CHARS} characters.", is_error=True)
    if name.startswith(RESERVED_EVENT_NAME_PREFIX) or name in RESERVED_EVENT_NAMES:
        return _text_result(
            f"{name!r} is reserved for Desk's own events (the `desk.` prefix and "
            f"{', '.join(sorted(RESERVED_EVENT_NAMES))}); pick another name.",
            is_error=True,
        )
    payload = args.get("payload")
    try:
        encoded_size = len(json.dumps(payload).encode("utf-8"))
    except (TypeError, ValueError) as e:
        return _text_result(f"payload is not JSON-serializable: {e}", is_error=True)
    if encoded_size > MAX_EVENT_PAYLOAD_BYTES:
        return _text_result(
            f"payload is {encoded_size} bytes of JSON, over the {MAX_EVENT_PAYLOAD_BYTES}-byte limit; "
            "write it to a file and raise an event naming the file instead.",
            is_error=True,
        )
    mediator = current_context.get_event_mediator()
    if mediator is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    subscribers = sum(1 for names in mediator.list_subscriptions().values() if name in names)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, mediator.publish, name, payload, AGENT_EVENT_SENDER_ID)
    return _text_result(f"Raised {name!r}; {subscribers} widget instance(s) subscribed at publish time.")


def wait_for_event_hook(input_data: dict[str, Any]) -> dict[str, Any]:
    """The decision half of `ClaudeSession`'s PreToolUse hook for
    desk_wait_for_event (TODO 30069f6), kept here and pure so it can be
    checked without a live session: deny a call that is not made from inside
    a sub-agent. The hook input carries `agent_id` only when the call comes
    from a Task-spawned sub-agent (absent on the main conversation), and a
    PreToolUse hook fires whatever the permission mode, unlike
    `can_use_tool`. The SDK gives no foreground/background flag, so a
    *foreground* sub-agent still passes -- the tool description and
    tempui-agent-events.md say to use a background one."""
    if input_data.get("agent_id"):
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{WAIT_FOR_EVENT_TOOL_NAME} can wait indefinitely, so calling it from the main "
                "conversation would freeze it. Spawn a background sub-agent (Agent tool with "
                "run_in_background) and call it from there."
            ),
        }
    }


def _event_wait_result(status: str, **fields: Any) -> dict[str, Any]:
    return _text_result(json.dumps({"status": status, **fields}))


def _wait_for_mediated_event(
    mediator: Any, listener_id: str, cancel: threading.Event, timeout_seconds: float | None
) -> tuple[str, MediatedEvent | None]:
    """Blocking half of desk_wait_for_event, run on `_listener_pool`:
    ("event", e), ("timeout", None), ("ended", None) (the subscription
    vanished -- Desk switched and `clear_all()` dropped it) or
    ("cancelled", None)."""
    deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
    while not cancel.is_set():
        if listener_id not in mediator.list_subscriptions():
            return "ended", None
        slice_seconds = EVENT_WAIT_SLICE_SECONDS
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "timeout", None
            slice_seconds = min(slice_seconds, remaining)
        event = mediator.poll(listener_id, slice_seconds)
        if event is not None:
            return "event", event
    return "cancelled", None


@tool(
    "desk_wait_for_event",
    "Block until a named desk event arrives and return it (status, name, payload, sender, "
    "timestamp) -- e.g. the answer a widget publishes after you asked it something with "
    "desk_raise_event. It can wait with NO timeout, so call it ONLY from a background sub-agent "
    "(Agent tool with run_in_background), never from the main conversation, which would freeze "
    "it; a call from the main conversation is refused. Optional timeout_seconds ends the wait "
    "early with status \"timeout\". Status \"ended\" means Desk was switched and the listening "
    "stopped. Listening lasts only while the call is in flight, so an event published between "
    "two calls is missed: call again right after handling each result, and keep anything that "
    "must not be lost in a file.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "timeout_seconds": {"type": "number"},
        },
        "required": ["name"],
    },
)
async def _wait_for_event(args: dict[str, Any]) -> dict[str, Any]:
    global _active_listeners
    name = args.get("name")
    if not isinstance(name, str) or not name.strip():
        return _text_result("name must be a non-empty string.", is_error=True)
    timeout_seconds = args.get("timeout_seconds")
    if timeout_seconds is not None and (
        isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0
    ):
        return _text_result("timeout_seconds must be a positive number, or omitted to wait indefinitely.", is_error=True)
    mediator = current_context.get_event_mediator()
    if mediator is None:
        return _text_result(_NOT_READY_MESSAGE, is_error=True)
    with _active_listeners_lock:
        if _active_listeners >= MAX_CONCURRENT_EVENT_LISTENERS:
            return _text_result(
                f"{_active_listeners} desk_wait_for_event calls are already waiting (limit "
                f"{MAX_CONCURRENT_EVENT_LISTENERS}); wait for one to finish.",
                is_error=True,
            )
        _active_listeners += 1
    listener_id = EVENT_LISTENER_ID_PREFIX + uuid.uuid4().hex
    cancel = threading.Event()
    mediator.subscribe(listener_id, name)
    loop = asyncio.get_event_loop()
    try:
        status, event = await loop.run_in_executor(
            _listener_pool, _wait_for_mediated_event, mediator, listener_id, cancel, timeout_seconds
        )
    except asyncio.CancelledError:
        cancel.set()
        raise
    finally:
        cancel.set()
        mediator.unsubscribe_all(listener_id)
        with _active_listeners_lock:
            _active_listeners -= 1
    if status == "event" and event is not None:
        return _event_wait_result(
            "event", name=event.name, payload=event.payload, sender=event.sender_instance_id, timestamp=event.timestamp
        )
    if status == "timeout":
        return _event_wait_result("timeout", name=name, timeout_seconds=timeout_seconds)
    return _event_wait_result("ended", name=name)


_TOOLS = [
    _reveal_widget,
    _screenshot_widget,
    _screenshot_desk,
    _list_widget_instances,
    _save_desk,
    _list_todo_items,
    _get_next_todo_item,
    _list_widget_logs,
    _query_widget_log,
    _install_job,
    _run_installed_job_tool,
    _run_pipeline,
    _git_commit,
    _raise_event,
    _wait_for_event,
]


def build_desk_mcp_server() -> McpSdkServerConfig:
    """Builds a fresh in-process MCP server instance -- called once per
    `ClaudeSession.start()` (TODO a762501), same lifecycle as the rest
    of that call's `ClaudeAgentOptions`."""
    return create_sdk_mcp_server(name=DESK_MCP_SERVER_NAME, tools=_TOOLS)
