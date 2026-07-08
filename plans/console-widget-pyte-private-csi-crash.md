# Fix console widget crash on private CSI / device-status-report queries (COMPLETED)

## Summary

Confirmed via a real-app crash log: running `claude` in the Console widget
crashed the *entire* Desk process (`Abort trap: 6`), not just the widget:

```
TypeError: Screen.report_device_status() got an unexpected keyword argument 'private'
```

Root cause: `pyte`'s `Stream` dispatches DEC-private CSI sequences (`ESC[?...`)
by calling the matching `Screen` method with an extra `private=True` keyword
argument (`streams.py`: `csi_dispatch[char](*params, private=True)`). This is
confirmed to be a real, current gap in `pyte` 0.8.2 (the latest release on
PyPI — there is no newer version to upgrade to): of the ~22 methods CSI
sequences can dispatch to, only `erase_in_line` declares a `private`
parameter, and only `erase_in_display`, `report_device_attributes`,
`set_mode`, and `reset_mode` accept `**kwargs` to silently absorb it. The
other ~16 — including `report_device_status`, `cursor_position`,
`cursor_to_column`, and `set_margins` — accept neither, so *any* program that
happens to send one of those as a DEC-private variant crashes the process.
`claude`'s underlying TUI stack evidently does this (almost certainly a
cursor-position or terminal-status query, given the specific method that
crashed).

Separately: `pyte.Screen.write_process_input()` — which `report_device_status`
calls to reply to cursor-position (`ESC[6n`) and terminal-status (`ESC[5n`)
queries — is a no-op by default (see its docstring: "By default is a noop").
So even once the crash is fixed, such queries would silently get no reply at
all, which can cause programs that block waiting for one to hang or
misbehave. This needs fixing too, since it directly affects `claude`'s own
terminal-capability detection.

## Affected files

- `widgets/console/widget.py` (edit): add a `Screen` subclass wiring
  `write_process_input` back to the real PTY, and guard `_stream.feed()`
  against dispatch errors from unsupported private-CSI sequences.
- `LEARNINGS.md` (edit): record the `pyte` private-CSI dispatch gap.

## Design

### Guard against dispatch crashes (the crash fix)

Originally planned as a single `try/except` wrapped around the whole
`self._stream.feed(...)` call. Testing that approach surfaced a worse problem:
`pyte.Stream.feed()` has no internal per-character recovery, so an exception
partway through a chunk aborts its entire `while` loop — everything *after*
the offending sequence in that same PTY read (e.g. a command's real output,
if it happened to arrive in the same read as the bad escape sequence) never
gets processed at all. A `try/except` around the whole call "fixes" the crash
but silently eats real output right after it — confirmed directly: feeding
`"before "` + a crashing private DSR + `"after"` in one chunk left `"after"`
missing from the rendered document even though no exception escaped.

Fixed instead with `_ResilientStream(pyte.Stream)`, overriding `feed()` with
an exact copy of the upstream implementation but wrapping only the
per-character dispatch call (`self._send_to_parser(...)`) in `try/except
Exception`. `_send_to_parser` already resets pyte's internal parser state on
exception (see its docstring reference to PR #101) specifically so the
parser stays usable afterward — pyte is explicitly designed to tolerate being
fed a sequence it chokes on; recovering at the per-character level (not the
per-chunk level) is what actually uses that design correctly. This covers
all ~16 vulnerable methods uniformly, not just the one that happened to
crash first.

### Wire up real device-status replies (the functional gap)

Subclass `pyte.Screen` (`_PtyScreen`) overriding `write_process_input` to
`os.write` the reply straight back to `self._master_fd` (the same fd already
used for input). This makes cursor-position/terminal-status queries behave
like a real terminal: the querying program gets an actual reply instead of
silence, instead of only "no longer crashes."

### Everything else about the widget is unchanged

PTY spawn, key forwarding, `destroyed`-triggered cleanup, and the `_redraw()`
rendering path from `plans/console-widget-real-terminal-emulation.md` are
untouched — this only touches screen construction and the `feed()` call site.

## Verification

1. Headless: reproduce the crash directly — feed the exact sequence that
   crashed in the real app (a DEC-private device-status query, `ESC[?6n`)
   into a `TerminalWidget` and confirm it no longer raises, and that
   subsequent normal input/output still works correctly afterward (i.e. the
   guard doesn't leave the stream in a broken state).
2. Headless: confirm `write_process_input` now actually replies — feed
   `ESC[6n` (plain, not private — the one `pyte.Screen.report_device_status`
   fully supports) and confirm the correct `ESC[{row};{col}R` reply bytes
   appear on `master_fd` (read them back directly).
3. Regression: re-run the previous plan's headless tests (cursor-overwrite,
   color/bold formatting, cursor position/visibility) and the original
   `plans/console-widget.md` regression checks (echo round-trip, process
   spawn/cleanup) to confirm nothing else broke.
4. Full-app: launch the real app and run `claude` in the Console widget to
   confirm the specific reported crash no longer reproduces.

## Key design decisions / tradeoffs

- **Per-character recovery inside `feed()`, not a `try/except` around the
  whole call.** The whole-call version is simpler but silently discards real
  output queued after the bad sequence in the same chunk — confirmed
  directly, not just a theoretical concern. Overriding `feed()` itself
  (mirroring pyte's own upstream implementation, guarding only the dispatch
  call) is more code but is the only version that doesn't lose data.
- **Actually implement `write_process_input`, not just suppress the
  crash.** Silencing the crash alone would still leave device-status queries
  unanswered, which is a real (if less visible) correctness gap for any
  program that depends on the reply — worth fixing now since the wiring is
  small (one `os.write` call) and directly relevant to `claude`'s own
  terminal-capability probing.
- **Reaching into `pyte.Stream`'s underscore-prefixed internals
  (`_send_to_parser`, `_text_pattern`, `_taking_plain_text`) to override
  `feed()`.** Normally worth avoiding, but justified here: the alternative
  (silent data loss on any private-CSI hiccup) is worse, `pyte` is a small
  and slow-moving library (0.8.2 has been the latest release for a while),
  and the override is a byte-for-byte copy of the upstream method with a
  single added `try/except`, easy to re-diff against a future pyte release
  if it ever changes.

## Status

Implemented and verified:

1. Headless: fed the exact crashing sequence (`ESC[?6n`, a DEC-private
   cursor-position query) into a live shell session via real keystrokes
   (`printf '\033[?6n'; echo $((21*2))` typed through the widget), confirmed
   no exception escapes and that `$((21*2))`'s output (`42`) — which arrived
   in the *same* PTY read as the crashing sequence — still renders
   correctly, proving the per-character recovery doesn't drop subsequent
   output the way a whole-call `try/except` did in initial testing.
2. Headless: confirmed `_PtyScreen.write_process_input` writes the correct
   raw reply bytes (`ESC[1;4R"` for a cursor at row 1/col 4) to the PTY,
   verified via an isolated raw/non-canonical pty pair (reading the slave
   side directly, to avoid the tty driver's `ECHOCTL` cosmetic rendering of
   control bytes as `^X` when read back from the master side, which is a
   test-observation artifact, not a bug).
3. Regression: re-ran all of `plans/console-widget-real-terminal-emulation.md`'s
   headless tests (cursor-overwrite, color/bold formatting, cursor
   position/visibility) and `plans/console-widget.md`'s original checks
   (echo round-trip, process spawn, cleanup-on-destroy) — all still pass.
4. Full-app: launched the real widget and ran `claude` interactively.
   Confirmed via byte-level tracing that the exact original crash trigger
   fires during `claude`'s startup (`\x1b[?6c`, a private device-attributes
   query) and is now caught and logged ("pyte failed to dispatch a terminal
   escape sequence; skipping it") instead of aborting the process; `claude`'s
   actual TUI (version banner, model/plan info) then renders correctly
   afterward — the originally reported crash no longer reproduces.
