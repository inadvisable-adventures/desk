# Fix file-watcher schedule/dispatch lock-ordering deadlock (TODO `c4d79f0`)

## Summary

The user reported Desk hanging on launch: the process starts (icon
shows in cmd-tab), no window ever paints, and it never recovers --
only Ctrl+C in the terminal breaks it. The interrupted traceback lands
at `desk_services/file_watcher/service.py:113` (`FileWatcherService.
watch()`, called via `DeskWindow.__init__` -> `_provision_temp_ui` ->
`_ensure_questions_watcher`), blocked acquiring watchdog's own
`BaseObserver._lock` inside `self._observer.schedule(...)`. A crash
log matching the pasted trace exactly is already sitting in
`.desk_temp/DESK-CRASH-2026-08-06T14-29-15.log`, confirming this is
the real, reproduced failure, not a one-off.

Root cause: a lock-ordering (AB-BA) deadlock between our own
`FileWatcherService._lock` and watchdog's internal `BaseObserver.
_lock`.

- `FileWatcherService.watch()` acquires **our** lock, then -- for a
  brand-new key -- calls `self._observer.schedule(...)`, which
  acquires **watchdog's** lock. Order: ours -> theirs.
- Watchdog's own dispatch thread (`BaseObserver.dispatch_events`)
  acquires **watchdog's** lock first (wrapping the whole per-event
  handler loop), then calls `handler.dispatch(event)` ->
  `_NormalizingHandler.on_any_event` -> our `_dispatch()`, which
  acquires **our** lock to copy the subscriber list. Order: theirs ->
  ours.

If thread A is mid-`watch()` (holding ours, about to request theirs)
at the exact moment thread B (watchdog's dispatch thread) is
mid-`dispatch_events` for some *other*, already-scheduled key (holding
theirs, about to request ours), both threads block forever. This isn't
a rare timing fluke -- it's the ordinary shape of Desk's startup:
`DeskWindow.__init__` already has other watches active (widget
directories, `TempUiManager`) before `_ensure_questions_watcher()`
schedules the Questions-file watch, and `_provision_temp_ui` is
actively writing files into `.desk_temp` around the same moment,
which is exactly what fires a dispatch on an existing watch.

## Affected files

- `src/desk_services/file_watcher/service.py` -- `FileWatcherService.
  watch()`, the only place that calls `self._observer.schedule(...)`
  while holding `self._lock`. (`_unsubscribe` already calls
  `self._observer.unschedule(...)` *outside* the lock -- that half is
  already correct and needs no change.)
- `tests/verify/verify_file_watcher.py` -- add a deterministic
  regression repro.

## Design decisions

- **Fix on our side, not watchdog's.** We don't control watchdog's
  internals, and its own locking (dispatch holds its lock across the
  full per-event handler loop) is reasonable on its own terms. The fix
  is to never hold *our* lock while calling into watchdog's `schedule`
  -- that's the only ours-then-theirs acquisition anywhere in this
  file, and removing it leaves only theirs-then-ours (during dispatch),
  which is safe.
- **Restructure `watch()` to release our lock before calling
  `schedule()`, with a re-check on the way back in** rather than a
  broader rewrite (e.g. a queue/executor for all observer calls):
  smallest change that removes the specific ours-then-theirs
  acquisition, matches this file's existing style (`_unsubscribe`
  already uses exactly this "compute under the lock, act on the
  observer outside the lock" shape).
  - Under the lock: check whether this `key` is new (`key not in
    self._subscribers`) and append the callback to `self._subscribers
    [key]` (creating the list if needed). Only the *first* caller for
    a brand-new key observes `is_new = True` -- callers racing on the
    same new key serialize through this same lock, so there's no
    double-`schedule()` risk.
  - Outside the lock (only when `is_new`): call `self._observer.
    schedule(...)`.
  - Re-acquire the lock to store the resulting `ObservedWatch` into
    `self._observed_watches[key]` -- but only if `key` is still present
    in `self._subscribers` (i.e. nobody cancelled every subscriber for
    it while `schedule()` was in flight). If it's gone, call `self.
    _observer.unschedule(watch)` immediately instead of storing it, so
    an unlucky watch-then-immediately-cancel-before-schedule-returns
    sequence can't leak a native FSEvents watch with nothing left to
    ever unschedule it.
- **No change to `_dispatch`/`_unsubscribe`.** Both already do the
  minimal-lock-hold-time pattern this fix brings to `watch()`;
  `_dispatch` in particular already releases the lock before invoking
  any subscriber callback, which is unrelated to (and not a
  contributor to) this deadlock.

## Step-by-step implementation

1. Rewrite `FileWatcherService.watch()` per the Design decisions above.
2. Add a docstring note on `watch()` explaining *why* the lock is
   dropped before calling `schedule()` (non-obvious -- the reason lives
   in how watchdog's own dispatch thread re-enters this class).
3. Add a deterministic regression repro to `tests/verify/
   verify_file_watcher.py`: force the exact interleaving (thread A
   holds `svc._lock` directly, thread B is driven into `_dispatch`
   -- via a real filesystem event on an already-watched key -- so it
   blocks trying to acquire `svc._lock`, then thread A calls `svc.
   _observer.schedule(...)` directly) and assert it completes within a
   generous timeout via a background thread + `join(timeout=...)`,
   rather than hanging the test suite itself if the fix regresses.
4. Add a `LEARNINGS.md` entry: watchdog's dispatch thread re-enters
   caller code (event-handler callbacks) *while holding its own
   internal lock*, so any lock a caller's `schedule()`-time code holds
   must never nest inside that call.
5. Run the full `tests/verify/` suite.

## Key tradeoffs

- The re-check-after-schedule pattern narrows the leak window (watch
  cancelled while `schedule()` was in flight) to essentially zero, but
  doesn't eliminate every theoretical concurrent-`watch()`-for-the-
  same-key-while-a-schedule-is-in-flight-and-being-cancelled edge case
  (three-way race). That residual case was already outside what the
  pre-fix code guaranteed too, isn't the reported bug, and isn't worth
  a more invasive redesign (e.g. per-key condition variables) to close.

## Verification

New test in `tests/verify/verify_file_watcher.py`,
`test_watch_during_dispatch_does_not_deadlock`:
- Real `FileWatcherService`, real filesystem, real watchdog `Observer`
  (no mocking).
- Establishes watch #1 on a temp dir.
- Forces the exact interleaving described in the deadlock analysis
  above (thread A holds `svc._lock` directly; a real filesystem event
  drives watchdog's dispatch thread into `_dispatch`, which blocks on
  `svc._lock`; thread A then calls `svc._observer.schedule(...)`
  directly, which blocks on watchdog's lock) and asserts, via a
  background thread joined with a timeout, that this resolves instead
  of hanging forever.
- Existing `test_dedup_and_fanout` and `test_nested_path_collision_fixed`
  continue to pass unmodified -- confirms the fix doesn't change
  normal (non-racing) `watch()`/`cancel()` behavior.
- Full `tests/verify/` regression suite.
