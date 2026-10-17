# Investigation: text caret jumps out of the box being typed in

**Status:** open; focus logging (TODO `b4d99a1`) and the Focus Logger widget (TODO `00ea6b3`) both
exist and work end-to-end (see "Update" sections below). Two live sessions with the widget (one
narrated/recorded, one targeted at hypothesis 5) produced no repro, and the plan became: leave the
Focus Logger widget placed but idle and switch it on if the bug recurred during ordinary use. **It
did, on 2026-10-16, in another project (`ae_samothrace`), and was captured** -- see the third
"Update" section at the end: scene focus is being reassigned by something inside Qt itself (no Desk
Python frame on the stack, tagged `MouseFocusReason` with no mouse press), apparently when a frame
has a close neighbour whose widget updates on its own schedule. The cause is not yet isolated;
TODO `48fd3e0` adds the instrumentation (distinguish Qt-internal from input-driven, record the
events and repaints just before each focus change) to settle it. TODOs `b4d99a1` (focus logging in
Desk), `00ea6b3` (Focus Logger widget), `9e74c40` (agent guidance, still open), `48fd3e0` (cause
attribution). Nothing has been fixed yet; this records what has been established, what has not,
and where to go next. Related, already-fixed: TODO `e69f209` (Tab handing
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

- Keys or mouse when it happens? Only typed letters, or Tab, arrows, Enter, clicking nearby? --
  **Answered 2026-10-13: just typing plain letters. No Tab, no mouse.** Weakens hypothesis 1
  (Tab-escape reclaim) and hypothesis 3 (mouse hit-testing near frame edges) as the cause.
- Where does the caret land? -- still open.
- Which widgets (two Claude (Desk) prompts? Editor next to TODO?), and how close (touching,
  overlapping, a few pixels apart)? -- **Answered 2026-10-13: not restricted to one pair or even
  one widget *kind* -- "possibly any widget with a text box"; confirmed with Claude (Desk) alone
  and with Claude (Desk) next to an HTML widget. Distance "more than a few pixels, maybe as far as
  five mouse-pointer widths" -- i.e. not touching or overlapping,** which rules out any
  hit-testing-region explanation (hypothesis 3/4) at that range.
- Does it happen with the neighbour present but never touched, or only after interacting with it?
  -- still open.
- Is the Claude (Desk) widget (which updates its own UI while streaming) always involved? --
  **Partially answered: confirmed involved in at least one case, but not described as required**
  (also reported with Claude (Desk) + an HTML widget, and a general "any text box" suspicion).
  Still consistent with hypothesis 5 if the real trigger is *some* widget's own background UI
  update (not specifically Claude (Desk)'s) stealing focus while another widget is being typed
  into.

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

## Update 2026-10-13: the instrumentation exists

`desk.focus_logger` records the events listed in `plans/focus-logging-in-desk.md` into the
`desk-focus` named log. Two things learned while building it: focus moving between controls
of one widget produces *no* scene-level signal (so it is logged from `FocusIn`/`FocusOut`
instead; LEARNINGS), and a `py=` call stack on each focus entry names the Python code that
requested a change, or shows only input-handling frames when Qt itself did it. That makes
hypothesis 5 (programmatic `setFocus`) directly testable from the first captured jump.

## Update 2026-10-13: first live session, no repro

**Files:** transcript `.desk_temp/timecoded-transcripts/rec-1791938204671-6c44.txt` (recording id
`rec-1791938204671-6c44`, started `2026-10-13T17:36:44.671-07:00`); `desk-focus` log, same window
through `2026-10-13T17:38:06.242-07:00` (62 entries, `rec=rec-1791938204671-6c44` throughout --
the Focus Logger widget auto-started on the `recording` event and auto-stopped on
`stopped_recording`, as designed). Two `scratch` widget instances: `8410bd91` (left/first-placed)
and `f6fb06cc` (right/second-placed).

**What happened, per the log:** the user placed one Scratch widget (`8410bd91`, via the spawn
menu), clicked into it, and typed for a while (`typing`/`key` entries, no anomalies). They then
placed a second Scratch (`f6fb06cc`) and dragged it next to the first until `gap=5.9` scene units
apart (the nearest-neighbour distance logged on the surrounding `focus_item`/`mouse_press`
entries) -- closer than their own "~5 cursor-widths" estimate of when the bug happens, i.e. this
test covered *closer* than the reported trigger distance. They then typed and backspaced
continuously in the left one (`8410bd91`) for about 27 seconds (17:37:34.884 to 17:38:01.903) --
**zero `focus_item`/`focus_in`/`focus_settled` entries fired during that entire stretch.** Every
focus change anywhere in the whole session has a `mouse_press` (or spawn-menu activation) at the
same millisecond and a `py=` stack that bottoms out in ordinary event-loop/mouse-handling frames
(`canvas.py:...:mousePressEvent`, `widget_spawn_menu.py:...`) -- no `tab_nav`/`tab_reclaim` (no
Tab was pressed, consistent with the user's report), and no case of a focus change whose `py=`
stack pointed at something *other* than the input event that caused it (i.e. no programmatic
`setFocus()` from elsewhere fired during this session -- hypothesis 5 untested further than "it
didn't happen this time," not ruled out).

**Reading:** the bug did not reproduce. Plain typing alone, at a distance closer than previously
reported, between two plain `QPlainTextEdit`-backed Scratch widgets, was not sufficient. Candidate
reasons, not yet distinguished: the widget *kind* matters (neither Scratch widget updates its own
UI independently of the user's typing, unlike Claude (Desk) streaming or some HTML widgets'
background refreshes -- this session had nothing else actively updating anywhere on the canvas);
longer exposure is needed; or some other widget needs to be mid-update (hypothesis 5) rather than
merely present and close. Next attempt should pair a widget that updates its own UI on its own
schedule (Claude (Desk) while streaming; any HTML widget that refreshes itself) with the one being
typed into, rather than two otherwise-static widgets.

## Update 2026-10-13: second session (targeted at hypothesis 5), still no repro

Built two disposable `DefineWidget` HTML widgets specifically to test the "something else updates
its own UI on its own schedule" shape of hypothesis 5, independent of a real narrated recording:
source at `.desk_temp/widgets/KeypressPublisher/` and `.desk_temp/widgets/KeypressEchoer/` (not yet
promoted -- still available for a future attempt without rebuilding). `KeypressPublisher` has a
text box and publishes a `focus-probe.keypress` desk event on every keydown; `KeypressEchoer`
subscribes and, ~2s after each event, appends the key to its *own* text box, so it keeps editing
its own content on a timer that's deliberately decoupled from wherever the user is actually
typing.

The user tried several placements of these two plus this Claude (Desk) widget, including typing
directly into this Claude (Desk) instance's own prompt box while the Keypress widgets echoed
nearby. **No repro.** No `desk-focus` data from this round -- the Focus Logger widget stayed off
(by design: the user's plan going forward is to leave it placed but idle, and switch it on
only if the bug actually recurs, rather than logging continuously). The two Keypress widgets are
left placed and un-promoted for whenever a future attempt wants them again.

**Status:** still unreproduced after two sessions, including one aimed squarely at hypothesis 5.
Nothing here rules hypothesis 5 out -- a desk-event round-trip plus `setTimeout` is not the same
code path as whatever Claude (Desk) or a real HTML widget's own refresh logic does internally --
but it's no longer the obvious next thing to try first. Worth reconsidering the hypothesis list
itself (or widening capture, per "Possible paths after the first data" above) before the next
attempt, rather than re-running the same shape of test a third time.

## Update 2026-10-16: third session, first real repro

Reported from `ae_samothrace` (a different project; its Focus Logger widget had been left
placed-but-idle per the plan above, and the user switched it on after noticing the bug recur during
ordinary use -- not a deliberate repro attempt). The write-up and the full raw log are preserved in
`../FEEDBACK/implemented/FEEDBACK-DESK-text-focus-stability-repro-data-2026-10-16-1709.md`
(outside this repo), because the `desk-focus` store is in-memory and ring-bounded and belongs to
that project's running Desk process. **Files:** `desk-focus` log, `2026-10-16T15:23:34.137-07:00`
through `15:27:25.153-07:00` (181 entries, no `rec` tag -- not a narrated session; no timecoded
transcript, the user reported the symptom retroactively and an agent pulled the log with
`desk_query_widget_log`).

**Configuration, unlike either prior attempt:** the neighbours update their own UI on their own
schedule. The focused widget was a `claude_desk` instance (`bf796696`); its nearest neighbour for
most of the window was `SamothraceMap` (`34a5236c`, with its own recording/replay machinery),
`gap` between 0.0 and 96.1 scene units across the session, `overlap=1` at the closest. The two
earlier sessions used two static Scratch widgets, or a synthetic keypress-echo pair decoupled from
any real widget's own internal update path.

**What happened, per the log:** while `bf796696` held real, user-driven focus (15:23:35 to 15:24:48),
scene focus repeatedly and spontaneously flipped to `34a5236c` and back, tagged
`reason=MouseFocusReason`, with **no `mouse_press` entry anywhere nearby** and `since_input` from
93ms up to 14548ms at the moment of the flip. Every one of these flips has a `py=` stack that
bottoms out at `app.py:62:main<__main__.py:6:<module>`, never `canvas.py:...:mousePressEvent`,
which does appear on every click-driven focus change in the same log (e.g. `15:23:35.628`,
`15:23:49.559`). So these flips were not driven by Desk's own mouse handling; something inside Qt's
event processing reassigned scene focus and labelled it a mouse focus change.

The clearest instance was mid-keystroke:

```
15:23:57.189  typing n=1
15:23:57.312  focus_out frame=bf796696 widget=_PromptInput reason=MouseFocusReason
15:23:57.313  focus_in  frame=34a5236c widget=QWidget reason=MouseFocusReason from=_PromptInput py=app.py:62:main<__main__.py:6:<module>
15:23:57.321  focus_item old=bf796696 new=34a5236c reason=MouseFocusReason widget=QWidget since_input=131 py=app.py:62:main<__main__.py:6:<module> gap=0.0 nbr=8c61c442... overlap=1
15:23:57.324  typing n=2
```

123ms after a real keystroke focus left the box being typed in, and the next keystroke landed with
focus already elsewhere. That is the original report ("the text caret sometimes jumps out of the
current text box that it is typing in") with no Tab, click or other hypothesis 1/3/4 trigger,
matching the user's 2026-10-13 answer ("just typing plain letters, no Tab, no mouse").

The same shape recurred later between two other frames (`625702b6` and the Focus Logger widget's own
frame `b14110bd`, `15:26:13.845` to `15:26:16.585`, `gap` 72 to 101, `overlap=0`), so it is not
specific to `SamothraceMap` or `claude_desk`, and not limited to overlapping frames.

**Reading:** strengthens hypothesis 5, refined. It is not "a widget calls `setFocus()` on itself or
a sibling" -- the `py=` stacks hold no Desk or widget frame at all, so it isn't our code calling
`setFocus`. It is "Qt's own focus machinery reassigns the scene's focus item on its own, under
conditions this session satisfied and the two static-widget sessions didn't". The irregular gaps
between flips argue against a simple timer and toward something state- or geometry-dependent: frame
proximity (`gap`/`overlap` is logged on every flip) combined with some widget's own background
repaint (both `claude_desk` and `SamothraceMap` update independently of input) is the leading
candidate, but not proven. Nothing in the current instrumentation shows *which* widget's update
preceded a given flip, only that one happened nearby in time.

Two things the data does not settle:

- **`py=app.py:62:main<...` is ambiguous.** It is the event-loop entry (`main` calling `exec()`), so
  it is what a change with no Python frame involved looks like, but it is also what a change made by
  Qt's C++ handling of an input event looks like. `native` (the value meant to mean "no Python
  frame") never appears in practice because those two frames are always on the stack.
- **Whether the proximity pattern is causal.** Flips mostly occur with `gap=0.0 overlap=1` against
  `34a5236c`, but the 15:25:46 and 15:26:13 flips happened at gaps of 101.3 and 72.2 with
  `overlap=0`.

**Caveats:** the log was read well after the fact, from a project other than this one; no timecoded
transcript backs it.

**Next step (TODO `48fd3e0`, done 2026-10-16):** `py=` now says `native` when nothing but the
event-loop entry is on the stack, and `focus_item`/`focus_in` carry `ev=` (the events dispatched just
before, with receiver class and age) and `painted=` (frames repainted in the last 100 ms). On the
next recurrence, read the flip entries for: `py=native` (Qt alone, no Desk code) vs a Desk frame;
`ev=` naming a `Timer` and whose (a neighbour's own animation timer would point at hypothesis 5's
repaint half); and `painted=` naming the new focus target's frame or a neighbour. A single capture
only shows what preceded a flip, not how often the same thing happens without one -- compare against
the ordinary entries in a longer capture before calling it causal. See
`plans/focus-log-cause-attribution.md`.
