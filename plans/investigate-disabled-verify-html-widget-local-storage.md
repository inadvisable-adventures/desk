# Plan: TODO 6a5202c (COMPLETED) — investigate `disabled_verify_html_widget_local_storage.py`

## Investigation

Confirmed: fixture drift. `_FakeWindowWithView` (a hand-written fake
`DeskWindow` double) predates two attributes/methods the real
`_place_widget` now requires unconditionally: `_bind_event_mediator`
(TODO `6f9c51b`) and `_custom_widget_content_hash` (found only once
the first gap was fixed and the script hit a second one at the same
call site).

## Resolution

Bind `_bind_event_mediator = DeskWindow._bind_event_mediator` onto the
fake double (a genuine no-op for this script's own html-kind widgets,
since `_bind_event_mediator`'s own `isinstance(frame.content,
PythonWidgetHost)` check returns before ever touching
`self._event_mediator` — no fake attribute needed for that one) and
add `self._custom_widget_content_hash = {}` to the fake's `__init__`.

## Verification

Re-run standalone (passes, all 7 checks); full `tests/verify/` suite:
disabled count drops to 8, 0 new failures.
