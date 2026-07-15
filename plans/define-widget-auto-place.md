# Plan: TODO 5ff02d2 (COMPLETED) — fix DefineWidget's silent no-instance-placed gap

See design-docs/custom-widget-authoring.md section 2 for the full
rationale.

## Summary

Two independent, cheap fixes for the same gap: dropping a `DefineWidget`
tempui file registers a new widget kind but currently gives no visible
signal and places no instance, unlike every other tempui kind.

## Fix 1: louder docs

In `src/desk/temp_ui.py`'s `_CUSTOM_WIDGETS_DOC`, add a one-line callout
right after the section's opening paragraph (before the "Lines are
tab-separated" bullet list): **"Defining a widget kind does not place an
instance on the canvas by itself — see 'Invoking a defined widget' below
for the separate step that does."** Bump `TEMPUI_DOC_VERSION` by 1.

## Fix 2: auto-place the first instance

`DeskWindow._handle_define_widget_file(path)` is called identically from
both `_on_temp_ui_file_added` and `_on_temp_ui_file_edited` today. Give it
an `is_new: bool = False` parameter, passed `True` only from
`_on_temp_ui_file_added`. After a successful `_register_custom_widget`
call, if `is_new` is true *and* the keyword wasn't already known before
this registration (checked before mutating `_custom_widget_definitions`,
not after), place one instance automatically — centered in the current
view, the same positioning `_place_discuss_claude_widget` and
`_activate_temp_ui` already use for their own auto-placements.

This deliberately does **not** fire from
`_register_custom_widgets_from_desk_temp` (the bulk startup/Desk-switch
rescan of already-known tempui `DefineWidget` files) or from a re-save of
an existing keyword — only a genuinely new keyword seen via the live
file-added watcher path, so restarting Desk or fixing a typo and re
-saving never place a duplicate instance.

### Affected code

- `_handle_define_widget_file`: add `is_new` param, capture
  `definition.keyword in self._custom_widget_definitions` *before*
  calling `_register_custom_widget`, call a new
  `_auto_place_new_custom_widget(keyword)` when both conditions hold.
- `_on_temp_ui_file_added`: pass `is_new=True`.
- New `_auto_place_new_custom_widget(self, keyword: str) -> None`: looks
  up `self._widgets.get(keyword)`, centers the view same as
  `_place_discuss_claude_widget`, calls `self._place_widget(keyword,
  widget, center, widget.default_size)`. No-op if the widget id somehow
  isn't in the catalog (shouldn't happen right after a successful
  registration, but matches this file's general "missing lookup is a
  silent no-op" posture elsewhere).

Re-invocation (the existing explicit keyword-only tempui file) keeps
working unchanged for placing *additional* instances later.

## Verification

- Doc: confirm the callout text and version bump.
- Behavior, via the established unbound-method-on-a-fake-double pattern:
  - A live-added brand-new `DefineWidget` file places exactly one
    instance.
  - The same keyword's file being *edited* afterward places no
    additional instance.
  - `_register_custom_widgets_from_desk_temp` (startup/Desk-switch bulk
    scan) places no instance for any already-known definition.
  - A `DefineWidget` file whose keyword collides/fails to register
    (`_register_custom_widget` returns `False`) places nothing.
- Run the full scratchpad regression suite (`git stash` before/after to
  rule out pre-existing failures) to confirm no other tempui/custom
  -widget flow regresses.
