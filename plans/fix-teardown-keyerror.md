# Fix Cmd+Q teardown KeyError (COMPLETED)

TODO `03f623a`.

## Summary

Quitting with Cmd+Q raised `KeyError` from inside
`watchdog.observers.api.Observer.unschedule()`, breaking clean
teardown. Root cause (confirmed by reading `desk/app.py` and
`desk_services/file_watcher/service.py`, matching the reported
traceback exactly): `app.aboutToQuit` slots run synchronously, in
connection order, on the GUI thread -- `get_service().stop()` is
connected last specifically so it runs after other `aboutToQuit`
-connected cleanup, but the TODO widget's (and Questions widget's)
`watcher.stop()` isn't wired to `aboutToQuit` at all. It's inside a
`destroyed`-signal-triggered closure, which only fires *after*
`aboutToQuit` finishes, as part of Qt's own widget-teardown cascade
during actual application shutdown. So by the time that closure calls
`SingleFileWatcher.stop()` -> `WatchHandle.cancel()` ->
`FileWatcherService._unsubscribe()` -> `self._observer.unschedule
(watch)`, the shared `Observer` has already been fully stopped (and
`.join()`-ed) by the earlier `aboutToQuit`-triggered `get_service()
.stop()` -- watchdog's own internal `_emitter_for_watch` bookkeeping no
longer has this watch, hence the `KeyError`. This is a deterministic
ordering issue on one thread (not a flaky race), matching the reliably
-reproduced crash.

## Key decision

- **Wrap the `unschedule()` call itself in `try/except KeyError`**,
  rather than trying to guarantee a stricter connection-order
  invariant between `aboutToQuit` and a widget's own `destroyed`
  signal -- those are two different Qt signals firing at two different
  phases of shutdown, and nothing about connecting one "last" can
  actually order it relative to the other. A `KeyError` here means
  watchdog's own bookkeeping already has nothing to unschedule (either
  because the whole Observer already stopped, or any other reason) --
  there's nothing left to clean up, and the process is already
  quitting, so silently treating it as already-unscheduled is correct,
  not just convenient. This is also strictly more robust than a
  narrower `self._observer.is_alive()` pre-check would be: it covers
  this exact scenario *and* any other watchdog-internal inconsistency
  this codebase's own locking doesn't fully anticipate, matching the
  "must never itself introduce a new failure" philosophy already
  applied to `crash_handler.py` and TODO `810a5d6`'s Qt-slot-exception
  fix.
- **No change to `desk/app.py`'s connection order** -- the existing
  comment's stated intent ("runs after every individual consumer's own
  aboutToQuit-triggered watcher.stop()") is still correct for
  *aboutToQuit-connected* cleanup; it just doesn't (and can't, via
  connection order alone) cover `destroyed`-triggered cleanup, which is
  what actually needed the fix.

## Affected files

- `src/desk_services/file_watcher/service.py` --
  `FileWatcherService._unsubscribe`.

## Verification

Headless: a `FileWatcherService` instance, `watch()` a real temp
directory, call the shared `Observer`'s own `.stop()` directly
(simulating `get_service().stop()` having already run), then call
`WatchHandle.cancel()` on the still-registered handle -- confirms this
previously raised `KeyError` and now completes without one, and that
`_unsubscribe`'s own bookkeeping (`_subscribers`/`_observed_watches`)
is still correctly cleared either way. Also a normal, no-preceding
-stop cancel() still unschedules correctly (regression check for the
non-crashing path).

## Status

Implemented as planned: `FileWatcherService._unsubscribe` (in
`src/desk_services/file_watcher/service.py`) wraps
`self._observer.unschedule(watch)` in `try/except KeyError: pass`.
Also updates `design-docs/architecture.md`'s File Watcher Service
entry (item 19).

Verified directly (not headless-Qt -- this is plain Python/threading
code, no QApplication needed): first confirmed the exact reported
`KeyError` reproduces against the pre-fix code (via `git stash`) by
constructing a real `FileWatcherService`, watching a temp directory,
calling the shared `Observer`'s own `.stop()`+`.join()` directly
(simulating `get_service().stop()` having already run), then calling
`WatchHandle.cancel()` -- this raised the identical `KeyError` before
the fix and completes cleanly after it, with `_subscribers`/
`_observed_watches` bookkeeping still correctly cleared either way.
Also confirmed: `cancel()` stays idempotent (calling it twice never
raises), a normal `cancel()` while the Observer is still running still
actually unschedules (regression check for the non-crashing path), and
a watch shared by two subscribers only unschedules once the *last*
one cancels (regression check for the reference-counting behavior the
fix must not disturb).

Regression-checked: re-ran every other verification script from this
session (tempui-live-refresh, Questions-notification, drag-and-drop,
new-Desk-seeding, paste-clipboard-routing, `WidgetSpawnMenu` grouping
/keyboard-nav, MRU-file-existence, crash-log) -- all still pass
unaffected.

Added a `LEARNINGS.md` entry: the underlying fact that `aboutToQuit`
connection order and a widget's own `destroyed`-signal timing can't be
assumed ordered relative to each other is a genuinely non-obvious Qt
teardown gotcha (it's exactly what the original, now-corrected
`desk/app.py` comment got wrong) worth remembering if a similar issue
surfaces elsewhere.
