# MCP tools for agents to call hmsvcs in the hosting Desk (TODO `ffd183b`) (COMPLETED)

User request (2026-11-18): "MCP tool with which agents can call hmsvcs in the hosting desk."

hmsvc (`src/desk/hmsvc.py`) services are ASGI apps on a loopback port that is new on every launch. Before this, only a
widget could reach one (`desk.hmsvc.list()` for the URL, then its own `fetch`); an agent had no way in.

## Design

- **`desk_call_hmsvc(name, method?, path?, json?, body?, headers?, timeout?)`** -- one HTTP request to a *running* service
  of the current project (the MCP server runs inside Desk, so "the hosting Desk" is `DeskWindow._hmsvc`). Returns
  `{service, status, content_type, truncated, body}` (plus `location` for a redirect).
- **`desk_list_hmsvcs()`** -- read-only list (name, description, status, loopback url) so an agent can discover services.
  Needed because the tool takes a name, and the ports change.
- The agent names the service, **never a host or port**; the URL is built from the manager's loopback address.
- Safety: path must be a plain absolute path (single leading `/`, no whitespace/backslash/control characters) so it can
  never retarget the request; **redirects are not followed** (reported with `location`); `Host`/`Content-Length`
  etc. cannot be overridden; header injection refused; request body capped at 1 MB; response text capped at 100 KB
  (`truncated` flag); binary responses are not shown; timeout default 30 s, at most 120 s.
- An HTTP error status (404, 500) is a **normal result** -- the agent needs the service's own error body. Only a missing,
  stopped or unreachable service, or a malformed request, is a tool error.
- **Does not start a stopped service** (the user starts it from the Microservices widget); the error says so. Starting
  arbitrary project code on an agent's say-so seemed worth a deliberate decision.
- stdlib `urllib` only (no dependency), in `src/desk/hmsvc_call.py` (Qt-free), run via `asyncio.to_thread`.

## Verification

`tests/verify/verify_hmsvc_call.py` (36 checks): a real stdlib HTTP server as the service, all methods, JSON/text
bodies, headers, 404 and redirect handling, truncation, binary, timeouts, every refusal, both MCP tools, the docs/tag.
Also run once by hand against a real `HmsvcManager` with a real FastAPI service subprocess (GET with a query and a POST
with JSON both returned correctly). Not tried from a live agent session.
