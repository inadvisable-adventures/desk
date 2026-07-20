# Investigation: why Desk shutdown can take a long time

**TODO `9d1544b`.** Traced the actual shutdown path end-to-end and
measured each candidate directly (real subprocesses, a real HTTP
long-poll against a real running server, a real `watchdog` Observer) —
not just read the code and guessed. Two real, significant, additive
contributors were found and empirically confirmed; a third suspected
candidate was measured and ruled out.

## The shutdown path

`src/desk/app.py`'s `main()` connects four handlers to
`QApplication.aboutToQuit`, in this order:

```python
app.aboutToQuit.connect(watcher.stop)               # WidgetWatcher
app.aboutToQuit.connect(handle.stop)                # ServerHandle (local web server)
app.aboutToQuit.connect(window.save_current_desk)    # DeskWindow
app.aboutToQuit.connect(get_service().stop)          # FileWatcherService
```

`aboutToQuit` handlers run **synchronously, in connection order, on
the GUI thread**, and are guaranteed to finish before Qt's event loop
actually stops (`app.exec()` returning). Any blocking call inside one
of these is directly felt as "the app hasn't quit yet."

There's a **second, easy-to-miss phase** after that: once `app.exec()`
returns and the process actually starts exiting, Qt destroys its whole
remaining widget tree (the `QApplication`/`QMainWindow`/every placed
widget) as a C++ object-ownership cascade. Any widget connected to its
own `destroyed` signal for cleanup — the Console and Claude widgets
both are (`TerminalWidget._cleanup_resources`) — runs that cleanup
**at this point**, still on the same thread, still blocking the
process from actually terminating, even though the window has already
visually disappeared.

## Finding 1 (confirmed): terminal-backed widget teardown, up to ~2s *per widget*, sequential

`TerminalWidget.__init__` (`src/desk/terminal_widget.py`) connects:

```python
self.destroyed.connect(lambda: TerminalWidget._cleanup_resources(master_fd, process))
```

```python
@staticmethod
def _cleanup_resources(master_fd: int, process: subprocess.Popen) -> None:
    try:
        os.close(master_fd)
    except OSError:
        pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
```

Both the **Console widget** and the **Claude widget** are built on
`TerminalWidget` — a real PTY-backed subprocess (`bash`, which the
Claude widget then `exec`s into `claude` via `type_into_shell`, so the
same PID keeps running as whatever program was launched).

**Measured directly** (bypassing Qt's `deleteLater()`/event-loop
scheduling entirely, calling `_cleanup_resources` as a bare function
against real child processes):

| Scenario | Measured cleanup time |
|---|---|
| Plain `bash`, no SIGTERM handler | 0.004s |
| A child that installs a real `SIGTERM` handler and takes >2s to respond (simulating a real interactive CLI doing its own graceful-shutdown/session-save work before exiting) | **2.005s** |

This is the exact `process.wait(timeout=2)` cap being hit, confirmed
to the millisecond. `claude` itself is a real, full Node.js TUI
application with its own signal handling and session-state-saving
logic — there's no reason to assume it always dies instantly on
`SIGTERM`, especially mid-request ("`✽ Working…`", observed directly
in an earlier session's terminal capture).

**Why this is additive, not a one-time cost:** Qt's widget-tree
destruction cascade destroys each remaining widget **one at a time**,
and `_cleanup_resources` for one widget must finish before the next
widget's own destruction (and thus its own `destroyed` signal) is
processed — this is single-threaded, synchronous C++ object teardown,
not something that runs concurrently across widgets. A Desk with **3
open Claude/Console widgets, each mid-session and slow to respond to
`SIGTERM`, adds up to ~6 seconds of pure subprocess-teardown delay**
alone, on top of everything else. This project's own development
workflow routinely has multiple Console/Claude widgets open at once
(this very investigation was done from inside one).

(An initial attempt to measure this through the real `TerminalWidget` +
`deleteLater()` + `QApplication.processEvents()` path produced
confusing, inconsistent numbers dominated by `deleteLater()`'s own
`DeferredDelete` event-processing quirks under a bare `processEvents()`
polling loop — not a real signal. Bypassing that entirely and calling
`_cleanup_resources` directly against real child processes, as above,
is what actually isolated and confirmed the real behavior.)

## Finding 2 (confirmed): the local web server can block quitting for the full 5-second timeout

`ServerHandle.stop` (`src/desk/server/runner.py`):

```python
def stop(self, timeout: float = 5.0) -> None:
    self._server.should_exit = True
    self._thread.join(timeout=timeout)
```

This is the **second** `aboutToQuit` handler — it runs early, while
the window is still visibly open, so this delay is directly visible to
the user as "the app isn't quitting."

The Bridge API's `events.onMessage` (`bridge_client.py`'s
`pollEvents()`) is a **long-poll loop**: every `kind: "html"` widget
that registers even one event listener keeps a `GET
/api/bridge/events/poll?timeout=25` request open essentially
continuously — as soon as one resolves (an event arrives, or the
25-second server-side timeout elapses), it immediately re-issues
another one (`src/desk/server/bridge_client.py`). The server route
(`src/desk/server/app.py`) blocks a thread-pool-executor call for up
to that same 25 seconds:

```python
event = await loop.run_in_executor(None, mediator.poll, instance_id, timeout)
```

**Measured directly**: started a real server, subscribed a real caller,
started a real in-flight long-poll request (mirroring the exact client
behavior), then called `handle.stop()` while it was still pending:

```
handle.stop() took 5.002s
poll thread finished: False
```

`uvicorn`'s graceful shutdown waits for in-flight requests to complete
naturally rather than forcibly cancelling them — since the poll had
just started (and could run for up to 25s), `join(timeout=5.0)` simply
gave up at its own cap, having blocked the GUI thread for the full 5
seconds, **without the request actually finishing** (it's a daemon
thread, so it just gets killed when the process eventually exits).

**Any Desk with even one open `kind: "html"` widget that listens for
events is very likely to have an in-flight long-poll at any given
moment** — this isn't a rare edge case, it's the steady-state behavior
of that whole mechanism.

## Ruled out: the shared file-watcher service

`FileWatcherService.stop` (`src/desk_services/file_watcher/service.py`)
has the same shape (`self._observer.stop(); self._observer.join(timeout=5.0)`).
**Measured directly** with a real, active `watchdog.Observer` watch: **0.000s**.
`watchdog`'s own `Observer.stop()` reacts essentially instantly under
normal conditions — this is a defensive timeout that isn't actually
being hit in practice, not a real contributor. (Confirmed the
underlying `Observer` thread is `daemon=True`, same as the two findings
above — see the shared theme in Recommendations below.)

## Not deeply investigated

`DeskWindow.save_current_desk` (`_capture_desk_state`, iterating every
placed widget's `get_widget_local_storage()`) wasn't measured in depth.
For `kind: "html"` widgets this reads an already-cached dict (no
blocking round-trip); for `kind: "python"` widgets it's a direct,
in-process method call — likely fast in the general case, but a
individual widget's own `get_widget_local_storage()` implementation
doing something slow (disk I/O, etc.) was not audited across every
built-in widget. Worth a follow-up pass if the two confirmed findings
above turn out not to fully explain an observed slow shutdown.

## Recommendations, ranked by expected impact

1. **Parallelize `TerminalWidget` process termination instead of
   sequential per-widget teardown.** The single biggest lever: instead
   of relying on Qt's own one-at-a-time destruction cascade to trigger
   `process.terminate()` + `wait(timeout=2)` per widget, send `SIGTERM`
   to *every* still-running terminal-backed process up front (e.g. from
   `DeskWindow`, iterating all placed `Console`/`Claude` instances
   before quitting), then wait on all of them concurrently (a single
   shared timeout, not `N × 2s`). This turns the worst case from
   `N × ~2s` into roughly `~2s` regardless of how many terminal widgets
   are open.
2. **Shorten (or drop) the `ServerHandle.stop`/`FileWatcherService.stop`
   join timeouts.** Both underlying threads are already `daemon=True`
   — confirmed directly for both the uvicorn server thread and the
   `watchdog.Observer` thread — meaning the OS/interpreter will kill
   them at process exit regardless of whether `join()` ever returns.
   The `join()` call's only purpose today is "wait around to *know*
   it's done," not correctness. A 5-second cap trades a rare,
   already-guaranteed-eventually-fine outcome for a very real,
   frequently-hit 5-second user-visible stall (Finding 2). Cutting this
   to something like 0.5–1s (or making it fire-and-forget, not joined
   at all, given the daemon-thread guarantee) removes essentially all
   of the downside with no loss of correctness.
3. **If (2) feels too aggressive, have `ServerHandle.stop` proactively
   cancel in-flight long-poll requests** rather than passively waiting
   for `uvicorn`'s own graceful-shutdown drain — e.g. track outstanding
   `events/poll` calls and set a cancellation event `mediator.poll`
   checks, so a pending long-poll returns immediately once shutdown
   begins instead of running out its own up-to-25-second window. More
   invasive than (2); only worth doing if (2) alone isn't considered
   sufficient.
4. **Lower `events/poll`'s default timeout** (currently 25s, both
   client and server default) as a smaller, complementary mitigation —
   reduces the *window* during which an in-flight poll could be caught
   mid-request by a shutdown, though it doesn't change the worst case
   on its own (a poll can still be caught right after starting).
