# Simple browser widget (COMPLETED)

## Summary

TODO bc75b07: a new `kind: "python"` widget (`widgets/browser/`) — a
`QWebEngineView` with an address bar and forward/back/reload buttons, for
browsing arbitrary URLs from the canvas (distinct from `ChromiumWidget`,
which loads one fixed `kind: "html"` widget's own bundled page, not
arbitrary user-navigable URLs).

## Design

- `python`-kind, not `html`-kind: this is native Qt chrome (address bar,
  nav buttons, built directly with Python/PyQt6) hosting a
  `QWebEngineView` as content — the same "a `python` widget can import
  and use any PyQt6 module directly" pattern the Console widget
  (`pty`/`subprocess`) and Editor widget (`QScintilla`) already
  established, just with `QWebEngineView` this time instead of going
  through the `ChromiumWidget`/local-server/Bridge-API machinery (which
  is specifically for `kind: "html"` widgets' own bundled pages).
- Toolbar: back/forward/reload `QPushButton`s wired directly to
  `QWebEngineView.back()`/`.forward()`/`.reload()`, plus a `QLineEdit`
  address bar. Back/forward buttons track `QWebEngineView.history()
  .canGoBack()`/`.canGoForward()`, updated on `urlChanged`, so they're
  disabled when there's nowhere to go rather than silently no-op'ing.
- Address bar: `returnPressed` navigates via `QUrl.fromUserInput(text)`
  — Qt's own standard address-bar-style URL interpretation (handles a
  full URL, a bare hostname like `example.com`, etc.) rather than
  hand-rolled URL-guessing heuristics. `urlChanged` updates the address
  bar's text to match the page actually navigated to (bidirectional
  sync — e.g. following a link updates what's shown, not just typing a
  new one).
- Starts at `about:blank`, not an external site — no external network
  dependency just from placing the widget, and nothing surprising
  navigated to on your behalf by default.

## Affected files

- `widgets/browser/widget.json`, `widgets/browser/widget.py` (new).

## Verification

Entirely headless, using local `setHtml()`-loaded content (not real
external network requests, matching this project's `QWebEngineView`
-testing approach for the Bridge API — hermetic, no network flakiness),
run as a real script file with `QApplication(sys.argv)` (not `[]` — an
empty `argv` crashes `QtWebEngine`'s Chromium init, see `LEARNINGS.md`):

1. Confirm the widget constructs with the address bar showing
   `about:blank`.
2. Load a page via the address bar (`_address_bar.setText(...)` +
   `returnPressed.emit()`), confirm the view actually navigates there.
3. Navigate to a second page, confirm the address bar's text updates to
   match (not just the first navigation).
4. Confirm `Back` returns to the first page and updates the address bar
   accordingly; confirm `Forward` returns to the second.
5. Confirm back/forward button enabled state matches actual history
   availability (disabled with no history in that direction, enabled
   once there is).

## Status

Implemented and verified, entirely headlessly (run as a real script file
with `QApplication(sys.argv)`, `QtWebEngineWidgets` imported before
constructing it):

1. Confirmed the widget starts at `about:blank`.
2. Confirmed navigating via the address bar (`data:` URLs, avoiding real
   external network dependency in verification) actually loads the page.
3. Confirmed navigating to a second page updates the address bar to
   match.
4. Confirmed Back/Forward correctly move between the two pages.
5. Confirmed the back button becomes disabled once history is
   exhausted.
6. Regression: confirmed `discover_widgets` picks up the new
   `widgets/browser` manifest, and a real `DeskWindow.open_widget
   ("browser")` correctly builds and places a working `BrowserWidget`.
