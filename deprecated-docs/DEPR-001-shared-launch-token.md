> # ⚠ DEEP-DIVE HISTORY ONLY — NOT CURRENT DOCUMENTATION
>
> This file records an API Desk has **replaced**. It exists only so that someone
> investigating *why* something changed, or reading very old code, can find what
> the old behavior was. **If you are doing anything else, stop reading and use
> the current documentation.** Nothing below describes behavior you should use,
> write against, or explain to a user.
>
> Never load this file into context as a side effect of normal work, and never
> link to it from current docs. See `README.md` in this directory.

# DEPR-001 — Shared per-launch Bridge token with header-asserted identity

- **Deprecated:** a single per-launch token, shared by every Bridge caller, that
  proves only "someone who knows the launch token"; callers state *who they are*
  in the `X-Desk-Widget-Id` / `X-Desk-Instance-Id` request headers and the server
  believes them.
- **Replaced by:** per-instance Bridge credentials (TODO `929e730`). Each placed
  `kind: "html"` widget instance and each hmsvc service gets its own token, which
  `CredentialRegistry` (`src/desk/server/credentials.py`) binds to that caller's
  identity; the server takes identity from the credential and ignores the
  identity headers. Documented (as the only mechanism) in `design-docs/architecture.md` ("Security
  Considerations", the `kind: "html"` widget auth paragraph, the hmsvc paragraph)
  and `design-docs/isolation.md`.
- **Since:** 2026-10-03, TODO `929e730`.
- **Status:** **tombstoned** (2026-10-03, TODO `df8138a`). A request that presents
  only the shared launch token and asserts an identity in the identity headers is
  reported to Desk and refused with HTTP 403 and the tombstone message (the shared
  token still authenticates routes that need no identity, such as `/api/ping` and
  page assets). Before that it had been *transitional* (TODO `929e730`): still
  accepted, with a one-time warning, and switchable off via
  `allow_legacy_identity=False` / `DESK_BRIDGE_ALLOW_LEGACY_IDENTITY=0` -- that
  switch and the warning were removed in the conversion.
- **How you'd notice:** the 403 body (naming DEPR-001, what to use, and a command
  for an agent), a report in Desk, and the `[ERROR]` marker on the claimed widget.
- **Removal condition:** the tombstone is the end state under the new model; whether
  tombstones are ever deleted is an open question in the process plan.

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

From `architecture.md`, the Bridge API capability/identity paragraph:

> The caller identifies
> its *kind* via an `X-Desk-Widget-Id` header the injected client library
> attaches automatically, and (TODO `5734529`) its specific *instance* via
> a sibling `X-Desk-Instance-Id` header — `ChromiumWidget`/the injected
> client are both constructed with a concrete `instance_id` up front (see
> `DeskWindow._place_widget`), the same identity `WidgetState`/`WidgetFrame`
> already carry, just newly threaded all the way to the calling page itself
> (nothing before TODO `5734529` let the server tell two same-kind widget
> instances apart at all, which `self.getLocalStorage`/`setLocalStorage`
> fundamentally needs — `WidgetState.state` is per-*instance*).
> `self.getLocalStorage`/`setLocalStorage` deliberately resolve the caller
> from that header alone, not via the same `discover_widgets(widgets_dir)`
> lookup every other route uses (which only ever finds real, on-disk
> `widgets/<id>/` directories — see `PARKINGLOT.md` for the resulting gap
> this doesn't fully close for tempui-DSL-defined custom widgets and every
> *other* Bridge capability).
