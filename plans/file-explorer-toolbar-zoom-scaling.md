# File Explorer toolbar controls don't scale their chrome with zoom

TODO `465c404`.

## Summary

Reported with a screenshot of the File Explorer widget zoomed in (roughly
3-4x). The widget's own chrome (the "File Explorer" titlebar label and the
"x" close button) renders at the normal, constant screen size, exactly as
designed (`design-docs/widget-ux.md`'s "Chrome Stays a Constant Screen
Size" — that's the `WidgetFrame` proxy counter-scaling, working
correctly). The bug is inside the widget's own *content*: the "Open
Folder" `QPushButton`'s text is huge, overflowing well outside its own
grey rounded-pill background, which stayed a visibly smaller size than
the (correctly, by design) zoomed text; the `QLineEdit` search box's
"Search..." placeholder text is similarly oversized, overflowing past
the right edge of the box's own thin border rectangle. In both cases the
*text* scaled correctly with the view's zoom (as intended — "zooming
should only magnify each widget's content") but each control's own
native-style-painted background/border chrome did not scale in
proportion, visually desyncing from its own text.

This is the same category of bug as the already-fixed tree
expand/collapse arrows in this same widget (`_FileTreeView.drawBranches`,
see its docstring and `plans/file-explorer-widget.md`): a
native-platform-style-painted decoration visually desyncing from the rest
of the widget once composited through a `QGraphicsProxyWidget` at
non-1.0 zoom. The arrow was fixed by no longer relying on the native
style to draw it at all (painting a plain triangle ourselves, directly
within the same Qt logical geometry the click hit-testing already uses).
`QPushButton`/`QLineEdit` render their background/border chrome the same
native-style way the arrow used to.

## Investigation

Reproducing the *broken* rendering directly wasn't possible in this
environment: `QT_QPA_PLATFORM=offscreen` (the only platform available
here) uses Qt's own "Fusion" style by default (confirmed directly --
`QApplication.style().objectName()` reports `"fusion"` under offscreen),
not the real native "macOS" style the actual app runs under. A minimal
repro (a plain `QPushButton`/`QLineEdit` pair inside a
`QGraphicsProxyWidget`, rendered through a 3x-zoomed `QGraphicsView`)
rendered correctly under this environment's default Fusion style --
which doesn't prove the fix works, but is suggestive: Fusion paints all
of its own chrome as ordinary vector/QPainter operations (rounded rects,
lines) that pass through whatever transform the painter already has, the
same way text and the hand-painted tree arrow already do, rather than
through native macOS theme APIs.

## Key decision

- **Force Qt's built-in "Fusion" style specifically on the two affected
  controls** (`open_folder_button`, `self._search_box`) via
  `QStyleFactory.create("Fusion")` + `widget.setStyle(...)`, rather than
  hand-painting custom button/line-edit chrome (the arrow's approach).
  Reasoning: a `QPushButton`/`QLineEdit` has meaningfully more visual
  states to get right by hand (hover, pressed, focus ring, disabled)
  than a single static triangle did, so re-deriving all of that as
  custom paint code is a much bigger, more error-prone undertaking for
  the same underlying problem Qt already has a built-in, non-native,
  transform-respecting renderer for. This mirrors the arrow fix's actual
  underlying strategy ("stop relying on native-style painting for this
  element") without reimplementing a native style's visual states from
  scratch.
- **Scoped to just these two controls, not the whole app.** Matches this
  codebase's existing precedent of narrow, local fixes for this bug
  category (the arrow fix touched only `_FileTreeView.drawBranches`, not
  every `QTreeView` in the app). A global native-style-versus-Fusion
  switch is a much bigger visual-consistency decision (every button/line
  edit in the app would look different) that isn't warranted by what was
  actually reported.
- **Known tradeoff, called out rather than hidden:** these two controls
  will render with Fusion's cross-platform dark-mode-aware look rather
  than the OS-native macOS control look the rest of the app's buttons
  use. Given this is a small dev-tool utility toolbar (not
  brand-sensitive chrome) and the alternative is either the reported bug
  or a much larger hand-painting effort, this is judged an acceptable
  trade for correctness at zoom. Worth revisiting if it reads as visually
  jarring in practice.
- **PyQt gotcha to guard against**: `QWidget.setStyle()` does **not**
  take ownership of the `QStyle` -- the caller must keep a live
  reference for as long as the widget exists, or Python's GC can free
  the `QStyle` out from under the (still-referencing) C++ widget.
  `self._toolbar_style = QStyleFactory.create("Fusion")` is stored as an
  instance attribute and shared by both controls (one `QStyle` instance
  can back multiple widgets simultaneously -- this is the same pattern
  `QApplication.setStyle()` already uses application-wide).

## Affected files

- `widgets/file_explorer/widget.py` -- `open_folder_button` and
  `self._search_box` both get `.setStyle(self._toolbar_style)`, where
  `self._toolbar_style = QStyleFactory.create("Fusion")` is created once
  in `__init__` and kept alive as an instance attribute.

## Verification

- Headless (what's actually checkable in this environment): building
  the widget with the style override applied doesn't raise, doesn't
  change the toolbar's logical layout/sizing, the button's `clicked`
  signal still fires `_choose_root`, and the search box's
  `textChanged`-driven search flow still works end-to-end (unchanged
  from before -- `setStyle()` only affects painting, not behavior or
  geometry hints in a way that breaks either).
- **Not verifiable here, flagged rather than silently skipped** (same
  spirit as this codebase's existing "note it in the plan if a browser
  -requiring verification step was skipped"): confirming the *actual*
  reported symptom is fixed requires the real running app under macOS's
  native style, zoomed in on the File Explorer widget, which this
  headless/offscreen environment cannot reproduce either the broken or
  the fixed rendering for (offscreen already defaults to Fusion). Needs
  a visual check by the user in the real app; if Fusion's own look
  reads as jarring, or the bug somehow persists, the fallback is
  hand-painted custom chrome for these two controls, matching the tree
  arrow's approach more literally.

## Status

Not yet implemented.
