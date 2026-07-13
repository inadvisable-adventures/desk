"""Tiny, dependency-free Qt helpers shared across `desk.shell` -- kept
separate from any one module so both `desk_picker.py` and `canvas.py`
(which don't import from each other, and `window.py` already imports
from `canvas.py`, not the reverse) can use it without risking a
circular import."""

from PyQt6.QtCore import QTimer


def deferred(fn):
    """Wraps `fn` so calling the result schedules `fn` to run on the
    *next* event-loop iteration instead of synchronously, within the
    caller's own call stack, right now.

    The fix for a specific, confirmed Qt/PyQt crash (TODO `8c9436b`,
    generalizing TODO `4716585`): a `WA_DeleteOnClose`,
    `QAbstractItemView`-based popup (`QListWidget`/`QTreeWidget`) that
    closes itself and then emits a signal whose eventual receiver shows
    a modal dialog -- the modal's own nested event loop is what
    actually processes the popup's deferred deletion, and if a stale,
    still-in-flight native mouse event targets the popup at exactly
    that moment, it's delivered to an object that's fully freed or
    mid-teardown. Wrapping the popup's own outgoing re-emission with
    this means every downstream receiver (present and future) always
    runs on a fresh event-loop iteration, decoupled from whatever
    native event triggered the signal in the first place -- fixed once,
    at the source, not once per eventual receiver. See LEARNINGS.md."""

    def wrapper(*args) -> None:
        QTimer.singleShot(0, lambda: fn(*args))

    return wrapper
