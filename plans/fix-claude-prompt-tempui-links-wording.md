# Claude widget prompt: follow tempui doc links only as needed, not unconditionally (COMPLETED)

TODO `855ca76`.

## Summary

TODO `e57ce5f` split `desk-temporary-ui.md` into a main file plus
sibling `tempui-*.md` files, and updated `CLAUDE_WIDGET_PROMPT` to
tell a freshly-launched `claude` session to "follow those links too,
not just this one file" — read as an instruction to open every linked
file unconditionally, on every session, regardless of whether that
session ever touches the capability it covers. That defeats the whole
point of splitting the doc in the first place (letting an agent read
only what's relevant to what it's actually doing) and burns context on
material that's frequently irrelevant (e.g. reading
`tempui-lightning-round.md` on a session that never runs a lightning
round).

## Fix

Reworded `CLAUDE_WIDGET_PROMPT` (`widgets/claude/widget.py`) to make
the conditional nature explicit: open a linked `tempui-*.md` file only
once you actually need that specific capability, with a concrete
example (only read `tempui-lightning-round.md` if you're about to run
a lightning round) — mirroring the exact example given in the
request. The main `desk-temporary-ui.md` intro's own per-capability
bullet list (each one already a single line describing *what* the
capability is for, before its link) already gives "just enough context
to understand use cases" for an agent to decide whether it needs to
open a given split file at all — reviewed and confirmed as already
satisfying this without needing a content change of its own; only the
prompt's own instruction wording was actually the problem.

## Affected files

- `widgets/claude/widget.py` — `CLAUDE_WIDGET_PROMPT` wording only.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`): the
rendered prompt text no longer contains unconditional phrasing
("too", "also", "as well" applied to reading every linked file) and
does contain the "only if you need it" framing plus a concrete
example; the existing regression check (prompt construction unchanged
when `development-process.md` is absent, from TODO `fbd0554`) still
holds, since only the constant's own text changed, not the
construction logic around it. Full scratchpad regression suite
re-run.

## Status

Implemented exactly as planned -- `CLAUDE_WIDGET_PROMPT` reworded to
explicitly say "only open one of those if you actually need that
particular capability," with the lightning-round example from the
request, ending "not unconditionally." Reviewed `desk-temporary-ui.md`'s
own intro bullet list (from TODO `e57ce5f`) against the request's
second point ("desk-temporary-ui.md should include just enough
context... that the agent can understand use cases") and confirmed it
already satisfies this as written -- each bullet is already a single
line stating what the capability is for before its link, which is
exactly the "enough to decide, without opening the link" shape asked
for; no content change was needed there.

Verified headlessly: sanity-checked the fix is real first (`git
stash`-ing just `widgets/claude/widget.py` reproduces the old,
corrected wording, and the new test fails against it as expected).
With the fix: the new verification asserts the prompt contains the
conditional framing and the concrete example, and no longer contains
the old unconditional phrasing; the existing TODO `fbd0554` regression
check (prompt construction unchanged when `development-process.md` is
absent) still passes unchanged. Full scratchpad regression suite
re-run -- same three pre-existing, unrelated failures as every recent
prior TODO, none touching the file edited here.

No `LEARNINGS.md` entry -- a straightforward wording correction on
feedback about a change made earlier in this same session, not a
surprising discovery.
