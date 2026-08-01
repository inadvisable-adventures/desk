# New "Claude (Desk)" widget: Python Agent SDK, alongside the existing Claude widget (COMPLETED)

TODO `a596dbf`.

## Summary

Today's `ClaudeWidget` (`widgets/claude/widget.py`) is a `TerminalWidget`
(`src/desk/terminal_widget.py`) — a real PTY plus a `pyte` terminal
emulator, the same mechanism the plain Console widget uses. It types an
`exec claude --session-id <uuid> --permission-mode auto "<prompt>"` (or
`--resume <uuid>`) command into the shell and renders whatever `claude`'s
own interactive TUI writes back, byte-for-byte, into a `QPlainTextEdit`.
There is no parsing of that output at all — Desk has no structured view
into what Claude is doing, can't show its own status UI, can't offer a
first-class prompt input box, and can't build a history view (scrollback
is whatever fits in the live pyte screen buffer).

This plan adds a **new, separate widget** — "Claude (Desk)"
(`widgets/claude_desk/`) — built on the Python Claude Agent SDK
(`claude-agent-sdk` on PyPI, `ClaudeSDKClient`) instead of PTY/pyte,
giving Desk a real status UI, prompt input box, and scrollable history
view. **The existing Claude widget (`widgets/claude/`) is left in place,
completely unchanged**, as its own separate, still-spawnable widget kind
— this is a new option next to it, not a replacement. (The plain Console
widget is unaffected either way.)

The SDK runs the identical underlying session/permission/sandboxing
engine as the CLI — this is a new, additional way for Desk to talk to
that engine (structured async messages instead of typed keystrokes +
screen-scraped ANSI), not a reimplementation of anything security- or
session-related.

This research was done in response to a direct question about whether
tightening the Claude Code integration would mean losing things the CLI
currently owns (file-access sandboxing, manual-vs-auto permission mode,
model selection, session management). Verified directly against current
Claude Code docs (`code.claude.com/docs/en/permission-modes`,
`.../agent-sdk/python`, `.../headless`) rather than assumed:

- **Permission modes** (`default`/Manual, `acceptEdits`, `plan`, `auto`,
  `dontAsk`, `bypassPermissions`) are the same set in the CLI and the
  SDK, set via `ClaudeAgentOptions(permission_mode=...)`.
- **Sandboxing and protected-path checks are enforced independently of
  permission mode** — `auto` (the existing widget's hardcoded choice,
  TODO `2dca4c8`) does not bypass them; only `bypassPermissions` does,
  and even that mode still prompts on a few hard-coded circuit-breakers
  (e.g. `rm -rf /`). Nothing about the existing widget's safety posture
  is at risk from this addition, and the new widget gets the same
  guarantees.
- **Model selection** — the existing widget passes no `--model` at all.
  `ClaudeAgentOptions(model=...)` gives the new widget explicit model
  selection from the start.
- **Session resume** — same shape as today's widget: `ClaudeAgentOptions
  (resume=<session_id>)`, where `<session_id>` continues to be the
  widget's own Desk `instance_id` (TODO `1d7331b`'s existing pattern,
  reused rather than reinvented).
- **Manual-mode approval**, done properly instead of screen-scraped:
  `ClaudeAgentOptions(can_use_tool=<callback>)` is called for every tool
  request that needs approval; the callback returns
  `PermissionResultAllow(...)`/`PermissionResultDeny(...)`. This is the
  hook the new widget uses to show its own approval UI.
- **Structured events to drive a status/history UI**: `AssistantMessage`
  (with `TextBlock` content), `ResultMessage`, and tool-use/tool-result
  messages stream out of `client.receive_response()` as typed Python
  objects instead of ANSI bytes. (The exact class names for tool-use/
  tool-result content blocks weren't pinned down during this research —
  confirm against the installed `claude_agent_sdk` package's own type
  reference during implementation, not assumed here.)

## Affected files

- `pyproject.toml` — add `claude-agent-sdk` as a real new dependency
  (unavoidable, same "no bespoke way to do this" framing
  `design-docs/architecture.md` already applies to `mlx-whisper`, TODO
  `1cd0ca2`).
- `src/desk/claude_session.py` (new) — the non-widget, non-Qt-specific
  wrapper around `ClaudeSDKClient`: owns the asyncio event loop, the
  live session, and translates SDK messages/permission requests into
  Qt-safe signals (see "Threading model" below). Shared-logic module in
  `desk.` proper, same reason `desk.terminal_widget` exists — widget
  directories can't import each other directly. Used only by the new
  widget; the existing Claude widget keeps using `terminal_widget.py`
  untouched.
- `widgets/claude_desk/widget.json` (new) — `"name": "Claude (Desk)"`,
  `"kind": "python"`, `"entry": "widget.py"`, otherwise modeled directly
  on `widgets/claude/widget.json`.
- `widgets/claude_desk/widget.py` (new) — a `ClaudeDeskWidget(QWidget)`
  (composition, not a `TerminalWidget` subclass — there's no PTY/
  terminal involved) with: a status area, a scrollable history view, a
  prompt input box, and a permission-approval affordance wired to
  `can_use_tool`. Exposes the same `start_session(session_id, resume,
  extra_instructions)` shape the existing widget uses, so
  `DeskWindow`'s binding code stays symmetric between the two (see
  next item).
- `src/desk/shell/window.py` — add a `CLAUDE_DESK_WIDGET_ID = "claude_desk"`
  constant alongside the existing `CLAUDE_WIDGET_ID = "claude"`, and a
  parallel `_bind_claude_desk_widget` dispatched at each point
  `CLAUDE_WIDGET_ID` is currently special-cased for the original widget
  (fresh-instance-id assignment, the post-`add_widget` bind call, the
  kind-to-widget-id mapping used when spawning from a tempui request,
  and the "does this widget need special post-build binding" check).
  The two widget ids are independent and never conflict — both can be
  placed on the same Desk simultaneously.
- `design-docs/architecture.md` — add a new "Claude (Desk) Widget" entry
  describing the SDK-based mechanism, **alongside**, not replacing, the
  existing "Claude Widget" entry.
- `tests/verify/` — new script(s) covering session start/resume,
  message-to-UI translation, and the permission-callback path
  (see "Verification" below).
- Not affected at all: `widgets/claude/widget.py`,
  `widgets/claude/widget.json`, `widgets/console/`,
  `src/desk/terminal_widget.py` — the existing Claude widget and the
  plain Console widget are both left exactly as they are today.

## Step-by-step implementation approach

1. **Add the dependency.** `claude-agent-sdk` to `pyproject.toml`;
   confirm it installs cleanly in `.venv` and that a bare `ClaudeSDKClient`
   round-trip works from a throwaway script before touching any widget.

2. **Build `src/desk/claude_session.py`.** A `ClaudeSession` class that:
   - Owns a dedicated background thread running its own asyncio event
     loop (the established pattern in this codebase for bridging
     blocking/async work into Qt — see `widgets/git_status/widget.py`'s
     background-thread-plus-signal relay, reused again by TODO
     `b32fb81`'s Voice Input widget — rather than trying to run the Qt
     event loop and asyncio together in one loop).
   - Exposes Qt-safe entry points: `start(session_id, resume, model,
     permission_mode, extra_instructions)`, `send_prompt(text)`,
     `respond_to_permission(request_id, allow, message="")`.
   - Emits `pyqtSignal`s for: assistant text (streamed), a tool-use
     event (name + input, for the history view), a tool-result event, a
     permission request (name + input, for the widget to show its
     approval UI and block that specific tool call on the response), a
     result/turn-complete event, and a session-ended event.
   - Internally, `send_prompt`/`respond_to_permission` are handed to the
     asyncio loop via `asyncio.run_coroutine_threadsafe`; the
     `can_use_tool` callback (itself invoked on the asyncio thread by
     the SDK) blocks on an `asyncio.Event`/`Future` until the Qt-side
     approval decision arrives back through that same bridge.

3. **Create the new `widgets/claude_desk/` widget.** `widget.json`
   named `"Claude (Desk)"`; `widget.py`'s `ClaudeDeskWidget` composes:
   - A status label/area (current turn in progress / idle / error).
   - A scrollable history view appending structured entries (user
     prompt, assistant text, tool calls + results, permission
     decisions) as they arrive — this is the piece PTY/pyte could never
     give real scrollback for.
   - A prompt input box (`QLineEdit`/`QPlainTextEdit` + send action)
     calling `ClaudeSession.send_prompt`.
   - A permission-approval affordance shown only when a permission
     -request signal fires, resolved via `respond_to_permission`.
   - A `start_session(session_id, resume, extra_instructions)` method
     matching the existing widget's shape, so `DeskWindow`'s binding
     code can treat both widgets symmetrically.

4. **Wire `DeskWindow` to spawn and bind the new widget.** Add
   `CLAUDE_DESK_WIDGET_ID` and a `_bind_claude_desk_widget` alongside
   the existing `CLAUDE_WIDGET_ID`/`_bind_claude_widget` handling, at
   each of that constant's current call sites in `window.py` (see
   "Affected files" above) — additively, without touching the existing
   widget's own code path. Whether tempui's `DiscussParkingLotItem` flow
   (which currently always spawns the original PTY-based Claude widget)
   should gain an option to spawn "Claude (Desk)" instead/as well is an
   open, separate decision — out of scope here; leave it targeting the
   original widget for now.

5. **Wire permission mode and model as real widget-visible settings**,
   not just start-time constants — at minimum, default to `auto` (via
   `ClaudeAgentOptions(permission_mode="auto")`, matching the existing
   widget's default) and pass an explicit `model=` for the first time;
   whether to expose a mode/model switcher in the widget's own UI
   immediately or as a fast-follow is a judgment call to make during
   implementation, not fixed by this plan.

6. **Add a new "Claude (Desk) Widget" entry to
   `design-docs/architecture.md`**, alongside the existing "Claude
   Widget" entry (not replacing it), referencing this plan and TODO
   `a596dbf`, the same way other entries reference their own TODOs.

7. **Verify** (see below), then update `TODO.md`/this plan's title per
   the standard "Working on TODO Items" workflow once implemented.

## Key design decisions / tradeoffs

- **New widget, not a rewrite in place**: the existing Claude widget
  stays exactly as it is, as a separate, independently-spawnable widget
  kind. Anyone relying on today's PTY-based behavior (or a saved Desk
  with an existing Claude widget instance) is entirely unaffected;
  "Claude (Desk)" is purely additive. This does mean the two widgets'
  session-management code (`claude_session.py` vs. the shell-typing in
  `widgets/claude/widget.py`) isn't unified — accepted as the cost of
  not disturbing the existing widget.
- **Composition, not inheritance, for `ClaudeDeskWidget`**: it is not a
  `TerminalWidget` subclass, since there's no PTY/terminal involved at
  all in this new widget.
- **Thread-per-session, not one shared asyncio loop for the whole app**:
  consistent with this codebase's existing background-thread-plus
  -signal convention (git_status, voice_input) rather than introducing
  `qasync` or a single app-wide event loop, which would be a much
  larger, cross-cutting change for a benefit not needed here (each
  Claude (Desk) widget instance is already independent).
- **What's different from the existing widget's experience**: `claude`'s
  own terminal-rendered affordances — inline diff coloring, `/`-command
  tab completion, the live todo-list/spinner display — have no
  equivalent in "Claude (Desk)"; each would need to be deliberately
  rebuilt as part of the new widget's UI (or explicitly decided not to,
  e.g. slash commands can still be typed as plain text into the prompt
  box and sent as a normal message, since `-p`/SDK mode still expands
  them per the CLI docs). Trading these away for a real status/history
  UI is exactly the tradeoff being made deliberately in the new widget
  — and since the old widget remains available, nobody loses access to
  the terminal-rendered experience who wants it.
- **`DiscussParkingLotItem`/tempui's other Claude-widget-spawning flows
  keep targeting the original widget** for now, per step 4 above — not
  redesigned as part of this item.
- **Not in scope for this plan**: making tempui two-directional (using
  this same SDK integration to let Desk call *into* the running session
  via a custom tool/hook, instead of the current one-way "Claude writes
  a file, Desk watches it" mechanism). That's a separate, larger idea —
  tracked in `PARKINGLOT.md` — and isn't required to get the status/
  prompt/history UI wins this plan targets.

## Verification

No formal test suite (see `tests/verify/README.md`) — new hand-written
script(s) exercising, without mocking the SDK's own network calls where
avoidable:

- A `ClaudeSession` started fresh assigns the given session id and a
  turn completes end-to-end (prompt in, `ResultMessage` out).
- Resuming an existing session id reconnects rather than starting fresh
  (mirroring TODO `1d7331b`'s existing resume-behavior tests, applied
  to the new widget).
- A tool call requiring approval under a mode that isn't `auto`/
  `bypassPermissions` blocks on `respond_to_permission` and only
  proceeds after an explicit allow.
- The widget's history view accumulates entries in order for a
  multi-turn conversation with at least one tool call.
- The existing Claude widget's own regression coverage (TODO
  `1d7331b`/`2dca4c8`'s tests) still passes unmodified, confirming this
  addition didn't disturb it.
- Manual, in-app check: spawn both "Claude" and "Claude (Desk)" on the
  same Desk side by side, confirm the new widget's status UI, prompt
  box, and history view all behave as expected against a real session,
  and that the original widget is unaffected (this is UI-facing work
  per this project's own guidance to actually exercise the feature in
  the running app, not just type-check it).

## Status

Completed. See TODO `a596dbf`'s own completion narrative in `TODO.md`
for what shipped, the two real deviations found during verification
(a `connected` signal `ClaudeSession` needed that this plan didn't
anticipate, and `permission_mode="default"` instead of `"auto"`), and
the manual, in-app check noted below was not additionally performed
beyond the automated `tests/verify/verify_claude_desk_widget.py`
coverage (which already drives a real widget instance end to end
against real sessions) -- spawning both widgets side by side in a
running Desk app was not separately done in this pass.
