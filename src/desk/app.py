import logging
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from desk import __version__
from desk.crash_handler import install as install_crash_handler
from desk.desks import default_desk_path, discover_desk_files
from desk.hotreload import HotReloadBroker
from desk.server.app import DEFAULT_WIDGETS_DIR
from desk.server.runner import start_server
from desk.shell.window import DeskWindow
from desk.widgets import WidgetWatcher, discover_widgets
from desk_services.file_watcher import get_service

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("desk")


def main() -> int:
    install_crash_handler()
    logger.info("Desk %s starting", __version__)

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

    return app.exec()
