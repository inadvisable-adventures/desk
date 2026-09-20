import contextlib
import secrets
import socket
import threading
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from desk.event_mediator import EventMediator
from desk.hmsvc import HmsvcManager
from desk.schema_registry import SchemaRegistry
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
    event_mediator: EventMediator
    schema_registry: SchemaRegistry
    hmsvc_manager: HmsvcManager
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
        for the very next request.

        TODO 4eb3d9e: re-mounting an already-mounted widget_id (a live
        re-registration -- Desk switch, a DefineWidget live edit, a
        promoted widget's rebuild-on-demand) first removes any existing
        route of the same name. Confirmed directly (not just suspected):
        Starlette's Router.mount only ever *appends* a route and
        resolves requests by walking routes in registration order, so
        without this, a second mount_html_widget call for the same
        widget_id at a *different* directory is silently shadowed
        forever behind the first one ever registered -- every later
        request keeps serving the original (now stale) directory's
        content, regardless of what's mounted afterward. This stayed
        invisible for a still-tempui-sourced DefineWidget widget (its
        own materialize() always reuses one fixed cache directory, so a
        "remount" just re-serves the same path with fresher bytes
        already on disk) and mostly invisible for an in-place promoted
        -widget rebuild too (build_from_source also writes to a fixed,
        stable path across rebuilds) -- but not for the one moment the
        mounted directory itself actually changes, e.g. right after
        promotion moves a widget from its pre-promotion materialized
        path to desk_widgets/<name>/.build/."""
        self.widgets[widget_id] = info
        name = f"widget-{widget_id}"
        self._app.router.routes[:] = [
            route for route in self._app.router.routes if getattr(route, "name", None) != name
        ]
        self._app.mount(
            f"/widgets/{widget_id}",
            StaticFiles(directory=directory, html=True),
            name=name,
        )

    def stop(self, timeout: float = 5.0) -> None:
        self.hmsvc_manager.stop_all()
        self._server.should_exit = True
        self._thread.join(timeout=timeout)


def start_server(
    widgets_dir: Path = DEFAULT_WIDGETS_DIR,
    host: str = "127.0.0.1",
) -> ServerHandle:
    port = _free_port()
    token = secrets.token_urlsafe(32)
    gui_bridge = GuiBridge()  # must be constructed on the GUI thread -- see desk.shell.bridge
    # Unlike GuiBridge, EventMediator has no GUI-thread requirement (it's
    # plain-Python/thread-safe, see desk.event_mediator) -- constructed
    # here anyway, once for the whole app run, so both this server and
    # DeskWindow (via ServerHandle.event_mediator) share the exact same
    # instance, the same "one shared mediator" shape GuiBridge itself uses.
    event_mediator = EventMediator()
    # Same "one shared instance for the whole app run" reasoning as
    # event_mediator above (TODO af7898b) -- runtime-only, never
    # persisted, rebuilt fresh on every process start. Given the same
    # event_mediator (TODO 6330249) so it can publish
    # desk.state.schema_changed on every successful mutation.
    schema_registry = SchemaRegistry(event_mediator)
    # TODO e75b165: same "one shared instance for the whole app run"
    # shape; told where to find this server's Bridge API so a launched
    # service can call back into Desk.
    hmsvc_manager = HmsvcManager()
    hmsvc_manager.configure_bridge(f"http://{host}:{port}", token)
    app = create_app(
        token,
        widgets_dir=widgets_dir,
        gui_bridge=gui_bridge,
        event_mediator=event_mediator,
        hmsvc_manager=hmsvc_manager,
    )

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
        event_mediator=event_mediator,
        schema_registry=schema_registry,
        hmsvc_manager=hmsvc_manager,
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
