import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, "src")

from desk_services.file_watcher.service import FileWatcherService, _WatchKey


def wait_for(predicate, timeout=3.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_dedup_and_fanout():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d).resolve()
        svc = FileWatcherService()
        try:
            calls_a = []
            calls_b = []
            h1 = svc.watch(d, calls_a.append, recursive=False)
            h2 = svc.watch(d, calls_b.append, recursive=False)
            key = _WatchKey(d, False)
            assert len(svc._observed_watches) == 1, "two watches on identical key should share one native schedule"
            (d / "f.txt").write_text("hello")
            assert wait_for(lambda: calls_a and calls_b), f"both subscribers should fire: {calls_a} {calls_b}"

            h1.cancel()
            calls_a.clear()
            calls_b.clear()
            (d / "f2.txt").write_text("hello2")
            assert wait_for(lambda: calls_b), "remaining subscriber should still fire after the other cancels"
            assert not calls_a, "cancelled subscriber should not fire"
            assert key in svc._observed_watches, "native watch should still be scheduled while one subscriber remains"

            h2.cancel()
            assert key not in svc._observed_watches, "native watch should be unscheduled once last subscriber cancels"

            calls_c = []
            svc.watch(d, calls_c.append, recursive=False)
            (d / "f3.txt").write_text("hello3")
            assert wait_for(lambda: calls_c), "re-watching the same key after full cancellation should work cleanly"
            print("test_dedup_and_fanout: PASS")
        finally:
            svc.stop()


def test_nested_path_collision_fixed():
    # Reproduces the real reported bug: two DIFFERENT raw watchdog.Observer
    # instances watching nested paths raises "already scheduled" on macOS.
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    with tempfile.TemporaryDirectory() as d:
        d = Path(d).resolve()
        sub = d / "sub"
        sub.mkdir()

        raised = False
        try:
            obs1 = Observer()
            obs1.schedule(FileSystemEventHandler(), str(d), recursive=False)
            obs1.start()
            obs2 = Observer()
            obs2.schedule(FileSystemEventHandler(), str(sub), recursive=False)
            obs2.start()
            time.sleep(0.5)  # give FSEvents a beat to actually collide
        except RuntimeError as e:
            if "already scheduled" in str(e):
                raised = True
        finally:
            for o in (obs1, obs2):
                try:
                    if o.is_alive():
                        o.stop()
                        o.join(timeout=2)
                except Exception:
                    pass

        # Through the shared service instead: both should schedule cleanly.
        svc = FileWatcherService()
        try:
            outer_events = []
            inner_events = []
            svc.watch(d, outer_events.append, recursive=False)
            svc.watch(sub, inner_events.append, recursive=False)
            (d / "top.txt").write_text("x")
            (sub / "nested.txt").write_text("y")
            ok_outer = wait_for(lambda: outer_events)
            ok_inner = wait_for(lambda: inner_events)
            assert ok_outer and ok_inner, "both nested watches should fire independently through the shared service"
            print(f"test_nested_path_collision_fixed: PASS (raw-Observer collision reproduced={raised})")
        finally:
            svc.stop()


def test_watch_does_not_hold_lock_across_observer_schedule():
    # Regression test for TODO c4d79f0: FileWatcherService.watch() used
    # to call self._observer.schedule() *while holding* self._lock.
    # watchdog's own dispatch thread acquires its own internal lock
    # first, then calls back into our _dispatch (needing self._lock) --
    # opposite acquisition order from a thread already holding
    # self._lock and entering schedule(), which is a reliable AB-BA
    # deadlock (this is exactly what hung Desk on every launch).
    #
    # Verified directly and deterministically, independent of real
    # FSEvents/thread timing: monkeypatch self._observer.schedule to
    # probe -- from a separate helper thread, so the probe itself can
    # never hang the test -- whether self._lock is held at the instant
    # schedule() is entered. A plain threading.Lock isn't reentrant, so
    # if watch()'s own thread still holds it, the helper thread's
    # non-blocking-with-timeout acquire attempt will fail to get it.
    with tempfile.TemporaryDirectory() as d:
        d = Path(d).resolve()
        svc = FileWatcherService()
        try:
            real_schedule = svc._observer.schedule
            lock_was_held = []

            def spying_schedule(*args, **kwargs):
                probe_acquired = []

                def probe():
                    got = svc._lock.acquire(timeout=0.5)
                    probe_acquired.append(got)
                    if got:
                        svc._lock.release()

                probe_thread = threading.Thread(target=probe)
                probe_thread.start()
                probe_thread.join(timeout=2)
                lock_was_held.append(not (probe_acquired and probe_acquired[0]))
                return real_schedule(*args, **kwargs)

            svc._observer.schedule = spying_schedule
            calls = []
            svc.watch(d, calls.append, recursive=False)
            assert lock_was_held == [False], (
                "FileWatcherService.watch() must not hold self._lock while inside "
                "self._observer.schedule() -- doing so deadlocks against watchdog's "
                "dispatch thread, which acquires its lock before calling back into "
                "our _dispatch (needs self._lock) (TODO c4d79f0)"
            )
            (d / "f.txt").write_text("x")
            assert wait_for(lambda: calls), "watch() should still work normally after the spy is installed"
            print("test_watch_does_not_hold_lock_across_observer_schedule: PASS")
        finally:
            svc.stop()


if __name__ == "__main__":
    test_dedup_and_fanout()
    test_nested_path_collision_fixed()
    test_watch_does_not_hold_lock_across_observer_schedule()
    print("ALL PASS")
