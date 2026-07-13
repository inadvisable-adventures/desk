import contextlib
import secrets
import socket
import threading
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from desk.server.app import DEFAULT_WIDGETS_DIR, create_app
from desk.shell.bridge import GuiBridge
from desk.widgets import WidgetInfo, discover_widgets


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass
class ServerHandle:
    host: str
    port: int
    token: str
    widgets: dict[str, WidgetInfo]  # kind:"html" widgets served by this server
    gui_bridge: GuiBridge
    _server: uvicorn.Server
    _thread: threading.Thread
    _app: FastAPI

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/?token={self.token}"

    def widget_url(self, widget_id: str) -> str:
        return f"http://{self.host}:{self.port}/widgets/{widget_id}/?token={self.token}"

    def mount_html_widget(self, widget_id: str, directory: Path, info: WidgetInfo) -> None:
        """Mounts a widget whose kind:"html" content lives at
        `directory` (materialized from a tempui/.desk-embedded base64
        payload -- see desk.custom_widgets, TODO 91b3f42) onto this
        already-running server, so widget_url(widget_id) serves real
        content immediately. Safe after the server has already started
        handling requests: Starlette resolves routes by walking
        self.routes fresh on every request, not from some compiled
        -at-startup table, so appending here (the same call
        create_app's own startup-time mounting loop makes) takes effect
        for the very next request."""
        self.widgets[widget_id] = info
        self._app.mount(
            f"/widgets/{widget_id}",
            StaticFiles(directory=directory, html=True),
            name=f"widget-{widget_id}",
        )

    def stop(self, timeout: float = 5.0) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=timeout)


def start_server(
    widgets_dir: Path = DEFAULT_WIDGETS_DIR,
    host: str = "127.0.0.1",
) -> ServerHandle:
    port = _free_port()
    token = secrets.token_urlsafe(32)
    gui_bridge = GuiBridge()  # must be constructed on the GUI thread -- see desk.shell.bridge
    app = create_app(token, widgets_dir=widgets_dir, gui_bridge=gui_bridge)

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    ready = threading.Event()
    original_startup = server.startup

    async def startup_and_signal(*args, **kwargs):
        await original_startup(*args, **kwargs)
        ready.set()

    server.startup = startup_and_signal

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    ready.wait(timeout=5.0)

    html_widgets = {
        widget_id: widget
        for widget_id, widget in discover_widgets(widgets_dir).items()
        if widget.kind == "html"
    }

    return ServerHandle(
        host=host,
        port=port,
        token=token,
        widgets=html_widgets,
        gui_bridge=gui_bridge,
        _server=server,
        _thread=thread,
        _app=app,
    )


@contextlib.contextmanager
def running_server(widgets_dir: Path = DEFAULT_WIDGETS_DIR, host: str = "127.0.0.1"):
    handle = start_server(widgets_dir=widgets_dir, host=host)
    try:
        yield handle
    finally:
        handle.stop()
