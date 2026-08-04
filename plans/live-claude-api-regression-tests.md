# Properly integrate regression tests that make real Claude API calls (TODO `9bc522b`)

## Summary

Several `tests/verify/` scripts start a real Claude session -- either
`desk.claude_session.ClaudeSession` (the Claude Agent SDK wrapper) or
`widgets/claude/widget.py`'s `ClaudeWidget` (which execs the real
`claude` CLI inside a PTY) -- as part of their coverage. Every one of
these makes real network calls to the live Claude API, incurs real API
cost/quota, takes real (if usually short) wall-clock time, and depends
on the live model's actual behavior rather than fixed local logic.
Extracted (the project's standard `disabled_` prefix convention) as an
immediate fix, so a normal regression sweep doesn't make live API
calls at all:

- `tests/verify/disabled_verify_claude_desk_widget_claude_api.py` --
  split out of `tests/verify/verify_claude_desk_widget.py`, which
  keeps its other, API-free tests (widget.json shape, DeskWindow
  wiring) running normally.
- `tests/verify/disabled_verify_discuss_parking_lot_item_claude_api.py`
  -- split out of `tests/verify/verify_discuss_parking_lot_item.py`,
  which keeps its other, API-free tests (tempui parsing, doc-content
  checks) running normally.
- `tests/verify/disabled_verify_questions_discuss_button_claude_api.py`
  -- split out of `tests/verify/verify_questions_discuss_button.py`,
  which keeps its other, API-free test (the Discuss button's
  hover/click UI, driven through a patched discuss-starter hook)
  running normally.

That's the immediate fix. This TODO is the follow-up: decide how
coverage like this should actually be integrated long-term, rather
than leaving it disabled indefinitely -- this is real, valuable
coverage (e.g. it's what actually exercises `ClaudeSession`'s
resume-reconnects-context behavior, the tool-permission gate, and the
message queue against a real model).

## Affected files

Not yet known precisely -- depends on which direction is chosen (see
Status below). Candidates: the four `disabled_*` files above (either
renamed back, rewritten to mock the Claude Agent SDK/CLI layer, or
left as manually-run scripts); possibly `tests/verify/README.md` for
a new "occasionally run these by hand" category if that ends up being
the chosen shape.

## Step-by-step implementation

Not written -- blocked on the open questions below.

## Status

Blocked on real answers, not just a judgment call this session should
make unilaterally -- recorded in `QUESTIONS.md`. Same tension as TODO
`b2ab79f` (hardware-dependent tests): this project's whole
verification philosophy strongly prefers real, non-mocked behavior
over mocks, and these tests are a genuine, deliberate expression of
that -- but "real" here means "costs real money/quota and depends on
a live external service," which a normal, frequent regression sweep
shouldn't be doing unprompted.
