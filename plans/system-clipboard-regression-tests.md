# Properly integrate regression tests that use the real system clipboard (TODO `b6abde2`)

## Summary

`tests/verify/verify_paste.py`'s every test reads/writes the real
system clipboard (`QApplication.clipboard()`) -- and two of them
(`test_menu_hides_paste_item_when_clipboard_empty`,
`test_empty_clipboard_is_noop`) call `clipboard.clear()`, which
destroys whatever the user actually had copied at the time the
regression sweep ran. Disabled outright (the project's standard
`disabled_` prefix convention, whole file since every test in it
touches the clipboard) as an immediate fix, renamed to
`tests/verify/disabled_verify_paste.py`.

## Affected files

Not yet known precisely -- depends on which direction is chosen (see
Status below). Candidate: `tests/verify/disabled_verify_paste.py`
(either renamed back with save/restore-real-clipboard wrapping added
around each test, rewritten to mock/fake the clipboard object
entirely, or left as a manually-run script).

## Step-by-step implementation

Not written -- blocked on the open questions below.

## Status

Blocked on real answers, not just a judgment call this session should
make unilaterally -- recorded in `QUESTIONS.md`. Narrower than TODO
`9bc522b`/TODO `0d91c74`/TODO `b2ab79f` -- this isn't about API
cost/network dependency, it's specifically about not clobbering real
user state (the clipboard) during an automated sweep. Saving and
restoring the real clipboard's contents around each test looks like
the simplest fix on its face, but needs a real decision (and a check
that Qt's clipboard API actually round-trips every MIME flavor these
tests set -- text, `text/markdown`, images -- losslessly) rather than
assuming it just works.
