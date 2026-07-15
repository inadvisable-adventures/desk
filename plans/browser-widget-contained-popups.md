# Fix: Browser widget pop-ups escape into a separate macOS window

TODO `e35bcf0`.

## Summary

Reported: a page loaded in the Browser widget (`widgets/browser/`,
`kind: "python"`, a plain `QWebEngineView`) that opens a pop-up (a
`window.open()` call, or a `target="_blank"` link) gets that pop-up
shown in a genuinely separate, OS-level macOS window — not contained
within the Desk canvas or the widget's own frame at all.

## Root cause (research)

`BrowserWidget` never connects to `QWebEnginePage.newWindowRequested`
(`QWebEngineNewWindowRequest`, `PyQt6.QtWebEngineCore`, confirmed
present in the installed PyQt6-WebEngine 6.11). This is the modern
(Qt 6.2+, replacing the older, deprecated `QWebEnginePage.createWindow`
virtual-method-override approach) signal Chromium fires whenever a page
wants a new browsing context — `window.open()`, `target="_blank"`,
`Ctrl`/`Cmd`-click on a link, etc. — regardless of the requested
`DestinationType` (`InNewWindow`/`InNewTab`/`InNewDialog`/
`InNewBackgroundTab`).

If nothing connects to this signal, Qt WebEngine's own default handling
creates a genuinely separate, unmanaged top-level native window for the
request — exactly the reported symptom. This is the same pattern Qt's
own official `simplebrowser` example handles by connecting the signal
and calling `request.openIn(somePage)` to redirect the new browsing
context into a page the app already owns and displays somewhere of its
own choosing, instead of leaving Chromium to create its own window.

**Yes, this is avoidable, and pop-ups can be fully contained within the
widget's own frame** — connect `newWindowRequested` and redirect every
request into a second, embedded `QWebEngineView` shown as an in-widget
panel, never a new canvas widget or OS window.

## Design

`BrowserWidget` gains a second, initially-hidden `QWebEngineView` (the
"pop-up view") plus a small toolbar (a read-only URL label, matching
the non-selectable-label convention other widgets' status labels
already use, plus a "✕ Close pop-up" button) — both wrapped in their own
container widget. A `QStackedWidget` holds two pages: the existing
main browsing UI (toolbar + main view, unchanged) and the new pop-up
panel; `BrowserWidget`'s own top-level layout becomes just this stack.

- `self._view.page().newWindowRequested` connects to a handler that
  calls `request.openIn(self._popup_view.page())` (redirecting the new
  browsing context into the embedded pop-up view, regardless of
  `destination()` — every kind is treated the same way: contained,
  never a new OS window or a new canvas widget) and switches the stack
  to the pop-up page.
- `self._popup_view.page().windowCloseRequested` (fires when the
  pop-up's own JS calls `window.close()` — common for e.g. an
  OAuth-style flow that closes itself when done) connects once, at
  construction, to the same "switch back to the main page" handler the
  close button uses.
- The pop-up panel reuses one `QWebEngineView`/page across repeated
  pop-ups (not a stack of many simultaneous ones) — matches the
  request's own framing ("could they be fully contained within the
  widget frame, instead?", not "support N simultaneous pop-ups");
  opening a new pop-up while one is already showing just replaces it.

No change to the main view's own back/forward/reload/address-bar
behavior at all.

## Affected files

- `widgets/browser/widget.py`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, a real `QApplication` and real
`QWebEngineView`/`QWebEnginePage` — this is exactly the kind of
behavior that can't be verified by reading the code alone):

- A tiny local test page (served via a temporary `http.server`, since
  `window.open()` from a `data:`/`about:` URL is unreliable in
  QtWebEngine's default popup-blocking behavior for non-http origins)
  with a button calling `window.open(...)`, loaded into a real
  `BrowserWidget`. Clicking it (a real, synthetic click dispatched into
  the page) confirms: the widget's own pop-up panel becomes visible
  (stack switches), the pop-up view actually navigates to the requested
  URL, and — the actual point of this fix — `QApplication
  .topLevelWidgets()`'s count does not increase (no separate top-level
  window was created anywhere, on this widget or otherwise).
- The pop-up's own `window.close()` (simulated via JS `runJavaScript`)
  switches the stack back to the main page.
- The close button does the same.
- Regression: the main view's existing address-bar/back/forward/reload
  behavior (already covered by `plans/browser-widget.md`'s own
  verification) still passes unchanged.

## Status

Not yet implemented — plan written first per `development-process.md`.
