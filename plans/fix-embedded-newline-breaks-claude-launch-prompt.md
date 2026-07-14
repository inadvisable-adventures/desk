# Fix (COMPLETED): a literal embedded newline in a claude launch prompt breaks readline mid-command

TODO `fc17b55`.

## Summary

Reported: clicking a Parking Lot widget's "Discuss" button (TODO
`a48e968`) launched a new claude widget, but the shell was left stuck
showing bash's `>` continuation prompt partway through the command,
with the rest of the intended one-line `exec claude ...` command
visibly split across several `>`-prefixed lines -- `claude` never
actually started.

## Root cause

`DeskWindow._place_discuss_claude_widget` (introduced by TODO
`c0875bc`, extended by TODO `624ff3a`) builds its `instructions` string
like this:

```python
instructions = (
    f"\n\nLet's discuss {what}. Have this discussion here, in this "
    ...
)
```

Note the leading `f"\n\n..."` -- two literal newline *characters*
embedded in the middle of the string, not just paragraph-break
markdown. This string becomes part of `extra_instructions`, which
`ClaudeWidget.start_session` (`widgets/claude/widget.py`) splices into
`prompt`, wraps whole in `shlex.quote(prompt)`, and writes via
`TerminalWidget.type_into_shell` -- one `os.write()` of the entire
`exec claude --session-id ... '<prompt>'\n` command string straight to
the PTY's master fd.

`shlex.quote` only guarantees the *shell parser* will see one correctly
-quoted argument once the whole line has been received and submitted.
It says nothing about what happens *while* that string is being fed
into an interactive terminal one byte at a time. `bash` here is
running interactively under `readline` (stdin is a real PTY, no script
file given) -- and to `readline`, every raw `\n` byte arriving on its
input is "the user pressed Enter," full stop, regardless of whether
the line typed so far is inside an still-open, unterminated
single-quoted string. The moment those two embedded `\n` bytes arrive
(partway through the still-open `'<prompt>...`), `readline` submits
what it has so far -- an unterminated quote -- and bash falls back to
its `PS2` (`> `) continuation-prompt mode, exactly matching the
reported symptom. (The command likely *would* eventually reassemble
correctly once the final closing `'` arrives, the same way a human
typing a multi-line quoted string at an interactive prompt would --
but it reads as broken, and is fragile in a way that's easy to break
further, e.g. by a `!`-history-expansion match landing right at one of
these accidental line breaks.)

This fully supersedes the "maybe `histexpand`, maybe a PTY canonical
-mode race" speculation from TODO `624ff3a`'s own investigation, which
never actually drove a real, live, interactive PTY end to end (its own
plan's Verification section says as much: "Real `claude` binary launch
itself can't be exercised in this environment ... this stops at
confirming the exact command string built"). That gap is exactly why
this bug went uncaught until now -- this is the first time this flow
has actually been exercised against a real live PTY + bash + readline
since TODO `624ff3a` landed.

`_place_discuss_claude_widget` is the *only* producer of
`claude_extra_instructions` anywhere in the codebase (confirmed via
`grep -rn "extra_instructions="`), so this one string is the entire
affected surface -- this isn't a per-call-site bug spread across
multiple places.

## Design

### 1. Remove the embedded newlines at the source

Change `instructions`'s leading `f"\n\n..."` to a plain leading space,
matching the exact convention `_development_process_instruction()`
(`widgets/claude/widget.py`) already uses to glue an additional
sentence onto the end of a prompt that has no explicit paragraph
-break: `f" Let's discuss {what}. ..."`.

### 2. A defensive normalization at the actual boundary

The real invariant this bug violates -- "no literal `\n` may reach
`ClaudeWidget.start_session`'s `prompt` before it's typed into an
interactive PTY, no matter how it was built" -- belongs to
`start_session` itself, not to whichever caller happens to build
`extra_instructions` today. `_place_discuss_claude_widget` is the only
producer right now, but `extra_instructions` crosses a real module
boundary (arbitrary future widget/window code could pass anything).
Add a one-line normalization in `start_session`, right where `prompt`
is assembled, replacing any stray `\n` with a space before
`shlex.quote` -- cheap, and it turns this exact bug class into a
silently-corrected minor formatting wrinkle instead of a broken launch,
for every current and future caller at once.

## Affected files

- `src/desk/shell/window.py` (`_place_discuss_claude_widget`)
- `widgets/claude/widget.py` (`ClaudeWidget.start_session`)

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`):

- `_place_discuss_claude_widget`'s built `instructions`/prompt no
  longer contains `"\n"` for both the `parking_lot_line` and
  `item_text` paths (regression check: still contains the expected
  content).
- A **real, live PTY** test (not just inspecting the built string):
  spawns actual `bash` under `pty.openpty()` + `subprocess.Popen`
  (mirroring `TerminalWidget.__init__` exactly), writes a
  `printf`-based stand-in command (same `exec ... {shlex.quote(...)}\n`
  shape `ClaudeWidget.start_session` builds, swapping `printf '%s'` for
  `claude` so it doesn't require a real `claude` binary) via one
  `os.write` exactly like `type_into_shell`, then reads back the PTY's
  output:
  - With the **old, buggy** instructions text (leading `"\n\n"`,
    `start_session`'s normalization bypassed to isolate the source
    bug): confirms bash's echoed output shows the `> ` continuation
    prompt appearing mid-command -- reproducing the reported bug
    exactly.
  - With the **fixed** instructions text and the new normalization:
    confirms `printf` receives and echoes back exactly the intended
    single-line argument, with no `> ` continuation prompt anywhere in
    the output.

## Status

Implemented as designed above. Verification re-run and confirmed: the
real, live PTY test above was executed (old buggy instructions
reproduce the stuck `CONT>` continuation prompt with normalization
bypassed; fixed instructions + `start_session`'s normalization produce
a single clean line, no continuation prompt). COMPLETED.
