import threading
from typing import Any, Callable

from PyQt6.QtCore import QObject, pyqtSignal


class GuiBridge(QObject):
    """Lets the Local Web Server (running on a background thread, in the
    same process) synchronously call into GUI-thread-owned state (the
    DeskWindow) and get a result back -- for the Desk Bridge API's
    workspace.getState/widgets.open/widgets.close (see
    plans/desk-bridge-api.md).

    Must be constructed on the GUI thread. .call(fn) is invoked from any
    other thread: it emits a Qt signal (thread-safe -- Qt auto-queues
    delivery onto the thread the receiving QObject lives on, the same
    guarantee HotReloadBroker already relies on for fire-and-forget
    notifications), then blocks only the *calling* thread until the GUI
    thread has run fn() and produced a result (or raised).

    .call_async(starter) (TODO 9767c1a) is the same idea for a GUI
    -thread operation that's itself asynchronous -- e.g.
    QWebEnginePage.runJavaScript, whose result only arrives later via
    its own callback, delivered on the GUI thread's event loop. `fn()`
    in .call() is expected to return its result synchronously; a
    `starter` that instead tried to block *inside* itself waiting for
    that later callback would deadlock the GUI thread against its own
    event loop (the callback that would unblock it can never run while
    the thread that would process it is itself blocked). .call_async
    keeps `starter` non-blocking (it only kicks off the async operation
    and returns immediately) and lets the operation's own callback --
    still running on the GUI thread, whenever Qt gets to it -- call
    `resolve(value)` to actually complete the call. Only the *original
    calling* thread ever blocks, exactly like .call()."""

    _call_requested = pyqtSignal(object, object)  # fn, (result_holder, done_event)
    _async_call_requested = pyqtSignal(object)  # run_starter (no return value)

    def __init__(self) -> None:
        super().__init__()
        self.window: Any = None
        self._call_requested.connect(self._run_on_gui_thread)
        self._async_call_requested.connect(self._run_async_starter)

    def attach(self, window: Any) -> None:
        self.window = window

    def call(self, fn: Callable[[], Any], timeout: float = 5.0) -> Any:
        if self.window is None:
            raise RuntimeError("GuiBridge: no DeskWindow attached yet")
        holder: dict[str, Any] = {}
        done = threading.Event()
        self._call_requested.emit(fn, (holder, done))
        if not done.wait(timeout=timeout):
            raise TimeoutError("GuiBridge: GUI thread did not respond in time")
        if "error" in holder:
            raise holder["error"]
        return holder.get("value")

    def call_async(self, starter: Callable[[Callable[[Any], None]], None], timeout: float = 10.0) -> Any:
        if self.window is None:
            raise RuntimeError("GuiBridge: no DeskWindow attached yet")
        holder: dict[str, Any] = {}
        done = threading.Event()

        def resolve(value: Any) -> None:
            holder["value"] = value
            done.set()

        def run_starter() -> None:
            try:
                starter(resolve)
            except Exception as e:  # noqa: BLE001 -- propagated to the caller, not swallowed
                holder["error"] = e
                done.set()

        self._async_call_requested.emit(run_starter)
        if not done.wait(timeout=timeout):
            raise TimeoutError("GuiBridge: async GUI-thread operation did not complete in time")
        if "error" in holder:
            raise holder["error"]
        return holder.get("value")

    def _run_on_gui_thread(self, fn: Callable[[], Any], holder_and_event: tuple[dict, threading.Event]) -> None:
        holder, done = holder_and_event
        try:
            holder["value"] = fn()
        except Exception as e:  # noqa: BLE001 -- propagated to the caller, not swallowed
            holder["error"] = e
        finally:
            done.set()

    def _run_async_starter(self, run_starter: Callable[[], None]) -> None:
        # Deliberately does NOT wrap this in its own try/except that sets
        # `done` afterward -- unlike _run_on_gui_thread, this call
        # returning is not the same as the operation completing.
        # run_starter's own try/except (built in call_async) already
        # handles a *synchronous* exception from `starter` itself; a
        # later exception from within an async callback is on the
        # caller of that callback to handle, same as any other Qt slot.
        run_starter()
