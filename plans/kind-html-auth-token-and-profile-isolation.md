# Fix kind:"html" widgets losing the auth token on sub-resource requests, with per-instance Chromium profile isolation (TODO `a5f66cc`)

## Summary

`kind: "html"` widgets are served with the per-launch auth token as a
query parameter on the top-level navigation
(`ServerHandle.widget_url`), but an ordinary relative-path browser
reference (`<script src>`, `<link href>`, CSS `url(...)`, `<img src>`)
does not carry that query string forward, and a native resource tag
can't attach a custom header either. Every such sub-resource request
therefore arrives at `TokenAuthMiddleware` with no credential, gets
401'd, and silently aborts the module/resource graph with no console
output. This affects any `kind: "html"` widget built as an ordinary
multi-file web project (only single-inlined-file `DefineWidget`
widgets avoid it, as a side effect of their format, not by design).

Fix: a same-origin cookie carrying the token, set on the widget's
main-page response, additive to the existing query-param/header
checks. Folded into the same item, per discussion with the user: give
each `ChromiumWidget` instance its own persistent `QWebEngineProfile`
(today every instance shares Qt's default profile — confirmed no
`QWebEngineProfile` is constructed anywhere in the codebase), so the
new token cookie — and all other browser storage this widget's own JS
or an external service might set — is scoped to that one instance,
not shared across every `kind: "html"` widget on the origin.

## Affected files

- `src/desk/server/app.py` — `_token_from_scope` gains a cookie
  fallback; `TokenAuthMiddleware` sets the cookie on the widget-page
  response.
- `src/desk/shell/chromium_widget.py` — `ChromiumWidget`/
  `_LoggingWebEnginePage` take a `profile_dir` and construct/use a
  per-instance `QWebEngineProfile` instead of the implicit default.
- `src/desk/shell/window.py` — `_place_widget` computes and passes
  `profile_dir`; `close_widget` deletes it on permanent removal.
- `design-docs/architecture.md` — documents the token requirement and
  the per-instance profile isolation property.
- `tests/verify/verify_shared_document_editor_base.py` — update its 4
  direct `ChromiumWidget(...)` constructions for the new required
  `profile_dir` argument.
- `tests/verify/` — new coverage (see Verification).

## Design decisions

- **Cookie is additive, never a replacement.** The existing
  query-param (top-level nav) and `X-Desk-Token` header (Bridge XHR
  calls, per `bridge_client.py`'s `call()` helper) checks are
  untouched; the cookie only covers the gap those two don't (a plain
  relative-path resource load with no way to carry either).
- **Cookie is set only when auth succeeded via the query param
  specifically** (not on every already-authenticated request) — the
  query param is, in practice, only ever present on the widget's own
  top-level page navigation (Bridge calls always use the header), so
  this naturally fires exactly once per real page load, not on every
  request.
- **Cookie attributes**: `HttpOnly` (no reason page JS needs to read
  it — and it's already exposed to the page via the injected Bridge
  client script regardless, so this doesn't reduce any existing
  exposure, it just avoids adding a new avenue), no `Secure` (plain
  HTTP over loopback), `SameSite=Lax`, `Path=/`, no explicit
  `Max-Age`/`Expires` — session-lifetime is fine since the very first
  navigation of any new launch already carries a fresh `?token=` that
  re-sets the cookie immediately; correctness never depends on the
  cookie surviving to the next launch.
- **Why per-instance profiles, not just a shared-profile cookie.**
  Cookies are scoped by host+path, not port (RFC 6265) — Desk's
  per-launch port changes but its host (`127.0.0.1`) doesn't, and
  every `kind: "html"` widget already shares one origin (same
  host:port, different paths). A cookie on the shared default profile
  would (a) be attached to every widget instance's requests, not just
  the one that set it, and (b) persist indefinitely in Qt's on-disk
  persistent cookie jar across separate Desk launches, accumulating
  one stale token per historical port forever. Neither is a real
  security problem (the token already isn't treated as secret from
  the page), but both are avoidable by construction: giving each
  instance its own profile makes the cookie (and everything else)
  inherently scoped to that instance, with no cross-instance sharing
  and no accumulation beyond one instance's own tiny profile.
- **Profile location: `.desk_temp/chromium-profiles/<instance_id>/`**,
  using `setPersistentStoragePath`/`setCachePath` to point there
  explicitly rather than relying on `QWebEngineProfile`'s own
  storage-name-derived default location (which would put it in the
  OS's global app-data directory, not travel with the project).
  `instance_id` is already the stable, restart-surviving identity
  `desk.self.getLocalStorage` relies on for the same reason — reused,
  not reinvented.
- **`.desk_temp/`'s "fully disposable, regenerate on demand"
  convention doesn't apply to this subdirectory.** Real per-widget
  browser storage (cookies/localStorage a widget's own JS or an
  external service sets) isn't regenerable the way compiled JS output
  is. Called out explicitly in the doc update and in a code comment,
  not left implicit.
- **Cleanup**: `DeskWindow.close_widget` (permanent removal) deletes
  the instance's profile directory; `WorkspaceView.clear_widgets`
  (Desk-switch) does not — a widget merely removed from the canvas
  temporarily still needs its profile intact for when that Desk
  reopens. Deletion is deferred via `QTimer.singleShot(0, ...)`,
  scheduled after `frame.deleteLater()`'s effect, matching this
  codebase's established caution around Qt's own deferred-deletion
  timing (see e.g. `_position_desk_picker`'s docstring for the same
  general pattern elsewhere).
- **`widgets/browser/widget.py`'s `BrowserWidget` is untouched.** It's
  a structurally separate `kind: "python"` widget with its own plain
  `QWebEngineView()`, not built on `ChromiumWidget` — confirmed
  directly by reading it, not assumed. It keeps using Qt's default
  profile (real, persisted logins/cookies for actual web browsing)
  exactly as today; nothing in this change touches it.
- **No new abstraction for "get a widget's profile directory."** Both
  `_place_widget` and `close_widget` compute
  `current_desk.directory / TEMP_UI_DIRNAME / "chromium-profiles" /
  instance_id` inline — two call sites, not enough to justify a
  shared helper function yet.

## Step-by-step implementation

1. `chromium_widget.py`: `ChromiumWidget.__init__` gains a
   `profile_dir: Path` parameter (positional, required — every real
   call site must decide this explicitly, no silent fallback to the
   shared default profile). Construct
   `self._profile = QWebEngineProfile(f"widget-{instance_id}", self)`,
   then `setPersistentStoragePath(str(profile_dir / "storage"))` and
   `setCachePath(str(profile_dir / "cache"))`. `_LoggingWebEnginePage
   .__init__` gains a `profile` parameter, forwarded to
   `QWebEnginePage.__init__(profile, parent)`; `ChromiumWidget`
   constructs it as `_LoggingWebEnginePage(self._profile, self)`.
2. `window.py`: `_place_widget`'s `kind == "html"` branch computes
   `profile_dir = self.current_desk.directory / TEMP_UI_DIRNAME /
   "chromium-profiles" / instance_id` and passes it to
   `ChromiumWidget(...)`.
3. `window.py`: `close_widget` captures `frame.instance_id` before
   `self.view.remove_widget(frame)`, then (after the existing
   confirm/remove/unsubscribe/save sequence) schedules deletion of
   that instance's profile directory via `QTimer.singleShot(0, lambda:
   shutil.rmtree(profile_dir, ignore_errors=True))` if it exists.
   `shutil` is already imported in this file.
4. `app.py`: `_token_from_scope` adds a third check — parse the
   `cookie` header (stdlib `http.cookies.SimpleCookie`) for a
   `desk_token` cookie, checked after the query param and header.
   `TokenAuthMiddleware.__call__`: when the token specifically came
   from the query string, wrap `send` to inject a `Set-Cookie` header
   on the `http.response.start` message before forwarding.
5. `design-docs/architecture.md`: add the token-requirement paragraph
   to the `kind: "html"` widget description, and a note under
   Security Considerations about per-instance profile isolation
   (extending the existing "own renderer process" claim to
   storage/cookies/cache too).
6. `tests/verify/verify_shared_document_editor_base.py`: give each of
   the 4 direct `ChromiumWidget(...)` calls a `profile_dir` (a
   subdirectory under that test's own tempdir, keyed by instance id —
   doesn't need to be `.desk_temp`-shaped since this test isn't
   exercising `_place_widget`).
7. New verify coverage (see below); run the full `tests/verify/`
   suite.

## Key tradeoffs

- N separate on-disk profile directories (SQLite-backed cookie/cache/
  storage stores) instead of one shared one — real but small per-
  widget overhead; not benchmarked here, judged acceptable given the
  isolation/correctness benefit and that `kind: "html"` widgets are
  not the common case for most Desks.
- No general "reconsider `DefineWidget`'s single-file requirement" or
  "visible failure signal for a blank widget" work here — deliberately
  left parked in `PARKINGLOT.md` as follow-ups, per the discussion
  that led to this item.

## Verification

New script(s) in `tests/verify/`, real (no mocking) throughout:

- A real multi-file `kind: "html"` widget fixture (an `index.html`
  with an external `<script src>` referencing a sibling file that
  defines and registers a custom element) now loads successfully end
  -to-end through a real `ChromiumWidget`/local web server — the
  custom element's `shadowRoot` is non-null after load (mirroring the
  original hex_flower diagnosis's own verification method), where it
  would have been `null` before this fix.
- The widget-page HTTP response actually carries a `Set-Cookie` header
  for the token (checked via a real HTTP client against the running
  server, not through Qt).
- A follow-up HTTP request carrying only the cookie (no query param, no
  `X-Desk-Token` header) is accepted by `TokenAuthMiddleware`.
- Two `ChromiumWidget` instances of the same widget kind get distinct,
  real on-disk profile directories once used.
- `close_widget` deletes a permanently-removed instance's profile
  directory; a Desk-switch (`clear_widgets`) does not remove a
  still-placed widget's profile directory.
- `BrowserWidget`'s own `QWebEngineView().page().profile()` is
  unchanged (`QWebEngineProfile.defaultProfile()`), confirming this
  change doesn't touch it.
- Full `tests/verify/` regression suite (including the updated
  `verify_shared_document_editor_base.py`).
