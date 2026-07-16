import sys
import tempfile
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


if __name__ == "__main__":
    test_dedup_and_fanout()
    test_nested_path_collision_fixed()
    print("ALL PASS")
