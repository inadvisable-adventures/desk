# Bind Bridge credentials to the calling instance (TODO `929e730`) (COMPLETED)

## Summary
Today one per-launch token is shared by every Bridge caller and the caller's
identity comes from client-supplied headers, so a widget could assert another's
identity (see `design-docs/isolation.md`). Issue each placed instance (and each
hmsvc service) its own token; the server maps token -> identity itself.

## Affected files
`src/desk/server/credentials.py` (new), `src/desk/server/app.py`,
`src/desk/server/runner.py`, `src/desk/hmsvc.py`, `src/desk/shell/window.py`,
`design-docs/architecture.md`, `design-docs/isolation.md`,
`deprecated-docs/DEPR-001-shared-launch-token.md` (new; moved there from `design-docs/` when the isolation rule was adopted), `TODO.md`,
`tests/verify/verify_bridge_per_instance_credentials.py` (new).

## Design
- **`CredentialRegistry`** (Qt-free, thread-safe): `issue(widget_id, instance_id)`
  returns a fresh `secrets.token_urlsafe(32)` bound to that identity (re-issuing
  for an instance revokes its previous token); `issue_service(name)` binds
  `hmsvc:<name>` for both ids (the existing synthetic caller id); `lookup`,
  `revoke_instance`, `revoke_all_instances`.
- **Middleware** accepts, from the same three places as before (query param,
  `X-Desk-Token`, cookie), either a registered per-instance token (the request
  gets a server-set identity in `scope["desk_identity"]`) or the legacy shared
  launch token. The cookie-setting path is unchanged and generic, so a page
  loaded with its per-instance token sets *that* token as its sub-resource
  cookie.
- **Identity dependencies** (`require_caller`, `require_instance_id`,
  `self/getManifest`) take the identity from `scope["desk_identity"]` when
  present and **ignore the identity headers entirely** (a mismatching header is
  not an error, it is simply not trusted). Without a bound identity they behave
  exactly as before (headers required) -- the **deprecated legacy path, kept
  available** per the user's instruction -- but log a one-time
  "legacy identity" warning per (widget id, instance id), and `allow_legacy_
  identity=False` (also `DESK_BRIDGE_ALLOW_LEGACY_IDENTITY=0`) turns it into a
  403, as the strict mode a future removal would make the default.
- **Issuing**: `DeskWindow._place_widget` issues a per-instance token for every
  `kind: "html"` instance (page URL, injected Bridge client and hence cookie all
  use it) and revokes it on close and on a Desk switch; if the handle has no
  registry (older fakes) it falls back to the shared token. `HmsvcManager`
  issues one per service start via configurable issuer/revoker and revokes it
  when the process ends; unconfigured it keeps using the shared token.
- **Docs**: the security/auth sections of `architecture.md` describe the
  per-instance mechanism; the old shared-token + header-identity description is
  moved, verbatim, into the isolated `deprecated-docs/` directory (DEPR-001), which
  current docs never link to. TODO `df8138a` plans the deprecation process
  (tombstones) itself.

## Verification
Registry unit tests; real-server tests: a per-instance token's identity wins
over spoofed headers (A's token plus B's id gets A's capabilities, not B's), a
service token acts as `hmsvc:<name>`, a revoked token is 401, the legacy shared
token + headers still works and warns once, strict mode refuses legacy identity,
cookie path carries the per-instance token. Whole suite (the 38 existing server
tests exercise the legacy path).
