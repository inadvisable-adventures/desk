# Git Status widget (TODO ef77819) (COMPLETED)

## Summary

TODO ef77819: a new `python` widget, "Git Status", showing the current
Desk directory's git status, kept relatively fresh without adding too
much compute burden.

## Design

### Directory resolution

Same pattern as the TODO widget/code editor: `current_context
.get_current_desk_directory()`, then `desk.git_utils.find_git_root()` to
resolve the actual repository root (the Desk directory itself may be a
subdirectory of the repo, or not a repo at all).

### Freshness vs. compute burden: poll on a timer, off the GUI thread, skip redundant redraws

Unlike the TODO widget's single-file watcher or the Temporary UI
feature's directory watcher, "git status changed" has no small, precise
set of paths to watch — almost any change anywhere in the working tree
(or the index, or `HEAD`) can affect it. A `watchdog` recursive
whole-tree watcher would be both complex (matching git's own ignore
rules to avoid firing on every `.git/objects` write) and exactly the
"too much compute burden" the TODO warns against. A plain polling timer
running the real `git status` subprocess is simpler and enough:

- `QTimer(self)` on a fixed interval (`POLL_INTERVAL_MS = 3000` — a few
  seconds is "relatively fresh" for a status display a human is glancing
  at, not a sub-second live feed) calls `_poll()`.
- `_poll()` skips entirely if `not self.isVisible()` — a cheap, direct
  way to cut the compute burden further without added complexity: no
  point running `git status` on a timer for a widget that isn't even
  being looked at (scrolled off-canvas, etc.).
- The actual `git status`/branch subprocess calls run on a background
  `threading.Thread` (daemon), never the GUI thread — same reasoning as
  `widgets/todo/widget.py`'s `_write_and_commit` (a slow/hung `git`
  invocation must never freeze the whole app, caret-blink timer
  included — see LEARNINGS.md). Reports back via a small `QObject`
  -owned `pyqtSignal` relay, the same `_CommitResultRelay`/
  `_FileChangeRelay` shape already established there.
- The result handler only actually rebuilds the displayed list if the
  raw `git status --porcelain=v1` output (and branch name) differ from
  the last poll — skips a pointless widget repaint when nothing changed,
  which on an unchanged repo (the common case between edits) is most
  polls.
- A stale-result guard (`if root != self._root: return`) in case the
  current Desk directory changed while a poll was still in flight.

### Git invocation

- `git -C <root> rev-parse --abbrev-ref HEAD` — current branch name.
- `git -C <root> status --porcelain=v1` — machine-stable status lines
  (`XY path`), not human-oriented `git status` output, which varies by
  git version/locale/config and isn't meant to be parsed.

### UI

- A status label: `"{root} — {branch}"`, or `"Not a git repository."` if
  no root was found, or `"{root} (git status failed)"` if the
  subprocess itself errored (a real but rare case — a corrupt repo, git
  not installed, permissions).
- A `QListWidget` of raw porcelain status lines, one item each verbatim
  (e.g. ` M path/to/file.py`, `?? new_file.py`) — simplest thing that
  actually shows "git status", no icon/color parsing of the XY codes
  beyond what's asked for. A single "Working tree clean" placeholder
  item when there's nothing to show.

## Affected files

- `widgets/git_status/widget.json` (new), `widgets/git_status/widget.py`
  (new).
- `design-docs/architecture.md` (edit) — a new Git Status Widget
  component entry.

## Verification

Entirely headless (`QT_QPA_PLATFORM=offscreen`), against real temp git
repos (`git init`, real commits/working-tree changes) and this project's
own real repo:

1. No current Desk directory / directory not a git repo: shows "Not a
   git repository."; no crash.
2. A real git repo with a clean working tree: shows the repo root,
   correct branch name, and the "Working tree clean" placeholder.
3. A real git repo with actual modified/untracked files: shows the
   correct porcelain status lines.
4. Polling behavior: confirm a second poll with no underlying change
   does *not* rebuild the list (import-level instrumentation counting
   `_populate_list` calls), and a poll *after* a real working-tree change
   does rebuild it with the new status.
5. Confirm `_poll()` is a no-op while the widget isn't visible (`not
   self.isVisible()`), and confirm the git subprocess calls happen off
   the GUI thread (the widget/timer must remain responsive while a poll
   is in flight — same shape as TODO widget's existing verification of
   its own background-thread commits).

## Status

Implemented and verified.

**A real bug was found and fixed during verification, not just at
sign-off**: the very first `_poll()` call, made synchronously at the end
of `__init__`, was silently a no-op every time, because
`self.isVisible()` is always `False` at construction time — a widget
hasn't been parented/shown by whoever placed it yet at the moment its
own constructor runs. This left every freshly-placed Git Status widget
blank until the first `POLL_INTERVAL_MS` timer tick fired. Fixed by
giving `_poll` an `initial: bool = False` parameter, calling
`self._poll(initial=True)` once from `__init__`, and only applying the
`isVisible()` gate when `initial` is `False` — separating "skip this
*later*, timer-driven poll, nobody's looking" from "always run the very
first one." Confirmed directly: constructed a widget pointed at a real
repo and *never called `.show()` on it at all* — the initial poll still
completed and populated real status.

Verified headlessly:

1. No current Desk directory → "Not a git repository.", no crash.
2. A real temp git repo (`git init`, a real commit) with a clean working
   tree → correct root/branch and the "Working tree clean" placeholder.
3. Real modified + untracked files in that repo → correct porcelain
   status lines for both.
4. Instrumented `_populate_list`: a second poll with no underlying
   change makes zero calls to it (confirming the redundant-redraw skip);
   an initial poll (or one after a real change) does call it.
5. `_poll()` while hidden is a no-op (no exception, no stale data
   touched); the fixed initial-poll behavior (above) confirms the
   visibility gate doesn't block the one poll that actually matters at
   construction.
6. Full-app regression: a real `DeskWindow`, `git_status` widget placed,
   `current_context` pointed at this project's own real repository —
   the widget's status label correctly showed this repo's real path and
   current branch. (Note: this specific check used
   `DeskWindow.change_current_desk_directory`, which — as a side effect
   of its own normal behavior, `save_current_desk()` — wrote a stray
   `full_app_gs.desk` file directly into this project's real root
   directory; caught and deleted immediately after the check. `*.desk`
   is gitignored, so it was never at risk of being committed, but a
   dedicated scratch/copy directory should be used instead of a live
   project directory for any future test that exercises Desk-switching
   /directory-changing behavior, to avoid this kind of side effect
   entirely.)
