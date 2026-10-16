# `desk_git_commit` MCP tool (TODO c33657f)

Follows from TODO `8e8db18`'s root-cause finding
(`plans/heredoc-apostrophe-root-cause.md`): `git commit -m "$(cat <<EOF ...
EOF)"` can fail on an odd apostrophe count in the message body, because the
message has to pass through a shell string at all. A new, narrowly-scoped
MCP tool that takes the commit message as a structured parameter sidesteps
shell quoting entirely -- not just this one trigger, but every shell
-quoting hazard a commit message could ever hit (backticks, `$`, unusual
unicode, embedded quotes of any kind). Discussed with the user 2026-10-15;
see that conversation for the full reasoning, including why this is scoped
to commit-message-writing specifically and not "a git MCP" generally (status/
diff/log/add already work fine through Bash -- they don't smuggle freeform
multi-line text through shell quoting, so there's no analogous structural
win).

**Implementation note, per the user's explicit request**: this needs to be
implemented by a different agent than the one running this project's own
live `claude_desk` widget session, since the change touches
`src/desk/shell/desk_mcp_server.py` and `desk.claude_session.ClaudeSession`
-- the exact in-process MCP server and session machinery backing *this*
agent's own live tool connections. Desk doesn't yet have a safe way for an
agent to modify and have reloaded the server it's currently talking
through without risking its own session. Implement and verify this on a
separate checkout/worktree or via a different agent entirely, not inline in
a live Claude (Desk) session that's currently relying on
`desk_mcp_server.py` as-is.

## Summary

A new tool, `desk_git_commit`, registered in `src/desk/shell/desk_mcp_server.py`
alongside the existing `desk_save`/`desk_list_todo_items`/etc. tools (same
`@tool(...)` + `_TOOLS` list pattern -- see that file's own existing entries
for the shape to match). Takes the commit message (and, for convenience,
which files to stage) as structured MCP parameters, and runs `git commit`
via `subprocess.run([...], cwd=..., shell=False)` -- an argv list, never a
shell string -- so the message text never passes through any shell
quoting/parsing at all.

## Interface

```
desk_git_commit(message: str, files: list[str] | None = None) -> result
```

- `message` -- the commit message, verbatim, any content (newlines,
  apostrophes, backticks, `$(...)`, anything) -- no quoting/escaping needed
  by the caller at all, which is the entire point.
- `files` -- optional. If given, each path (resolved relative to the
  current project directory, like every other Bridge API file-path
  convention -- see `.desk_temp/tempui-custom-widgets.md`'s `desk.fs.*`
  entry for the precedent) is `git add`-ed before committing. **Deliberately
  no blanket-add option** (no `"."`/`-A` equivalent) -- matches this
  project's own `CLAUDE.md`-adjacent git safety convention (prefer adding
  specific files by name; broad adds risk sweeping in something like a
  `.env`). If omitted, commits whatever is already staged, same as a bare
  `git commit`.
- Returns the resulting short commit hash and `git commit`'s own stdout on
  success; on failure (nothing staged, a pre-commit hook failing, not a git
  repo at all, a given `files` path escaping the project directory, etc.),
  returns the real stderr/stdout as an error result (`is_error: true`,
  matching every other tool in this file) rather than swallowing it -- the
  calling agent needs to see exactly what happened to react correctly (fix
  a hook issue and retry, etc.), the same visibility a failed Bash command
  already gives.

## Explicitly out of scope for v1

- `git add -A`/`.`, `--amend`, `--no-verify`, force-anything -- this tool
  should enforce the exact same git safety rules already written into this
  project's own git-usage conventions (prefer new commits over amends,
  never skip hooks, never broad-add), not just happen to follow them by
  omission. If a future need for one of these shows up, add it as an
  explicit, separately-considered parameter, not a default.
- Staging via patterns/globs -- `files` is a plain list of exact paths.
- A parallel `desk_gh_pr_create`-style tool for PR body text, which has the
  identical structural hazard (`gh pr create --body "$(cat <<'EOF' ...
  EOF)"`) -- noted as a natural, low-risk follow-up once this one is proven,
  not required here.
- Anything resembling "a git MCP" beyond commit-message writing (status,
  diff, log, branch, push, ...) -- out of scope per the discussion this plan
  follows from.

## Design questions for the implementer to resolve, not pre-decided here

- **Does this fit `desk_mcp_server.py`'s existing stated scope?** That
  file's own top comment frames every existing tool as "deliberately
  read-only or side-effect-bounded to actions a user could already trigger
  by hand via existing UI... nothing here lets an agent do something it
  couldn't already do by clicking around." A git commit doesn't mirror any
  existing Desk GUI button. The counter-argument (worth confirming, not
  assuming): this tool grants no new *capability* at all -- the agent can
  already run `git commit` via the Bash tool today, gated by the exact same
  `can_use_tool` approval hook this file's own comment says every tool here
  already goes through (confirmed directly against a real SDK session,
  per that comment) -- this tool only changes *how* the message text
  travels (a structured parameter vs. a shell string), not *what* is
  possible or *what* gets approved. Decide whether that distinction is
  enough to fit this file's existing rationale, or whether a git-commit
  tool belongs in its own, separately-scoped registration instead (still
  the same `create_sdk_mcp_server`/`@tool` pattern) so this file's own
  documented scope statement stays accurate rather than quietly stretched.
- **Where should agent-facing guidance to actually prefer this tool live?**
  The real payoff only materializes if agents reach for it instead of a
  Bash heredoc -- and the Bash tool's own embedded instructions (outside
  this repo's control) are currently quite prescriptive about the
  heredoc-based commit workflow, so a new tool with no pointer to it risks
  going unused out of habit (see the 2026-10-15 discussion this plan
  follows from). `widgets/claude_desk/widget.py`'s `CLAUDE_WIDGET_PROMPT`
  (around line 54) already does exactly this kind of steering for a small,
  curated set of tools ("desk_reveal_widget, ... prefer them over dropping
  a DeskProc file when one of them already covers what you need") --
  appending a similar one-sentence nudge there ("prefer desk_git_commit
  over a Bash heredoc for commit messages") is the most direct precedent
  to follow. But that blurb is explicitly framed as "interacting with
  Desk's own live shell," which a git-commit tool arguably isn't -- decide
  whether it belongs there anyway, in its own short addition elsewhere in
  the same prompt, or (per `development-process.md`'s "Give agent-visible
  features a real doc, not a one-line mention") a dedicated short
  `tempui-*.md` doc if there's enough to say beyond one sentence. Either
  way, don't skip this step -- a tool nobody is told to prefer won't get
  preferred.
- **Changelog tag, mandatory, not optional**: per
  `development-process.md`'s "Keep the tempui changelog docs current" --
  this is a new agent-visible `mcp__desk__` tool, so it needs a freshly
  minted tag (`desk.temp_ui.generate_tag`), added to `CURRENT_TAGS`, and a
  matching `_NEW_FEATURES` entry in `src/desk/temp_ui.py`, in the same
  commit as the rest of this change -- the same standing requirement every
  other agent-visible Desk change already follows (see e.g. the recent
  `named widget logs + log query MCP tools #211800` tag for the shape of a
  comparable entry).

## Verification

A `tests/verify/` script, headless, no real Claude session or GUI thread
needed (the handler function can be called directly against a disposable
real git repo, the same "real object, no mock" style `tests/verify/`
already generally prefers):

1. Create a throwaway git repo in a temp directory (`git init`, one initial
   commit so there's a real history to extend).
2. Call the `desk_git_commit` handler directly with a message containing
   every character that has caused (or could plausibly cause) a shell
   -quoting problem elsewhere in this project's own history: an odd number
   of apostrophes (the exact TODO `8e8db18` trigger), backticks, a literal
   `$(...)`  sequence, embedded double quotes, and multiple lines.
3. Confirm the resulting commit's real message (`git log -1 --format=%B`)
   matches the input byte-for-byte, and that this exact message would have
   broken the old heredoc approach if constructed the old way (i.e. the
   test should itself demonstrate the bug this tool fixes, not just assert
   success in isolation).
4. Confirm `files` stages exactly the given paths (nothing more), and that
   omitting `files` commits only what was already staged beforehand.
5. Confirm a `files` path that resolves outside the project directory is
   rejected with a clear error, not silently followed.
6. Confirm a clear, real error (not a crash) when: nothing is staged and no
   `files` given; the target directory isn't a git repository at all.

## Status: COMPLETED (2026-10-15)

Decisions on the open design questions:

- **Scope**: kept in `desk_mcp_server.py` rather than a separate registration;
  the module docstring's scope statement now names `desk_git_commit` as the one
  exception (no new capability vs. Bash, same approval hook, only the message's
  transport differs).
- **Guidance**: one sentence appended to `CLAUDE_WIDGET_PROMPT`, plus the
  changelog entry. No dedicated `tempui-*.md` doc: a single tool whose full
  contract fits in its description and the entry.
- **Changelog tag**: `desk_git_commit MCP tool for commit messages #570472`.
- **Transport**: `git commit -F -` with the message on stdin (not `-m`), so even
  argv handling never sees it. A message that is empty/whitespace is refused.
- **Path check**: `files` entries resolve (following symlinks) and must stay
  inside the current Desk directory; absolute paths inside it are allowed.
- **Verification note**: the original heredoc failure lives in the tool layer
  around the shell, not in bash, so `verify_desk_git_commit.py` demonstrates the
  general shell-string hazard (a naive `bash -c "git commit -m '...'"` of the
  same message fails) rather than that exact trigger.
