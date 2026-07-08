from PyQt6.QtCore import QObject, pyqtSignal


class HotReloadBroker(QObject):
    """Connects the Local Web Server's widget-source file watcher (running
    on a background thread) to ChromiumWidget instances on the GUI thread.
    Qt signal emission is thread-safe: emitting from any thread queues
    delivery onto the thread the receiving QObject lives on, so no manual
    locking/marshalling is needed here."""

    widget_changed = pyqtSignal(str)
