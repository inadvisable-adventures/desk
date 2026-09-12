# `[chat]` widget button (TODO `93364f9`) (COMPLETED)

## Summary

A `[chat]` titlebar button on every placed widget instance (not just
certain kinds). Clicking it places a fresh `claude_desk` ("Claude
(Desk)") widget instance, positioned just to the right of the clicked
frame, with a fresh session whose initial prompt orients it to that
specific instance: its live identity (kind/instance_id/title), where
its source lives on disk, its declared manifest, and what shared
state/MCP tools/Installed Jobs infrastructure might be relevant --
so the user doesn't have to explain any of that before the real
discussion starts. Same centralized-chrome-click pattern as every
other titlebar button (`_TempuiPromoteButton`/`_StaleIndicatorButton`/
`_ErrorIndicatorButton`), and a sibling to `_place_discuss_claude_widget`
(which places the older PTY-based `claude` kind, viewport-centered,
with no per-instance context) rather than a reuse of it.

## Affected files

- `src/desk/shell/widget_frame.py` -- new `_ChatButton`; wired into
  `_TitleBar.__init__`/`_refresh_button_visibility`/
  `_visible_button_widgets_for_full_state`/`_button_target_width`/
  `apply_scale`.
- `src/desk/shell/canvas.py` -- `_ChatButton` import; `"chat"` (and the
  already-missing `"error"`) added to `_BUTTON_KINDS`; `_hit_test_chrome`
  handles `_ChatButton`; new `chat_button_clicked` signal;
  `mouseReleaseEvent` dispatches it.
- `src/desk/shell/window.py` -- connect the new signal;
  `_on_chat_button_clicked`, `_place_widget_chat_about`,
  `_build_widget_chat_instructions`; generalize
  `_write_discuss_instructions_file` into `_write_claude_instructions_file(body, prefix)`.
- `tests/verify/verify_widget_chat_button.py` (new).

## Implementation approach

1. **`src/desk/shell/widget_frame.py`**
   - `_ChatButton(QWidget)`: same shape as `_TempuiPromoteButton`
     (widget_frame.py:162-190) -- `QHBoxLayout` with
     `TEMPUI_BUTTON_MARGIN`, a non-selectable `QLabel("[CHAT]")`,
     pointing-hand cursor, tooltip "Start a new Claude (Desk) session
     to discuss this widget instance.", `apply_scale` matching the
     others (standard `#e8e8e8` label color, not `_ErrorIndicatorButton`'s
     red).
   - `_TitleBar.__init__`: `self.chat_button = _ChatButton()` +
     `layout.addWidget(...)`, right after `error_button`, before
     `lock_button`.
   - `_refresh_button_visibility`: popup branch ->
     `self.chat_button.setVisible(False)`; normal branch ->
     `self.chat_button.setVisible(show and not self._locked)`, grouped
     with lock/bring-to-front/send-to-back/close (i.e. it collapses
     while locked or title_only-degraded, same as those, unlike the
     eye button's own always-on exception).
   - `_visible_button_widgets_for_full_state`: add `self.chat_button`
     into the non-locked `else` branch list (alongside lock/bring/
     send/close/eye) so degrade-width math accounts for it.
   - `_button_target_width`'s `text_by_type` map: add
     `_ChatButton: "[CHAT]"`.
   - `apply_scale`: add `self.chat_button.apply_scale(view_scale)`.

2. **`src/desk/shell/canvas.py`**
   - Import `_ChatButton` alongside the other chrome-button imports.
   - `_BUTTON_KINDS`: add `"chat"`. Also add `"error"`, which was
     missing even though `_hit_test_chrome` returns it and
     `mouseReleaseEvent` has a real `elif kind == "error":` branch --
     without it in `_BUTTON_KINDS`, `mousePressEvent` never treated an
     `[ERROR]` press as a button-click in the first place (it fell
     through to the generic drag path). Pre-existing bug, fixed here
     since it's a one-line addition to the exact set this item already
     touches.
   - `_hit_test_chrome`: add `_ChatButton` to the walk-up isinstance
     tuple; `if isinstance(child, _ChatButton): return frame, "chat"`.
   - New signal: `chat_button_clicked = pyqtSignal(WidgetFrame)  # TODO 93364f9`,
     next to `widget_stale_clicked`/`widget_error_clicked`.
   - `mouseReleaseEvent`: `elif kind == "chat": self.chat_button_clicked.emit(frame)`.

3. **`src/desk/shell/window.py`**
   - Connect: `self.view.chat_button_clicked.connect(self._on_chat_button_clicked)`,
     next to the other `self.view.*_clicked.connect(...)` calls.
   - `_on_chat_button_clicked(self, frame: WidgetFrame) -> None`:
     `widget_info = self._widgets.get(frame.content.widget_id)`
     (`.widget_id` is exposed directly by both `PythonWidgetHost` and
     `ChromiumWidget`, no isinstance check needed -- same as
     `_refresh_stale_indicators_for`'s own unchecked access); if found,
     `self._place_widget_chat_about(frame, widget_info)`.
   - `_place_widget_chat_about(self, frame: WidgetFrame, widget_info: WidgetInfo) -> WidgetFrame | None`:
     - `widget = self._widgets.get(CLAUDE_DESK_WIDGET_ID)`; `None` ->
       return `None`.
     - Position: `proxy = frame.graphicsProxyWidget()`; if not `None`,
       `rect = proxy.sceneBoundingRect()`, `pos = (rect.right() + 24, rect.top())`;
       else fall back to `self.view.mapToScene(self.view.viewport().rect().center())`
       (same fallback shape `_place_discuss_claude_widget` always uses).
     - `extra_instructions = self._write_claude_instructions_file(self._build_widget_chat_instructions(frame, widget_info), prefix="chat")`.
     - `return self._place_widget(CLAUDE_DESK_WIDGET_ID, widget, pos, widget.default_size, claude_extra_instructions=extra_instructions)`.
     - No `instance_id`/dedup -- same "always independent, fresh
       session" choice `start_discussion` already made (no natural
       stable identity to dedup a button click against).
   - Generalize `_write_discuss_instructions_file(self, body)` into
     `_write_claude_instructions_file(self, body: str, prefix: str) -> str`:
     identical body, except the temp filename becomes
     `f"{prefix}-instructions-{uuid.uuid4().hex}.md"`. Update
     `_place_discuss_claude_widget`'s call site to pass
     `prefix="discuss"`.
   - `_build_widget_chat_instructions(self, frame: WidgetFrame, widget_info: WidgetInfo) -> str`:
     composes the prompt body with four sections -- the live instance
     (kind/name/instance_id/title, plus a pointer to the
     `desk_list_widget_instances` MCP tool for this instance's
     *current* position/size/per-instance state, since those can
     change after the note is written), the code (manifest + entry
     paths, project-relative, resolved from `widget_info.path`/`.entry`
     directly rather than left for the new session to guess), the
     definition/shared state (declared `capabilities`, plus an accurate
     note that the desk-wide `desk.state.*` store is available to any
     widget regardless of the capabilities list -- confirmed by reading
     `get_state`/`set_state`/`_check_schema_conflict` that nothing gates
     it on a capability today, correcting the TODO's own draft
     assumption -- and where to look for a relevant schema:
     `./desk-schemas/`/`.desk_temp/schemas/`), and the tools available in
     this session (the `desk` MCP server's tool list, including
     `desk_install_job`/`desk_run_installed_job` in case this widget's
     behavior is backed by an Installed Job). Trailing instruction:
     have the discussion here rather than starting another new Desk
     discussion of its own, mirroring `_place_discuss_claude_widget`'s
     own trailing instruction.

## Key design decisions

- **New placement helper, not a reuse of `_place_discuss_claude_widget`.**
  That helper is hardcoded to the older PTY-based `claude` widget kind
  and centers on the viewport with no per-instance context -- neither
  fits a button meant to open a *scoped* conversation about one
  specific already-placed instance.
- **Always visible, on every widget kind, but collapses under the same
  conditions as the other action buttons** (locked, or title_only/
  greeked chrome degrade) -- resolves the TODO's "every widget or only
  certain kinds" question per explicit user confirmation.
- **No dedup / no stable instance_id tied to the source widget.** Each
  click opens an independent, fresh session, matching
  `start_discussion`'s existing precedent for the same reason.
- **Corrects a stale assumption in the TODO's own text**: `desk.state.*`
  access isn't gated by a widget's declared `capabilities` (nothing
  today declares a `"state"` capability, and the store isn't
  capability-checked at all) -- the generated instructions describe
  this accurately instead of repeating the outdated assumption.
- **Fixed the adjacent `_BUTTON_KINDS` missing-`"error"` bug** while
  touching that exact set, rather than leaving a newly-noticed,
  trivially-fixable bug in place.

## Verification

New `tests/verify/verify_widget_chat_button.py`, headless
(`QT_QPA_PLATFORM=offscreen`), following `verify_widget_error_indicator.py`'s
`_FakeWindow` harness for chrome/dispatch coverage and
`verify_claude_desk_titlebar_session_id.py`'s `_FakeSession` (no live
API/network calls) for the placement/prompt coverage:

1. `[CHAT]` shows on a fresh, unlocked, non-popup titlebar; hides while
   locked; hides when `_buttons_hidden` (title_only degrade) is set;
   never shows on a popup titlebar.
2. `"chat"` and `"error"` are in `_BUTTON_KINDS`; `_hit_test_chrome`
   returns `(frame, "chat")` for a synthetic click on the button, which
   results in `WorkspaceView.chat_button_clicked` firing with that
   frame.
3. Driving `DeskWindow._on_chat_button_clicked` on a frame wrapping an
   ordinary widget instance places a new `claude_desk` frame positioned
   to the right of the source frame, writes a
   `.desk_temp/chat-instructions-*.md` file whose contents include the
   source widget's kind, instance_id, title, manifest path, and entry
   path, and passes a pointer instruction through to
   `_FakeSession.start_calls`'s `initial_prompt`.

Run with `QT_QPA_PLATFORM=offscreen python3 tests/verify/verify_widget_chat_button.py`
from the repo root, then the full `tests/verify/` suite. The live
end-to-end experience (click `[CHAT]`, confirm a real Claude (Desk)
session opens and behaves sensibly) needs the real GUI + live Claude
API; noted here as manually-skipped per this project's own process,
same as every other `disabled_verify_*_claude_api.py` split-out case.
