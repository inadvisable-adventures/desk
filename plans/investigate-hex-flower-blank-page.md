# Investigate widgets/hex_flower's blank page, write a DESK_FEEDBACK doc (COMPLETED)

TODO `4ab5875`.

## Summary

`widgets/hex_flower` (a `kind: "html"` widget another Claude instance
built, porting `../../claude-projects/hexsheet`'s hex-flower sheet
item -- TypeScript compiled via `tsc` to `dist/*.js`, plain CSS files,
loaded by `index.html` via ordinary relative-path `<script src>`/
`<link href>` tags) renders as a blank page. Deliverable requested:
investigate the root cause and write `DESK_FEEDBACK-<timestamp>.md`
with (a) documentation suggestions and (b) tempui-widget-feature
improvement suggestions -- not a code fix to `hex_flower` or to Desk
itself, which is deliberately out of scope for this item (see the doc
itself for why).

## Diagnosis approach

Read `widgets/hex_flower`'s own source first (`widget.json`,
`index.html`, `dist/*.js`, the `src/*.ts` they were compiled from) --
found nothing that would explain a blank page from the code alone
(real built output exists, `customElements.define('hex-flower', ...)`
is present, no obviously-throwing top-level module code, correct
`kind: "html"` manifest).

Confirmed the Local Web Server itself serves every one of `hex_flower`'s
assets correctly (200, correct `Content-Type`) when fetched with the
per-launch token attached -- ruling out a missing/misconfigured MIME
type or a genuinely missing build artifact.

Built a headless diagnostic harness (`QT_QPA_PLATFORM=offscreen`, a
real `QWebEnginePage`/the real `ChromiumWidget` class, `page
.javaScriptConsoleMessage` overridden to capture console output,
`page.runJavaScript` to inspect the live DOM after load) to actually
load the widget the same way the real Shell does and observe what
happens -- zero console messages, and `document.querySelector
('hex-flower').shadowRoot` is `null` (the custom element's
`connectedCallback` never ran, meaning `customElements.define` for it
never executed, meaning the module script graph never finished
evaluating).

Isolated the cause with a minimal from-scratch reproduction (a trivial
`kind: "html"` widget with one external classic `<script src>`) run
through the exact same harness -- reproduced instantly, independent of
anything specific to `hex_flower`'s own code. Fetching that same
external script *without* the token query parameter directly (`curl`
-equivalent via `urllib`) returns `401 Unauthorized`; with it, `200`.
Root cause confirmed directly, not inferred: **`TokenAuthMiddleware`
requires the per-launch token on every request (query param or
`X-Desk-Token` header) — the main widget page's own URL carries the
token as a query parameter, but a plain relative-path browser resource
reference (`<script src="dist/main.js">`, `<link href="styles.css">`)
resolves to a URL that does *not* inherit the original query string at
all (standard URL-resolution semantics: a relative reference replaces
the whole path+query, it doesn't append to it) — so every such
sub-resource request arrives with no token and gets rejected. The
browser has no way to attach a custom header or preserve the query
string for a plain `<script src>`/`<link>` tag; only `fetch()`
-initiated requests (which is exactly what the injected Bridge client
does) can. This affects every `kind: "html"` widget with any file
*not* inlined into its single entry HTML document -- which is every
ordinary, non-tempui-DSL `kind: "html"` widget built the normal way.
Tempui's own `DefineWidget`-created widgets never hit this, purely as
a side effect of being forced to be one self-contained inline HTML
document by design (TODO `91b3f42`) -- not because anyone had
diagnosed or intentionally avoided this bug.

Also checked whether `hex_flower`'s own state-persistence approach
(ported from `hexsheet`'s `RegisterDatastore`/`RegisterSignalSender`
custom-event protocol, dispatched to a "sheet" parent controller that
doesn't exist in Desk) uses the Desk Bridge API's `self.getLocalStorage`/
`setLocalStorage` (TODO `5734529`) at all -- it doesn't; those events
just bubble up and are silently ignored in Desk's environment, a
second, independent finding worth feeding back.

## Deliverable

`DESK_FEEDBACK-2026-07-13T012144.md` (project root, alongside
`TODO.md`/`PARKINGLOT.md`/`LEARNINGS.md`) -- the diagnosis above,
plus organized (a) documentation and (b) tempui-widget-feature
improvement suggestions, the most significant being: fix the
token-vs-relative-path auth gap (a same-origin cookie set on the main
page load, checked as a third fallback alongside the existing query
-param/header checks, is the standard web-platform answer -- cookies
*are* automatically attached by the browser to every same-origin
sub-resource request, unlike headers/query strings on a plain
`<script src>`); document the constraint explicitly in both
`design-docs/architecture.md` (which currently doesn't mention it
under `kind: "html"` at all) and, once genuinely non-Desk-repo
-referencing content exists to say it, somewhere the DefineWidget/
Bridge API tempui docs would benefit from it too; and, once the auth
gap is fixed, consider extending `DefineWidget` to support more than
one file so a custom widget doesn't have to inline everything into
one document just to sidestep this constraint.

## Affected files

- `DESK_FEEDBACK-2026-07-13T012144.md` (new, project root) -- the
  actual deliverable.

No source code changed -- deliberately out of scope for this item
(see the feedback doc's own framing of what's proposed vs. actually
implemented here).

## Verification

Every claim in the feedback doc is backed by a directly-run, real
check performed during this investigation (not inferred/guessed):
real `Content-Type`/status checks against the running Local Web
Server for every `hex_flower` asset; a real `ChromiumWidget`
loading the real widget and confirming, via `page.runJavaScript`,
that the custom element never upgrades; a minimal from-scratch
reproduction confirming the bug is general, not `hex_flower`-specific;
a direct `urllib` fetch confirming the exact 401-without-token/
200-with-token behavior that explains the mechanism precisely.
