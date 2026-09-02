# In-process Desk MCP server (TODO `a762501`)

## Summary

A new in-process MCP server (`claude_agent_sdk.create_sdk_mcp_server`,
`type: "sdk"` -- no subprocess, no port) wired into every Claude
(Desk)/`claude` session's own `ClaudeAgentOptions.mcp_servers`, giving
an agent a live, queryable channel into Desk's own running shell --
reveal/screenshot a placed widget, list what's currently placed, force
a save, and read the current project's `TODO.md` state -- instead of
the file-drop-and-click-Start `Job`/`DeskProc` ceremony for these
specific actions. Confirmed directly, with a real live session against
the actual installed SDK (not assumed from docs), that MCP-server
tools are discovered (via `ToolSearch`, the same deferred-tool
mechanism this environment's own outer harness uses), permission-gated
through the exact same `can_use_tool` hook `ClaudeSession` already
implements (no new approval UI needed), and round-trip a real result
back to the model.

## Affected files

- `src/desk/shell/desk_mcp_server.py` (new) -- the server itself: one
  `@tool`-decorated async handler per capability, `build_desk_mcp_server()
  -> McpSdkServerConfig`.
- `src/desk/claude_session.py` -- `_connect_and_maybe_prompt`'s
  `ClaudeAgentOptions(...)` call gains `mcp_servers={"desk":
  build_desk_mcp_server()}`.
- `tests/verify/` -- new coverage.

## Design decisions

- **Tool handlers are thin async wrappers over `current_context`
  hooks, duplicated rather than reusing `widgets/desk_proc_runner
  /widget.py`'s `DeskProcApi`.** A widget's own `widget.py` isn't
  meant to be imported from outside its directory (see
  `CLAUDE_WIDGET_PROMPT`'s own duplication note in
  `widgets/claude_desk/widget.py`: "widget directories can't import
  each other"), and this server isn't itself a widget -- it's
  constructed directly by `claude_session.py`. Each tool re-derives
  its own thin wrapper instead; kept in sync by hand with
  `DeskProcApi`'s equivalent methods, the same accepted cost that
  duplication already has elsewhere in this codebase.
- **GUI-thread marshaling reuses `desk.server.app.run_on_gui`'s exact
  idiom** (`await loop.run_in_executor(None, gui_thread_caller, fn)`),
  not a raw blocking call to `current_context.get_gui_thread_caller()`
  -- a tool handler is `async def`, running on this session's own
  private event loop (`ClaudeSession._loop`); blocking that loop
  synchronously while waiting for the GUI thread would stall anything
  else that loop needs to do (e.g. a concurrent `_can_use_tool` future
  resolution) for no reason, when `run_in_executor` avoids it for
  free.
- **No new capability/permission mechanism -- reuses `ClaudeSession
  ._can_use_tool` as-is.** Confirmed directly: an MCP-server tool call
  (`mcp__desk__<name>`) is gated through the exact same `can_use_tool`
  hook every other tool already is, so it surfaces through
  `ClaudeDeskWidget`'s existing real approval UI automatically -- no
  special-casing by tool name anywhere.
- **Read-only/side-effect-bounded tool set for this first pass**:
  reveal a widget, screenshot a widget/the canvas, list placed widget
  instances, force a save, list `TODO.md` items, get the next
  actionable `TODO.md` item. All either read-only or (`desk_save`,
  `desk_reveal_widget`) side effects a user could already trigger by
  hand via existing UI (a titlebar button, the eye button) -- nothing
  here lets an agent do something it couldn't already do by clicking
  around, just without needing the file-drop ceremony. The `TODO.md`
  tools are deliberately **read-only** (list/get-next, no
  mark-complete/reorder) -- see TODO `a762501`'s own `TODO.md` note on
  why a mutating tool would bypass this project's plan-then-verify
  discipline.
- **`desk_list_todo_items`/`desk_get_next_todo_item` reuse
  `desk.todo_file.find_nearest_todo_file`/`parse_todo_file` directly**
  -- the exact same parser the real TODO widget already uses, so
  "what does the TODO API say" and "what does the TODO widget show"
  can never drift apart.
- **The "harder half" (Desk pushing structured input into an
  already-running session) is explicitly out of scope for this pass**
  -- per the TODO item's own note, that's a different technical shape
  (server-initiated, not tool-call-initiated) and not resolved here.

## Step-by-step implementation

1. `src/desk/shell/desk_mcp_server.py` (new): `_text_result`,
   `_call_on_gui_thread` (the `run_on_gui`-mirroring helper), one
   `@tool`-decorated handler each for `desk_reveal_widget`,
   `desk_screenshot_widget`, `desk_screenshot_desk`,
   `desk_list_widget_instances`, `desk_save`, `desk_list_todo_items`,
   `desk_get_next_todo_item`; `build_desk_mcp_server() ->
   McpSdkServerConfig`.
2. `claude_session.py`: import `build_desk_mcp_server`; add
   `mcp_servers={"desk": build_desk_mcp_server()}` to the existing
   `ClaudeAgentOptions(...)` call in `_connect_and_maybe_prompt`.
3. New verify coverage (see below) -- calling each tool handler
   directly as a plain async function with fake `current_context`
   hooks, **not** a real live SDK session (matching
   `verify_claude_desk_widget.py`'s own established "none touching the
   real Claude API" convention, for cost/reliability reasons) --
   real-session behavior was confirmed manually, ad hoc, during this
   session's own design validation (see this plan's Summary), not
   baked into the permanent, repeatedly-run suite.
4. Run the full `tests/verify/` suite.

## Key tradeoffs

- No automated, permanently-run test actually exercises a real
  `ClaudeSDKClient` session calling through to this server -- the
  ad hoc manual check during design (a real session, `desk_ping`
  round-tripping a marker string end to end, including the
  `can_use_tool` approval hook firing) isn't repeatable/checked-in,
  consistent with this codebase's existing avoid-the-real-API
  testing convention for Claude sessions specifically.
- `desk_screenshot_widget`/`desk_screenshot_desk`/`desk_reveal_widget`
  duplicate `DeskProcApi`'s own logic rather than sharing it (see
  Design decisions) -- a future refactor could pull the shared
  "resolve `current_context` hooks, marshal to GUI thread" logic into
  a common, non-widget-directory module both could import, but that's
  not done here.
- Doesn't expose `desk.state.*` (the shared, schema-validated key/value
  store) as tools -- left for a later pass if/when a concrete need for
  it shows up here specifically.

## Verification

New checks, real (no mocking of `current_context` itself -- real hook
registration/lookup, fake `DeskWindow`-shaped objects standing in for
the GUI thread):
- `tests/verify/verify_desk_mcp_server.py` (new): each tool handler
  called directly as a plain async function (`asyncio.run`), with a
  fake `current_context.get_gui_thread_caller()` (runs `fn()`
  synchronously, recording calls) and a fake main-window-shaped
  object: `desk_reveal_widget`/`desk_screenshot_widget`/
  `desk_screenshot_desk`/`desk_save` route through to the real fake
  window methods with the right arguments and return the right
  `is_error`/text shape; `desk_list_widget_instances` returns the
  fake's `get_state_dict()`'s own `"widgets"` list as JSON;
  `desk_list_todo_items`/`desk_get_next_todo_item` against a real,
  temporary `TODO.md` fixture (mixed `COMPLETED`/`PENDING`/plain
  items) confirm the right item set/next-item resolution, and a clear
  error (not a crash) when no `TODO.md`/no current Desk directory is
  known; every handler returns a clear, non-`is_error` "not ready yet"
  message (not a raised exception) when no GUI thread caller is
  registered at all; `build_desk_mcp_server()` returns a real
  `McpSdkServerConfig` naming all seven tools.
- Full `tests/verify/` regression suite.
