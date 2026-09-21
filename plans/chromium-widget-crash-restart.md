# Crash placeholder with [RESTART] for ChromiumWidget (TODO 5abf5a0) (COMPLETED)

## Summary

A `ChromiumWidget` whose render process terminated
(`QWebEnginePage.renderProcessTerminated`) used to stay a blank view
forever. It now shows a "Widget crashed" overlay (status + exit code)
with a **[RESTART]** button that reloads the page. Deliberately not the
`[STALE]` tag (content-hash mismatch only).

## Affected files

- `src/desk/shell/chromium_widget.py` (new `_CrashedOverlay`, signal
  hookup, `resizeEvent`, `reload` hides the overlay)
- `tests/verify/verify_chromium_widget_crash_restart.py` (new)
- `design-docs/architecture.md`, `TODO.md`

## Approach

1. `_CrashedOverlay`: a child `QWidget` covering the view, label + button.
2. On `renderProcessTerminated`: log, show the overlay, and raise the
   existing titlebar error indicator via `error_state_changed`.
3. `reload()` (already the shared path for hot reload / [STALE] reload)
   hides the overlay and clears the error indicator, so [RESTART] is
   just `reload`.

## Verification

Real crash: navigate the page to `chrome://crash` (offscreen), confirm
the overlay appears and covers the view, click [RESTART], confirm the
page content is live again. Not verified visually in the running app.

## Notes

- No tempui changelog entry: not a DSL/Bridge API change.
- Introspect against a crashed widget still waits out its own timeout;
  out of scope here (see TODO b89cf17 for its error reporting).
