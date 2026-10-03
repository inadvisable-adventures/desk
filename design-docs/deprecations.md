# Desk — Deprecations

Tracks things Desk still supports but has replaced: what the old way was, what
replaces it, where it stands, and what has to happen before it is removed. The
**original documentation of each deprecated option is preserved verbatim** here,
so it stays findable after the main docs have moved on to the replacement.

How deprecations are managed in general (warning, tracking, removal criteria) is
not settled yet -- TODO `df8138a` is to plan that process. Until then this file
is the single place to look, and each entry states its own status.

## Entry format

- **Deprecated** -- the old way, in one line.
- **Replaced by** -- the new way, and where it is documented.
- **Since** -- the date (and TODO) it was deprecated.
- **Status** -- still supported / warns / can be switched off / removed.
- **How you'd notice** -- what a caller using the old way sees.
- **Removal condition** -- what would have to be true to remove it.
- **Original documentation (verbatim)** -- the text that used to describe it.

---

## 1. Shared per-launch Bridge token with header-asserted identity

- **Deprecated:** a single per-launch token, shared by every Bridge caller, that
  proves only "someone who knows the launch token"; callers state *who they are*
  in the `X-Desk-Widget-Id` / `X-Desk-Instance-Id` request headers and the server
  believes them.
- **Replaced by:** per-instance Bridge credentials (TODO `929e730`). Each placed
  `kind: "html"` widget instance and each hmsvc service gets its own token, which
  `CredentialRegistry` (`src/desk/server/credentials.py`) binds to that caller's
  identity; the server takes identity from the credential and ignores the
  identity headers. Documented in `architecture.md` ("Security Considerations",
  the `kind: "html"` widget auth paragraph, the hmsvc paragraph) and
  `isolation.md`.
- **Since:** 2026-10-03, TODO `929e730`.
- **Status:** still supported, and the default for any caller that presents the
  shared launch token (`ServerHandle.token`, `?token=` on `handle.url`, and a
  `ServerHandle` or `HmsvcManager` that was not given a credential registry).
  Desk's own widgets and services no longer use it. Can be switched off:
  `create_app(..., allow_legacy_identity=False)` /
  `start_server(..., allow_legacy_identity=False)` or the environment variable
  `DESK_BRIDGE_ALLOW_LEGACY_IDENTITY=0` make every identity-bearing Bridge route
  refuse it with HTTP 403 (the shared token still authenticates routes that need
  no identity, such as `/api/ping`).
- **How you'd notice:** one WARNING per (widget id, instance id) from the
  `desk.bridge` logger: "Bridge caller ... is using the deprecated shared-token,
  header-asserted identity; see design-docs/deprecations.md".
- **Removal condition:** nothing Desk ships uses it (true as of this entry apart
  from test fixtures that stand in for older handles); strict mode has been the
  default for a release without breaking anything; any external scripts known to
  use it have a migration path. To be formalised by TODO `df8138a`.

### Original documentation (verbatim)

From `architecture.md`, "Security Considerations":

> - The Local Web Server (used only for `kind: "html"` widgets) binds to
>   `127.0.0.1` only and uses an unpredictable, per-launch port plus a
>   per-launch token required on all requests, so other local
>   processes/browser tabs can't drive Desk.

From `architecture.md`, the `kind: "html"` widget auth paragraph:

> Every request the browser makes for a widget's own page — not just the
> top-level navigation — must carry the per-launch auth token
> (`TokenAuthMiddleware`, `src/desk/server/app.py`). The top-level
> navigation carries it as a query parameter; the injected Bridge client's
> own calls carry it as an `X-Desk-Token` header; and (TODO `a5f66cc`) a
> same-origin cookie set on the widget's main-page response covers
> everything else

From `architecture.md`, the Desk-hosted microservices paragraph:

> A service reaches Desk through `desk.hmsvc_client.desk` (stdlib `urllib`,
> reading `DESK_BRIDGE_URL`/`DESK_BRIDGE_TOKEN`), which calls the
> **existing** Bridge routes (state, events, workspace) rather than a
> parallel API: `require_caller` accepts the synthetic widget id
> `hmsvc:<name>` (also the mediator instance id) with capabilities
> from `service.json`.

From `TokenAuthMiddleware`'s original docstring (`src/desk/server/app.py`):

> Rejects any HTTP/WebSocket request that doesn't carry the per-launch
> token, so only the Shell (which knows the token) can talk to this
> server. See design-docs/architecture.md#security-considerations.

From `HmsvcManager.configure_bridge`'s docstring (`src/desk/hmsvc.py`, still
current and still used for the legacy fallback):

> Where a service reaches Desk's Bridge API (base URL, no trailing slash) and the
> per-launch token; set once the Local Web Server is up.
