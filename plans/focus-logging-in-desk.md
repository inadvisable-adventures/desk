# Focus logging inside Desk (TODO b4d99a1)

Part of the text-focus-stability investigation (`investigations/text-focus-stability.md`):
instrument Desk so that when the text caret jumps out of the box being typed in, the data to
explain it exists. Follow-ups: TODO `00ea6b3` (Focus Logger widget), `9e74c40` (agent guidance).

## Summary

A switchable, off-by-default `desk.focus_logger.FocusLogger`, owned by `DeskWindow`, that records
focus-relevant facts as one-line `kind key=value ...` entries into the named widget log
`desk-focus` (`desk.widget_logs.WidgetLogStore`, epoch-ms timestamps), readable by agents with
`desk_query_widget_log`. Reachable by widgets via `current_context.get_focus_logger()`.

## What is recorded

| kind | source | fields |
|---|---|---|
| `session_start` / `session_stop` | `enable()` / `disable()` | `tag` (a recording id, if any) |
| `focus_item` | `QGraphicsScene.focusItemChanged` | `old`, `new` (frame instance ids), `reason`, `widget` (focused control, `Class#objectName`), `gap`/`nbr`/`overlap` of the new frame, `since_input`, `py` |
| `focus_settled` | one event-loop turn later, **only if** the scene's focus item differs from what the signal reported (the "resolved after the event" phenomenon in LEARNINGS) | `new`, `now` |
| `focus_in` / `focus_out` | app-level `FocusIn`/`FocusOut` for any widget inside a frame; the only way to see focus moving *between controls of one widget* (no scene-level signal fires for that) | `frame`, `widget`, `reason`, `from`, `py` |
| `key` | `KeyPress` on the view | `key` (name), `mods`; printable characters are never recorded, only counted |
| `typing` | coalesced printable keys | `n` (count), flushed on a non-printable key, any other entry, or 500 ms idle; stamped with the first key's time |
| `ime` | `InputMethod` events on the view | no content |
| `mouse_press` | `MouseButtonPress` on the viewport | `button`, `frame`, `chrome` (`content`/`titlebar`/`<edge>`/button), `stack` (every frame under the point, front to back), `gap`/`nbr`/`overlap` of the hit frame |
| `bring_to_front` / `send_to_back` | `WorkspaceView` | `frame`, `z` |
| `tab_nav` / `tab_reclaim` | `WidgetFrame.focusNextPrevChild` / `_reclaim_focus_if_escaped` | `frame`, `next`, `escaped`, `target` |
| `focus_last_widget` | titlebar click | `frame`, `target` |
| `app_state` / `focus_window` | `QGuiApplication` signals | `state` / window title |

`gap` is the scene-unit distance from a frame to its nearest neighbour (`0` and `overlap=1` when
they intersect); `nbr` is that neighbour's instance id. `py` is a compact Python call stack
(Desk/widget frames only) taken inside the focus slot: since `focusItemChanged`/`FocusIn` are
delivered synchronously, a programmatic `setFocus()` shows its Python caller there, and `py=native`
means Qt itself (key/mouse handling) caused it. Every entry carries `rec=<tag>` while a tag is set.

## Design decisions

- **Off by default and removable**: all event filters and signal connections exist only while
  enabled. The app-level filter sees every event in the process, so it is quick-rejected by event
  type; overhead is only paid while logging. `DESK_FOCUS_LOG=1` enables it at startup.
- **Printable characters are never logged** (the log is agent-readable): only key identity for
  non-printable keys; printable keys are counted.
- **Qt-level, not Python-wrapper level**: uses `focusItemChanged` and `FocusIn`, per LEARNINGS
  (`QApplication.focusChanged` reports the view, not the embedded control).
- **Small public surface for other modules**: module-level `focus_logger.note(kind, **fields)`
  is a no-op unless a logger is enabled, so `WidgetFrame`/`WorkspaceView` can report their own events
  without importing the logger's owner or paying anything when off.
- **Single shared log name** `desk-focus`; sessions are separated by `session_start`/`session_stop`
  entries and the `rec` tag. The store is in-memory and ring-bounded (10000 entries).

## Affected files

- new `src/desk/focus_logger.py`
- `src/desk/shell/canvas.py` (`chrome_at`, z-order notes), `src/desk/shell/widget_frame.py` (tab and
  focus_last_widget notes)
- `src/desk/shell/current_context.py` (`set/get_focus_logger`), `src/desk/shell/window.py` (owns it)
- `tests/verify/verify_focus_logger.py`, `design-docs/` mention, `LEARNINGS.md` if surprises.

## Not in scope

The widget (TODO `00ea6b3`), agent docs and changelog tag (`9e74c40`; this is not yet agent-visible
because nothing exposes it until the widget exists), any fix of the underlying bug.

## Verification

Headless `verify_focus_logger.py` with a real `WorkspaceView`, two close/overlapping frames and a real
`WidgetLogStore`: off-by-default and fully detached when disabled; scene focus changes; intra-frame
focus moves; Tab through a multi-field widget (`tab_nav`/`tab_reclaim`); typing coalesced with no
characters leaked; mouse press stack and gap; z-order notes; programmatic `py=` stack; `rec` tag.
Real-app interactive use is skipped here (belongs with TODO `00ea6b3`).
