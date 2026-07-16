# Plan: TODO d8a6c96 (COMPLETED) — investigate `disabled_verify_tempui_custom_widgets.py`

## Investigation

Same fixture-drift category as several sibling scripts in this batch:
`_FakeWindow` (and `_FakeWindowWithView`, which subclasses it) predates
`_register_custom_widget` setting
`self._custom_widget_content_hash[keyword]` unconditionally.
`_FakeWindowWithView` also binds `_place_widget` without
`_bind_event_mediator` (the same gap fixed in several sibling scripts
above) — worth adding preemptively since this file also exercises
`_place_widget` for python-kind widgets.

## Resolution

Add `self._custom_widget_content_hash = {}` to `_FakeWindow.__init__`
(inherited by `_FakeWindowWithView`); add
`_bind_event_mediator`/`_event_mediator` to `_FakeWindowWithView`.

Two further gaps surfaced only once the first was fixed (each one only
reachable after the previous fix let execution proceed further):
`_refresh_stale_indicators_for` (called at the end of every
`_register_custom_widget`) needed binding onto `_FakeWindow`, and its
own body needs `self.view._frames` to exist — `_FakeView` (the
lightweight fake used by plain `_FakeWindow`, distinct from
`_FakeWindowWithView`'s real `WorkspaceView`) had no such attribute, so
added an empty list. `_relocate_promoted_widget_source` (called by
`_on_tempui_promote_requested`) also needed binding.

## Verification

Re-ran standalone after each fix until fully passing (18 checks); full
`tests/verify/` suite: disabled count drops to 0 — every script in
this batch is now enabled, 0 new failures.
