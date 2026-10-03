# Deprecation agent handoff (TODO `18fa45f`) (COMPLETED)

## Summary
Wherever Desk reports a tombstone use, offer the always-available fix paths: a short
command to paste into an agent console, and a "launch an agent console" action that
opens a Claude (Desk) widget already seeded with what to do. Today the command is only
embedded in the error text.

## Affected files
`src/desk/deprecations.py` (`agent_instructions`), `src/desk/shell/window.py`,
`tests/verify/verify_deprecation_agent_handoff.py` (new), `tests/verify/verify_deprecations.py`,
`design-docs/deprecation-process.md`, `TODO.md`.

## Design
- **Where it is offered:** (a) clicking the `[ERROR]` marker a tombstone use lit on a
  placed widget -- the marker remembers the report (`frame.deprecation_report`) and, if
  the message is still the tombstone's (a later different error replaces it), the click
  offers the actions instead of the plain dialog; (b) straight away for frameless usage
  (a tempui file, a manifest). A python hook stays log-only: its own caller is already
  getting the exception, and it has no frame to hang a dialog on.
- **The dialog** (`_ask_deprecation_action`, patchable like the other confirms) shows the
  tombstone message and the command, with three buttons: Copy command, Launch agent
  console, Dismiss. Copy puts the `agent_command` text on the system clipboard.
- **Launch** (`open_deprecation_agent`) mirrors the `[CHAT]` button: a fresh Claude (Desk)
  widget placed just right of the affected widget (view-centered if there is none), with
  its initial instructions written to a file under `.desk_temp` (the existing
  `_write_claude_instructions_file`, which keeps the command line short and apostrophe
  free) -- no scoping, since fixing means editing the widget's source.
- **What the agent is told** (`agent_instructions`): the deprecation id, old API,
  replacement and message **from the registry**, where Desk saw it (widget kind, instance,
  source directory, authored-from path for DefineWidget widgets, the call that tripped it;
  the tempui file and its first line; the manifest path; the python call site), and "find
  the code, switch it to the replacement, check it works -- everything you need is on this
  page, do not go looking for documentation of the old API". It never names the history
  store, so the isolation rules hold.
- The command's `where` is the widget's display name for a placed widget, the file or
  manifest path otherwise.

## Verification
Instruction content and isolation, the three dialog outcomes (clipboard really set, the
agent really placed with the right pieces, dismiss inert), context per surface, the
error-click routing (tombstone vs ordinary error, stale message), and report handling.
