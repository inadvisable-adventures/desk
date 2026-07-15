# Generic fix: Fusion-style every canvas-embedded widget's content, automatically

TODO `8afef71`.

## Summary

TODO `465c404` (File Explorer toolbar) and TODO `593a464` (Event Log
toolbar) each independently fixed one widget's specific buttons by
forcing Qt's Fusion style onto them, because native-platform-style
chrome (`QPushButton`, `QLineEdit`, `QComboBox`, scrollbars, header
sections, ...) doesn't respect the Workspace Canvas's `QGraphicsView`
zoom transform once embedded via `QGraphicsProxyWidget`, while Fusion's
own vector-painted chrome does (see `LEARNINGS.md`'s "A native-style
-drawn control ... can visually desync ..." entry).

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
`WidgetFrame.__init__` (`src/desk/shell/widget_frame.py:350`), which
receives each widget's `content` and wraps it in the chrome before the
whole frame is added to the canvas as one `QGraphicsProxyWidget`
(`canvas.py`'s `self.scene().addWidget(frame)`).

## Design

### `_ContentStyleGuard`

A small `QObject` (new class in `widget_frame.py`) that:

1. On construction, is handed a single shared `QStyle` instance
   (`QStyleFactory.create("Fusion")`, created once per `WidgetFrame` and
   kept alive as `self._content_style` -- `setStyle()` doesn't take
   ownership, same PyQt gotcha as TODO `465c404`/`593a464`).
2. `apply_recursive(widget)`: applies the style (`.setStyle(...)`) and
   installs itself as an event filter on `widget` and every existing
   descendant (`widget.findChildren(QWidget)`), guarded by a `set` of
   already-seen widgets so a widget already covered by an ancestor's
   `findChildren` pass isn't redundantly reprocessed.
3. `eventFilter`: watches for `QEvent.Type.ChildAdded` on any widget
   it's installed on. When a new child widget appears -- e.g.
   `lightning_round` tearing down and rebuilding `self._option_buttons`
   on every render -- it recursively applies the style to that new
   child (and *its* existing descendants, in case a whole pre-built
   subtree was attached in one shot) and installs itself on all of
   them too, so further-nested additions keep cascading. This is what
   makes the fix automatic for dynamically-recreated controls, not just
   ones present at construction time.

`WidgetFrame.__init__` calls `self._content_style_guard =
_ContentStyleGuard(self._content_style, self)` then
`self._content_style_guard.apply_recursive(content)`, right after
`self.content = content`.

**Scoped to `content` only** -- never applied to `WidgetFrame`'s own
chrome (titlebar, resize handles, buttons). That chrome is already
hand-painted (`_TitlebarButton` draws its own background/glyph via
plain `QWidget`/`QLabel`, not `QPushButton`), so it was never subject to
this bug in the first place -- it stays a constant on-screen size via
an entirely different mechanism (`set_view_scale`'s counter-scaling),
untouched by this change.

### Cleanup: remove now-redundant per-widget fixes

`widgets/file_explorer/widget.py` and `widgets/event_log/widget.py`'s
own manual `QStyleFactory.create("Fusion")` + `.setStyle(...)` calls
(from TODO `465c404`/`593a464`) become dead weight once every widget's
content gets this automatically -- removed, since keeping duplicate
logic around serves no purpose and could read as if the generic fix
*doesn't* already cover these two widgets.

## Affected files

- `src/desk/shell/widget_frame.py` -- new `_ContentStyleGuard` class;
  `WidgetFrame.__init__` constructs one and applies it to `content`.
- `widgets/file_explorer/widget.py` -- remove the now-redundant
  `self._toolbar_style`/`.setStyle(...)` calls (TODO `465c404`).
- `widgets/event_log/widget.py` -- remove the now-redundant
  `self._toolbar_style`/`.setStyle(...)` calls (TODO `593a464`).

## Verification

- Headless (`QT_QPA_PLATFORM=offscreen`): construct a real `WidgetFrame`
  wrapping a plain `QWidget` containing a `QPushButton` + `QLineEdit`
  (a minimal stand-in) and confirm both report `style().objectName() ==
  "fusion"` after construction, with no explicit per-control code
  involved.
- Dynamic case: construct a `WidgetFrame` wrapping a container, then
  *after* construction add a new `QPushButton` into that container
  (simulating `lightning_round`'s rebuild-on-render pattern) and
  confirm the new button also reports Fusion -- proves the
  `ChildAdded`-based cascade actually works, not just the initial pass.
- Nested pre-built subtree case: build a small composite widget (a
  `QWidget` containing its own `QPushButton` child) entirely *before*
  attaching it to the already-embedded content, then attach it in one
  shot, and confirm the grandchild button also picks up Fusion --
  proves `apply_recursive` on a `ChildAdded` child correctly walks that
  child's pre-existing subtree too, not just the child itself.
- Regression, real widgets: build several real widgets known from the
  audit to have both static controls (`svg_viewer`, `sheet`) and
  dynamic ones (`lightning_round`, `question`), wrap each in a real
  `WidgetFrame`, and confirm their native-style controls report Fusion
  -- including, for `lightning_round`/`question`, re-triggering a
  render cycle and confirming the *rebuilt* buttons are still Fusion
  -styled.
- Regression: `file_explorer` and `event_log` still report Fusion for
  their controls after the redundant per-widget code is removed (the
  generic mechanism alone now covers them).
- Confirm `WidgetFrame`'s own chrome (titlebar buttons, resize handles)
  is untouched -- still the hand-painted `_TitlebarButton`/`_ResizeHandle`
  classes, not `QPushButton`, and not run through
  `_ContentStyleGuard` at all (only `content` is).
- `pyflakes` on every touched file.
- **Not verifiable here, flagged rather than silently skipped** (same
  as TODO `465c404`/`593a464`): this environment's offscreen Qt
  platform defaults to Fusion regardless, so it can't reproduce the
  *broken* native-macOS-style rendering directly. Needs a visual check
  by the user in the real running app across a representative sample of
  widgets, zoomed in.

## Status

Not yet implemented.
