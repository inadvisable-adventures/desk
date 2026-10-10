# Transient zoom-gesture snapshot (TODO `19052bc`) (COMPLETED)

Cites `../FEEDBACK/FEEDBACK-DESK-greek-widgets-during-zoom-performance-2026-10-09-1923.md`.

## Summary

During a continuous zoom, frames show a cached pixmap of their content
instead of re-laying-out/repainting the live widget on every scale step;
live content returns once, at the final scale, when the gesture ends.

## Design

- `WidgetFrame` wraps `content` in `_content_stack` (page 0 content, page 1
  `_SnapshotPage`). A separate stack from the existing greek stack: only the
  content swaps, the counter-scaled chrome keeps scaling, and greeking still
  works independently. `begin_zoom_snapshot()` / `end_zoom_snapshot()`.
- `WorkspaceView._begin_zoom_gesture()` from `_apply_zoom` (wheel/pinch) and
  from the slider (`_on_zoom_slider` -> `_apply_zoom_centered(gesture=True)`);
  a single-shot `ZOOM_GESTURE_END_MS` (150 ms) timer, restarted per event,
  ends it. `clear_widgets` ends it.
- Discrete zooms (reset, fit, `set_view_state`) never snapshot: one repaint
  either way.
- The feedback proposed reusing the `greeked` name/page; I used a separate
  inner stack instead so the chrome isn't frozen and the two triggers cannot
  interfere (the feedback left this open).

## Exclusions (the feedback's HUD exception, plus two of mine)

- HUD-pinned frames (`hud_pinned`): the HUD overlay renders live content.
- Already-greeked frames: already the cheapest page.
- **The keyboard-focused frame**: hiding its content drops focus and
  flickers the focused titlebar.
- **Frames with a `QWebEngineView`**: `grab()` of a web view is not reliably
  the real page; they keep paying live cost. Not verified either way
  headless -- a follow-up could test a real web view's `grab()` and drop this
  exclusion (they are the heaviest widgets).

## Low-zoom regrow check (the feedback's warning)

`_SnapshotPage` reports 1x1 `sizeHint`/`minimumSizeHint`; the frame's
explicit `setMinimumSize(1, 1)` (TODO `9585a5a`) stands.
`verify_widget_frame_low_zoom_size.py` still passes.

## Not measured

No timing was done (the feedback reports no observed jank); the benefit is
by construction (no per-step content layout/repaint), not benchmarked.
Snapshot is 1x resolution, so a zoom-in looks soft until the gesture ends.
Not agent-visible, so no tempui changelog tag.

## Verification
`tests/verify/verify_zoom_gesture_snapshot.py` (gesture start/reuse/end,
each exclusion, discrete zooms, slider, wheel path, clear mid-gesture).
