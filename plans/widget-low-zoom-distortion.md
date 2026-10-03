# Widget shapes distort at low zoom (TODO `9585a5a`) (COMPLETED)

## Summary
Investigate the reported distortion; it reproduced, so fix it.

## Live repro (headless `WorkspaceView`, real frames, 2026-10-03)
A real `claude_desk` widget, a widget of eight buttons and a plain label, each
at two placed sizes, zoomed through 1.0 -> 0.03 with the event loop pumped
after each step; frame size compared with the placed size:
- **General, not Claude-Desk-specific.** At low zoom *every* kind regrew: e.g.
  a 300x200 label became 390x298 at 0.12 (greeked) and 463x355 at 0.06; eight
  buttons at 480x560 became 907x560 at 0.25 (title_only). The `title_only` /
  `greeked` degrade tiers were chosen correctly -- the frame was simply being
  resized afterwards.
- **Claude (Desk) additionally regrew at 100% zoom**: its content minimum was
  ~620px wide in a 480px frame (the top row had accumulated status, queue,
  rate-limit, stale and context labels, two combos and three buttons through
  recent TODOs), so the frame grew 480 -> 621 immediately on placement.

## Classification
A **gap in TODO `33d3e8d`'s fix**, not a regression: `SetNoConstraint` plus one
deferred `_reassert_size` stopped the layout from resizing the frame itself but
not the proxy embedding, which grows the proxy to the widget's *derived*
minimum size -- the largest minimum over *all* `QStackedLayout` pages (the
hidden normal page counts while greeked, and its counter-scaled chrome is huge
in local units at low zoom) plus the content's minimum. Confirmed by the fix:
setting an explicit `setMinimumSize(1, 1)` on `WidgetFrame` makes all six cases
stable, with no other change.

## Changes
- `src/desk/shell/widget_frame.py`: explicit 1x1 minimum (documented in place).
- `widgets/claude_desk/widget.py`: the top row is split into two rows (controls
  above, indicators and panel toggles below); content minimum width 387px
  (was ~620) so the default 480px frame needs no clipping.
- `tests/verify/verify_widget_frame_low_zoom_size.py` (new), `LEARNINGS.md`,
  `design-docs/widget-ux.md`, `TODO.md`.

## Tradeoff
A widget can now be dragged smaller than its content's minimum and the content
clips instead of the frame refusing; the real floors are `WorkspaceView`'s own
resize-drag clamps. That matches `33d3e8d`'s stated goal of being able to shrink
widgets small on screen.

## Verification
The regression script reproduces the repro above for three widget kinds, two
sizes and six zoom levels (all fail without the fix), and asserts the Claude
(Desk) widget's minimum width fits its default size.
