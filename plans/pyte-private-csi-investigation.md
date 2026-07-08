# Investigate `pyte`'s `private=True` CSI dispatch gap further (COMPLETED)

## Summary

TODO 950774b already fixed the crash (skip-and-log via
`_ResilientStream`, verified against the real originally-reported
`claude` crash). This item's own pasted evidence confirms that fix is
working exactly as designed: the app no longer crashes, it logs a
`WARNING` and keeps running. What's actually open is two judgment calls,
not a bug: (1) is skip-and-log the right *permanent* behavior, or should
the affected `Screen` methods be patched to actually handle the private
variant; (2) is the current per-occurrence `WARNING` + full traceback too
noisy for something this routine.

## Investigation and conclusions

### Should the affected `Screen` methods be patched to handle `private=True` correctly?

**No — keep skip-and-log as the permanent behavior.** Reasoning:

- Most of the affected methods' *private* CSI variants
  (`report_device_status`'s `ESC[?Pn`, and the private forms of
  `cursor_position`/`cursor_to_column`/`set_margins`/etc.) are DEC
  -private status reports with no single, universally-correct reply —
  e.g. printer status, UDK status, locator status/identification, macro
  space, memory checksum, multiple-session status. These are old,
  terminal-specific extensions, not a well-defined protocol with one
  obvious right answer to hand-implement.
- The current behavior has already been empirically proven sufficient:
  `claude` runs correctly end-to-end under it (TODO 950774b's own
  verification: `claude --help` and a real interactive session, both
  with this exact guard in place).
- Guessing/fabricating a reply for an ambiguous private query risks being
  *worse* than not replying at all — a program that gets a reply it
  doesn't expect for a status query it doesn't really need answered could
  misbehave in a way that silently skipping the sequence never causes.
- This traceback's specific trigger (`report_device_status`, i.e. a
  private-form `n`-suffixed DSR) is a *different* private query than TODO
  950774b's own confirmed trigger (a private-form `c`-suffixed device
  -attributes query) — direct evidence that `claude` sends more than one
  kind of private CSI query over the course of a real session, and the
  existing per-character guard (not a per-method patch) already covers
  all of them uniformly. Patching individual methods one at a time would
  just be chasing whichever one happens to get hit next.

### Is the logging too noisy?

**Yes — downgrade it.** A `WARNING` with a full `exc_info=True` traceback
was appropriate while this was a *newly diagnosed* condition worth
flagging loudly; it no longer is, now that the root cause is fully
understood and documented (`LEARNINGS.md`, TODO 950774b, this item). Per
this item's own evidence, `claude` triggers this routinely (apparently on
every startup) — logging a full stack trace every single time adds noise
without adding diagnostic value for something already this well
-understood. Downgrade to `DEBUG`, drop the traceback dump.

## Affected files

- `widgets/console/widget.py` (edit) — logging level/verbosity only; no
  behavior change to the dispatch-guard logic itself.

## Verification

Headless: confirm the guard still catches the dispatch exception and the
stream stays usable afterward (regression, already covered by TODO
950774b's own tests — re-run, not re-derived); confirm the log record
emitted is now `DEBUG` level with no exception traceback attached.

## Status

Implemented and verified headlessly:

1. Fed the exact crashing private DSR sequence (`ESC[?6n`) and confirmed
   the guard still catches it and output after it survives.
2. Confirmed the emitted log record is `DEBUG` level with `exc_info`
   `None` (no traceback), by attaching a real logging handler and
   inspecting the captured record directly.
3. Regression: re-ran TODO 950774b's own headless checks (cursor
   -overwrite, echo round-trip, process spawn/cleanup) — all still pass.
