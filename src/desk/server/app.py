import asyncio
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.types import ASGIApp, Receive, Scope, Send

from desk.event_mediator import EventMediator
from desk.file_type_registry import FILE_TYPE_REGISTRY_UPDATED_EVENT
from desk.hmsvc import HmsvcManager, service_name_from_caller_id
from desk.installed_jobs import INSTALLED_JOB_RUN_TIMEOUT_SECONDS
from desk.shell.bridge import GuiBridge
from desk.widgets import WidgetInfo, discover_widgets

# src/desk/server/app.py -> repo root, then the widgets directory.
DEFAULT_WIDGETS_DIR = Path(__file__).resolve().parents[3] / "widgets"

# TODO a5f66cc: a same-origin cookie, additive to the query-param/
# X-Desk-Token-header checks below -- the one credential mechanism a
# browser attaches automatically to every same-origin request,
# including a kind:"html" widget's own plain <script src>/<link href>
# sub-resource loads (which carry neither the query string nor a
# custom header). See design-docs/architecture.md#security-considerations.
DESK_TOKEN_COOKIE = "desk_token"


def _token_from_query(scope: Scope) -> str | None:
    query = parse_qs((scope.get("query_string") or b"").decode())
    return query["token"][0] if "token" in query else None


def _token_from_scope(scope: Scope) -> str | None:
    token = _token_from_query(scope)
    if token is not None:
        return token
    headers = dict(scope.get("headers") or [])
    header_token = headers.get(b"x-desk-token")
    if header_token:
        return header_token.decode()
    cookie_header = headers.get(b"cookie")
    if cookie_header:
        cookies = SimpleCookie()
        cookies.load(cookie_header.decode())
        if DESK_TOKEN_COOKIE in cookies:
            return cookies[DESK_TOKEN_COOKIE].value
    return None


def _inject_set_cookie(send: Send, token: str) -> Send:
    """Wraps an ASGI `send` so the next `http.response.start` message
    also carries a Set-Cookie for the token -- HttpOnly (no reason page
    JS needs to read it, and it's already exposed to the page via the
    injected Bridge client script regardless), no Secure (plain HTTP
    over loopback), SameSite=Lax, no Max-Age (session-lifetime is fine:
    the very first navigation of any new launch already carries a
    fresh ?token= that re-sets this immediately, so correctness never
    depends on the cookie surviving to the next launch)."""

    async def wrapped(message: dict) -> None:
        if message["type"] == "http.response.start":
            headers = list(message.get("headers", []))
            headers.append(
                (b"set-cookie", f"{DESK_TOKEN_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax".encode())
            )
            message = {**message, "headers": headers}
        await send(message)

    return wrapped


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
            # TODO a5f66cc: only when the token specifically came from
            # the query string -- in practice that's only ever a
            # widget's own top-level page navigation (Bridge XHR calls
            # always use the X-Desk-Token header, never the query
            # string -- see bridge_client.py's call() helper), so this
            # fires once per real page load, not on every request.
            if scope["type"] == "http" and _token_from_query(scope) == self.token:
                send = _inject_set_cookie(send, self.token)
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
        # None for an ordinary widgets/<id>/widget.json-backed widget --
        # only a tempui-DSL-defined custom widget (TODO 5995ffd) has
        # one, so its own JS can call self.getManifest() to check which
        # version of its definition is currently registered.
        "content_hash": widget.content_hash,
        # TODO af7898b: desk.state.* schema declarations this widget
        # made, and any conflict/syntax-error message Desk has appended
        # for it -- see WidgetInfo.state_schema/desk_widget_loading_errors.
        "state_schema": widget.state_schema,
        "desk_widget_loading_errors": widget.desk_widget_loading_errors,
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


class SetSubtitleRequest(BaseModel):
    text: str | None


class EventNamesRequest(BaseModel):
    names: list[str]


class EventPublishRequest(BaseModel):
    name: str
    payload: object = None


class SetStateRequest(BaseModel):
    key: str
    value: object
    edit: object = None
    type_hint: str | None = None


class IntrospectSnapshotRequest(BaseModel):
    target_instance_id: str


class SetFileTypeRegistryRequest(BaseModel):
    entries: list[dict]


class OpenEditorOrScrapRequest(BaseModel):
    path: str


class PopupsShowRequest(BaseModel):
    title: str
    message: str
    buttons: list[str]
    default: str | None = None


class TransformsRunRequest(BaseModel):
    transform_id: str
    input: str
    config: dict | None = None


class HmsvcNameRequest(BaseModel):
    name: str


class InstalledJobsRunRequest(BaseModel):
    name: str
    config_path: str | None = None


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
    hmsvc_manager: HmsvcManager | None = None,
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
            # TODO e75b165: a Desk-hosted microservice (desk.hmsvc)
            # identifies itself as "hmsvc:<name>" -- not a widget at
            # all, so it gets a synthetic WidgetInfo whose capabilities
            # come from its own service.json.
            service_name = service_name_from_caller_id(x_desk_widget_id)
            if service_name is not None:
                capabilities = hmsvc_manager.capabilities_for(service_name) if hmsvc_manager else None
                if capabilities is None:
                    raise HTTPException(400, f"Unknown service: {service_name!r}")
                if capability is not None and capability not in capabilities:
                    raise HTTPException(403, f"Service {service_name!r} lacks capability {capability!r}")
                return WidgetInfo(
                    id=x_desk_widget_id,
                    path=Path("."),
                    kind="python",
                    name=service_name,
                    entry="service.py",
                    capabilities=capabilities,
                    default_size=None,
                )
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
        except ValueError as e:
            # TODO af7898b: a desk.state.* schema mismatch/invalid
            # typeHint (DeskWindow.get_state/set_state), or a
            # desk.state.* schema conflict blocking widgets.open
            # (DeskWindow.open_widget) -- both real, expected-shape
            # rejections, not a bug, so a 400 with the message rather
            # than a 500.
            raise HTTPException(400, str(e)) from e
        except Exception as e:  # noqa: BLE001
            # TODO b89cf17: anything else raised on the GUI thread
            # (e.g. introspect.snapshot against a crashed widget) used
            # to fall through to a bare, detail-free 500.
            raise HTTPException(500, f"{type(e).__name__}: {e}") from e

    def require_mediator() -> EventMediator:
        if event_mediator is None:
            raise HTTPException(503, "Event mediator not available")
        return event_mediator

    async def _current_desk_directory() -> Path:
        return await run_on_gui(lambda: gui_bridge.window.current_desk.directory)

    async def _resolve_fs_path(raw_path: str) -> Path:
        """TODO c892403: a relative desk.fs.* path used to resolve
        against the server process's own ambient working directory,
        which has no reliable relationship to whichever project is
        actually open -- silently reading/writing somewhere the user
        never sees, with no error at all. Resolves against the current
        Desk's own directory instead; an already-absolute path is used
        as-is (no GUI-thread round-trip needed for that case)."""
        path = Path(raw_path)
        if path.is_absolute():
            return path
        directory = await _current_desk_directory()
        return directory / path

    @app.get("/api/bridge/self/getManifest")
    async def self_get_manifest(
        x_desk_widget_id: str = Header(...), widget: WidgetInfo = Depends(require_caller(None))
    ):
        # TODO af7898b: prefers the live, DeskWindow-owned WidgetInfo
        # (which carries desk_widget_loading_errors/state_schema as
        # DeskWindow itself last updated them) over the
        # require_caller-injected one, which for a real built-in widget
        # is always a fresh, separate discover_widgets(widgets_dir) scan
        # -- see require_caller's own resolution order above -- and so
        # would otherwise show a permanently-stale, always-empty
        # desk_widget_loading_errors for a built-in. Falls back to the
        # injected `widget` (pre-attach, or truly not found) unchanged.
        live_widget = None
        if gui_bridge is not None:
            try:
                live_widget = await run_on_gui(lambda: gui_bridge.window.get_widget_info(x_desk_widget_id))
            except HTTPException:
                live_widget = None
        manifest = _widget_info_dict(live_widget if live_widget is not None else widget)
        # TODO c892403: lets a widget that genuinely needs to construct
        # its own project-relative path do so correctly and portably,
        # without needing the "fs" capability just to find out where it
        # is.
        manifest["directory"] = str(await _current_desk_directory())
        return manifest

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

    @app.post("/api/bridge/self/setSubtitle")
    async def self_set_subtitle(
        body: SetSubtitleRequest, instance_id: str = Depends(require_instance_id)
    ):
        await run_on_gui(lambda: gui_bridge.window.set_widget_subtitle(instance_id, body.text))
        return {"ok": True}

    @app.get("/api/bridge/workspace/getState")
    async def workspace_get_state(widget: WidgetInfo = Depends(require_caller("workspace"))):
        return await run_on_gui(lambda: gui_bridge.window.get_state_dict())

    @app.get("/api/bridge/state/get")
    async def state_get(
        key: str,
        type_hint: str | None = None,
        widget: WidgetInfo = Depends(require_caller("state")),
        instance_id: str = Depends(require_instance_id),
    ):
        return await run_on_gui(lambda: gui_bridge.window.get_state(key, type_hint))

    @app.post("/api/bridge/state/set")
    async def state_set(
        body: SetStateRequest,
        widget: WidgetInfo = Depends(require_caller("state")),
        instance_id: str = Depends(require_instance_id),
    ):
        await run_on_gui(
            lambda: gui_bridge.window.set_state(body.key, body.value, body.edit, instance_id, body.type_hint)
        )
        return {"ok": True}

    @app.get("/api/bridge/state/getHistory")
    async def state_get_history(
        key: str,
        limit: int = 50,
        widget: WidgetInfo = Depends(require_caller("state")),
        instance_id: str = Depends(require_instance_id),
    ):
        history = await run_on_gui(lambda: gui_bridge.window.get_state_history(key, limit))
        return {"history": history}

    @app.get("/api/bridge/fs/readFile")
    async def fs_read_file(path: str, widget: WidgetInfo = Depends(require_caller("fs"))):
        resolved = await _resolve_fs_path(path)
        try:
            return {"contents": resolved.read_text()}
        except OSError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/bridge/fs/writeFile")
    async def fs_write_file(
        body: WriteFileRequest, widget: WidgetInfo = Depends(require_caller("fs"))
    ):
        resolved = await _resolve_fs_path(body.path)
        try:
            # TODO ad20867: writeFile has no separate "create the
            # directory first" step -- a write to a not-yet-existing
            # directory used to just reject, silently, with no visible
            # error (this exact shape shipped in four separate
            # downstream widgets). exist_ok=True makes this safe to run
            # unconditionally: never touches an already-existing
            # directory.
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(body.contents)
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

    # --- hmsvc (TODO e75b165) -- Desk-hosted microservices. The manager
    # is plain thread-safe Python, so these run directly on the request
    # thread (start/stop can block for a few seconds -> executor).

    def require_hmsvc() -> HmsvcManager:
        if hmsvc_manager is None:
            raise HTTPException(503, "Microservice manager not available")
        return hmsvc_manager

    @app.get("/api/bridge/hmsvc/list")
    async def hmsvc_list(widget: WidgetInfo = Depends(require_caller("hmsvc"))):
        return {"services": require_hmsvc().list_services()}

    @app.get("/api/bridge/hmsvc/logs")
    async def hmsvc_logs(name: str, limit: int = 200, widget: WidgetInfo = Depends(require_caller("hmsvc"))):
        return {"lines": require_hmsvc().get_logs(name, limit)}

    def _hmsvc_action(action: str):
        async def handler(body: HmsvcNameRequest, widget: WidgetInfo = Depends(require_caller("hmsvc"))):
            manager = require_hmsvc()
            loop = asyncio.get_event_loop()
            ok, message = await loop.run_in_executor(None, getattr(manager, action), body.name)
            return {"ok": ok, "message": message}

        return handler

    for _action in ("start", "stop", "restart"):
        app.post(f"/api/bridge/hmsvc/{_action}")(_hmsvc_action(_action))

    # --- filetypes (TODO b5d52c0) -- the file type registry service.
    # get both reads the registry and subscribes the caller to future
    # edits (via the mediator directly, same "cheap enough to call
    # inline" reasoning as events/subscribe above) in one call, so a
    # widget never needs a separate subscribe call just to stay current.

    @app.get("/api/bridge/filetypes/get")
    async def filetypes_get(
        widget: WidgetInfo = Depends(require_caller("filetypes")),
        instance_id: str = Depends(require_instance_id),
    ):
        mediator = require_mediator()
        mediator.subscribe(instance_id, FILE_TYPE_REGISTRY_UPDATED_EVENT)
        entries = await run_on_gui(lambda: gui_bridge.window.get_file_type_registry_dicts())
        return {"entries": entries}

    @app.post("/api/bridge/filetypes/set")
    async def filetypes_set(
        body: SetFileTypeRegistryRequest,
        widget: WidgetInfo = Depends(require_caller("filetypes")),
        instance_id: str = Depends(require_instance_id),
    ):
        await run_on_gui(lambda: gui_bridge.window.set_file_type_registry(body.entries, instance_id))
        return {"ok": True}

    # --- editor (TODO 2da314f) -- exposes DeskWindow
    # .open_editor_or_scrap (TODO da4f9c0) to kind:"html" widgets, the
    # same service a kind:"python" widget already reaches via
    # current_context.get_editor_or_scrap_opener().

    @app.post("/api/bridge/editor/openOrScrap")
    async def editor_open_or_scrap(
        body: OpenEditorOrScrapRequest, widget: WidgetInfo = Depends(require_caller("editor"))
    ):
        resolved = await _resolve_fs_path(body.path)
        await run_on_gui(lambda: gui_bridge.window.open_editor_or_scrap(resolved))
        return {"ok": True}

    @app.post("/api/bridge/popups/show")
    async def popups_show(
        body: PopupsShowRequest, widget: WidgetInfo = Depends(require_caller("popups"))
    ):
        # Blocking (PopupsService.show_blocking runs its own nested
        # QEventLoop on the GUI thread until a button is clicked/the
        # popup is dismissed) -- run_on_gui (synchronous), not
        # run_on_gui_async, same as request_introspect_permission's own
        # blocking confirmation dialog below.
        clicked = await run_on_gui(
            lambda: gui_bridge.window.show_popup(body.title, body.message, body.buttons, body.default)
        )
        return {"clicked": clicked}

    # --- introspect (TODO 9767c1a) -- unlike every other capability
    # above, a declared capability alone isn't enough: the Desk user
    # must also approve this specific (caller, target) pair, via a
    # blocking confirmation dialog (DeskWindow.request_introspect_
    # permission, run synchronously through the existing GuiBridge.call
    # -- showing a modal is itself already a normal blocking GUI
    # operation). The DOM snapshot itself then runs through the new
    # GuiBridge.call_async, since QWebEnginePage.runJavaScript's own
    # result only arrives via a later callback.

    async def run_on_gui_async(starter, timeout: float = 10.0):
        if gui_bridge is None:
            raise HTTPException(503, "GUI bridge not available")
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, gui_bridge.call_async, starter, timeout)
        except RuntimeError as e:
            raise HTTPException(503, str(e)) from e
        except TimeoutError as e:
            raise HTTPException(504, str(e)) from e
        except ValueError:
            # Left for the calling route to translate (e.g.
            # installedJobs.run's own not-installed/stale-hash 400).
            raise
        except Exception as e:  # noqa: BLE001
            # TODO b89cf17: see run_on_gui above.
            raise HTTPException(500, f"{type(e).__name__}: {e}") from e

    @app.post("/api/bridge/transforms/run")
    async def transforms_run(
        body: TransformsRunRequest, widget: WidgetInfo = Depends(require_caller("transforms"))
    ):
        # run_on_gui_async, not the plain synchronous run_on_gui above:
        # a transform invocation can genuinely take a while (a node
        # subprocess for a TypeScript/JavaScript transform), and must
        # not block the FastAPI event loop or the GUI thread while it
        # runs -- same pattern introspect/snapshot below uses.
        result = await run_on_gui_async(
            lambda resolve: gui_bridge.window.run_transform(
                body.transform_id,
                body.input,
                body.config,
                lambda output, error: resolve({"output": output, "error": error}),
            )
        )
        return result

    @app.post("/api/bridge/installedJobs/run")
    async def installed_jobs_run(
        body: InstalledJobsRunRequest, widget: WidgetInfo = Depends(require_caller("installed_jobs"))
    ):
        # Same run_on_gui_async shape as transforms.run above (a real
        # run can genuinely take a while) -- but with a longer,
        # explicit timeout (INSTALLED_JOB_RUN_TIMEOUT_SECONDS): unlike
        # the agent-facing desk_run_installed_job MCP tool (an
        # unbounded await), this is a synchronous HTTP request/response
        # and can't wait forever. A run that outlives this timeout
        # keeps executing to completion regardless -- this route's own
        # caller just stops waiting for the result (see
        # desk.installed_jobs.INSTALLED_JOB_RUN_TIMEOUT_SECONDS's own
        # docstring). A ValueError from DeskWindow
        # .get_installed_job_for_run (not installed, or the on-disk
        # source no longer matches the installed version -- TODO
        # 7dca383/888b537's load-bearing safety check) is a genuine bad
        # request, not a job-ran-but-failed result, so it's a 400
        # here -- distinct from `{"ok": false, ...}`, the same "bad
        # request vs. the thing you asked for actually failed" split
        # the MCP tool's own is_error already draws.
        try:
            return await run_on_gui_async(
                lambda resolve: gui_bridge.window.run_installed_job(
                    body.name,
                    body.config_path,
                    lambda ok, stdout, stderr, tb: resolve(
                        {"ok": ok, "stdout": stdout, "stderr": stderr, "traceback": tb}
                    ),
                ),
                timeout=INSTALLED_JOB_RUN_TIMEOUT_SECONDS,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/bridge/introspect/snapshot")
    async def introspect_snapshot(
        body: IntrospectSnapshotRequest,
        widget: WidgetInfo = Depends(require_caller("introspect")),
        instance_id: str = Depends(require_instance_id),
    ):
        approved = await run_on_gui(
            lambda: gui_bridge.window.request_introspect_permission(instance_id, body.target_instance_id)
        )
        if not approved:
            raise HTTPException(403, "The Desk user declined this inspection request")
        result = await run_on_gui_async(
            lambda resolve: gui_bridge.window.start_dom_snapshot(body.target_instance_id, resolve)
        )
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result

    for widget_id, widget in html_widgets.items():
        app.mount(
            f"/widgets/{widget_id}",
            StaticFiles(directory=widget.path, html=True),
            name=f"widget-{widget_id}",
        )

    app.add_middleware(TokenAuthMiddleware, token=token)
    return app
