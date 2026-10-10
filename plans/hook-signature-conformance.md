# Hook signature conformance (TODO `66aa766`) (COMPLETED)

Cites `../FEEDBACK/FEEDBACK-DESK-claude-desk-markdown-view-button-crashes-opener-arg-mismatch-2026-10-09-1420.md`
and `investigations/hook-signature-drift.md` (why it happened; read that first).

## Summary

`current_context` documented the centered opener as `(widget_id, path)`;
the real `DeskWindow.open_widget_content_centered` took `(widget_id, size,
instance_id, path)`. The Claude (Desk) Markdown View button and `[image]`
link therefore put a `Path` in `size` and crashed. Fix the signature and add
a mechanical conformance check so the class of bug fails in the suite.

## Changes

- `open_widget_content_centered(widget_id, path=None, *, size=None,
  instance_id=None)`: `path` second, the rest keyword-only. No caller passed
  `size`/`instance_id` positionally (all callers audited), so nothing else
  changes behavior.
- `current_context.CenteredWidgetOpener`, a `Protocol` single-sourcing that
  contract; the hook variable/setter/getter use it. Module docstring says the
  other `Callable` aliases are unchecked documentation, with the verify
  script as their check.
- `tests/verify/verify_current_context_hook_signatures.py`: (1) every
  `set_X(self.method)` binding in `window.py` -- alias arity/order/types vs
  the method; (2) Protocol signature equals the real method's exactly;
  (3) the real method called positionally as the widgets call it.
  Confirmed to fail against the old signature.
- The Claude (Desk) verify scripts now register the REAL method (on a
  stand-in) instead of a lambda copy of the alias; they fail against the
  old signature too. `verify_viewer_widgets_edit_button`'s stand-in
  mirrors the new shape.
- `development-process.md`: a rule under "Verification scripts" about
  changing hook shapes together and exercising them through the real method.

## Decisions (mine)

- No type checker / pre-commit infrastructure: no dependency allowed, and
  the verify suite is the gate. See the investigation's option table.
- Not agent-visible (an internal Python hook), so no tempui changelog tag.
- Not changed: the other aliases (audit found no other drift). `widget_opener`'s
  alias still hides its optional params; left as is.
