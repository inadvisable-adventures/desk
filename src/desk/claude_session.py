"""ClaudeSession (TODO a596dbf): a background-thread wrapper around
claude_agent_sdk.ClaudeSDKClient, translating its async message/
permission-request stream into Qt-safe signals for the Claude (Desk)
widget (widgets/claude_desk/widget.py). See
plans/claude-widget-agent-sdk-integration.md.

Shared-logic module in desk. proper (not under widgets/) for the same
reason desk.terminal_widget exists -- widget directories can't import
each other directly. Only used by the new widget; the original PTY
-based Claude widget (widgets/claude/widget.py) is untouched.

Threading model: one dedicated background thread per ClaudeSession,
running its own asyncio event loop for the lifetime of the session --
the same background-thread-plus-signal-relay shape this codebase
already uses for other blocking/async work (widgets/git_status/
widget.py, widgets/voice_input/widget.py), rather than merging asyncio
into the Qt event loop (which would need a dependency like `qasync` for
a benefit not needed here -- each session is already independent).
send_prompt()/respond_to_permission() are handed to that loop via
asyncio.run_coroutine_threadsafe()/call_soon_threadsafe(); the
can_use_tool callback (itself invoked on the asyncio thread by the SDK)
blocks on an asyncio.Future until the Qt-side approval decision arrives
back through that same bridge.

Scoped sessions (TODO 0529501, start()'s allowed_paths): confirmed
directly (real live sessions, not assumed from docs) that neither
ClaudeAgentOptions(cwd=..., add_dirs=...) nor can_use_tool is an actual
access boundary -- a Read outside cwd/add_dirs just triggers a normal
permission_request (same as any other gated call, and succeeds once
allowed), and can_use_tool's own docstring says it's never consulted
under permission_mode="bypassPermissions". A `PreToolUse` hook is the
real boundary: it fires for every tool call regardless of permission
mode, confirmed to still deny an out-of-scope path even under
bypassPermissions. See plans/scoped-claude-session-api.md.
"""
import asyncio
import threading
import uuid
from pathlib import Path

import claude_agent_sdk as sdk
from PyQt6.QtCore import QObject, pyqtSignal

from desk.shell.desk_mcp_server import DESK_MCP_SERVER_NAME, RUN_INSTALLED_JOB_TOOL_NAME, build_desk_mcp_server

# Re-exported (TODO f4a7872) so widgets/claude_desk/widget.py never needs
# its own `import claude_agent_sdk` just to check whether a background
# task's status is terminal -- this module stays the one place that
# import lives, same reasoning as everything else here.
TERMINAL_TASK_STATUSES = sdk.TERMINAL_TASK_STATUSES

# TODO 0529501: the fixed tool set for a scoped (allowed_paths-restricted)
# session. Deliberately excludes Bash -- its tool_input is just
# {"command": "..."}, with no structured path field a hook could check,
# so the only safe answer is not granting it at all, not attempting to
# sandbox it. Also excludes Glob/Grep/WebFetch/WebSearch/Task/Skill --
# out of scope for the motivating "hand Claude this specific file" use
# case; a real caller needing directory search would need its own
# path-checking added deliberately, not assumed safe by omission.
_SCOPED_TOOLS = ["Read", "Write", "Edit", "NotebookEdit"]


def _path_is_allowed(path_str: str, allowed_paths: list[Path]) -> bool:
    """Whether `path_str` (a tool call's own file_path/notebook_path)
    resolves to one of `allowed_paths`' files, or under one of its
    directories. Both sides are resolved so a relative or
    symlink-through-a-non-malicious-intermediate path still matches --
    see plans/scoped-claude-session-api.md's "Key tradeoffs" for what
    this deliberately doesn't try to defend against."""
    try:
        resolved = Path(path_str).resolve()
    except OSError:
        return False
    for allowed in allowed_paths:
        allowed_resolved = allowed.resolve()
        if resolved == allowed_resolved or allowed_resolved in resolved.parents:
            return True
    return False


class ClaudeSession(QObject):
    """One Claude Agent SDK session. Signals are emitted from the
    session's own background thread; PyQt6 auto-queues delivery onto
    whichever thread each connected slot's receiver lives on (the same
    guarantee widgets/git_status/widget.py's _Relay already relies
    on), so callers never need to marshal these themselves."""

    assistant_text = pyqtSignal(str)
    tool_use = pyqtSignal(str, str, dict)  # tool_use_id, name, input
    tool_result = pyqtSignal(str, object, bool)  # tool_use_id, content, is_error
    permission_request = pyqtSignal(str, str, dict)  # request_id, tool_name, input
    turn_complete = pyqtSignal(dict)  # see _handle_message's ResultMessage branch
    session_error = pyqtSignal(str)
    session_ended = pyqtSignal()
    # TODO f4a7872: one combined signal for every background-task
    # lifecycle message (task_id, patch) -- the four Task*Message
    # subtypes below each just update *some* fields of one tracked
    # task, so the widget-side handling is a single dict-merge
    # regardless of which subtype produced it. A field a given subtype
    # doesn't itself report is simply absent from `patch` -- but a
    # present field CAN still be `None` (e.g. TaskProgressMessage's own
    # `last_tool_name` before any tool has run yet), so a receiver must
    # filter `None` values out of its own merge rather than assume
    # their mere absence is the only case to handle.
    task_event = pyqtSignal(str, dict)
    # Emitted once connect() succeeds, before any initial_prompt turn (if
    # any) is sent. A resumed session with no initial_prompt never fires
    # turn_complete/session_error at all otherwise -- found via real
    # verification (tests/verify/verify_claude_desk_widget.py), not
    # assumed: without this, the widget's prompt input would stay
    # disabled forever after a resume with nothing queued to send.
    connected = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: sdk.ClaudeSDKClient | None = None
        # Only ever read/written from _loop's own thread (created inside
        # _can_use_tool, resolved inside respond_to_permission's
        # call_soon_threadsafe callback) -- no lock needed.
        self._pending_permissions: dict[str, asyncio.Future] = {}
        # Set by start() when scoped (TODO 0529501); read only by
        # _check_path_scope, itself only ever invoked (by the SDK) after
        # start() has run, so no race with __init__'s own None default.
        self._allowed_paths: list[Path] | None = None

    def start(
        self,
        session_id: str,
        resume: bool,
        model: str | None,
        permission_mode: str,
        cwd: Path | None,
        initial_prompt: str = "",
        allowed_paths: list[Path] | None = None,
    ) -> None:
        """Starts the background thread/event loop and connects. On a
        fresh (non-resume) session, session_id is assigned up front (so
        a later reload can resume it, mirroring the existing widget's
        --session-id/--resume split, TODO 1d7331b) and initial_prompt
        (if non-empty) is sent as the first turn; on resume,
        initial_prompt is ignored -- same convention as
        ClaudeWidget.start_session.

        allowed_paths (TODO 0529501): when given, the session is scoped
        to only the file(s)/directory(ies) listed -- see this module's
        own docstring and plans/scoped-claude-session-api.md for why a
        `PreToolUse` hook (not cwd/add_dirs/can_use_tool) is what
        actually enforces this. `None` (the default) is today's
        unrestricted behavior, unchanged."""
        self._allowed_paths = allowed_paths
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        asyncio.run_coroutine_threadsafe(
            self._connect_and_maybe_prompt(session_id, resume, model, permission_mode, cwd, initial_prompt),
            self._loop,
        )

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        self._loop.close()

    async def _connect_and_maybe_prompt(
        self,
        session_id: str,
        resume: bool,
        model: str | None,
        permission_mode: str,
        cwd: Path | None,
        initial_prompt: str,
    ) -> None:
        scoped = self._allowed_paths is not None
        options = sdk.ClaudeAgentOptions(
            session_id=None if resume else session_id,
            resume=session_id if resume else None,
            model=model,
            permission_mode=permission_mode,
            cwd=str(cwd) if cwd is not None else None,
            can_use_tool=self._can_use_tool,
            # TODO 0529501: a scoped session gets a fixed, narrower tool
            # set (no Bash -- see _SCOPED_TOOLS's own comment) and no
            # Desk MCP server (TODO a762501's live shell-control channel
            # is broader than "only the files this session was scoped
            # to" and has no place here), enforced by the PreToolUse
            # hook below rather than by tools/mcp_servers alone -- see
            # this module's docstring for why cwd/add_dirs/tools by
            # themselves were confirmed not to be a real boundary.
            tools=_SCOPED_TOOLS if scoped else None,
            hooks={"PreToolUse": [sdk.HookMatcher(matcher=None, hooks=[self._check_path_scope])]}
            if scoped
            else None,
            # TODO a762501: the in-process Desk MCP server -- a live,
            # queryable channel into Desk's own running shell. Tool
            # calls (mcp__desk__...) flow through can_use_tool above
            # like any other tool, no separate approval path. Omitted
            # entirely for a scoped session (TODO 0529501, see above).
            mcp_servers={} if scoped else {DESK_MCP_SERVER_NAME: build_desk_mcp_server()},
            # TODO b9d3de5: a static, launch-time self-fact -- session_id
            # doubles as this widget's own instance_id (see
            # DeskWindow._bind_claude_desk_widget) -- exposed as a real
            # env var rather than a prompt sentence so it costs nothing
            # per turn and survives context compaction. Documented in
            # desk-temporary-ui.md's "Environment variables" section.
            env={"DESK_WIDGET_INSTANCE_ID": session_id},
        )
        try:
            self._client = sdk.ClaudeSDKClient(options)
            await self._client.connect()
        except Exception as exc:  # noqa: BLE001 -- surfaced to the user, not swallowed
            self.session_error.emit(str(exc))
            return
        self.connected.emit()
        if initial_prompt:
            await self._query_and_stream(initial_prompt)

    def send_prompt(self, text: str) -> None:
        if self._loop is None or self._client is None:
            return
        asyncio.run_coroutine_threadsafe(self._query_and_stream(text), self._loop)

    def set_permission_mode(self, mode: str) -> None:
        """Changes permission mode live, mid-session (TODO `e9eddba`) --
        a no-op before any session has started or after it's stopped
        (self._loop/self._client not set yet/no longer set), same
        guard shape as send_prompt above, so a caller (the widget's own
        combo box) never needs its own "is a session currently live"
        bookkeeping."""
        if self._loop is None or self._client is None:
            return
        asyncio.run_coroutine_threadsafe(self._set_permission_mode(mode), self._loop)

    async def _set_permission_mode(self, mode: str) -> None:
        assert self._client is not None
        try:
            await self._client.set_permission_mode(mode)
        except Exception as exc:  # noqa: BLE001 -- surfaced to the user, not swallowed
            self.session_error.emit(str(exc))

    async def _query_and_stream(self, text: str) -> None:
        assert self._client is not None
        try:
            await self._client.query(text)
            async for message in self._client.receive_response():
                self._handle_message(message)
        except Exception as exc:  # noqa: BLE001
            self.session_error.emit(str(exc))

    def _handle_message(self, message: object) -> None:
        if isinstance(message, sdk.AssistantMessage):
            for block in message.content:
                if isinstance(block, sdk.TextBlock):
                    self.assistant_text.emit(block.text)
                elif isinstance(block, sdk.ToolUseBlock):
                    self.tool_use.emit(block.id, block.name, block.input)
                elif isinstance(block, sdk.ToolResultBlock):
                    self.tool_result.emit(block.tool_use_id, block.content, bool(block.is_error))
        elif isinstance(message, sdk.ResultMessage):
            self.turn_complete.emit(
                {
                    "is_error": message.is_error,
                    "result": message.result,
                    "total_cost_usd": message.total_cost_usd,
                    "duration_ms": message.duration_ms,
                    "num_turns": message.num_turns,
                }
            )
        elif isinstance(message, sdk.TaskStartedMessage):
            self.task_event.emit(
                message.task_id, {"description": message.description, "status": "running"}
            )
        elif isinstance(message, sdk.TaskProgressMessage):
            self.task_event.emit(
                message.task_id,
                {
                    "description": message.description,
                    "status": "running",
                    "last_tool_name": message.last_tool_name,
                },
            )
        elif isinstance(message, sdk.TaskNotificationMessage):
            self.task_event.emit(
                message.task_id, {"status": message.status, "summary": message.summary}
            )
        elif isinstance(message, sdk.TaskUpdatedMessage):
            # `patch` is the CLI's own raw payload (TODO f4a7872) --
            # `status` is folded in under its own key (rather than left
            # nested) so the widget's merge only ever needs to look at
            # top-level "status", the same shape TaskNotificationMessage
            # above already produces.
            patch = dict(message.patch)
            if message.status is not None:
                patch["status"] = message.status
            self.task_event.emit(message.task_id, patch)

    async def _check_path_scope(self, input_data: dict, tool_use_id: str | None, context: object) -> dict:
        """`PreToolUse` hook callback, only installed when `start()` was
        given `allowed_paths` (TODO 0529501). Fires for *every* tool
        call unconditionally -- confirmed directly (a real session
        under permission_mode="bypassPermissions") that this still
        denies an out-of-scope path even in the one mode `can_use_tool`
        is never consulted for. Returns a deny for any call whose
        file_path/notebook_path is missing or resolves outside
        self._allowed_paths; an empty dict otherwise, which falls
        through to normal can_use_tool handling for genuinely in-scope
        calls (this hook only ever narrows access, never grants it)."""
        assert self._allowed_paths is not None
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if path is None or not _path_is_allowed(path, self._allowed_paths):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{tool_name}: path outside this session's allowed_paths scope"
                        if path is None
                        else f"{tool_name}: {path!r} is outside this session's allowed_paths scope"
                    ),
                }
            }
        return {}

    async def _can_use_tool(self, tool_name: str, tool_input: dict, context: object) -> object:
        """The SDK's own tool-approval hook (claude_agent_sdk
        .ClaudeAgentOptions.can_use_tool) -- confirmed directly (a real
        session, not assumed from docs) that this fires for genuinely
        gated actions (e.g. Write, or a file-creating Bash command) and
        is NOT invoked for actions the CLI's own built-in heuristics
        already auto-approve (e.g. a plain read-only `echo`), same as
        real interactive `claude` usage."""
        # TODO 7dca383: an Installed Job is approved once, at
        # desk_install_job time (which stays on the normal gated path
        # below) -- running it via desk_run_installed_job must never
        # re-prompt, per that item's own spec, so it's auto-allowed
        # here before a pending-permission future is even created. This
        # is only safe because desk_run_installed_job itself refuses to
        # run if the on-disk source no longer matches the version hash
        # that was actually installed/approved -- see that tool's own
        # docstring in desk.shell.desk_mcp_server.
        if tool_name == f"mcp__{DESK_MCP_SERVER_NAME}__{RUN_INSTALLED_JOB_TOOL_NAME}":
            return sdk.PermissionResultAllow(behavior="allow", updated_input=None, updated_permissions=None)
        request_id = uuid.uuid4().hex
        assert self._loop is not None
        future = self._loop.create_future()
        self._pending_permissions[request_id] = future
        self.permission_request.emit(request_id, tool_name, tool_input)
        allow, message = await future
        del self._pending_permissions[request_id]
        if allow:
            return sdk.PermissionResultAllow(behavior="allow", updated_input=None, updated_permissions=None)
        return sdk.PermissionResultDeny(behavior="deny", message=message, interrupt=False)

    def respond_to_permission(self, request_id: str, allow: bool, message: str = "") -> None:
        """Called from the Qt/GUI thread once the widget's own approval
        UI resolves a pending permission_request. Resolves the
        asyncio.Future _can_use_tool is awaiting, via
        call_soon_threadsafe since this runs on a different thread than
        the one that owns _loop."""
        if self._loop is None:
            return

        def _resolve() -> None:
            future = self._pending_permissions.get(request_id)
            if future is not None and not future.done():
                future.set_result((allow, message))

        self._loop.call_soon_threadsafe(_resolve)

    def stop(self) -> None:
        """Disconnects the client and stops the background loop/thread,
        without blocking the calling (GUI) thread -- teardown runs
        entirely on _loop's own thread; session_ended is emitted from
        there once done (PyQt6 auto-queues it back to the GUI thread,
        same as every other signal here)."""
        if self._loop is None:
            return

        async def _disconnect_and_stop() -> None:
            if self._client is not None:
                try:
                    await self._client.disconnect()
                except Exception:  # noqa: BLE001 -- best-effort teardown
                    pass
            self.session_ended.emit()
            self._loop.stop()

        asyncio.run_coroutine_threadsafe(_disconnect_and_stop(), self._loop)
