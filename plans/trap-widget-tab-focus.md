# Trap Tab/Shift+Tab focus within a WidgetFrame instead of escaping to a sibling canvas widget (COMPLETED)

TODO `e69f209`.

## Summary

Reported bug: "when widgets with carets overlap visually, sometimes
focus seems to switch between them while typing." Reproduced directly
(headless, real `QGraphicsScene`/`QGraphicsProxyWidget`, not a guess):
two `WidgetFrame`s placed on the canvas so they visually overlap, each
wrapping a `QLineEdit`-based content widget. Typing ordinary characters
never moves focus. Pressing **Tab** does: `QLineEdit` (like most
single-line/plain-line editing controls, unlike `QPlainTextEdit`/
`QScintilla`, which consume Tab themselves for indentation) doesn't
handle Tab itself, so Qt's normal "nothing local left to tab to, hand
off to whatever's next" chain runs -- and for a `QGraphicsProxyWidget`
-embedded widget, "whatever's next" is resolved at the *scene* level,
handing keyboard focus to a **different `WidgetFrame` entirely**, with
no relationship to the one that was just being typed in beyond
happening to be next in the scene's internal item list.

This is real, reproducible, unrelated to any actual mouse click, and
matches the report precisely: every widget on this canvas is meant to
behave like an independent floating window (arbitrary free-form
position, no intentional "tab order" relationship to any other
widget), not a tab stop in some canvas-wide sequence -- but Qt doesn't
know that, and treats every embedded widget in the shared
`QGraphicsScene` as fair game for its own default Tab-escape handling.
The **overlap** in the report isn't a separate cause, it's what makes
the bug legible: the stolen widget's caret appears in the same screen
region the user was just looking at and typing into, reading as "focus
flickered between them" rather than "focus silently jumped to some
unrelated widget elsewhere on the canvas" (which is the same
underlying bug, just easier to notice when the two widgets don't
overlap and the caret visibly relocates across the screen).

## Diagnosis detail

`WidgetFrame` (`src/desk/shell/widget_frame.py`) is the exact `QWidget`
handed to `scene().addWidget(frame)` in `WorkspaceView.add_widget`
(`canvas.py`) -- the natural boundary between "this widget's own
content" and "the shared canvas." It doesn't override
`focusNextPrevChild` (Qt's own hook for "I'm out of local candidates,
what now"), so the default `QWidget` implementation runs, and for a
proxy-embedded widget that ends with the scene handing focus to a
sibling `QGraphicsProxyWidget` item.

**A synchronous fix doesn't work**, confirmed directly: overriding
`focusNextPrevChild` and simply returning `True` (claiming "handled,
no escalation needed") to suppress the escape only works when there's
exactly one focusable control in the widget. With more than one
(confirmed with two `QLineEdit`s), the *second* Tab (from the last
field, nothing further within the widget) still returned `True` from
`super().focusNextPrevChild()`, and `self.focusWidget()` still
reported the expected widget immediately afterward -- yet the scene's
real focus item ended up on the *other* `WidgetFrame` a moment later
anyway. This is the same shape already documented in `LEARNINGS.md`
for the Lightning Round widget's click-to-focus fix:
`QGraphicsProxyWidget` resolves scene-level focus *after* whatever ran
synchronously for the triggering event, not during it -- so a
synchronous check inside `focusNextPrevChild` can't see the eventual
outcome, and a synchronous fix can't prevent it either.

## Fix

`WidgetFrame.focusNextPrevChild` runs the normal `super()` call (so
internal cycling between multiple focusable controls inside the same
widget -- e.g. the Stack widget's per-frame title/notes fields --
still works exactly as before), then schedules a
`QTimer.singleShot(0, ...)` reclaim check for *after* whatever
resolves scene-level focus has actually run (matching the Lightning
Round fix's own deferred pattern). That check: if this widget's own
`QGraphicsProxyWidget` is no longer the scene's `focusItem()` (focus
escaped this widget's subtree entirely), re-focus the first (Tab) or
last (Shift+Tab) still-focusable descendant found via
`findChildren(QWidget)` filtered to a real `focusPolicy()` -- which,
for a widget with only one focusable control, is that same control
(a harmless idempotent re-affirm), and for a widget with several,
wraps back around to the boundary one instead of leaking out. Always
returns `True` from `focusNextPrevChild` itself -- there's no case
where "hand focus to a sibling `WidgetFrame`" is the desired outcome,
so there's nothing to conditionally allow.

**Known, accepted minor gap**: Shift+Tab pressed on the very *first*
focusable control (nothing before it locally) doesn't wrap forward to
the *last* one the way plain Tab from the last control wraps back to
the first -- it just leaves focus where it already is. Confirmed this
still never leaks focus to a sibling widget (the actual bug), just
isn't perfectly symmetric at that one boundary. Not chased further:
Qt's own internal signal for "did anything actually change" isn't
reliable enough here (see Diagnosis detail above) to safely distinguish
"legitimately nothing to wrap to" from "the thing I'd wrap to is
already focused," and getting this one boundary case pixel-perfect
isn't worth more speculative poking at undocumented `QGraphicsProxyWidget`
internals for a cosmetic asymmetry that was never part of the reported
bug.

## Affected files

- `src/desk/shell/widget_frame.py` -- `WidgetFrame.focusNextPrevChild`
  (new), `WidgetFrame._reclaim_focus_if_escaped` (new).
- `design-docs/widget-ux.md` -- brief mention alongside the existing
  focus-tracking (TODO `397770c`)/titlebar-click-to-focus (TODO
  `a1c701d`) description.
- `LEARNINGS.md` -- new entry (this is exactly the kind of
  non-obvious, took-real-investigation, easy-to-repeat-without-a-note
  finding that file is for -- and it directly extends the existing
  Lightning Round entry's own documented mechanism).

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, real
`WorkspaceView`/`QGraphicsScene`/`QGraphicsProxyWidget` -- not
mocked, since the whole bug lives inside real proxy-widget focus
resolution):

- Two overlapping `WidgetFrame`s, single-`QLineEdit` content each:
  typing ordinary characters into one never moves scene focus to the
  other (regression baseline, already true before this fix). Pressing
  Tab repeatedly inside the one being typed into never moves scene
  focus to the other either (the actual fix, confirmed false/broken
  before this change, true after).
- Two overlapping `WidgetFrame`s, one with two `QLineEdit`s: Tab
  cycles field1 -> field2 -> (wraps) field1, never landing on the
  other widget at any point; Shift+Tab steps field2 -> field1
  correctly.
- Typing after a Tab-driven wraparound still lands in the correct
  (originally-focused) widget's field, not the sibling's.

## Status

Implemented exactly as planned: `WidgetFrame.focusNextPrevChild` +
`WidgetFrame._reclaim_focus_if_escaped` added to
`src/desk/shell/widget_frame.py`. `design-docs/widget-ux.md`'s Widget
Focus section and `LEARNINGS.md` updated.

Verified headlessly with a real `WorkspaceView`/`QGraphicsScene`/
`QGraphicsProxyWidget` (two `WidgetFrame`s placed so they visually
overlap, exactly matching the report):

- Sanity-checked the bug itself first, before writing the fix: `git
  stash`-ing just `widget_frame.py` and re-running the new
  verification script reproduces the reported symptom directly (Tab
  moves scene focus to the unrelated overlapping sibling; asserted
  `False`) -- confirming the fix (re-running the same script with the
  change restored) actually changes real, previously-broken behavior,
  not just adding assertions that were already true.
- Typing ordinary characters never moved focus even before this fix
  (regression baseline) and still doesn't after.
- Repeated Tab on a single-focusable-control widget never leaks focus
  to an overlapping sibling (previously did, immediately, on the very
  first Tab).
- A widget with two focusable controls: Tab cycles field1 -> field2 ->
  wraps back to field1, Shift+Tab steps field2 -> field1 correctly --
  at no point does scene focus land on the overlapping sibling widget.
  Typing after a Tab-driven wraparound lands in the correct widget's
  field.
- `QPlainTextEdit`'s own pre-existing "Tab inserts a literal tab
  character, no focus change" behavior confirmed unchanged (it already
  consumes Tab itself, before this widget-boundary logic would ever
  run).

Re-ran the full scratchpad regression suite, including the existing
widget-focus-tracking suite (`verify_widget_focus.py`, covering TODO
`397770c`'s titlebar-highlight-on-focus and TODO `a1c701d`'s
titlebar-click-to-refocus, both untouched by this change) -- all still
pass. Three pre-existing, unrelated failures found (same three flagged
in TODO 02eda20/`c458012`'s plans), none touching any file edited
here.

**Known minor gap** (documented in the Fix section above, not chased
further): Shift+Tab on the very first focusable control doesn't wrap
forward to the last one -- it just leaves focus where it is. Confirmed
this still never leaks focus to a sibling widget.
