# Plan: TODO 086e922 (COMPLETED) — investigate `disabled_verify_new_desk_flow.py`

## Investigation

Confirmed fixture drift, in two layers: `_OrderTrackingWindow` (a
hand-written fake `DeskWindow` double whose real `switch_desk` method
is bound in via `win.__class__.switch_desk = DeskWindow.switch_desk`)
predates `switch_desk` gaining both `self._event_mediator.clear_all()`
(TODO `6f9c51b`) and `self._introspect_grants.clear()` (a Bridge API
introspection-grant cache) — the second gap only surfaced once the
first was fixed.

## Resolution

Add a real `EventMediator()` and an empty `set()` for
`_introspect_grants` to the fake's `__init__`.

## Verification

Re-run standalone (passes, all 14 checks); full `tests/verify/` suite:
disabled count drops to 6, 0 new failures.
