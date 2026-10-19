# Non-blocking .gitignore prompts as Desk notifications (TODO `0593797`)

## Summary

Source: `../FEEDBACK/FEEDBACK-DESK-install-job-guibridge-timeout-during-concurrent-session-2026-10-19-1108.md`.
`DeskWindow.install_job` runs inside `GuiBridge.call` (5s timeout) and, at its end, calls
`ensure_installed_jobs_gitignore_entry`, whose `ask` is a blocking `QMessageBox.question`. If the
user doesn't answer within 5s, `desk_install_job` fails with "GuiBridge: GUI thread did not
respond in time" while the dialog stays open (and retries stack more dialogs). More generally, a
modal dialog is the wrong tool for "should I update .gitignore?" -- the user should follow up at
their own pace.

Replace the two *conditional* `.gitignore` questions (`desk_widgets/**/.build/` and
`desk-installed-jobs/**/target/`) with a new kind of Desk notification: text "Update .gitignore?",
buttons **Yes**, **More info** and the existing **✕** (dismiss). The banner is wider/taller than
ordinary ones so the buttons stay usable. Nothing blocks; "Yes" performs the edit.

Out of scope: the `.desk_temp` provisioning prompts in `TempUiManager.provision` (create-dir and
its `.gitignore` entry); they are startup/new-desk consent flows, not on a bridged call.

## Affected files

- `src/desk/temp_ui.py` -- factor the two near-identical `ensure_*_gitignore_entry` bodies into a
  shared helper plus `*_pending(directory)` predicates (no ask, no write). `ensure_*` keep their
  signatures.
- `src/desk/shell/temp_ui_notifications.py` -- `_NotificationBanner` gains optional `detail` text
  and action buttons; new `TempUiNotificationStack.notify_prompt(...)`. Body clicks on a prompt
  banner do nothing (only buttons act). "More info" expands the detail text in place.
- `src/desk/shell/canvas.py` -- `WorkspaceView.notify_temp_ui_prompt` passthrough.
- `src/desk/shell/window.py` -- `_offer_gitignore_entry(kind)`; replace the four `ensure_*` call
  sites (`_provision_temp_ui` x2, promotion, `install_job`) with it. Dedup key per kind, so
  repeated installs replace rather than stack.
- `tests/verify/verify_gitignore_notification.py`; design-docs note.

## Steps

1. Refactor temp_ui.py helpers; keep existing verify scripts green.
2. Banner/stack prompt support.
3. Window wiring: if pending, show prompt; Yes calls `ensure_*(dir, lambda: True)`, closes banner.
4. Verify: no QMessageBox on `install_job`; pending predicate; Yes writes entry; dismiss doesn't;
   More info toggles detail; repeated offers dedup.

## Decisions

- "More info" is non-modal (expands detail in the banner) so it can't reintroduce blocking.
- Install still succeeds immediately; the notification is a follow-up.
