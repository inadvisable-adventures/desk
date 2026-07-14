# COMPLETED: Fix: discuss-claude launch still breaks -- move instructions to a file instead of the command line

TODO `51be2bc`.

## Summary

Reported, after TODO `fc17b55` had already fixed the embedded-newline
bug: starting a new Parking Lot "Discuss" session still got stuck --
the shell just sat there. Typing a single `'` and pressing Enter was
enough to unstick it and launch `claude` normally.

## Root cause

Typing one stray `'` followed by Enter is exactly what it takes to
close an unterminated single-quoted shell string and submit the line
-- the same "stuck at an open quote" symptom TODO `fc17b55` fixed for
a different cause (an embedded literal `\n`). This time, the open
quote isn't caused by a raw newline; it is a side effect of
`shlex.quote` on a string containing literal `'` characters, combined
with the whole thing being typed into an interactive PTY in one shot.

`_place_discuss_claude_widget`'s `instructions` string contains two
apostrophes ("Let's discuss", "don't immediately"), and the shared
`CLAUDE_WIDGET_PROMPT` (`widgets/claude/widget.py`) contains a third
("if you're about to run a lightning round"). `shlex.quote` handles an
embedded `'` by closing the open quote, splicing in an escaped quote
via a double-quoted segment, and reopening the quote (`it'"'"'s`) --
correct POSIX syntax once the whole line is submitted, but it makes an
already-long, hand-written-prose command line even longer and more
quote-heavy. `ClaudeWidget.start_session` writes the entire assembled
command in one `os.write` to the PTY's master fd
(`TerminalWidget.type_into_shell`), the same way TODO `fc17b55`'s own
investigation already flagged as a real, unproven risk: an
interactive shell's terminal line discipline is normally in canonical
("cooked") mode while idle at its prompt, and canonical mode has a
fixed-size kernel input queue (`MAX_CANON`) -- a line longer than that
limit can have its excess bytes silently dropped rather than delivered
to `readline` at all, which can easily leave a `'"'"'`-heavy quoted
string missing its final closing quote. That reproduces exactly the
reported symptom: the shell sits open (stuck at bash's `PS2`
continuation prompt, easy to miss/misread as "just sitting there"),
and one manually-typed `'` plus Enter is exactly what is needed to
close the truncated quote and submit the line.

This was flagged, but left unproven, in TODO `fc17b55`'s own
Learnings entry update -- this is the confirmation.

## Design

Per direct instruction: stop splicing free-form, hand-written prose
into the launch command line at all. Instead:

1. `_place_discuss_claude_widget` writes the actual "what to discuss
   and how" text to a standalone file under the current Desk's
   `.desk_temp` directory (`desk.temp_ui.TEMP_UI_DIRNAME`), named
   `discuss-instructions-<random-hex-token>.md` -- deliberately *not*
   a bare UUID, so the temp-ui file watcher (which treats any
   bare-UUID-named file in this directory as a new temp-ui widget --
   see `is_temp_ui_filename`) never mistakes it for one.
2. `claude_extra_instructions` becomes a short, fixed-shape
   instruction pointing at that file (its path is not free-form
   content -- a filesystem path built entirely from this project's
   own directory plus a `uuid4().hex` token has no reason to contain
   a quote character), phrased with no apostrophe at all: "Read the
   file at `<path>` now and follow its instructions for what to
   discuss and how." -- this keeps the command line itself short and
   quote-free regardless of how long or apostrophe-heavy the actual
   discussion content is.
3. `CLAUDE_WIDGET_PROMPT` (`widgets/claude/widget.py`) itself had the
   remaining apostrophe on every claude launch's command line, not
   just the discuss path ("if you're about to run a lightning
   round"). Reworded to "if you are about to run a lightning round"
   so the base prompt shared by every fresh launch is apostrophe-free
   too, not just today's one call site.

`start_session`'s existing embedded-`\n` normalization (TODO
`fc17b55`) is left in place unchanged -- still a correct, independent
defensive guard.

### 4. Defense in depth: `TerminalWidget.type_into_shell` retries short writes

Investigating the exact truncation mechanism (see Verification below)
surfaced a second, independent gap in the same delivery path:
`type_into_shell`'s single `os.write(self._master_fd, ...)` call is
made against a non-blocking fd (`os.set_blocking(self._master_fd,
False)` in `__init__`) but never checks how many bytes it actually
wrote -- a non-blocking `os.write` to a PTY master is free to accept
fewer bytes than requested, and the unwritten remainder was
previously dropped silently, forever. Fixed with a bounded retry loop
(`select.select` on writability, retrying `os.write` on a short
write or `BlockingIOError`, giving up after
`_TYPE_INTO_SHELL_TIMEOUT_S` and logging a warning). This can't
rescue a line that's fundamentally longer than the kernel's own
canonical-mode line buffer (see Verification) -- that's what the
file-based redesign above actually fixes -- but it does close a real,
separate short-write gap for any write, of any size, that the kernel
was otherwise willing to accept in full across multiple calls.

## Affected files

- `src/desk/shell/window.py` (`_place_discuss_claude_widget`, new
  `_write_discuss_instructions_file` helper)
- `widgets/claude/widget.py` (`CLAUDE_WIDGET_PROMPT` wording only)
- `src/desk/terminal_widget.py` (`TerminalWidget.type_into_shell`
  short-write retry loop -- design point 4 above)

## Verification

Headless (`QT_QPA_PLATFORM=offscreen` not needed for the pure
string/file-system checks; needed for the two `TerminalWidget`
checks):

- `_place_discuss_claude_widget`'s built `claude_extra_instructions`
  contains no `'` character at all, for both the `parking_lot_line`
  and `item_text` paths, and correctly references a real file written
  under a temp directory's `.desk_temp` with the expected content
  (byte-for-byte).
- The written file's name is confirmed *not* a valid UUID
  (`is_temp_ui_filename` returns `False` for it), so the temp-ui
  watcher would never mistake it for a temp-ui widget file.
- `CLAUDE_WIDGET_PROMPT.format(doc_path=...)` contains no `'`
  character, and neither does the full, realistic assembled prompt
  (`CLAUDE_WIDGET_PROMPT` + `_development_process_instruction()` +
  the new file-referencing `extra_instructions`) built via the real
  `widgets/claude/widget.py` helpers -- confirming `shlex.quote` never
  needs to fall back to its apostrophe-escaping/splicing form
  (`it'"'"'s`) for this command.
- Directly isolated the actual kernel mechanism with a real, live PTY
  (`pty.openpty()` + `subprocess.Popen(["bash", ...])`, non-blocking
  master fd): confirmed this environment's `PC_MAX_CANON` is exactly
  1024 bytes, and that a single unterminated line longer than that is
  truncated at exactly the 1024-byte boundary -- critically, *including
  the line's own terminating newline* if it falls past the boundary,
  which leaves a blocked `read`/`readline` call with no way to ever see
  a complete line (matching the reported "the shell just sits there"
  symptom -- not just a PS2 continuation-prompt guess). This directly
  confirms the root cause: it is not about *which* characters get
  dropped (quotes vs. anything else), it's that *anything* pushing an
  unterminated line past 1024 bytes risks losing the newline that would
  ever submit it.
  - The real, realistic command this fix produces (measured via the
    actual `widgets/claude/widget.py` prompt-assembly + `shlex.quote`
    code, not a stand-in) is 711 bytes regardless of how long the
    referenced-file's actual discussion content is -- comfortably under
    the confirmed 1024-byte boundary, which is the actual point of the
    file-based redesign (the command's length no longer depends on
    content length at all).
  - A **live, single-shot repro of the exact "stuck" failure mode**
    against the old, pre-fix, apostrophe-heavy inline-instructions
    command (padded out with a long filler, sent via one raw
    `os.write`, mirroring the pre-fix `type_into_shell` and TODO
    `fc17b55`'s own verification style) was attempted but did not
    reproduce cleanly/consistently in this session's sandboxed
    environment -- likely because the exact truncation boundary
    interacts with `os.write`'s own short-write behavior on this fd
    (see design point 4), making the precise byte offset where
    corruption lands sensitive to both. This is a weaker result than a
    clean before/after repro, but the *mechanism* (MAX_CANON truncation
    eating a line's terminating newline) is independently and directly
    confirmed above via a dedicated, isolated test (a plain `read line`
    with no quoting/printf involved), which is what the fix actually
    targets.
- `TerminalWidget.type_into_shell`'s new retry loop: with `os.write`
  monkeypatched to simulate genuine short writes (returning only 37 of
  the requested bytes for the first 5 calls against a real
  `TerminalWidget`'s real PTY master fd, mirroring the short-write
  behavior confirmed directly during this investigation), a 500-byte
  payload (kept under the 1024-byte `MAX_CANON` boundary, to isolate
  this from the separate kernel-level truncation above) is still
  delivered to the shell in full and echoed back correctly -- confirming
  the retry loop actually recovers from a short write rather than
  silently dropping the remainder the old single-call code would have.

## Status

Implemented as designed above. Verification re-run and confirmed
(including the additional `type_into_shell` short-write fix surfaced
during investigation -- see design point 4 and Affected files).
COMPLETED.
