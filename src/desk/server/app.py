import asyncio
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.types import ASGIApp, Receive, Scope, Send

from desk.event_mediator import EventMediator
from desk.shell.bridge import GuiBridge
from desk.widgets import WidgetInfo, discover_widgets

# src/desk/server/app.py -> repo root, then the widgets directory.
DEFAULT_WIDGETS_DIR = Path(__file__).resolve().parents[3] / "widgets"


def _token_from_scope(scope: Scope) -> str | None:
    query = parse_qs((scope.get("query_string") or b"").decode())
    if "token" in query:
        return query["token"][0]
    headers = dict(scope.get("headers") or [])
    header_token = headers.get(b"x-desk-token")
    return header_token.decode() if header_token else None


class TokenAuthMiddleware:
    """Rejects any HTTP/WebSocket request that doesn't carry the per-launch
    token, so only the Shell (which knows the token) can talk to this
    server. See design-docs/architecture.md#security-considerations."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if _token_from_scope(scope) == self.token:
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401})
        else:
            response = PlainTextResponse("Unauthorized", status_code=401)
            await response(scope, receive, send)


def _widget_info_dict(widget: WidgetInfo) -> dict:
    return {
        "id": widget.id,
        "kind": widget.kind,
        "name": widget.name,
        "capabilities": widget.capabilities,
        "default_size": (
            {"width": widget.default_size[0], "height": widget.default_size[1]}
            if widget.default_size
            else None
        ),
    }


class OpenWidgetRequest(BaseModel):
    widget_id: str
    x: float | None = None
    y: float | None = None
    width: int | None = None
    height: int | None = None


class CloseWidgetRequest(BaseModel):
    instance_id: str


class WriteFileRequest(BaseModel):
    path: str
    contents: str


class SetLocalStorageRequest(BaseModel):
    data: dict


class EventNamesRequest(BaseModel):
    names: list[str]


class EventPublishRequest(BaseModel):
    name: str
    payload: object = None


def _event_dict(event) -> dict:
    return {
        "timestamp": event.timestamp,
        "name": event.name,
        "sender_instance_id": event.sender_instance_id,
        "payload": event.payload,
    }


def create_app(
    token: str,
    widgets_dir: Path = DEFAULT_WIDGETS_DIR,
    gui_bridge: GuiBridge | None = None,
    event_mediator: EventMediator | None = None,
) -> FastAPI:
    """Serves only kind:"html" widgets (plus the Bridge API). kind:"python"
    widgets render natively in the Shell and never go through this server —
    see design-docs/architecture.md."""
    app = FastAPI(title="Desk")
    html_widgets = {
        widget_id: widget
        for widget_id, widget in discover_widgets(widgets_dir).items()
        if widget.kind == "html"
    }

    @app.get("/api/ping")
    async def ping() -> dict[str, object]:
        return {"status": "ok", "widgets": sorted(html_widgets)}

    @app.websocket("/ws")
    async def echo(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                message = await websocket.receive_text()
                await websocket.send_text(message)
        except Exception:
            pass

    # --- Desk Bridge API (see plans/desk-bridge-api.md) ---
    # Capability-scoped: each route (other than self.getManifest, which
    # isn't privileged) requires the calling widget to have declared the
    # relevant resource-level capability in its own widget.json.

    def require_caller(capability: str | None):
        async def dependency(x_desk_widget_id: str = Header(...)) -> WidgetInfo:
            widget = discover_widgets(widgets_dir).get(x_desk_widget_id)
            if widget is None:
                # Falls back to the live, GuiBridge-reachable widget
                # catalog (TODO f693275) -- discover_widgets(widgets_dir)
                # is a pure filesystem scan of the real widgets/
                # directory, so it can never find a tempui-DSL-defined
                # custom widget (TODO 91b3f42), whose WidgetInfo only
                # ever lives in DeskWindow._widgets. A genuinely-missing
                # gui_bridge/not-yet-attached window still correctly
                # surfaces run_on_gui's own 503 here, not a misleading
                # "unknown widget id" 400.
                widget = await run_on_gui(lambda: gui_bridge.window.get_widget_info(x_desk_widget_id))
            if widget is None:
                raise HTTPException(400, f"Unknown widget id: {x_desk_widget_id!r}")
            if capability is not None and capability not in widget.capabilities:
                raise HTTPException(
                    403, f"Widget {x_desk_widget_id!r} lacks capability {capability!r}"
                )
            return widget

        return dependency

    def require_instance_id(x_desk_instance_id: str = Header(...)) -> str:
        """Identifies the calling *instance*, not just its widget kind
        (TODO 5734529) -- deliberately not layered on require_caller:
        self.getLocalStorage/setLocalStorage need no broader capability
        at all -- a widget can only ever touch its own per-instance
        storage, the same "not a privileged operation" reasoning
        self.getManifest already uses -- so there's nothing to check
        here beyond the header itself, regardless of whether
        require_caller can also resolve a tempui-DSL-defined custom
        widget (TODO f693275; it couldn't, before that fix -- see
        PARKINGLOT.md's former entry on this)."""
        return x_desk_instance_id

    async def run_on_gui(fn):
        if gui_bridge is None:
            raise HTTPException(503, "GUI bridge not available")
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, gui_bridge.call, fn)
        except RuntimeError as e:
            raise HTTPException(503, str(e)) from e
        except KeyError as e:
            raise HTTPException(400, f"Unknown widget id: {e}") from e

    def require_mediator() -> EventMediator:
        if event_mediator is None:
            raise HTTPException(503, "Event mediator not available")
        return event_mediator

    @app.get("/api/bridge/self/getManifest")
    async def self_get_manifest(widget: WidgetInfo = Depends(require_caller(None))):
        return _widget_info_dict(widget)

    @app.get("/api/bridge/self/getLocalStorage")
    async def self_get_local_storage(instance_id: str = Depends(require_instance_id)):
        data = await run_on_gui(lambda: gui_bridge.window.get_html_widget_local_storage(instance_id))
        return {"data": data}

    @app.post("/api/bridge/self/setLocalStorage")
    async def self_set_local_storage(
        body: SetLocalStorageRequest, instance_id: str = Depends(require_instance_id)
    ):
        await run_on_gui(lambda: gui_bridge.window.set_html_widget_local_storage(instance_id, body.data))
        return {"ok": True}

    @app.get("/api/bridge/workspace/getState")
    async def workspace_get_state(widget: WidgetInfo = Depends(require_caller("workspace"))):
        return await run_on_gui(lambda: gui_bridge.window.get_state_dict())

    @app.get("/api/bridge/fs/readFile")
    async def fs_read_file(path: str, widget: WidgetInfo = Depends(require_caller("fs"))):
        try:
            return {"contents": Path(path).read_text()}
        except OSError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/bridge/fs/writeFile")
    async def fs_write_file(
        body: WriteFileRequest, widget: WidgetInfo = Depends(require_caller("fs"))
    ):
        try:
            Path(body.path).write_text(body.contents)
        except OSError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True}

    @app.get("/api/bridge/widgets/list")
    async def widgets_list(widget: WidgetInfo = Depends(require_caller("widgets"))):
        return {"widgets": [_widget_info_dict(w) for w in discover_widgets(widgets_dir).values()]}

    @app.post("/api/bridge/widgets/open")
    async def widgets_open(
        body: OpenWidgetRequest, widget: WidgetInfo = Depends(require_caller("widgets"))
    ):
        pos = (body.x, body.y) if body.x is not None and body.y is not None else None
        size = (body.width, body.height) if body.width is not None and body.height is not None else None
        instance_id = await run_on_gui(lambda: gui_bridge.window.open_widget(body.widget_id, pos, size))
        return {"instance_id": instance_id}

    @app.post("/api/bridge/widgets/close")
    async def widgets_close(
        body: CloseWidgetRequest, widget: WidgetInfo = Depends(require_caller("widgets"))
    ):
        closed = await run_on_gui(lambda: gui_bridge.window.close_widget_by_instance_id(body.instance_id))
        return {"closed": closed}

    # --- events (TODO 6f9c51b) -- the mediator-topology message channel:
    # widgets never talk to each other directly, only ever to the shared
    # EventMediator, identified by instance id (require_instance_id, not
    # require_caller's widget-definition id) same as self.*. publish/poll
    # can block (queue operations), so both run via run_in_executor rather
    # than inline on the event loop -- subscribe/unsubscribe are cheap
    # enough (lock + set mutation) to call directly.

    @app.post("/api/bridge/events/subscribe")
    async def events_subscribe(
        body: EventNamesRequest,
        widget: WidgetInfo = Depends(require_caller("events")),
        instance_id: str = Depends(require_instance_id),
    ):
        mediator = require_mediator()
        for name in body.names:
            mediator.subscribe(instance_id, name)
        return {"ok": True}

    @app.post("/api/bridge/events/unsubscribe")
    async def events_unsubscribe(
        body: EventNamesRequest,
        widget: WidgetInfo = Depends(require_caller("events")),
        instance_id: str = Depends(require_instance_id),
    ):
        mediator = require_mediator()
        for name in body.names:
            mediator.unsubscribe(instance_id, name)
        return {"ok": True}

    @app.post("/api/bridge/events/publish")
    async def events_publish(
        body: EventPublishRequest,
        widget: WidgetInfo = Depends(require_caller("events")),
        instance_id: str = Depends(require_instance_id),
    ):
        mediator = require_mediator()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, mediator.publish, body.name, body.payload, instance_id)
        return {"ok": True}

    @app.get("/api/bridge/events/poll")
    async def events_poll(
        timeout: float = 25.0,
        widget: WidgetInfo = Depends(require_caller("events")),
        instance_id: str = Depends(require_instance_id),
    ):
        mediator = require_mediator()
        loop = asyncio.get_event_loop()
        event = await loop.run_in_executor(None, mediator.poll, instance_id, timeout)
        return {"event": _event_dict(event) if event is not None else None}

    for widget_id, widget in html_widgets.items():
        app.mount(
            f"/widgets/{widget_id}",
            StaticFiles(directory=widget.path, html=True),
            name=f"widget-{widget_id}",
        )

    app.add_middleware(TokenAuthMiddleware, token=token)
    return app
