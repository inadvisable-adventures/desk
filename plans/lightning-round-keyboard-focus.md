# COMPLETED: Fix: Lightning Round widget not accepting key-presses (TODO 6cf4543)

## Summary

`LightningRoundWidget` (`widgets/lightning_round/widget.py`) already has
`Qt.FocusPolicy.StrongFocus` and a `keyPressEvent` override, and clicking
directly on an option button or on truly empty space inside the widget
does correctly grab keyboard focus (confirmed headlessly — see
Investigation below). But the most natural place for a user to click —
the prompt/item description text — lands on a `QLabel` child. Qt's
click-to-focus handling only considers the exact child widget under the
cursor; since `QLabel` defaults to `Qt.FocusPolicy.NoFocus` and this is
standard Qt behavior (not specific to being embedded via
`QGraphicsProxyWidget`), the click is silently swallowed for focus
purposes and the parent `LightningRoundWidget` never gains keyboard
focus. Any keys pressed afterward go nowhere, matching the reported
symptom exactly.

Fix: install an event filter on the two persistent labels
(`_prompt_label`, `_item_label`) that grabs focus for the widget itself
on `QEvent.Type.MouseButtonPress`, without swallowing the event (so
existing label behavior, e.g. text selection — currently disabled via
`NoTextInteraction` — is unaffected). This makes clicking *anywhere* on
the widget content reliably enable the keyboard shortcuts, which is the
real fix rather than a discoverability workaround (a "click here to use
keyboard" button was one option raised in the TODO item's own text, but
addressing the root cause is better: it removes the need for the user to
find/click a special affordance at all).

## Investigation (headless reproduction)

Built a real `WorkspaceView`, added a `LightningRoundWidget` via
`add_widget`, and used `QTest.mouseClick`/`QTest.keyClick` against it:

- Click on an option button: works today (the click itself answers, via
  the button's own `clicked` signal — no separate key-press step
  needed).
- Click on empty stretch space within the widget (no child widget at
  that point): `view.scene().focusItem()` becomes the widget's proxy,
  and a subsequent key press correctly answers via `keyPressEvent`.
- Click on the prompt/item `QLabel` text: `view.scene().focusItem()`
  stays `None`, and a subsequent key press does nothing. **This is the
  bug** — and it's also where a user is most likely to click, since
  that's the actual question/item text being read.

## Affected files

- `widgets/lightning_round/widget.py` — add the event filter.

## Implementation

`LightningRoundWidget.__init__` installs an event filter on
`_prompt_label`/`_item_label`; `eventFilter` grabs focus on
`QEvent.Type.MouseButtonPress` for either label, **deferred via
`QTimer.singleShot(0, ...)`** rather than called synchronously.

The synchronous version (`self.setFocus(...)` called directly inside
`eventFilter`) was tried first and confirmed, via the same headless
harness, to silently do nothing: `QGraphicsProxyWidget` resolves which
child widget under the cursor should own scene focus *after* installed
event filters run for that same press, and since the exact child
clicked (the label) is `NoFocus`, that later step clears scene focus
right back — clobbering the filter's synchronous grab. Deferring the
`setFocus()` call to the next event-loop iteration (same
`QTimer.singleShot(0, ...)` pattern already used elsewhere in this
codebase for a same-shaped "something else reasserts state right after
this" problem — see `canvas.py`'s `_position_desk_picker`/
`_position_zoom_control`) lets the grab happen after that clobbering
step instead, and it sticks.

`eventFilter` returns `super().eventFilter(obj, event)` (i.e. does not
consume the event), so the label keeps its normal — currently inert,
`NoTextInteraction` — behavior; this only piggybacks a focus grab on
the same click.

Needs `QEvent` and `QTimer` imported from `PyQt6.QtCore` (previously
only `Qt` was imported there).

## Verification

Headless, via `QTest` against a real `WorkspaceView`/`add_widget`
(a `LightningRoundWidget` is always wrapped in the `WidgetFrame` chrome
in real use, so the harness reproduces that, not a bare unwrapped
widget):

1. **First reproduction attempt was a false lead**: an initial repro
   clicked at a hardcoded content-relative offset that, once the real
   `WidgetFrame` wrapping (28px titlebar) was accounted for, turned out
   to land on the *titlebar chrome*, not the label — `WorkspaceView
   .mousePressEvent`'s `_hit_test_chrome` intercepts titlebar clicks
   for dragging before they ever reach the scene's normal item
   interaction, so that "reproduction" wasn't testing the reported bug
   at all. Corrected by computing the label's real on-screen position
   via `label.mapTo(frame, ...)` plus the proxy's scene position,
   confirmed against `view.itemAt(...)` landing on the proxy.
2. Confirmed the real, previously-broken case with the corrected
   coordinates: click on `_item_label` (and separately `_prompt_label`),
   then a key press, now correctly records an answer.
3. Regression-checked the two already-working cases are unaffected:
   click on empty stretch space then key press; clicking an option
   button directly (answers immediately, no key press needed).
4. Regression-checked that a titlebar click still behaves purely as a
   drag handle (no stray answer recorded) — since this fix touches
   focus handling on the same wrapped widget, worth confirming the
   titlebar-intercept path (unrelated code, `WorkspaceView`'s own hit
   -testing) wasn't accidentally affected.

No browser/visual step applies — this is a native Qt widget, verified
via `QTest` against a real `WorkspaceView`.
