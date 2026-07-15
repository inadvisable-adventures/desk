# Event Log widget's Live Tail/Clear Log buttons don't scale their chrome with zoom

TODO `593a464`.

## Summary

Reported with a screenshot of the Event Log widget's toolbar at a
non-1.0 zoom level: the "Live Tail" and "Clear Log" `QPushButton`s'
text renders oversized, overflowing well outside their own grey
rounded-pill backgrounds, which stayed a visibly smaller size than the
(correctly, by design) zoomed text.

This is the exact same bug already fixed once in this codebase for the
File Explorer widget's toolbar (TODO `465c404`,
`plans/file-explorer-toolbar-zoom-scaling.md`) and, before that, its
tree expand/collapse arrows (`plans/file-explorer-widget.md`): a
native-platform-style-painted control visually desyncing from the rest
of the widget once composited through a `QGraphicsProxyWidget` at
non-1.0 zoom (see `LEARNINGS.md`'s "A native-style-drawn control ...
can visually desync from its own click hit-region once embedded in a
zoomed `QGraphicsProxyWidget`" entry). `QPushButton` renders its
background/border chrome the same native-style way the tree arrow used
to.

## Key decision

Same fix as TODO `465c404`, applied to this widget's two buttons:
force Qt's built-in "Fusion" style specifically on `self._live_tail_
button` and the `clear_button` local (promoted to `self._clear_button`
so it's clearly owned alongside the other instance attributes) via
`QStyleFactory.create("Fusion")` + `.setStyle(...)`, rather than
hand-painting custom button chrome. Same reasoning as before: a
`QPushButton` has too many visual states (hover, pressed, checked --
this widget's Live Tail button is specifically checkable, unlike File
Explorer's plain Open Folder button -- focus ring, disabled) to
re-derive by hand for the same problem Qt's own non-native renderer
already solves.

Scoped to just these two controls, matching this codebase's existing
narrow-fix precedent for this bug category (not a global native-style
-versus-Fusion switch for the whole app).

**PyQt gotcha, same as TODO `465c404`**: `QWidget.setStyle()` does not
take ownership of the `QStyle` -- kept alive as an instance attribute
(`self._toolbar_style`), shared by both buttons.

## Affected files

- `widgets/event_log/widget.py` -- `self._live_tail_button` and
  `self._clear_button` (promoted from a local `clear_button`) both get
  `.setStyle(self._toolbar_style)`, where `self._toolbar_style =
  QStyleFactory.create("Fusion")` is created once in `__init__`.

## Verification

- Headless (`QT_QPA_PLATFORM=offscreen`): building the widget with the
  style override applied doesn't raise, doesn't change the toolbar's
  layout/sizing, Live Tail's checkable/toggle behavior and Clear Log's
  `clicked` -> `_clear_log` wiring both still work exactly as before.
- Rendering the real widget (not a mockup) through a 3x-zoomed
  `QGraphicsView`/`QGraphicsProxyWidget`, mirroring TODO `465c404`'s
  own verification setup: both buttons' background/border scale in
  proportion with their text at zoom, with no layout breakage.
- **Not verifiable here, flagged rather than silently skipped** (same
  as TODO `465c404`): this environment's offscreen Qt platform defaults
  to Fusion regardless of the fix, so it can't reproduce the *broken*
  native-macOS-style rendering the bug report showed, and can't prove
  by direct before/after comparison that this resolves that exact
  symptom. Needs a visual check by the user in the real running app,
  zoomed into the Event Log widget's toolbar. If Fusion's look reads as
  jarring, or the bug somehow persists, the fallback is hand-painted
  custom chrome for these two controls.
