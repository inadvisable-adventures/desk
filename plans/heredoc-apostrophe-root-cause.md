# Root cause of the heredoc-apostrophe `git commit` failure (TODO 8e8db18)

`LEARNINGS.md` already documents the symptom and the `git commit -F <file>`
workaround (added after repeated hits), but not why
`git commit -m "$(cat <<'EOF' ... EOF)"` intermittently fails with `unexpected
EOF while looking for matching` when the message body contains an apostrophe.
This investigates the actual trigger condition, empirically, rather than
guessing.

## Approach

Reproduce the failure in isolation with the smallest possible shell snippets
(no `git` involved at all, since the symptom is a shell/quoting error, not a
git error), then binary-search which specific ingredient is required by
toggling one variable at a time: presence of `$(...)` command substitution,
presence of a heredoc inside it, heredoc delimiter quoting style
(`<<'EOF'` vs `<<EOF`), and the number of literal apostrophes in the body.

## Findings

Fully reproducible, precise trigger: a **`$(...)` command substitution
containing a heredoc whose body has an odd number of literal apostrophe (`'`)
characters.** Confirmed by direct experiment (see
`LEARNINGS.md`'s updated entry for the exact commands and results):

- A bare heredoc (no `$(...)` at all) with an apostrophe in its body: **fine**.
- `$(...)` containing an apostrophe but no heredoc: **fine**.
- `$(...)` containing a heredoc with **two** apostrophes (even count): **fine**.
- `$(...)` containing a heredoc with **one** apostrophe (odd count): **fails**,
  every time, regardless of whether the delimiter is quoted (`<<'EOF'`) or
  not (`<<EOF`), and regardless of whether the result is assigned to a
  variable, echoed directly, or just evaluated for its side effect.
- The same heredoc+odd-apostrophe pattern inside **backtick** command
  substitution (`` `cat <<EOF ... EOF` ``) instead of `$(...)`: **fine** —
  the bug is specific to `$(...)` syntax, not command substitution in
  general.

This points at something outside both `bash` itself and this repository:
some layer around the actual shell process this environment's command-running
tool invokes appears to specifically detect/handle `$(...)` command
substitutions, and re-serializes or re-wraps the command text in a way that
doesn't escape an embedded, unbalanced literal `'` — consistent with the
observed "even apostrophe count is fine, odd fails" pattern (an odd count
prematurely closes some outer single-quoted wrapping the even case
coincidentally still balances). The exact mechanism is in that surrounding
tool/sandbox layer, not in anything under this repository's own source —
there is nothing to patch here, and no access to that layer's own
implementation from inside this project to confirm the mechanism further
than "empirically, this is the precise trigger."

## Resolution

Not a bug in Desk or in this repository's own code — nothing to fix here.
Deliverable is documentation: update `LEARNINGS.md`'s existing entry with the
precise trigger condition (narrower and more useful than the original
"intermittently fails... even for messages that look correctly quoted"), and
confirm `git commit -F <file>` remains the right, sufficient, permanent
workaround (it avoids the whole `$(...)` + heredoc pattern this bug requires,
not just the apostrophe). A narrower in-place mitigation also exists for
anyone who still wants the inline-heredoc style for some other `$(...)` use
(not just `git commit`): keep the apostrophe count in the heredoc body even,
or use backtick substitution instead of `$(...)`, or simply avoid nesting a
heredoc inside `$(...)` at all.

## Verification

No `tests/verify/` script -- this isn't Desk's own application code, it's a
property of the surrounding shell/tool environment, confirmed directly via
the reproduction commands recorded in `LEARNINGS.md`'s entry itself (anyone
doubting the finding can paste the same four-line snippets and get the same
result).

## Status: COMPLETED 2026-10-15

Root cause characterized precisely and reproducibly; `LEARNINGS.md` updated;
no code change needed or possible from within this repository.
