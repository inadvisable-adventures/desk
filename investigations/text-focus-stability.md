# Investigation: text caret jumps out of the box being typed in

**Status:** open. TODOs `b4d99a1` (focus logging in Desk), `00ea6b3` (Focus Logger widget),
`9e74c40` (agent guidance). Nothing has been reproduced or fixed yet; this records what has been
established, what has not, and where to go next. Related, already-fixed: TODO `e69f209` (Tab handing
focus to an unrelated sibling widget); see `LEARNINGS.md`, "Pressing Tab in a
`QGraphicsProxyWidget`-embedded widget can silently hand keyboard focus to an unrelated sibling".

## The report

2026-10-12: "When a widget is too close to another widget, then the text caret sometimes jumps out
of the current text box that it is typing in." Intermittent. Not yet known: which keys or mouse
actions are involved, which widgets, and where the caret ends up (another box in the same widget, a
neighbouring widget, or nowhere).

## What has been done so far

Code reading only (no reproduction, no instrumentation yet):

- `src/desk/shell/canvas.py`: click-to-focus and titlebar-click handling (`focus_last_widget`),
  scene-level focus tracking (`QGraphicsScene.focusItemChanged` -> `_on_scene_focus_item_changed`),
  and canvas-level hit-testing (`_hit_test_chrome`, `_frame_at`, both via `itemAt`, so the topmost
  item at a point wins).
- `src/desk/shell/widget_frame.py`: `focusNextPrevChild` / `_reclaim_focus_if_escaped`, the earlier
  Tab fix.
- No hover, proximity or snapping code that moves focus was found.

## What is established

- Typing ordinary characters into one embedded widget does not by itself move scene focus (shown for
  `QLineEdit` in the TODO `e69f209` work).
- Scene-level focus resolution in a `QGraphicsProxyWidget` happens *after* synchronous handlers for the
  triggering event, so a check made inside an event handler cannot see the real outcome (two
  LEARNINGS entries). Any instrumentation must look one event-loop turn later.
- `QApplication.focusChanged` reports the enclosing `QGraphicsView`, not the embedded widget
  (LEARNINGS, TODO `397770c`); `QGraphicsScene.focusItemChanged` plus the frame's own
  `focusWidget()` is the right level.

## Hypotheses (none confirmed)

1. **Tab escape plus a coarse reclaim.** `_reclaim_focus_if_escaped` refocuses the *first* (Tab) or
   *last* (Shift+Tab) focusable descendant, not the control that was being typed in. In a widget with
   several fields this reads as "the caret jumped out of my box". Only explains Tab/Shift+Tab.
2. **Another key path that escalates to the scene.** Anything that reaches
   `QGraphicsProxyWidget`/`QGraphicsScene` focus navigation other than plain Tab (Backtab,
   Ctrl+Tab, keys a control does not consume).
3. **Mouse near frame edges.** Resize handles, the titlebar and the content of two close or
   overlapping frames compete in `_hit_test_chrome`/`itemAt`; a press (or a titlebar click that
   triggers `focus_last_widget`) may land on the neighbour. "Too close" fits this best, if the report
   involves the mouse at all.
4. **Z-order changes.** `bring_to_front`/`send_to_back` (and eye-button flows) reorder items; scene
   Tab order and hit-testing both depend on item order.
5. **Programmatic `setFocus`.** A widget (or a timer, a state-update handler, a notification) calling
   `setFocus()` on itself or a sibling control while the user types.
6. **GUI-thread stalls** that look like focus loss (the caret stops blinking). Previously the true
   cause of an earlier "disappearing caret" report (LEARNINGS, TODO `62e8b05`). Does not explain a
   caret that moves *elsewhere*.
7. **OS-level window focus** (another application, an IME, a popup `Tool` window; see LEARNINGS on
   windows parented to proxy-embedded widgets).

## Questions for the user

- Keys or mouse when it happens? Only typed letters, or Tab, arrows, Enter, clicking nearby?
- Where does the caret land?
- Which widgets (two Claude (Desk) prompts? Editor next to TODO?), and how close (touching,
  overlapping, a few pixels apart)?
- Does it happen with the neighbour present but never touched, or only after interacting with it?
- Is the Claude (Desk) widget (which updates its own UI while streaming) always involved?

## Plan: instrument, then let the data decide

1. **Focus logging in Desk** (TODO `b4d99a1`): switchable, off by default. Record scene focus changes
   (old/new frame instance ids, focused control class/objectName), the key (identity only, never
   printable characters) and mouse events just before each change, the distance to the nearest
   neighbouring frame, z-order changes, and where cheap, the caller of a programmatic `setFocus`.
   Entries go into a named widget log (`desk.widget_logs`, timestamps in epoch ms).
2. **Focus Logger widget** (TODO `00ea6b3`): starts/stops the logging, shows it live, and follows the
   `recording`/`stopped_recording` events so it runs while the user narrates what they are doing.
   The timecoded transcript then supplies the user's own description of each moment.
3. **Agent guidance** (TODO `9e74c40`): an agent can place the widget for the user, read the log with
   `desk_query_widget_log` and correlate it with the transcript, so the investigation continues
   inside Desk.

## Possible paths after the first data

- If hypothesis 1: make the reclaim target the previously focused control (remember it before
  `super().focusNextPrevChild`) instead of the first/last one; keep a verify script that drives Tab
  through a multi-field widget in a real `QGraphicsProxyWidget`.
- If hypothesis 3: build a headless harness that places two frames at varying gaps and replays
  presses at their edges; consider shrinking or inset resize-handle zones, or giving the top frame's
  chrome priority.
- If hypothesis 5: add a debug hook that records the Python stack for each `setFocus` on a widget in
  the scene (opt-in, via the logger), to find the caller.
- If nothing reproduces: widen the capture (window activation, IME events, `QEvent::FocusIn/Out`
  reasons) and compare against `desk.log` for GUI-thread stalls.
- Whatever the cause, add the finding to `LEARNINGS.md` and the fix's verify script to `tests/verify/`.

## Related

`LEARNINGS.md` (Tab escape, click-to-focus in proxy widgets, `focusChanged` level, GUI-thread
stalls), `design-docs/widget-ux.md`, `plans/agent-widget-command-query.md`, `tempui-widget-logs.md`.
