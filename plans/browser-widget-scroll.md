# Browser widget: scroll wheel scrolls the page instead of zooming the canvas (COMPLETED)

TODO `c44e88f`.

## Investigation

`WorkspaceView.wheelEvent` (`src/desk/shell/canvas.py`) treats a wheel
event as a canvas zoom *unless* `_scrollable_at(pos)` says the cursor is
over an embedded widget that should scroll its own content. That helper
walks up from `frame.childAt(point)` looking for a `QAbstractScrollArea`
ancestor — which every "normal" scrollable Qt widget (QListWidget,
QTextEdit, QScrollArea, …) is built on.

But `QWebEngineView` is **not** a `QAbstractScrollArea` — it's a plain
`QWidget` wrapping a native compositor. Probed directly against a real
embedded browser widget: the parent chain over the web view is `QWidget
→ QWebEngineView → BrowserWidget → WidgetFrame`, with no scroll area in
it, so `_scrollable_at` returns `False` and every wheel event over the
page is eaten as a canvas zoom — the reported "scroll wheel doesn't work
in browser widget".

## Fix

Extend `_scrollable_at`'s ancestor check to also treat a `QWebEngineView`
as scrollable: `isinstance(child, (QAbstractScrollArea, QWebEngineView))`.
`QWebEngineView` is in the walk-up chain (confirmed), so this makes wheel
events over a web view get forwarded via `super().wheelEvent(event)` to
the embedded widget (the page scrolls its own content) instead of
zooming the canvas. This also correctly covers `kind:"html"` widgets
(`ChromiumWidget`, also a `QWebEngineView`) whose pages have scrollable
content.

### Re-entrancy guard (discovered during verification)

Forwarding the wheel to a `QWebEngineView` intermittently crashed with
`RecursionError`. `QtWebEngine` bounces an *unconsumed* wheel event (a
non-scrollable page, or one at its scroll limit) back up the parent
chain, which synchronously re-enters `wheelEvent` while the original
`super().wheelEvent()` is still on the stack → re-forward → bounce →
infinite recursion (timing-dependent, hence intermittent). Fixed with a
`self._forwarding_wheel` guard: set it around the `super().wheelEvent()`
forward, and if `wheelEvent` is re-entered while it's set, return
immediately (don't re-forward, and don't zoom on a bounce-back either).
See the new `LEARNINGS.md` entry.

## Affected files

- `src/desk/shell/canvas.py` — import `QWebEngineView`; add it to the
  `isinstance` check in `_scrollable_at`; add the `_forwarding_wheel`
  re-entrancy guard in `wheelEvent`.
- `LEARNINGS.md` — the `QWebEngineView` wheel-bounce recursion entry.

## Verification

Headless, against a real `WorkspaceView` with a real embedded browser
widget (as in the probe):
- `_scrollable_at` returns `True` for a point over the browser widget's
  `QWebEngineView` (it returned `False` before the fix).
- `wheelEvent` at that point forwards to the scene (does **not** change
  the canvas zoom) — assert `self._scale` is unchanged after delivering
  a synthetic wheel event over the web view, whereas a wheel event over
  empty canvas still zooms.
- The re-entrancy guard: with `_forwarding_wheel` forced True, a wheel
  over the web view returns immediately (no zoom, no recursion).
- Regression: `_scrollable_at` still returns `True` over a genuinely
  scrollable `QAbstractScrollArea` widget (a `QListWidget`) and `False`
  over empty canvas (which still zooms).

Note: actually observing the *page* scroll requires a loaded page with
overflowing content and the native compositor, which the offscreen test
environment can't drive; the fix's mechanism (wheel is forwarded, not
consumed as zoom) is what's verified, mirroring how the existing
scrollable-widget behavior is covered.

## Status

**Completed.** Implemented and verified headlessly (run repeatedly for
stability) as described above, including the re-entrancy guard for the
`RecursionError` found during verification.
