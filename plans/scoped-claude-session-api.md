# Scoped Claude session API for widgets (TODO `0529501`)

## Summary

Today the only widget-facing way to talk to Claude is the full,
unrestricted `desk.claude_session.ClaudeSession` (project-wide `cwd`,
every built-in tool, the in-process Desk MCP server). A widget that
already knows exactly which file(s) it's allowed to touch (the
motivating example: the peer `necro-4x` project's domain-analysis
widget, which has a prompt field meant to be handed to `claude` for
processing its one current file) has no way to get a Claude session
that can *only* reach those specific file(s), short of handing out a
full, unrestricted session.

This plan adds `allowed_paths` as a new optional parameter to the
existing `ClaudeSession.start()` — not a new class, not a new
`desk.` module — so any `kind: "python"` widget that already imports
`desk.claude_session.ClaudeSession` (the same way
`widgets/claude_desk/widget.py` does today) can opt into a
file-scoped session with one extra argument.

## Investigation (done before finalizing this design)

The TODO item itself flagged that `add_dirs`/`sandbox` were unproven
for real per-file scoping. Confirmed directly with two small live
`ClaudeSession`/`claude_agent_sdk` sessions (haiku, real API calls, not
assumed from docs):

1. **`cwd`/`add_dirs` alone are not a hard boundary.** A `ClaudeSession`
   started with `cwd` set to directory A, asked to `Read` an absolute
   path in unrelated directory B (never in `cwd` or `add_dirs`), fired
   a normal `permission_request` for the out-of-scope `Read` — same as
   any other gated action — and the read *succeeded* once allowed.
   Nothing about `cwd`/`add_dirs` refuses the call outright; they only
   affect which calls the CLI's own heuristics treat as "ask" vs
   "auto-allow." This matches `SandboxSettings`' own docstring in the
   installed `claude_agent_sdk` package, which says filesystem
   restriction is "configured via permission rules... not via these
   sandbox settings."
2. **`can_use_tool` alone is not a hard boundary either** — its own
   docstring says it's "not invoked for tool calls already permitted
   by `allowed_tools`, `permission_mode` (e.g. `acceptEdits` /
   `bypassPermissions`)... since those never reach a prompt." A caller
   using `permission_mode="bypassPermissions"` (or any future
   CLI-side auto-allow heuristic) would skip `can_use_tool` entirely,
   silently allowing an out-of-scope file.
3. **A `PreToolUse` hook is a real hard boundary.** A `PreToolUse`
   hook returning `{"hookSpecificOutput": {"hookEventName":
   "PreToolUse", "permissionDecision": "deny", ...}}` for a `Read`
   whose `file_path` resolved outside an allowed directory
   **actually blocked the read** (the model got the literal deny
   reason back as its tool result) even under
   `permission_mode="bypassPermissions"`, where `can_use_tool` is
   never consulted at all. This matches `can_use_tool`'s own docstring
   pointing at hooks for exactly this: "To observe or gate *every*
   tool call regardless of permission rules, use a `PreToolUse` hook."

Conclusion: **the hook is the actual enforcement mechanism; `cwd`/
`add_dirs`/`can_use_tool` are not.** `cwd` still matters for normal
session behavior (CLAUDE.md loading, relative-path resolution) but
carries no security weight for this feature.

## Design decisions

- **Extend `ClaudeSession.start()`, don't add a new class/module.**
  `ClaudeSession` already owns the threading/signal-relay machinery a
  scoped session needs unchanged (`permission_request`, `tool_use`,
  `turn_complete`, etc.); a scoped session is just a more-restricted
  configuration of the same engine, not a different one. Matches
  CLAUDE.md's "avoid adding dependencies, prefer bespoke solutions"
  and this codebase's existing pattern of one shared `desk.` module
  per capability rather than parallel near-duplicates.
- **New parameter: `allowed_paths: list[Path] | None = None`.** Each
  entry is either a file (matched exactly) or a directory (matched by
  prefix, resolved). `None` (the default) means today's unrestricted
  behavior — fully backward compatible, `widgets/claude_desk/widget.py`
  needs no changes.
- **When `allowed_paths` is set:**
  - `tools` is forced to a fixed list: `["Read", "Write", "Edit",
    "NotebookEdit"]`. No `Bash` — a shell command's arguments can't be
    reliably path-checked from a hook (its `tool_input` is just
    `{"command": "..."}`, no structured path field), so the only safe
    answer is to not grant Bash at all for a scoped session, not to
    attempt to sandbox it. No `Glob`/`Grep`/`WebFetch`/`WebSearch`/
    `Task`/`Skill` either — out of scope for the motivating "hand
    Claude this specific file" use case; can be added later behind
    their own path-checking if a real caller needs directory search.
  - The in-process Desk MCP server (`mcp_servers=
    {DESK_MCP_SERVER_NAME: ...}`) is **not** attached — it's a
    broader-than-file-scope capability (live Desk shell control,
    installed jobs) that doesn't fit "only the files this widget has
    access to."
  - A `PreToolUse` hook (`hooks={"PreToolUse": [HookMatcher(matcher=
    None, hooks=[self._check_path_scope])]}`) is installed. It reads
    `tool_input.get("file_path")` or `tool_input.get("notebook_path")`
    (the only two path-bearing fields the 4 allowed tools use),
    resolves it, and denies (`permissionDecision: "deny"`) unless it
    falls under one of `allowed_paths`. **Default-deny**: a call
    carrying neither field is also denied — nothing in the fixed tool
    set should ever lack one, so an unrecognized shape is treated as
    untrusted rather than silently let through.
  - `can_use_tool` is left wired exactly as today — it still handles
    ordinary in-scope approvals (e.g. a `Write` inside the allowed
    set) via the widget's existing `permission_request` signal/UI
    plumbing. The hook and `can_use_tool` are complementary, not
    redundant: the hook is the security boundary, `can_use_tool` is
    the existing user-approval UX for whatever's left inside it.
- **Headless, not a reused `ClaudeDeskWidget` UI.** The motivating use
  case is a widget with its own file picker/prompt field wanting an
  inline "send to Claude" affordance, not spawning a second full
  Claude (Desk) widget (history view, model/permission-mode combo
  boxes, background-tasks panel — all overkill for a one-off scoped
  call). A calling widget uses `ClaudeSession` directly and builds
  whatever minimal inline UI it needs (a button, a busy flag, maybe
  connecting `assistant_text`/`turn_complete`) — the same "bespoke,
  inline, background-thread-plus-signals" shape
  `widgets/git_status/widget.py`/`widgets/voice_input/widget.py`
  already use for their own async work. No new shared "mini Claude
  chat" widget component is built here — no second in-repo caller has
  asked for one yet, and its right shape (synchronous one-shot output
  vs. streaming, etc.) would depend on that caller. This item ships
  the scoping *mechanism*; a first concrete Desk-side consumer widget
  is separate, later work if/when one is needed (the motivating
  example, `necro-4x`'s widget, lives outside this repo).

## Affected files

- `src/desk/claude_session.py` — `start()` gains `allowed_paths`;
  `_connect_and_maybe_prompt` builds `tools`/`hooks`/`mcp_servers`
  conditionally; new `_check_path_scope` async hook callback and a
  small `_path_is_allowed` helper.
- `design-docs/architecture.md` — extend item 30 (Claude (Desk)
  Widget / `ClaudeSession`) with a short paragraph on scoped sessions
  and the investigation's conclusion (hook, not `cwd`, is the
  boundary).
- `tests/verify/` — new live-API coverage (see Verification), plus a
  `disabled_verify_` split so the normal sweep stays API-free, matching
  `disabled_verify_claude_desk_widget_claude_api.py`'s existing
  convention.

## Step-by-step implementation

1. `claude_session.py`: add `_SCOPED_TOOLS = ["Read", "Write", "Edit",
   "NotebookEdit"]` module constant.
2. Add `_path_is_allowed(path_str: str, allowed_paths: list[Path]) ->
   bool`: resolves `path_str`, returns whether it equals any allowed
   file or falls under any allowed directory (resolved on both sides).
3. Add `async def _check_path_scope(self, input_data, tool_use_id,
   context) -> dict`: reads `self._allowed_paths` (stored on the
   instance in `start()`), extracts `file_path`/`notebook_path` from
   `input_data["tool_input"]`, denies (hookSpecificOutput/
   permissionDecision="deny", with a `permissionDecisionReason`
   naming the tool and path) if missing or not `_path_is_allowed`,
   otherwise returns `{}` (no opinion — falls through to normal
   `can_use_tool` handling).
4. `start()`: add `allowed_paths: list[Path] | None = None` parameter,
   store `self._allowed_paths = allowed_paths`, thread it through to
   `_connect_and_maybe_prompt`.
5. `_connect_and_maybe_prompt`: when `allowed_paths is not None`, pass
   `tools=_SCOPED_TOOLS`, `hooks={"PreToolUse": [sdk.HookMatcher(
   matcher=None, hooks=[self._check_path_scope])]}`, and omit
   `mcp_servers` (empty dict) instead of the Desk MCP server; when
   `None` (default), behavior is unchanged from today.
6. `design-docs/architecture.md`: extend item 30 per Design decisions
   above.
7. Verification (step 5 below).

## Key tradeoffs / deliberately out of scope

- **No `Bash`, `Glob`, `Grep`, `WebFetch` for a scoped session.** A
  real caller needing directory search or a shell command inside its
  scope would need this revisited (e.g. sandboxed Bash via
  `SandboxSettings` plus its own, separate path-checking); not
  attempted here since nothing in this repo exercises it yet and
  getting it wrong would be a real security gap, not just a missing
  feature.
- **No new shared widget-facing "scoped chat" UI component** — see
  Design decisions. `current_context.py` gets no new hook either,
  since `ClaudeSession` is already directly importable by any
  `kind: "python"` widget (same as `widgets/claude_desk/widget.py`
  today) — no `DeskWindow`-owned state is involved.
- **Directory-prefix matching in `allowed_paths` uses simple resolved
  -path prefix comparison**, not symlink-aware canonicalization beyond
  what `Path.resolve()` already does. Good enough for the motivating
  use case (widget hands Claude file(s) it opened itself); a
  symlink-escape attack from a file the widget itself chose to expose
  is not this item's threat model.

## Verification

New live-API test (real `ClaudeSession`, matching
`disabled_verify_claude_desk_widget_claude_api.py`'s existing pattern
and reasons for being `disabled_` by default — see TODO `9bc522b`):

- A scoped session (`allowed_paths=[<one temp file>]`) asked to `Read`
  both that file and a second, unrelated temp file by absolute path:
  the in-scope read succeeds, the out-of-scope read is denied (no
  `permission_request` fires for it — the hook denies before it would
  ever reach one), and `tools` offered excludes `Bash`.
- Same, but with `permission_mode="bypassPermissions"` — confirms the
  hook still blocks the out-of-scope read even in the one mode
  `can_use_tool` is never consulted for (this is the case a
  `cwd`/`add_dirs`-only design would have silently failed).
- A scoped session attempting `Write` to a path outside
  `allowed_paths` is denied without ever prompting.
- Full `tests/verify/` regression suite (non-`disabled_` scripts)
  still passes, 0 failures — this change only adds a new opt-in
  parameter, no existing `ClaudeSession.start()` call site changes.
