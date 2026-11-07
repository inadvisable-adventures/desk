# shared-components/desk-select: drop-in <select> for html widgets (TODO b0dd8e1) (COMPLETED)

## Summary

A native `<select>` in a `kind:"html"`/`DefineWidget` widget opens an OS-level popup positioned from untransformed
screen coordinates, so with the Workspace Canvas zoomed/panned its list renders detached from the control (same class
as the documented `QComboBox` bug). Give html widgets a built-in replacement element and document the whole class.
Cites `../FEEDBACK/FEEDBACK-DESK-html-lt-select-gt-popups-misposition-under-canvas-zoom-pan-t-2026-11-06-1606.md`.

## Affected files

- `shared-components/desk-select/` (new): `desk-select.ts`, `template.html`, `README.md`; `shared-components/README.md`.
- `src/desk/temp_ui.py`: tag, changelog entry, `tempui-custom-widgets.md` "Reusable UI components" note.
- `tests/verify/verify_shared_desk_select.py` (new).

## Approach

- Delivered as a shared component (loaded only when a widget opts in -- import or copy, plus pasting the `<template>`),
  following `hsv-color-picker`'s conventions (strict TS script, template looked up by id, no deps). Not injected
  into every page.
- `<desk-select>`: light-DOM `<option>` children (observed for changes); `value`/`selectedIndex`/`disabled`/`options`;
  `input` + `change` events (bubbling, composed, user-driven only); keyboard nav + type-ahead; ARIA combobox/listbox.
- The list is `position: fixed` inside the shadow root: ordinary page content (rides the canvas transform, never an OS
  popup) and not clipped by `overflow:auto` ancestors. Flips above the control when there's more room there; closes
  on outside `pointerdown` (via `composedPath`), any scroll, and resize.
- Known caveat (documented): an ancestor with `transform`/`filter`/`contain: paint` becomes the containing block for
  fixed descendants. `<optgroup>`/`multiple`/form submission are not supported.
- Audit of the rest of the class (the feedback's last bullet): other native-popup controls -- date/time/month/week/
  datetime-local inputs, `<input type=color>`, `<input list>`, the context menu -- are listed in the README and in
  `tempui-custom-widgets.md` as to-avoid; only `<select>` gets a replacement now (color already has
  `hsv-color-picker`). A date picker / autocomplete component can be a later TODO if someone needs one.

## Verification

`verify_shared_desk_select.py` compiles the component with `tsc --strict` and exercises it in a real QtWebEngine page:
inside a shadow root inside an `overflow:auto` ancestor, the list is fixed-position, directly under the button, on top;
click/keyboard commit, `change` event, disabled-skipping, type-ahead, outside-click/Escape/scroll close, dynamic options,
and the docs/tag/mirroring checks.

## Status

Verified in a real (offscreen) QtWebEngine page. **Not verified live in Desk under a zoomed/panned canvas**, and the
claim that QtWebEngine's native `<select>` popup misplaces there rests on the feedback's live observation, not on a
check here. Per `python-widget-conventions.md`'s note that offscreen geometry isn't evidence of placement, worth a
quick look in the real app.
