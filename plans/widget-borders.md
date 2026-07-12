# Small borders around widgets by default (COMPLETED)

TODO `ff6514a`.

## Summary

Every `WidgetFrame` gets a subtle 1px border by default, so adjacent
widgets (and a widget against the plain canvas background) are
visually distinguishable at a glance, especially once other work in
this batch (TODO `397770c`) makes the titlebar itself change slightly
on focus -- the border gives every widget a baseline visible edge
even when unfocused.

## Key decisions

- **A plain `QFrame`-style border via stylesheet on `WidgetFrame`
  itself**, scoped with the class-name selector (`WidgetFrame { ... }`)
  rather than a bare `QWidget { ... }` selector -- an unscoped
  `QWidget` stylesheet rule cascades to every nested child QWidget
  (a well-known Qt stylesheet gotcha), which would add unwanted
  borders to buttons/fields inside arbitrary widget content. Scoping
  by class name avoids that entirely.
- **Constant on-screen thickness regardless of zoom**, matching how
  every other piece of chrome in this file already behaves
  (`_TitleBar`/`_ResizeHandle`/`_TitlebarButton`'s own
  `apply_scale`) -- the border thickness is counter-scaled the same
  way, via a new `WidgetFrame.apply_scale`-adjacent update rather than
  a fixed stylesheet value that would visually thicken/thin with zoom.
- **Color**: a muted gray (`#4a4d51`) distinct from both the canvas
  background and the titlebar's own `#3a3d41`, subtle enough not to
  compete with a focused widget's titlebar highlight (TODO `397770c`).

## Affected files

- `src/desk/shell/widget_frame.py` -- `WidgetFrame` border styling,
  applied in `__init__` and kept constant-thickness in
  `set_view_scale`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, a real
`WidgetFrame`): confirms the frame's stylesheet includes a border rule
after construction, and that `set_view_scale` updates the border
thickness in the stylesheet text proportionally to the given scale
(counter-scaled, same convention as the titlebar height).

## Status

Implemented as planned: `BORDER_THICKNESS`/`BORDER_COLOR` constants
and `WidgetFrame._apply_border_scale`, called from `__init__` and
`set_view_scale`, in `src/desk/shell/widget_frame.py`.

Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real `QApplication`,
a real `WidgetFrame`): a border rule is present by default, scoped to
the `WidgetFrame` class name (not a bare `QWidget` selector); the
local border thickness in the stylesheet shrinks as zoom increases and
grows as zoom decreases (counter-scaling, same convention as the rest
of this file's chrome), never below 1 local px.

No `LEARNINGS.md` entry needed -- nothing surprising, just following
this file's own already-established counter-scaling and
class-name-scoped-stylesheet conventions.
