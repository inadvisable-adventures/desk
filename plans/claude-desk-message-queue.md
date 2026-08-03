# Queue messages in the Claude (Desk) widget (TODO `e1f6391`)

## Summary

`ClaudeDeskWidget._set_busy(True)` currently disables `_prompt_input`
and `_send_button` for the entire time a turn is in flight (including
the initial "Connecting..." phase), so anything typed while Claude is
working has nowhere to go — the user has to wait, watching a dead
input box. This plan keeps the prompt input and Send button always
enabled, and instead **queues** a submission made while busy, sending
it automatically (in order) once the current turn finishes, with a
small visible indicator so a queued message doesn't feel like it
vanished.

## Affected files

- `widgets/claude_desk/widget.py` — the only file this touches.
- `tests/verify/verify_claude_desk_widget.py` — new coverage.
- `TODO.md` — mark `e1f6391` `COMPLETED`.

## Design decisions

- **`_prompt_input`/`_send_button` stay enabled while busy.**
  `_set_busy` no longer disables them (it still disables
  `_mic_button` — dictating a *new* message while a turn is in flight
  is unchanged, out of scope here). A new `self._busy: bool` flag
  (set by `_set_busy`) is what `_on_send_clicked` actually checks to
  decide "send now" vs. "queue" — Qt's own `isEnabled()` is no longer
  the signal for this.
- **Send button relabels to "Queue" while busy**, reverting to "Send"
  once idle — a cheap, direct signal that clicking it right now queues
  rather than immediately sends, addressing the "doesn't feel like it
  vanished" half of the request without new chrome.
- **Visible indicator**: a new `self._queue_label` (in the same row as
  `_status_label`/`_model_combo`), hidden when the queue is empty,
  otherwise showing `"Queued: N"` with the full queued text (each
  entry, in order) as its tooltip — avoids needing a whole separate
  list widget for what's meant to be an at-a-glance indicator, while
  still making the actual queued content inspectable, not just a bare
  count.
- **Queued messages also get an immediate `_history` entry**
  (`[queued] <text>`) at submit time, in addition to the normal
  `"> <text>"` entry once actually dispatched — two lines total per
  queued message, slightly redundant, but it keeps `_history` a
  complete, honest timeline (typed -> queued -> sent) without needing
  to locate-and-rewrite an earlier line in a `QPlainTextEdit` (which
  has no cheap "replace this specific prior line" operation).
- **Auto-drain only on a *successful* turn completion, not a session
  error.** `_on_turn_complete` drains the next queued message (if any)
  instead of going idle; `_on_session_error` does not — a session
  error might mean the session itself is in a bad state, and blindly
  firing the next queued message right after risks compounding
  confusion. Remaining queued messages stay visible (via
  `_queue_label`) but frozen until the user does something themselves;
  no auto-retry/flush mechanism is added for this first pass.
- **The resume-with-nothing-to-send path must drain the queue too.**
  `start_session`'s existing `self._session.connected.connect(lambda:
  self._set_busy(False))` (for a restored widget with no initial
  prompt) needs the same "drain the queue instead of going idle"
  treatment `_on_turn_complete` gets, or a message queued during the
  "Connecting..." phase of a *resumed* session would sit forever.
  Both call a shared `_finish_busy_period(idle_status)` helper instead
  of duplicating the drain-or-idle logic.
- **The very first (fresh-launch bootstrap) message is unaffected.**
  It's already sent through `ClaudeSession.start(...,
  initial_prompt=...)`, not `send_prompt`, and that isn't changed here
  — queuing only applies to anything typed after that point.

## Step-by-step implementation

1. Add `self._busy = False`, `self._message_queue: list[str] = []`,
   and `self._queue_label` (hidden by default) to `__init__`.
2. Change `_set_busy` to track `self._busy`, stop disabling
   `_prompt_input`/`_send_button`, and keep disabling `_mic_button`.
3. Add `_send_now(text)` (the current body of `_on_send_clicked`'s
   send path: append `"> text"` to history, `_set_busy(True)`,
   `self._session.send_prompt(text)`) and `_update_queue_label()`.
4. Rewrite `_on_send_clicked` to check `self._busy`: if busy, append
   to `self._message_queue` + a `"[queued] text"` history line +
   `_update_queue_label()`; otherwise call `_send_now(text)` directly.
5. Add `_finish_busy_period(idle_status: str)`: `_set_busy(False)`,
   then if `self._message_queue` is non-empty, pop the first entry and
   call `_send_now` on it (plus refresh the queue label) instead of
   setting the idle status.
6. Update `_on_turn_complete` and the resume-connected lambda in
   `start_session` to call `_finish_busy_period(...)` instead of
   `_set_busy(False)` directly.
7. Update the Send button's text in `_set_busy` ("Queue" vs. "Send").
8. New verify coverage (see below); run the full `tests/verify/` suite.

## Key tradeoffs

- Two history lines per queued message (queued + sent) instead of
  rewriting one in place: simpler and more honest about what actually
  happened, at the cost of some duplication in a busy session.
- No auto-retry after a session error: a real gap for a heavy-queuing
  workflow, but avoids guessing at recovery behavior for a case this
  plan hasn't designed around.
- No re-ordering/removal UI for already-queued messages (e.g.
  "cancel this queued one"): out of scope for this first pass, same
  spirit as the permission-mode selector's "ship the minimum, revisit
  once there's real usage" precedent elsewhere in this widget.

## Verification

New checks in `tests/verify/verify_claude_desk_widget.py`, real
sessions throughout (no mocking):
- Sending a message while a real turn is in flight queues it instead
  of sending immediately (`_session.send_prompt` not called yet,
  `_queue_label` becomes visible, `_history` gets a `[queued]` line)
  and the Send button reads "Queue".
- Once the in-flight turn completes, the queued message is sent
  automatically (an actual second real turn happens), the queue label
  clears, and the Send button reads "Send" again once idle.
- Two messages queued in a row are sent in the order they were
  queued.
- Full `tests/verify/` regression suite.
