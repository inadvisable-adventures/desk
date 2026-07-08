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
    thread has run fn() and produced a result (or raised)."""

    _call_requested = pyqtSignal(object, object)  # fn, (result_holder, done_event)

    def __init__(self) -> None:
        super().__init__()
        self.window: Any = None
        self._call_requested.connect(self._run_on_gui_thread)

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

    def _run_on_gui_thread(self, fn: Callable[[], Any], holder_and_event: tuple[dict, threading.Event]) -> None:
        holder, done = holder_and_event
        try:
            holder["value"] = fn()
        except Exception as e:  # noqa: BLE001 -- propagated to the caller, not swallowed
            holder["error"] = e
        finally:
            done.set()
