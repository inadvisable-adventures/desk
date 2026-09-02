# Permission-mode selector for the Claude (Desk) widget (TODO `e9eddba`) (COMPLETED)

## Summary

Adds a visible, user-changeable permission-mode dropdown to the Claude
(Desk) widget (`widgets/claude_desk/widget.py`), replacing the
hardcoded `PERMISSION_MODE = "default"` module constant (TODO
`a596dbf`) with a real control -- the same "expose the CLI's own
tradeoff in the UI" reasoning `claude`'s own `--permission-mode` flag
already offers, alongside the existing model combo box.

**Resolves this item's own previously-open design question**
("when can the mode change -- only before `start_session`, or live
mid-session via `ClaudeSDKClient.set_permission_mode`") -- **live**.
The Claude Agent SDK's own `set_permission_mode` is documented and
supported specifically for changing mode mid-conversation (its own
docstring example: default mode during review, then switch to
`acceptEdits` for implementation) -- confirmed directly in the
installed SDK (`claude_agent_sdk/client.py`). Restricting this to
"only before start" would be strictly worse for no real benefit,
given the SDK already makes live switching easy and this widget
already runs one persistent, streaming session per placed instance.

## Affected files

- `src/desk/claude_session.py` -- `ClaudeSession.set_permission_mode`.
- `widgets/claude_desk/widget.py` -- the dropdown itself, wired to both
  the initial `start_session` value and live changes.
- `tests/verify/` -- new coverage.

## Design decisions

- **The real SDK enum, not the user's example labels literally** --
  `claude_agent_sdk.types.PermissionMode` is `Literal["default",
  "acceptEdits", "plan", "bypassPermissions", "dontAsk", "auto"]`; the
  dropdown offers all six, with human-readable labels ("Default",
  "Accept Edits", "Plan", "Bypass Permissions", "Don't Ask", "Auto")
  mapped to the real SDK value, the exact same `(label, value)` tuple
  -list shape `MODEL_CHOICES` already uses for the model combo box.
- **Default selection is `"default"`**, matching the existing constant
  it replaces -- and for the same reason that constant was chosen over
  the plan's original `"auto"` suggestion (TODO `a596dbf`'s own
  comment: `can_use_tool` is consulted reliably under `"default"`, but
  `"auto"` gates inconsistently, and this widget's whole point is a
  real, meaningful approval UI).
- **Live changes go through `ClaudeSession.set_permission_mode`**,
  mirroring `send_prompt`'s exact
  `asyncio.run_coroutine_threadsafe(...)`-onto-`_loop` shape -- a
  no-op if `_loop`/`_client` aren't set yet (no session started, or
  already stopped), so wiring the combo box's `currentIndexChanged`
  unconditionally to call it needs no extra "is a session currently
  live" bookkeeping in the widget itself. A failure (should the SDK
  call raise for some reason) reuses the existing `session_error`
  signal/handler -- a real, worth-surfacing error, not a new channel.
- **No busy-gating** -- the model combo box isn't disabled while a
  turn is in flight either (`_set_busy` never touches it); the
  permission-mode combo follows the same precedent and stays
  interactive throughout.

## Step-by-step implementation

1. `claude_session.py`: `set_permission_mode(self, mode: str) -> None`
   (mirrors `send_prompt`'s guard-then-`run_coroutine_threadsafe`
   shape) and a private `_set_permission_mode(self, mode: str) ->
   None` coroutine (mirrors `_query_and_stream`'s try/except ->
   `session_error` shape) that awaits `self._client.set_permission_mode(mode)`.
2. `widget.py`: `PERMISSION_MODE_CHOICES` (the six `(label, value)`
   pairs above) and `DEFAULT_PERMISSION_MODE_INDEX` (pointing at
   `"default"`), replacing the `PERMISSION_MODE` module constant
   entirely; `self._permission_mode_combo = QComboBox()`, populated
   and added to `top_row` alongside `self._model_combo`;
   `start_session` reads the initial mode from
   `PERMISSION_MODE_CHOICES[self._permission_mode_combo.currentIndex()][1]`
   instead of the removed constant; a new
   `_on_permission_mode_changed(index)` slot calls
   `self._session.set_permission_mode(PERMISSION_MODE_CHOICES[index][1])`,
   connected to the combo's `currentIndexChanged`.
3. New/extended verify coverage (below); run the full `tests/verify/`
   regression suite.

## Key tradeoffs

- No visible confirmation that a live mode change actually took effect
  beyond the absence of an error -- the SDK's own `set_permission_mode`
  returns `None` on success, so there's nothing to display back. If
  this turns out to be confusing in practice, a status-line
  acknowledgement ("Permission mode: acceptEdits") is a small
  follow-up, not designed here.

## Verification

New checks, real (no mocking of the widget/session wiring itself,
though the SDK's own `ClaudeSDKClient` is naturally not exercised
headlessly -- same constraint every existing `claude_desk` test
already works within):
- `tests/verify/verify_claude_desk_widget.py` (extended): the
  permission-mode combo is present alongside the model combo, defaults
  to "Default"; `start_session` passes the currently-selected mode's
  real SDK value (not the label) to `ClaudeSession.start`, for each of
  the six choices; changing the combo's selection calls
  `ClaudeSession.set_permission_mode` with the newly-selected value;
  `ClaudeSession.set_permission_mode` itself is a real no-op (does not
  raise) when called before any session has started.
- Full `tests/verify/` regression suite (whatever the current count
  is as of this item's own implementation -- re-checked at
  completion, since concurrent work has been landing on this file).
