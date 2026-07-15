# UI zoom-scaling audit + "greek" undersized widgets (COMPLETED)

TODO `33d3e8d`.

## Summary

Two parts: (1) an audit confirming every zoom-affected UI element
(widget chrome, screen-space HUD overlays) genuinely stays a constant
on-screen size across zoom, fixing anything that doesn't; (2) a new
titlebar degrade sequence for a widget that's been zoomed out small
enough that its counter-scaled chrome no longer fits its own on-screen
width: full chrome → title-only → "greeked" (a plain colored
rectangle) — plus a click-to-zoom-in-on-it interaction for a greeked
widget, and a new always-present eye-emoji titlebar button that does
the same "zoom/pan so this widget fills the view, 20% margin" action
regardless of chrome state.

## Part 1: Audit

Scope (every screen-space/zoom-affected element in the app, confirmed
via research — see below): `WidgetFrame` chrome (`_TitleBar`'s buttons/
font, `_ResizeHandle`s, the frame border) and the three
viewport-pinned HUD overlays (`ZoomControl`, `DeskPicker`,
`TempUiNotificationStack`). Widget *content* itself is explicitly out
of scope — it's supposed to zoom/pan with the view like everything
else on the canvas; only chrome/HUD are meant to stay constant.

This area already has a long history of dedicated fixes (TODO
`d0d7b37`/`7845a0f`/`82d66c0`/`4adfcad`/`1f9bd34`/`cde51d4`), so the
audit is a real, headless re-verification pass (measuring actual
on-screen sizes at several zoom levels, not just reading the code and
trusting it), not a rewrite — fix anything a fresh check actually
catches, otherwise confirm and move on to Part 2, which is where this
item's real net-new scope is.

## Part 2: Titlebar degrade + greek

### Chrome state

`WidgetFrame` gains a third visual mode alongside its existing content,
tracked as `self._chrome_state ∈ {"full", "title_only", "greeked"}`,
recomputed on every `set_view_scale` call (already fires on every zoom
change: wheel/pinch, HUD slider, `zoom_to_fit`) **and** on the frame's
own `resizeEvent` (a manual resize-handle drag changes on-screen size
too, without any `set_view_scale` call) — both funnel into one
`_update_chrome_state()` using a stored `self._view_scale` (updated
whenever `set_view_scale` runs).

`on_screen_width = self.width() * view_scale`,
`on_screen_height = self.height() * view_scale` (the frame's own local
size times the view's current scale — the same relationship that makes
counter-scaled chrome land at a constant size in the first place).

- **full**: `on_screen_width` fits every currently-relevant button (the
  ones that would actually show — `tempui_promote` only if promotable,
  one of lock/unlock, bring-to-front, send-to-back, close, the new eye
  button) at their fixed on-screen size, plus a minimum readable title
  width.
- **title_only**: doesn't fit full chrome, but `on_screen_width` is
  still ≥ a minimum readable-title threshold and `on_screen_height` is
  still ≥ the titlebar's own constant on-screen height. All action
  buttons hide (`_TitleBar.set_buttons_visible(False)`); the title
  label alone remains.
- **greeked**: neither of the above holds (title itself wouldn't fit,
  or the widget is shorter on screen than one titlebar). The frame
  swaps its visible content entirely — via a `QStackedWidget` (the same
  page-swap shape the Browser widget's own pop-up containment, TODO
  `e35bcf0`, already established) — to a single, plain `QWidget` filled
  with the frame's own border color: no titlebar, no content, nothing
  else rendered. Resize handles are unavailable while greeked (nothing
  to grab, matching "there's no real chrome showing right now"); the
  only way out is zooming/panning it back into view.

Thresholds are computed from real `QFontMetrics`/button-size constants
already used for counter-scaling (`CLOSE_BUTTON_SIZE`,
`TITLEBAR_FONT_PT`, etc.) — measured once at the fixed on-screen pixel
size those constants already target, since that's genuinely what
they'll render as on screen regardless of current zoom (the entire
point of counter-scaling).

### Click-to-zoom-in on a greeked widget

`WorkspaceView._hit_test_chrome` checks `frame.is_greeked` **first**,
before any of its existing child-widget walking (a greeked frame's
titlebar/handles are stacked away, so there's nothing meaningful to
walk into) — a click landing anywhere on a greeked frame's bounds
returns `(frame, "greeked")`, added to `_BUTTON_KINDS`'s dispatch in
`mouseReleaseEvent`, calling a new `WorkspaceView.zoom_to_widget(frame,
margin_fraction=0.2)`.

### The eye button

A new `_TitlebarButton` subclass (👁), added to `_TitleBar` alongside
the existing close/lock/bring-to-front/send-to-back/tempui-promote
buttons — same counter-scaling, same central
`_hit_test_chrome`/`_BUTTON_KINDS`/`mouseReleaseEvent` dispatch pattern
every other button already uses, calling the same
`WorkspaceView.zoom_to_widget(frame, margin_fraction=0.2)` the greeked
-click path uses. Included in the same "does full chrome fit"
button-count calculation as every other button (so it degrades away
along with the rest in `title_only`/`greeked` states — greeked has its
own click-anywhere path instead).

### `zoom_to_widget`

`WorkspaceView.zoom_to_fit()` (whole-scene, 0.1% margin,
`itemsBoundingRect()`) and the new `zoom_to_widget(frame, margin_fraction)`
(one frame's proxy `sceneBoundingRect()`, 20% margin) share their core
"fit this rect with this margin fraction, clamp scale, call
`_on_scale_changed()`" logic via a new private helper (`_fit_rect`) —
avoids duplicating `fitInView`/anchor-juggling/clamping between the two
call sites.

## Affected files

- `src/desk/shell/widget_frame.py` — chrome-state machine, greek
  overlay page, eye button, threshold computation.
- `src/desk/shell/canvas.py` — `_hit_test_chrome`'s greeked-frame
  short-circuit, `_BUTTON_KINDS`, `mouseReleaseEvent` dispatch,
  `_fit_rect` helper, `zoom_to_widget`.
- `design-docs/widget-ux.md` — documents the new degrade sequence and
  `zoom_to_widget`, alongside the existing zoom-correct-chrome section.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, a real `WorkspaceView` +
real placed `WidgetFrame`s — this is fundamentally geometry/rendering
behavior, not something to trust from reading the code alone):

**Audit (Part 1)** — at several real zoom levels (e.g. 0.15x, 0.5x,
1.0x, 2.5x): titlebar height/font, resize-handle thickness, and frame
border thickness all measured as genuinely constant on-screen pixel
sizes; `ZoomControl`/`DeskPicker`/`TempUiNotificationStack` all stay
pinned to their respective corners through pan, zoom, and resize
(regression of the already-fixed behavior). Findings (if any) noted in
Status.

**Greek/degrade (Part 2)**:
- A widget's chrome state transitions correctly full → title_only →
  greeked as it's progressively zoomed out (and back the other way on
  zoom in), both via wheel-zoom and via a manual resize-handle drag
  shrinking it (confirming the `resizeEvent` trigger path, not just
  `set_view_scale`).
- In `title_only`, the title label is visible and every action button
  is hidden; in `greeked`, the stack shows only the plain colored page
  (no titlebar, no content widget reachable at all).
- Clicking anywhere within a greeked frame's bounds triggers
  `zoom_to_widget` (confirmed via the real `_hit_test_chrome` →
  `mouseReleaseEvent` path with synthetic `QMouseEvent`s, not calling
  the method directly) and the view's resulting scale/center actually
  puts that widget's bounds, with a real ~20% margin, inside the
  viewport.
- The eye button hit-tests and dispatches the same `zoom_to_widget`
  action; it's included in (and correctly shrinks) the full-chrome
  width budget.
- `zoom_to_fit` (whole scene, 0.1% margin) is unaffected by the shared
  -helper refactor — regression-checked against its existing behavior.

## Status

Implemented as planned, plus one unplanned but necessary fix.

**Part 1 (audit)**: re-verified headlessly (titlebar height/font,
resize-handle thickness, frame border thickness constant across
0.15x/0.5x/1.0x/2.5x zoom; `ZoomControl`/`DeskPicker`
/`TempUiNotificationStack` stay pinned through pan/zoom_to_fit
/reset_zoom/resize) — everything already held, no fixes needed.

**Part 2 (degrade + greek)**: implemented as planned --
`WidgetFrame.chrome_state ∈ {"full","title_only","greeked"}` recomputed
via `_update_chrome_state()` on both `set_view_scale` and the frame's
own `resizeEvent`; thresholds (`_TitleBar.min_full_width_px()`
/`min_title_only_width_px()`) computed from the same fixed on-screen
constants the counter-scaling itself targets; a `QStackedWidget` swaps
to a plain `BORDER_COLOR`-filled page while greeked; `_EyeButton` added
to the titlebar; `WorkspaceView._hit_test_chrome`'s `is_greeked`
short-circuit plus `_BUTTON_KINDS`/`zoom_to_widget` wire up both the
eye button and click-anywhere-on-a-greeked-widget to the same shared
`_fit_rect` helper `zoom_to_fit` was refactored onto.

**Unplanned fix found during verification**: a real, pre-existing bug
(not introduced by this change — reproduced with only the
already-shipped counter-scaling code, no chrome-state/greek code
involved) where `WidgetFrame`, once embedded via
`QGraphicsProxyWidget`, silently grows itself back up to fit its
layout's inflated minimum size (counter-scaled chrome's *local* sizes
balloon at low `view_scale`) on a deferred, later-processed event —
not synchronously, so a check performed immediately after a zoom
change can pass by accident while the same check fails once the event
loop actually runs. This directly blocked reliable greeking (a
widget's on-screen size would silently balloon back up right as it was
supposed to shrink below the greek threshold). `QLayout
.SetNoConstraint` on `WidgetFrame`'s own top-level layout only
partially fixed it; the full fix mirrors the existing Desk picker/zoom
control HUD-drift fix (TODO `82d66c0`/`4adfcad`/`1f9bd34`): snapshot
the known-good size before scaling, reassert it via
`QTimer.singleShot(0, ...)` after. See `WidgetFrame.set_view_scale`
/`_reassert_size` and the new `LEARNINGS.md` entry.

Verified entirely headlessly (`QT_QPA_PLATFORM=offscreen`, real
`WorkspaceView`/`WidgetFrame`s, synthetic `QMouseEvent`s routed through
the real `mousePressEvent`/`mouseReleaseEvent` handlers, not calling
handlers directly): the audit re-checks above; chrome state transitions
full → title_only → greeked and back via both wheel-zoom
(`set_view_scale`) and a manual resize-handle drag (`resizeEvent`
alone, no `set_view_scale` call); title_only hides every action button
while keeping the title label; greeked shows only the plain colored
page with the titlebar unreachable; clicking anywhere on a greeked
frame and clicking the eye button both trigger `zoom_to_widget` and
land the widget's full bounds inside the viewport with a real ~20%
margin; the eye button is included in (and shrinks) the full-chrome
width budget (confirmed a locked widget's threshold is smaller, since
it excludes bring-to-front/send-to-back/close/eye); `zoom_to_fit` is
unaffected by the `_fit_rect` refactor; a repeated zoom-cycle stress
test (10 changes across 0.1x-4.0x) confirmed the size-reassertion fix
holds stably, not just once; and a full regression of every
pre-existing titlebar button (close, lock/unlock, bring-to-front, send
-to-back, tempui-promote) plus titlebar drag and resize-handle drag,
exercised through the real view-level mouse-event path, confirmed
nothing broke from the `_TitleBar` visibility refactor or the
`WidgetFrame`/`QStackedWidget` restructuring. No step required real
-window/visual inspection.
