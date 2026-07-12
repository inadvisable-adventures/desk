# Audit code for uses of the old basic markdown widget

TODO `17ac2a8`.

## Summary

"Check for places in the code where the old basic markdown widget is
being used, and add to QUESTIONS.md about whether or not they should
be updated to point to the new markdown widget." Depends on TODOs
96013cf/858752b's rename (done) -- "the old basic markdown widget" is
now `markdown_old_basic`, "the new markdown widget" is `markdown`
(formerly `markdown_ex`).

## Approach

Grepped the whole codebase (`src/`, `widgets/`) for any hardcoded
reference to a markdown widget id, since widget directories can't
import each other directly -- the only way one widget opens another is
`current_context.get_widget_opener()("<widget_id>")`.

## Finding

Exactly one real reference: `widgets/todo/widget.py`'s "open plan"
button (`_open_hovered_plan`), `opener("markdown")` +
`widget.set_file(plan_path)` (see `plans/todo-open-plan-button.md`,
which itself only ever asked for "a markdown widget," not specifically
the plain one). No other call site anywhere references a markdown
widget id at all.

Because this call site already used the *id* `"markdown"` (not
anything hardcoding "the plain/basic" widget specifically), the rename
itself already transparently upgrades it: it now opens the new,
strictly-more-capable widget (TOC/folding/Mermaid) instead of the old
plain one, via the exact same `set_file(path)` call -- both widgets
share that identical public method, so no code change is needed here
at all. Checked `plans/markdown-ex-widget.md` for any documented
downside/tradeoff of the new widget vs. the old one (e.g. slower on
large files) that might argue for keeping this call site on the old,
simpler widget deliberately -- found none noted.

## Status

No blocking ambiguity found -- recorded as an already-answered entry in
`QUESTIONS.md` (per the TODO's own literal instruction to "add to
QUESTIONS.md"), with the conclusion: no code changes needed, the
existing `opener("markdown")` reference already correctly follows the
rename to the new, better widget.
