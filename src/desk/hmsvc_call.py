"""Calling a Desk-hosted microservice (hmsvc) over HTTP on behalf of an agent (TODO ffd183b).

Qt-free and stdlib-only (urllib). A service is an ASGI app on a loopback port that is new on every launch, so
the target is resolved from the HmsvcManager at call time -- the caller names a service, never a host or port.
Redirects are not followed (a service must not be able to bounce the request to another host), the request path
must be a plain absolute path, and the response body is capped. An HTTP error status (404, 500, ...) is a
normal result, not an exception: the agent needs to see the service's own error body.
"""
import json
import re
import urllib.error
import urllib.request

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 120.0
MAX_RESPONSE_CHARS = 100_000
MAX_REQUEST_BYTES = 1_000_000
_FORBIDDEN_HEADERS = {"host", "content-length", "connection", "transfer-encoding"}
_BAD_PATH = re.compile(r"[\s\x00-\x1f\x7f\\]")


class HmsvcCallError(Exception):
    """Something the caller can act on: unknown or stopped service, a bad path, a transport failure."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # surfaces the 3xx as an HTTPError, which call_service returns as a normal result


def _validate_path(path: object) -> str:
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or _BAD_PATH.search(path):
        raise HmsvcCallError(
            "path must be a plain absolute path such as /items?x=1: it starts with a single '/', with no spaces, "
            "backslashes or control characters (the service is chosen by `name`, not by the URL)."
        )
    return path


def call_service(
    manager,
    name: str,
    method: str = "GET",
    path: str = "/",
    json_body: object = None,
    body: str | None = None,
    headers: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """One HTTP request to the named, running service. Returns {service, status, content_type, truncated, body}."""
    if not isinstance(name, str) or not name.strip():
        raise HmsvcCallError("name must be the service name (see desk_list_hmsvcs).")
    method = str(method or "GET").upper()
    if method not in METHODS:
        raise HmsvcCallError(f"method must be one of {', '.join(METHODS)}.")
    path = _validate_path(path)
    if json_body is not None and body is not None:
        raise HmsvcCallError("Give json or body, not both.")
    if method in ("GET", "DELETE") and (json_body is not None or body is not None):
        raise HmsvcCallError(f"A {method} request carries no body; use query parameters in path, or POST.")
    try:
        timeout = min(MAX_TIMEOUT_SECONDS, max(1.0, float(timeout)))
    except (TypeError, ValueError):
        raise HmsvcCallError("timeout must be a number of seconds.") from None

    info = manager.get(name.strip())
    if info is None:
        known = ", ".join(s["name"] for s in manager.list_services()) or "(none in this project)"
        raise HmsvcCallError(f"No microservice named {name!r}. Services here: {known}.")
    if not info.get("url"):
        raise HmsvcCallError(
            f"Microservice {name!r} is {info['status']}, so it has no address to call. Start it from the "
            "Microservices widget (or ask the user to), then try again."
        )

    data = None
    request_headers = {"Accept": "application/json, text/plain;q=0.9, */*;q=0.5"}
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    elif body is not None:
        if not isinstance(body, str):
            raise HmsvcCallError("body must be a string; use json for structured data.")
        data = body.encode("utf-8")
        request_headers["Content-Type"] = "text/plain; charset=utf-8"
    if data is not None and len(data) > MAX_REQUEST_BYTES:
        raise HmsvcCallError(f"The request body is larger than {MAX_REQUEST_BYTES} bytes.")
    for key, value in (headers or {}).items():
        if not isinstance(key, str) or not isinstance(value, str) or not key.strip() or "\n" in key + value or "\r" in key + value:
            raise HmsvcCallError("headers must map header names to single-line string values.")
        if key.strip().lower() in _FORBIDDEN_HEADERS:
            raise HmsvcCallError(f"The {key.strip()} header is set by Desk and cannot be overridden.")
        request_headers[key.strip()] = value

    url = info["url"].rstrip("/") + path
    request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as e:
        response = e  # a normal result: the service's own error body is what the agent needs
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        raise HmsvcCallError(f"Could not reach microservice {name!r} ({reason}). Its status is {info['status']}.") from None
    try:
        raw = response.read(MAX_RESPONSE_CHARS * 4 + 1)
        status = response.status if hasattr(response, "status") else response.code
        content_type = response.headers.get("Content-Type", "")
        location = response.headers.get("Location")
    finally:
        response.close()
    text_like = (not content_type) or any(t in content_type.lower() for t in ("text", "json", "xml", "javascript", "yaml", "html", "csv"))
    if not text_like:
        text, truncated = f"(binary response, {len(raw)}{'+' if len(raw) > MAX_RESPONSE_CHARS * 4 else ''} bytes; not shown)", False
    else:
        text = raw.decode("utf-8", errors="replace")
        truncated = len(text) > MAX_RESPONSE_CHARS
        text = text[:MAX_RESPONSE_CHARS]
    result = {"service": name.strip(), "status": status, "content_type": content_type, "truncated": truncated, "body": text}
    if location:
        result["location"] = location  # a redirect is reported, not followed
    return result
