# Investigate self-window screenshot capability

## Summary

Determine whether Desk can capture screenshots of its own windows/widgets
from inside the running process without extra user/OS permission
(notably on macOS), to potentially support verification tooling or a
widget inspecting its own rendered state.

## Investigation

Qt's `QWidget.grab() -> QPixmap` (and the lower-level
`QWidget.render()`) renders a widget's own content directly into an
offscreen buffer via Qt's own paint machinery — it does not go through
macOS's system-level screen-capture APIs (`CGWindowListCreateImage`,
`ScreenCaptureKit`, etc.), which are what actually require the OS-level
"Screen Recording" permission (for capturing *other* processes' windows,
or the full physical screen as actually composited). Since `grab()` never
asks the OS "what's currently displayed on screen," there's nothing for
macOS's permission system to gate.

This was already confirmed empirically and extensively over the course of
this session, not just as a one-off check: every pixel-level rendering
verification done for TODO items 16/17/23 (console widget cursor/color
rendering) and item 21 (`QWebEngineView` client-library injection) relied
on `grab()`/`render()` — dozens of calls, across `QPlainTextEdit`,
`QWebEngineView`, and plain `QWidget`/`QLabel` instances, both `.show()`n
and never-shown — and none ever triggered a macOS permission prompt,
error, or blank/black image (the usual failure mode for *unauthorized*
screen capture on macOS). Confirmed once more directly, isolated and
minimal: constructing a bare `QLabel` (never `.show()`n), calling
`.grab()`, converting to `QImage`, and saving to a real PNG file all
succeed immediately with no permission dialog.

## Conclusion

**Yes — no extra permission is needed.** `QWidget.grab()`/`.render()`
already provide exactly the capability the TODO item asked about:
capturing a screenshot of Desk's own windows/widgets from inside the
running process, freely, on macOS (and this isn't macOS-specific — the
same holds on any platform, since it never touches OS screen-capture
APIs at all). This is already Desk's own de facto verification technique
(see `plans/console-widget-highlight-cursor-rendering.md`), not a new
capability to build — no further implementation work is needed for the
capability itself.

## Possible future use (not built here — investigation only)

- A `desk.debug.screenshot(widget) -> QImage` convenience helper, if
  self-screenshotting becomes a common enough verification need across
  multiple widgets/plans to be worth a shared utility rather than each
  plan writing its own `grab()`/`QImage` inspection inline. Not built now:
  no second concrete caller yet to justify the abstraction (every
  verification pass so far has had slightly different needs — pixel
  -frequency scanning, specific-coordinate sampling, etc.).
- Exposing this to widgets themselves (e.g. a Bridge API `self.screenshot()`
  for `html` widgets, or a direct Python helper for `python` widgets) if a
  concrete use case for a widget inspecting its own rendered state
  actually comes up — speculative, not scoped here.
