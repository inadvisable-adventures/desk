# ChromiumWidget: handle featurePermissionRequested, capability-gated media grant (TODO 2dbfd55) (COMPLETED)

## Summary

`ChromiumWidget` never connects `QWebEnginePage.featurePermissionRequested`.
A `kind: "html"` widget calling `getUserMedia` (e.g. via the Web Speech API)
currently gets Chromium's own default handling of an unanswered permission
request rather than a normal, catchable `NotAllowedError` -- the report
calls "an unhandled permission request causes the blanking" plausible.
Per direct user request, this TODO no longer requires a repro first and
the capability-gated grant is required, not a follow-up. Cites
`../FEEDBACK/FEEDBACK-DESK-html-widget-getusermedia-crash-2026-09-11-1735.md`
(suggested fix 1).

## Approach

A new `media` Bridge-style capability (the same coarse, resource-level
vocabulary as `workspace`/`fs`/`events`/... -- declared in a real
`widgets/<id>/widget.json`'s `"capabilities"` list, or a `DefineWidget`'s
`Capability<TAB>media` line), gating only the three "is this page allowed
to use the mic/camera" features Qt exposes (`MediaAudioCapture`,
`MediaVideoCapture`, `MediaAudioVideoCapture`). Every other
`QWebEnginePage.Feature` (`Geolocation`, `Notifications`,
`ClipboardReadWrite`, `DesktopVideoCapture`/`DesktopAudioVideoCapture`,
`MouseLock`, `LocalFontsAccess`) is out of scope for this TODO and always
denied -- not silently ignored, which is Chromium's own default and the
bug being fixed.

1. `ChromiumWidget.__init__` gains a `capabilities: Sequence[str] = ()`
   keyword-only-by-convention parameter (given a default so every
   existing positional call site, which passes exactly six positional
   args today, is unaffected), stored on `self`.
2. Connect `self._logging_page.featurePermissionRequested` to a new
   `_on_feature_permission_requested(origin, feature)`: grants (via
   `setFeaturePermission(origin, feature, PermissionGrantedByUser)`) only
   when `feature` is one of the three media features above and `"media"`
   is in `self._capabilities`; denies (`PermissionDeniedByUser`)
   otherwise. Logs the decision at INFO (widget id, feature, granted?) --
   a real breadcrumb, not silence, matching this file's existing
   logging-over-silence convention (e.g. `_on_render_process_terminated`).
3. `DeskWindow._place_widget` passes `widget.capabilities` through.
4. `desk.temp_ui`: `_CUSTOM_WIDGETS_DOC`'s `Capability` line and
   "Authoring from real source" `widget.json` paragraph gain `media` to
   their example capability lists; a short new subsection under "The
   Desk Bridge API" (or right after the capability list) names `media`
   specifically, since it is Qt-permission-gated rather than an HTTP
   Bridge route like the others -- says what it grants (`getUserMedia`
   for audio/video) and that every other browser permission stays denied
   regardless. New tag + `_NEW_FEATURES` entry (agent-visible).
5. Packaging note, not code: the macOS microphone *usage entitlement*
   (`NSMicrophoneUsageDescription`) is a property of the packaged app
   bundle, and this repo has no packaging/bundling target yet
   (`design-docs/architecture.md`'s own "Open Questions" already lists
   packaging as undecided) -- nothing here to add it to. Left as a
   one-line note in that same Open Questions entry so it isn't lost,
   not implemented as code.

## Affected files

- `src/desk/shell/chromium_widget.py`
- `src/desk/shell/window.py` -- one call site
- `src/desk/temp_ui.py` -- doc text, tag, `_NEW_FEATURES`
- `design-docs/architecture.md` -- one-line packaging note
- `tests/verify/verify_chromium_widget_media_permission.py` -- new

## Verification

Real `ChromiumWidget`/`QWebEnginePage`, no mocks: a page calling
`navigator.mediaDevices.getUserMedia({audio: true})` resolves when built
with `capabilities=["media"]` and rejects with `NotAllowedError` when
built with `capabilities=[]` -- both confirmed by JS actually running in
the page (`page().runJavaScript`), not by asserting the Qt call was made.
Also: a non-media feature (`Notifications.requestPermission()`) is denied
regardless of `media` capability. Directly drive
`_on_feature_permission_requested` for the exact `setFeaturePermission`
policy passed per feature, covering all three media features and one
non-media one. Re-run `verify_chromium_widget_crash_restart.py`,
`verify_kind_html_auth_token_and_profile_isolation.py`,
`verify_shared_document_editor_base.py` (existing `ChromiumWidget` call
sites, unaffected by the new default-valued parameter). Full
`tests/verify/` sweep.

## Status

Implemented as planned. One correction found during verification: a
denied `getUserMedia()` in this QtWebEngine/Chromium build actually
rejects with `AbortError` ("Invalid state"), not the spec-typical
`NotAllowedError` the TODO's wording assumed -- confirmed directly, so
the test (and this note) check that the promise settles/rejects at all
rather than hardcoding an exception name that turned out to be this
engine's own implementation detail. Also verified directly, before
trusting the other checks: disconnecting `featurePermissionRequested`
reproduces the original bug (the request is left pending forever).

Every non-media `QWebEnginePage.Feature` (tested via `Notifications`) is
always denied, capability or not -- out of this TODO's scope to grant.

The macOS microphone usage entitlement is a packaging-bundle property;
this repo has no packaging target yet (`design-docs/architecture.md`'s
own "Open Questions" already said so), so it's recorded as a note there
instead of code.

Verified: the new `verify_chromium_widget_media_permission.py` (real
`ChromiumWidget`/`QWebEnginePage`, no mocks -- actual `getUserMedia()`/
`Notification.requestPermission()` JS calls plus a direct-call policy
matrix), run 3x for flakiness. Full `tests/verify/` sweep (157 scripts)
passes. Browser launch not needed.

This was the last open item citing
`../FEEDBACK/FEEDBACK-DESK-html-widget-getusermedia-crash-2026-09-11-1735.md`
(b89cf17/aa0ce76/5abf5a0 completed by a separate session working on this
repo concurrently) -- moved to `../FEEDBACK/implemented/`.
