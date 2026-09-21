"""The client a Desk-hosted microservice (TODO e75b165) uses to reach
Desk itself -- events and `desk.state.*` -- over the existing Bridge
REST API. Stdlib-only (urllib), so a service needs no extra
dependency. Usage, inside a service's `service.py`:

    from desk.hmsvc_client import desk
    desk.state_set("counter", 1)
    desk.events_publish("my.event", {"x": 1})

Reads the DESK_BRIDGE_URL/DESK_BRIDGE_TOKEN/DESK_SERVICE_NAME
environment variables Desk sets when it launches the service. Every
call is a blocking HTTP request; from an `async def` handler wrap it in
`asyncio.to_thread(...)`. Which calls succeed depends on the
`capabilities` in the service's `service.json` (default `state`,
`events`); a missing one raises `DeskError` (HTTP 403)."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class DeskError(Exception):
    pass


class DeskClient:
    def __init__(self, url: str | None = None, token: str | None = None, name: str | None = None) -> None:
        self._url = url
        self._token = token
        self._name = name

    def _config(self) -> tuple[str, str, str]:
        url = self._url or os.environ.get("DESK_BRIDGE_URL", "")
        token = self._token or os.environ.get("DESK_BRIDGE_TOKEN", "")
        name = self._name or os.environ.get("DESK_SERVICE_NAME", "")
        if not (url and token and name):
            raise DeskError("Not running under Desk (DESK_BRIDGE_URL/DESK_BRIDGE_TOKEN/DESK_SERVICE_NAME unset).")
        return url, token, name

    def _call(self, method: str, path: str, body: dict | None = None, query: dict | None = None, timeout: float = 10.0):
        url, token, name = self._config()
        full = f"{url}{path}"
        if query:
            full += "?" + urllib.parse.urlencode(query)
        headers = {
            "X-Desk-Token": token,
            "X-Desk-Widget-Id": f"hmsvc:{name}",
            "X-Desk-Instance-Id": f"hmsvc:{name}",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(full, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read() or b"null")
        except urllib.error.HTTPError as e:
            raise DeskError(f"{e.code}: {e.read().decode(errors='replace')}") from e
        except urllib.error.URLError as e:
            raise DeskError(str(e.reason)) from e

    # -- state ---------------------------------------------------------

    def state_get(self, key: str, type_hint: str | None = None):
        query = {"key": key}
        if type_hint is not None:
            query["type_hint"] = type_hint
        return self._call("GET", "/api/bridge/state/get", query=query)

    def state_set(self, key: str, value, edit=None, type_hint: str | None = None) -> None:
        self._call("POST", "/api/bridge/state/set", {"key": key, "value": value, "edit": edit, "type_hint": type_hint})

    def workspace_get_state(self) -> dict:
        """Requires the `workspace` capability."""
        return self._call("GET", "/api/bridge/workspace/getState")

    # -- events --------------------------------------------------------

    def events_subscribe(self, names: list[str]) -> None:
        self._call("POST", "/api/bridge/events/subscribe", {"names": names})

    def events_unsubscribe(self, names: list[str]) -> None:
        self._call("POST", "/api/bridge/events/unsubscribe", {"names": names})

    def events_publish(self, name: str, payload=None) -> None:
        self._call("POST", "/api/bridge/events/publish", {"name": name, "payload": payload})

    def events_poll(self, timeout: float = 25.0) -> dict | None:
        """Blocks up to `timeout` seconds (Desk clamps to 30) for the
        next event this service is subscribed to; returns
        `{"timestamp", "name", "sender_instance_id", "payload"}` or
        None on timeout."""
        result = self._call("GET", "/api/bridge/events/poll", query={"timeout": timeout}, timeout=timeout + 10.0)
        return result["event"]


desk = DeskClient()
