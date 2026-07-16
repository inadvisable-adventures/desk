import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from desk_services.file_watcher.service import FileWatcherService  # noqa: E402


def noop_callback(path):
    pass


def test_cancel_after_observer_already_stopped_does_not_raise():
    with tempfile.TemporaryDirectory() as d:
        service = FileWatcherService()
        handle = service.watch(Path(d), noop_callback)

        # Simulates app.aboutToQuit's get_service().stop() having
        # already fully stopped the shared Observer before this
        # widget's own destroyed-triggered watcher.stop() runs (TODO
        # 03f623a) -- this reliably reproduced the reported KeyError
        # before the fix.
        service._observer.stop()
        service._observer.join(timeout=5.0)

        handle.cancel()  # must not raise

        # Bookkeeping is still cleared correctly.
        assert service._subscribers == {}
        assert service._observed_watches == {}
    print("cancel() after the shared Observer already stopped does not raise: PASS")


def test_cancel_is_idempotent():
    with tempfile.TemporaryDirectory() as d:
        service = FileWatcherService()
        handle = service.watch(Path(d), noop_callback)
        handle.cancel()
        handle.cancel()  # must not raise the second time either
        service.stop()
    print("cancel() is idempotent: PASS")


def test_normal_cancel_still_unschedules():
    with tempfile.TemporaryDirectory() as d:
        service = FileWatcherService()
        key_path = Path(d).resolve()
        handle = service.watch(Path(d), noop_callback)
        assert len(service._observed_watches) == 1

        handle.cancel()

        assert service._subscribers == {}
        assert service._observed_watches == {}
        service.stop()
    print("a normal cancel() (Observer still running) still unschedules correctly: PASS")


def test_shared_watch_only_unschedules_after_last_subscriber_cancels():
    with tempfile.TemporaryDirectory() as d:
        service = FileWatcherService()
        handle1 = service.watch(Path(d), noop_callback)
        handle2 = service.watch(Path(d), noop_callback)
        assert len(service._observed_watches) == 1  # shared, single native schedule

        handle1.cancel()
        assert len(service._observed_watches) == 1  # still one subscriber left

        handle2.cancel()
        assert service._observed_watches == {}
        service.stop()
    print("shared watch only unschedules once the last subscriber cancels: PASS")


test_cancel_after_observer_already_stopped_does_not_raise()
test_cancel_is_idempotent()
test_normal_cancel_still_unschedules()
test_shared_watch_only_unschedules_after_last_subscriber_cancels()
print("ALL PASS")
