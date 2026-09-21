import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication

from desk import __version__
from desk.crash_handler import install as install_crash_handler
from desk.desks import default_desk_path, discover_desk_files
from desk.hotreload import HotReloadBroker
from desk.logging_setup import configure_logging
from desk.server.app import DEFAULT_WIDGETS_DIR
from desk.server.runner import start_server
from desk.shell.window import DeskWindow
from desk.widgets import WidgetWatcher, discover_widgets
from desk_services.file_watcher import get_service

_log_file = configure_logging()
logger = logging.getLogger("desk")


def main() -> int:
    install_crash_handler()
    logger.info("Desk %s starting", __version__)
    logger.info("Log file: %s", _log_file)

    app = QApplication(sys.argv)

    broker = HotReloadBroker()
    widgets_dir = DEFAULT_WIDGETS_DIR
    widgets = discover_widgets(widgets_dir)

    watcher = WidgetWatcher(widgets_dir, broker)
    watcher.start()
    app.aboutToQuit.connect(watcher.stop)

    handle = start_server(widgets_dir=widgets_dir)
    app.aboutToQuit.connect(handle.stop)
    logger.info(
        "Local web server listening at %s (html widgets: %s)",
        handle.url,
        sorted(handle.widgets),
    )
    logger.info("Discovered widgets: %s", {wid: w.kind for wid, w in widgets.items()})

    initial_directory = Path.cwd()
    existing_desks = discover_desk_files(initial_directory)
    desk_path = existing_desks[0] if existing_desks else default_desk_path(initial_directory)
    logger.info("Opening desk: %s", desk_path)

    window = DeskWindow(widgets, handle, broker, desk_path, widgets_dir)
    handle.gui_bridge.attach(window)
    app.aboutToQuit.connect(window.save_current_desk)
    window.show()

    # Stops the shared file-watcher Observer thread itself (TODO
    # 578cb6b) -- connected last so it runs after every individual
    # consumer's own aboutToQuit-triggered watcher.stop()/handle.cancel(),
    # never racing a cancel() against an already-stopped Observer.
    app.aboutToQuit.connect(get_service().stop)

    exit_code = app.exec()

    # Tear the window (and every ChromiumWidget in it) down explicitly,
    # with DeferredDelete drained, *before* main() returns. Otherwise
    # the views/pages are still alive when the interpreter starts its
    # own shutdown, ChromiumWidget's destroyed-deferred
    # profile.deleteLater() never gets an event loop to run in, and
    # Chromium's per-profile teardown races interpreter exit ("Release
    # of profile requested but WebEnginePage still not deleted" ->
    # segfault). See LEARNINGS.md (TODO a5f66cc).
    #
    # The QGraphicsScene holding the embedded widgets must be cleared
    # here too: left alone, its QGraphicsProxyWidgets are only
    # destroyed at QApplication dealloc (interpreter exit), where a
    # QWebEngineView's hideEvent then calls setVisible() on an
    # already-deleted page (SIGSEGV in QWebEnginePage::setVisible).
    window.view.scene().clear()
    window.deleteLater()
    del window
    for _ in range(3):
        # Each pass can queue further deleteLater()s (profile after page).
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QCoreApplication.processEvents()

    return exit_code
