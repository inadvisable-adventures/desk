# Claude (Desk) widget: robust against an oversized tool-result message (TODO f35466a) (COMPLETED)

## Summary

A previous session reported the `Claude (Desk)` widget became "glitchy"
after loading back a screenshot too large for its JSON channel (a
~776KB base64-encoded, ~3456x2160 native/HiDPI capture) -- a JSON
import error, requiring a reload/restart to recover from. Neither
report had visibility into Desk's own client-side handling, so this is
symptom-level as filed. Cites
`../FEEDBACK/FEEDBACK-DESK-widget-glitches-on-oversized-screenshot-json-2026-09-18-2140.md`
(part a).

## Reproduction and classification

No live Claude API access in this environment (real `ClaudeSession`
tests need one -- see `disabled_verify_scoped_claude_session.py`'s own
precedent for splitting that kind of coverage out), so this reproduces
the failure at the exact boundary the TODO's own suspected cause points
to and Desk's own code owns: `claude_agent_sdk`'s subprocess transport
(`subprocess_cli.py`) confirmed, by reading its source directly, to
enforce `_DEFAULT_MAX_BUFFER_SIZE = 1024 * 1024` (1MB) against any
single NDJSON line read from the CLI's stdout, raising
`CLIJSONDecodeError` (aliased `SDKJSONDecodeError` internally) when
exceeded -- `ClaudeAgentOptions.max_buffer_size` overrides it, and
`ClaudeSession` (`src/desk/claude_session.py`) never sets it. **Confirmed
the suspected cause.**

Reproduced Desk's own handling of exactly this failure directly and
offline: a fake `sdk.ClaudeSDKClient` swapped into a real
`ClaudeSession`'s `self._client` (no subprocess/network involved),
`receive_response()` yielding one real message and then raising the
exact `CLIJSONDecodeError` `guard()` raises, run through the real
`_query_and_stream` coroutine. Result: the message that arrived before
the failure is still delivered (`assistant_text` fires normally);
`session_error` fires with a bounded, legible message (`CLIJSONDecode
Error.__str__` truncates to `line[:100]`, so this is never the giant
payload dumped into the UI); no hang; a **subsequent** call against a
healthy client completes a normal turn (`turn_complete` fires) --
the session is not left in a broken state. **Classification: a caught
parse error, already handled correctly at this layer** -- not a dead
transport, not a UI-layer crash. `widgets/claude_desk/widget.py`'s own
`_on_session_error` (unchanged, already correct) clears busy state and
appends a persistent, visible history entry; already covered by
`verify_claude_desk_widget.py`.

Whatever exactly made the widget look "glitchy" in the original,
live-API incident isn't reproducible from a symptom-level report alone
without further live access -- but the mechanism this TODO's own
suspected cause named is confirmed real and now fixed at the source,
and the resulting failure -- if it still occurs at some larger size --
is confirmed to degrade cleanly rather than corrupt the session.

## Approach

1. **Raise `max_buffer_size`.** `ClaudeAgentOptions(...)` in
   `_connect_and_maybe_prompt` gains `max_buffer_size=_MAX_BUFFER_SIZE`,
   a new module constant (10,000,000 bytes -- generously above even a
   large native HiDPI screenshot's base64 size, while still bounded,
   not unlimited). This is the concrete fix: a payload that would have
   failed before (the reported ~776KB case, and headroom well beyond
   it) now succeeds outright.
2. **Lock in the graceful-degradation behavior with a real regression
   test** (new, offline, no live API) -- the exact reproduction above,
   so a future regression here (e.g. a refactor of `_query_and_stream`
   that drops the broad `except`) is caught.
3. No change needed to `_query_and_stream`/`_on_session_error` --
   confirmed already correct by the reproduction above.

## Affected files

- `src/desk/claude_session.py` -- `_MAX_BUFFER_SIZE` constant,
  `ClaudeAgentOptions(max_buffer_size=...)`.
- `tests/verify/verify_claude_session_oversized_message.py` -- new.

## Verification

Real `ClaudeSession`, a fake `sdk.ClaudeSDKClient` substituted for
`self._client` (no subprocess/network) -- confirms `max_buffer_size` is
actually passed to a real `ClaudeAgentOptions` construction (inspecting
the object `sdk.ClaudeSDKClient.__init__` receives, via a patched
constructor, since `_connect_and_maybe_prompt` itself needs a real
`connect()` to run further); the oversized-message reproduction above
(partial message delivered, `session_error` fires with a bounded
message, no hang, session usable for a subsequent turn). Full
`tests/verify/` sweep. No browser launch needed.

## Status

Implemented as planned. Confirmed the sanity of the new test by
temporarily reverting `src/desk/claude_session.py` and re-running it: it
fails immediately at import (`_MAX_BUFFER_SIZE` doesn't exist yet),
proving the test exercises real, newly-added code rather than passing
vacuously.

Verified: the new `verify_claude_session_oversized_message.py` (10
checks -- `max_buffer_size` genuinely reaches a real
`ClaudeAgentOptions` construction; a message delivered before an
oversized-payload failure is not lost; `session_error` fires with a
bounded, legible message, not the oversized payload itself; no hang;
and, the TODO's own point 3, a subsequent turn against a working client
completes normally after a failed one -- the session is not left
broken), run 3x for flakiness (deterministic, no timing dependency
beyond a 5s safety timeout on the no-hang check). Full `tests/verify/`
sweep (160 scripts) passes. Browser launch not needed -- no live Claude
API access in this environment, so the reproduction is offline, at the
exact `ClaudeSession`/`sdk.ClaudeSDKClient` boundary Desk's own code
owns (mirrors `disabled_verify_scoped_claude_session.py`'s own
precedent for why real-API coverage is kept separate and disabled).

Both feedback files this and TODO 94d2b94 cite are now fully resolved
(every citing TODO item complete, no open PARKINGLOT.md entries) --
moved
`../FEEDBACK/FEEDBACK-DESK-widget-glitches-on-oversized-screenshot-json-2026-09-18-2140.md`
to `../FEEDBACK/implemented/`.
