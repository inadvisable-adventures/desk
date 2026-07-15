# Generic fix: zoom-safe stylesheet for every canvas-embedded widget's content, automatically (COMPLETED)

TODO `8afef71`.

## Summary

TODO `465c404` (Project Files toolbar) and TODO `593a464` (Event Log
toolbar) each independently fixed one widget's specific buttons by
forcing Qt's Fusion style onto them, because native-platform-style
chrome (`QPushButton`, `QLineEdit`, `QComboBox`, scrollbars, header
sections, ...) doesn't respect the Workspace Canvas's `QGraphicsView`
zoom transform once embedded via `QGraphicsProxyWidget`, while
non-native vector-painted chrome does (see `LEARNINGS.md`'s "A
native-style-drawn control ... can visually desync ..." entry).

A follow-up audit (prompted by a screenshot of the Event Log bug)
checked every other widget for the same category of bug and found it is
**not isolated** -- 17 of 19 widgets have at least one native-style
control embedded directly in their canvas-rendered content, including
both statically-created controls (a toolbar's Open/Save button, created
once in `__init__`) and dynamically-recreated ones (e.g.
`lightning_round`'s per-round option buttons, rebuilt on every
`_render()` call). Patching each file individually, as the previous two
fixes did, would mean ~30+ near-duplicate edits today and the same bug
resurfacing in every widget written from now on.

Per the user's decision, this is fixed once, generically, at the single
choke point every widget's content already passes through:
`WidgetFrame.__init__` (`src/desk/shell/widget_frame.py`), which
receives each widget's `content` and wraps it in the chrome before the
whole frame is added to the canvas as one `QGraphicsProxyWidget`
(`canvas.py`'s `self.scene().addWidget(frame)`).

## Investigation: the original `setStyle()`-based design didn't work

The first design (mirroring TODO `465c404`/`593a464` exactly) was a
`_ContentStyleGuard` that walked `content`'s descendants and called
`widget.setStyle(QStyleFactory.create("Fusion"))` on each one, plus a
`QEvent.ChildAdded` event filter to catch future dynamically-created
children.

Confirmed directly, this doesn't work once wrapped in a real
`WidgetFrame`: `WidgetFrame` itself already calls
`self.setStyleSheet(...)` on itself (`_apply_border_scale`, for its
own border) -- and setting a stylesheet on **any** ancestor silently
forces *every* descendant's effective `style()` onto Qt's internal
stylesheet-aware proxy, discarding whatever `setStyle()` a descendant
had explicitly been given, **regardless of call order** (confirmed:
calling `setStyle()` again *after* the ancestor's stylesheet is set
doesn't help either -- it's still immediately overridden). This means
TODO `465c404`/`593a464`'s original per-widget `setStyle()` fixes were
likely never actually effective in the real running app either, since
neither fix's own verification ever wrapped the widget in a real
`WidgetFrame` (both tested via a bare `scene.addWidget(widget)`, which
has no ancestor stylesheet to trigger this).

A second, related trap: `widget.style().objectName()`/`type(widget
.style())` -- the exact signal both prior plans' verification scripts
relied on -- turned out to be unreliable in this offscreen test
environment. Both the untouched platform-default style *and* a freshly
`QStyleFactory.create("Fusion")`-created style report as indistinguishable
`QCommonStyle`-wrapped objects with `objectName() == "fusion"` here,
so a check that merely confirms `objectName() == "fusion"` proves
nothing about whether a *specific* `setStyle()` call actually took
effect. Caught by switching to pixel-sampling the widget's actual
rendered output (`widget.grab().toImage().pixelColor(...)`) instead --
directly proves what the CSS engine painted, not what an indirect
style-object query reports.

## Design (actual, implemented)

Set a stylesheet **directly on `content` itself**
(`CONTENT_ZOOM_SAFE_STYLESHEET`, a new module-level constant in
`widget_frame.py`), not on individual descendants. Confirmed via
pixel-sampling that this reliably cascades to:

- static controls present at construction time,
- controls added dynamically *after* construction (the
  `lightning_round`/`question`/`parking_lot` per-render-rebuild case),
- and a whole pre-built subtree attached to `content` in one shot (a
  composite widget whose own children already exist before *it*
  becomes a child of `content`),

all without any event-filter machinery at all -- Qt's stylesheet
cascade is evaluated dynamically at paint/polish time for whatever the
current widget tree looks like, not pushed once to a fixed snapshot of
children, so newly-added descendants are automatically covered for
free. This is also dramatically simpler than the `_ContentStyleGuard`
class it replaces.

`CONTENT_ZOOM_SAFE_STYLESHEET` gives `QPushButton`/`QToolButton`/
`QLineEdit` (the three native-style-painted control types the audit
actually found in use) explicit `background-color`/`border`/
`border-radius`/`padding` rules -- plus `:hover`/`:pressed`/`:checked`/
`:disabled`/`:focus` states -- so Qt's CSS engine paints those
properties itself instead of deferring to native theme calls, the same
mechanism (confirmed via the audit) that already makes
`widgets/todo/widget.py`'s/`widgets/questions/widget.py`'s
`FILTER_BUTTON_STYLE`-styled buttons immune to this bug. Colors reuse
this file's own existing chrome palette constants (`BORDER_COLOR`,
`UNFOCUSED_TITLEBAR_COLOR`, `FOCUSED_TITLEBAR_COLOR`) for visual
consistency with the rest of a widget's frame.

A widget's own more specific per-control stylesheet (e.g. `todo`'s
`FILTER_BUTTON_STYLE`, applied directly to those buttons) still wins
over this content-level one, same as normal CSS cascade/specificity --
confirmed directly.

`WidgetFrame.__init__` calls `content.setStyleSheet
(CONTENT_ZOOM_SAFE_STYLESHEET)` right after `self.content = content`.

**Scoped to `content` only** -- never applied to `WidgetFrame`'s own
chrome (titlebar, resize handles, buttons). That chrome is already
hand-painted (`_TitlebarButton` draws its own background/glyph via
plain `QWidget`/`QLabel`, not `QPushButton`), so it was never subject to
this bug in the first place -- it stays a constant on-screen size via
an entirely different mechanism (`set_view_scale`'s counter-scaling),
untouched by this change.

### Cleanup: remove now-redundant per-widget fixes

`widgets/project_files/widget.py` and `widgets/event_log/widget.py`'s
own manual `QStyleFactory.create("Fusion")` + `.setStyle(...)` calls
(from TODO `465c404`/`593a464`) are removed -- confirmed (see
Investigation above) they weren't actually taking effect once wrapped
in a real `WidgetFrame` anyway, and the generic fix now covers both
widgets regardless.

## Affected files

- `src/desk/shell/widget_frame.py` -- new `CONTENT_ZOOM_SAFE_STYLESHEET`
  constant; `WidgetFrame.__init__` applies it to `content` via
  `content.setStyleSheet(...)`.
- `widgets/project_files/widget.py` -- remove the now-redundant/
  ineffective `self._toolbar_style`/`.setStyle(...)` calls (TODO
  `465c404`).
- `widgets/event_log/widget.py` -- remove the now-redundant/ineffective
  `self._toolbar_style`/`.setStyle(...)` calls (TODO `593a464`).

## Verification

All headless (`QT_QPA_PLATFORM=offscreen`), via pixel-sampling real
rendered output through a real `QGraphicsView`/`QGraphicsProxyWidget`
(not style-object introspection, per the Investigation section above):

- Static controls (`QPushButton`, `QLineEdit`) present at construction
  no longer show the environment's unstyled default background color.
- A `QPushButton` added *after* construction (the dynamic-recreation
  case) is also covered.
- A pre-built subtree (a composite widget with its own child button,
  attached to `content` in one shot) is also covered.
- A widget's own more specific stylesheet (simulating
  `FILTER_BUTTON_STYLE`) still wins over the generic one.
- A static `QToolButton` and a dynamically-added `QLineEdit` (the two
  other control types from `CONTENT_ZOOM_SAFE_STYLESHEET`, not just
  `QPushButton`) are both covered too.
- Real widgets from the audit: `svg_viewer` (static Open button),
  `lightning_round` (loading a real LightningRound tempui document,
  answering an item to force `_option_buttons` to actually tear down
  and rebuild, confirming the *rebuilt* buttons -- genuinely new
  objects, not the same ones -- are covered), `project_files` and
  `event_log` (both confirmed still covered after their own now-
  redundant per-widget code was removed; `event_log`'s Live Tail button
  additionally confirmed its `:checked` pseudo-state rule paints
  correctly, since it defaults to checked).
- `WidgetFrame`'s own chrome (titlebar) confirmed to never receive this
  stylesheet (only `content` does).
- `pyflakes` clean on every touched file.
- **Not verifiable here, flagged rather than silently skipped** (same
  as TODO `465c404`/`593a464`): this environment's offscreen Qt
  platform can't reproduce the real native-macOS-style rendering this
  bug category depends on. Needs a visual check by the user in the real
  running app across a representative sample of widgets, zoomed in.

## Status

Implemented as described above (a materially different design from the
plan's original `_ContentStyleGuard`/`setStyle()` approach -- see
Investigation). `CONTENT_ZOOM_SAFE_STYLESHEET` applied to every
widget's `content` in `WidgetFrame.__init__`; the now-redundant
per-widget fixes in `project_files`/`event_log` removed.

Verified extensively headlessly via pixel-sampling (see Verification
above) across static, dynamic, pre-built-subtree, pseudo-state, and
real-widget cases. As with the two prior fixes, real visual
confirmation in the actual running app (zoomed into a representative
sample of widgets) is still needed and flagged as not possible in this
offscreen environment.

**Update 2026-07-15: tested in the real running app, and the bug is
still present.** The Event Log toolbar buttons still do not scale
with zoom, despite every headless check above passing. The root cause
of this discrepancy -- why a stylesheet-driven fix that reliably
changes pixel output in the offscreen Qt platform doesn't resolve the
bug under real `QMacStyle`/native rendering -- has not been found yet.
Parked rather than continuing to iterate immediately; see
`PARKINGLOT.md` for the full attempt history and next steps.
