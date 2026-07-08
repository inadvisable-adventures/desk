# Fix TODO widget item editor caret disappearing (TODO 62e8b05) (COMPLETED)

## Summary

TODO 62e8b05: "Sometimes when editing in the TODO widget's TODO item
editor, the text caret will disappear; sometimes it comes back after a
few seconds and sometimes it doesn't... It might be that other processes
are stealing focus, but that seems unlikely."

Root cause (found by investigation, not focus-stealing): `_git_commit`/
`_write_and_commit` in `widgets/todo/widget.py` run `git` subprocess
calls (`rev-parse`, `add`, `commit`) synchronously, directly on the Qt
GUI thread, both immediately (`_add_item`/`_edit_item`) and from the
60-second debounce timer (`_flush_pending_commit`). `git commit` can
block for an unbounded time — a pre-commit hook, an index/`.git` lock
held by another process, a GPG-signing prompt, etc. — and while it's
blocked, the *entire* Qt event loop is frozen, including
`QPlainTextEdit`'s own internal caret-blink `QTimer`. That exactly
explains the reported symptom: the caret "disappears" (event loop
stalled, blink timer not firing) and "comes back after a few seconds"
once `git` finishes, or "sometimes doesn't" if `git` is genuinely hung.
It isn't real focus loss at all — nothing else is stealing focus; the
whole app is just unresponsive while `git` runs on the one thread Qt
needs.

Fix: move the actual `git` subprocess calls off the GUI thread into a
background thread, reporting the result back via a Qt signal (which Qt
auto-queues onto the GUI thread when emitted from elsewhere). Writing
`TODO.md` to disk stays synchronous (fast, and must stay in strict call
order on the GUI thread so concurrent edits are never applied out of
order).

## Affected files

- `widgets/todo/widget.py` (edit): `_write_and_commit`, `TodoWidget`
  (`__init__`, `_add_item`, `_edit_item`, `_flush_pending_commit`, the
  `destroyed`-triggered teardown flush).
- `LEARNINGS.md` (new entry, added once this is verified — see
  `development-process.md`'s Learnings workflow): the real cause here is
  a case of "a plausible-looking fix would have been wrong" — the bug
  report itself already suspected (and dismissed) focus-stealing, and
  the actual cause (blocking subprocess calls freezing the whole event
  loop, not just the widget) is exactly the kind of non-obvious behavior
  worth recording for a future dev/agent who hits a similar "something
  in the UI seems to freeze/lose responsiveness intermittently" report.

## Design

- **`_GIT_LOCK = threading.Lock()`** (module-level): serializes the
  actual `git` subprocess calls. Without it, two overlapping background
  commits (e.g. the user edits again while a previous commit is still
  slow/hung — plausible, since a hang is exactly this bug's scenario)
  could run `git add`/`git commit` concurrently against the same repo,
  which is unsafe. The lock only ever blocks a background thread, never
  the GUI thread.
- **`_write_and_commit(state, message, on_committed=None) ->
  threading.Thread | None`**: writes the file synchronously (unchanged,
  fast), then starts a daemon background thread that acquires
  `_GIT_LOCK`, calls the existing (unchanged) `_git_commit`, updates
  `state["pending"]`/`state["last_commit_ok"]`, and — if `on_committed`
  was given — calls it with the result. Returns the started thread (or
  `None` if there was no `todo_path` to write), so the one call site that
  still needs synchronous behavior (teardown, below) can `.join()` it
  instead of the function needing a separate "sync vs. async" parameter.
  `on_committed` must be a thread-safe hook — in practice, always a Qt
  signal's `.emit` (Qt automatically queues a cross-thread signal emit
  onto the receiving object's own thread), never something that touches
  a `QWidget` directly from the background thread.
- **`_CommitResultRelay(QObject)`**: a small QObject solely to own a
  `finished = pyqtSignal(bool)` — PyQt signals must live on a `QObject`
  subclass, so this is the minimal vehicle for a background thread to
  report a commit's result back onto the GUI thread safely. `TodoWidget`
  owns one instance (`self._commit_relay`), connected once in
  `__init__` to a new `_on_commit_finished(self, committed: bool) ->
  None` that just calls `self._report_commit_status()` (state was
  already updated by the background thread before it emitted).
- **`_add_item`/`_edit_item`**: after mutating `self._state["items"]`
  and stopping the debounce timer (unchanged), set the status label to
  an interim `"Saving…"`, call `_write_and_commit(self._state, message,
  self._commit_relay.finished.emit)` (fire-and-forget — no longer
  followed by an immediate `_report_commit_status()`, since the result
  isn't known yet), then `self._populate_list()` (unchanged — reflects
  the already-updated in-memory items immediately, independent of
  whether the commit has finished).
- **`_flush_pending_commit`**: same — call `_write_and_commit(self._state,
  REPRIORITIZE_MESSAGE, self._commit_relay.finished.emit)` and drop the
  immediate `_report_commit_status()` call (the existing "Reprioritized
  -- commit pending..." label from `_on_rows_moved` already covers the
  interim state; the final status arrives via `_on_commit_finished`).
- **`destroyed`-triggered teardown flush**: replace the current one-line
  lambda with a small closure that, if `state["pending"]`, calls
  `_write_and_commit(state, REPRIORITIZE_MESSAGE)` (no `on_committed` —
  there is no `self`/relay left to safely call back into after teardown,
  matching the existing constraint documented on this code path) and
  `.join()`s the returned thread. This keeps exit-time behavior exactly
  as before (a bounded, synchronous flush-before-teardown) — only the
  *interactive*, while-the-user-is-typing paths become non-blocking,
  since those are what the reported bug is actually about.
- **Not fixed here (noted, out of scope):** investigation also found a
  weaker second candidate — `_ItemDialog` is parented to `TodoWidget`,
  so if `widgets/todo/widget.py` itself is hot-reloaded while the dialog
  is open, `PythonWidgetHost._rebuild` tearing down the old `TodoWidget`
  would tear down the open dialog with it. This would fully close the
  editor, not just blank the caret, so it doesn't match the reported
  symptom — added to `PARKINGLOT.md` as a separate, unconfirmed
  observation rather than folded into this fix.

## Verification

Headless, using a fake `_git_commit` (monkeypatched) instead of a real
git repo, so timing/ordering can be controlled precisely:

1. **Non-blocking:** monkeypatch `_git_commit` to sleep briefly (e.g.
   0.3s) before returning `True`; call `_write_and_commit(state, "msg",
   callback)` and confirm the call returns in well under the sleep
   duration (proves the git call isn't run on the calling/GUI thread).
2. **Result delivery:** wait for the background thread to finish (join
   the returned `Thread`, or poll with a short sleep), then confirm
   `state["pending"] is False`, `state["last_commit_ok"] is True`, and
   the callback was invoked with `True`.
3. **Serialization:** monkeypatch `_git_commit` with a fake that fails an
   assertion if called while already running (a shared "in progress"
   flag), start two overlapping `_write_and_commit` calls back-to-back,
   join both threads, and confirm neither call ever saw the flag already
   set (i.e. `_GIT_LOCK` prevented real overlap).
4. **Teardown still synchronous:** call the extracted teardown-flush
   closure directly with a slow fake `_git_commit`; confirm it doesn't
   return until the fake commit has actually completed (same blocking
   contract as before — this path is deliberately unchanged).
5. **Regression, full widget:** construct a real `TodoWidget` against a
   temp git repo (real `_git_commit`, not mocked); add an item; confirm
   the list updates immediately (before waiting on the commit) and that
   after a short wait / a few `app.processEvents()` calls, the status
   label reflects a real commit (via `git log`) — mirroring
   `plans/todo-widget-edit-on-doubleclick.md`'s existing verification
   style but now asserting the list update happens without waiting for
   git first.
6. **Regression:** edit an existing item and reprioritize (drag) —
   confirm both still end in a correct commit, same as before.

No step requires a visible window.

## Status

Implemented and verified headlessly, all six steps above passed:

1-4 with a fake `_git_commit` (sleeping, then a shared-flag guard for
   serialization, then confirming the teardown-flush closure still
   blocks synchronously via `.join()`).
5-6 against a real `TodoWidget` + temp git repo: adding an item updates
   the list and shows an interim "Saving…" status immediately, then the
   status updates to reflect a real commit once the background thread's
   Qt-signal callback lands; editing and reprioritizing (a real row swap
   in the `QListWidget`, so the write actually produces a diff) both
   still end in a correct commit.

`LEARNINGS.md` updated with an entry on the general pitfall (a blocking
call anywhere on the Qt GUI thread can produce symptoms that look like
unrelated interference elsewhere, e.g. focus loss) — this was exactly a
case of the bug report's own plausible-looking theory (focus stealing)
being the wrong track.
