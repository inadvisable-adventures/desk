# desk-select: properties set before upgrade (TODO `c8bb4eb`) (COMPLETED)

## Summary

A widget that follows the "clone every control from a `<template>`"
convention built `<desk-select>` by clone -> `el.value = x` -> insert. A
template's content is inert, so the clone is not upgraded; the assignment
created an own data property that shadowed the class's `value` accessor
once the element upgraded. The control looked right but user picks never
changed `value` -- no error. Source feedback:
`FEEDBACK-DESK-lt-desk-select-gt-silently-breaks-wrong-value-saved-not-a-vi-2026-11-07-1645.md`.

## Changes (`shared-components/desk-select/desk-select.ts`)

- `connectedCallback` re-routes own `value` / `selectedIndex` /
  `disabled` through the real setters (the standard "upgrade property"
  pattern), so the natural construction order works.
- `value` / `selectedIndex` set before the element is connected were
  silently dropped (no options read yet). They now reflect to the `value`
  attribute / a `pendingIndex`, applied when `readOptions()` first runs.
- `readOptions()` no longer treats an explicit value matching no option as
  "unspecified": it selects nothing (like `<select>`, and as the README
  already said). The first-enabled/`selected` default applies only when
  nothing was specified.

## Finding: `customElements.upgrade()`

The report found it did not upgrade the clone and suspected a QtWebEngine
deviation. It is spec behavior: the clone's node document is the
template's inert content document, which has no browsing context or
custom-element registry. `document.importNode(templateChild, true)` adopts
into the live document and does upgrade (checked in this QtWebEngine
6.11.2 / Chrome 140). Documented in `tempui-custom-widgets.md` and the
component README.

## Not done

A shared `createElementFromTemplate` helper was suggested; with the
element self-healing and the docs naming `createElement`/`importNode`, it
is not needed now.

## Verification

`tests/verify/verify_desk_select_template_clone.py` (16 checks, real
QtWebEngine page): failed 10/16 before the fix; passes after.
`verify_shared_desk_select.py` (26) and `verify_shared_components.py` (26)
still pass.
