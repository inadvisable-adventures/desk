# Widget focus concept + titlebar-click-to-focus

TODOs `397770c` (focus concept) and `a1c701d` (titlebar click focuses
the inner control) -- implemented together since the second is a
direct, small extension of the first's own tracking, in the same
files.

## Summary

- `397770c`: whenever a control *inside* a widget's content has real
  Qt keyboard focus, the enclosing widget itself is considered
  "focused," and its titlebar changes slightly (a lighter background)
  to show that.
- `a1c701d`: clicking (press, then release without dragging) a
  widget's titlebar re-focuses whichever control inside that widget
  most recently had focus (or, if none ever has yet, the widget's
  content container itself) -- a fast way to "activate" a widget
  without having to click precisely into its content.

## Key decisions

- **Driven by one, app-wide `QApplication.focusChanged` connection**,
  wired once in `WorkspaceView.__init__` -- not something every
  individual widget kind needs to opt into or implement itself. A new
  `_enclosing_frame(widget)` helper walks the plain Qt parent-widget
  chain (not `.window()`, which is TODO 10b0321's already-established
  trick for a *different* purpose -- finding the frame from a
  *descendant that already knows it's embedded*; plain `parentWidget()`
  walking is simpler and sufficient here since `content` really is a
  layout-managed child of `WidgetFrame`) up from whatever widget just
  gained/lost focus, to find the enclosing `WidgetFrame` (or `None` if
  the focus change wasn't inside any widget's content at all -- e.g. a
  `QMessageBox`).
- **`WidgetFrame` remembers the single most-recently-focused
  descendant** (`remember_focused_widget`/`_last_focused_widget`),
  updated by that same app-wide handler -- zero changes required to
  any individual widget kind's own implementation. This is what makes
  `a1c701d` trivial once `397770c`'s tracking exists: "re-focus
  whichever control most recently had focus" is just re-reading that
  one remembered reference.
- **Titlebar visual change is a background-color shift** (`#3a3d41`
  unfocused -> `#4a4e54` focused) -- deliberately subtle ("change
  slightly," per the TODO's own wording), not a bold color swap that
  would compete with TODO `ff6514a`'s new default border or read as an
  error/warning state.
- **Click-vs-drag disambiguation reuses the existing titlebar-drag
  press tracking**, extended with a separate `_titlebar_click_frame`/
  `_titlebar_click_pos` pair recorded on *every* titlebar press
  (distinct from `_drag_frame`, which TODO `8d05920` will later stop
  setting for a *locked* widget's titlebar -- tracking the click
  candidate separately means locking a widget won't also break
  clicking it to focus its content, without needing to revisit this
  code again when that lands). On release, if the total mouse
  displacement since press is small (a `TITLEBAR_CLICK_THRESHOLD` of 4
  view-space px, the same "was this basically a click" tolerance shape
  as the existing chrome-button press/release matching), it counts as
  a click and triggers the focus restore; a real drag (or a
  resize-handle press, which never sets the click-candidate pair at
  all) does not.
- **Fallback when nothing was ever focused inside a widget yet**:
  `frame.content.setFocus()` -- not a no-op. Harmless even for widgets
  that don't set an explicit focus proxy (Qt just makes the container
  itself the focus item in that case); correct and useful for widgets
  that do.

## Affected files

- `src/desk/shell/widget_frame.py` -- `_TitleBar.set_focused`,
  `FOCUSED_BACKGROUND_COLOR`/`UNFOCUSED_BACKGROUND_COLOR`;
  `WidgetFrame.set_focused`/`remember_focused_widget`/
  `focus_last_widget`.
- `src/desk/shell/canvas.py` -- `WorkspaceView._on_focus_changed`/
  `_enclosing_frame`, wired to `QApplication.focusChanged` in
  `__init__`; `_titlebar_click_frame`/`_titlebar_click_pos` tracking in
  `mousePressEvent`/`mouseReleaseEvent`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, real
`WidgetFrame`s with a focusable child, e.g. a `QLineEdit`, embedded via
a real `WorkspaceView`/`QGraphicsScene` so the parent-widget chain is
the real one):

- Giving a descendant control focus marks its enclosing frame focused
  (titlebar background changes) and remembers that control; moving
  focus to a *different* frame's descendant un-focuses the first and
  focuses the second; moving focus to something outside any frame
  (e.g. a bare `QLineEdit` with no `WidgetFrame` ancestor) un-focuses
  whichever frame was focused, without focusing anything new.
  `_enclosing_frame` itself is checked directly against a few
  ancestor-chain shapes.
- A synthetic titlebar press+release with near-zero displacement
  re-focuses the frame's remembered last-focused control; the same
  press followed by a release far away (simulating a drag) does not;
  a widget whose content was never previously focused falls back to
  focusing `content` itself.

## Status

Not yet implemented.
