# Optional max_width downsampling for the screenshot tools (TODO 94d2b94) (COMPLETED)

## Summary

`desk_screenshot_desk`/`desk_screenshot_widget` (MCP tools) and
`deskproc.screenshot_desk`/`deskproc.screenshot_widget` (Desk Proc)
always capture at native resolution (often HiDPI 2x), with no way to
ask for a smaller image -- observed producing a ~776KB base64-encoded
payload for one Workspace Canvas screenshot, more than an agent needs
for "good enough to see what's on screen." Cites
`../FEEDBACK/FEEDBACK-DESK-screenshot-tools-no-downsampling-option-2026-09-18-2030.md`
and
`../FEEDBACK/FEEDBACK-DESK-widget-glitches-on-oversized-screenshot-json-2026-09-18-2140.md`
(part b).

## Approach

An optional `max_width` (pixels) on all four entry points, threaded
down to `DeskWindow.screenshot_widget_instance`/`screenshot_desk`
(`src/desk/shell/window.py`), which already do the actual
`pixmap.save(...)`. A shared helper scales the captured `QPixmap` down
proportionally (`Qt.AspectRatioMode.KeepAspectRatio`,
`Qt.TransformationMode.SmoothTransformation`) when its width exceeds
`max_width` -- **never up**, and a no-op when omitted (`None`, the
default) or when the capture is already narrower, so today's behavior
is unchanged unless a caller opts in.

- `src/desk/shell/window.py`: `_scaled_down_pixmap(pixmap, max_width)`
  helper; both screenshot methods gain `max_width: int | None = None`.
- `widgets/desk_proc_runner/widget.py`: `DeskProcApi.screenshot_widget`/
  `screenshot_desk` gain the same parameter, passed straight through.
- `src/desk/shell/desk_mcp_server.py`: `desk_screenshot_widget`/
  `desk_screenshot_desk` gain it too -- a hand-written JSON Schema (the
  `desk_run_installed_job` precedent, since the `{name: type}` shorthand
  makes every key required) so `max_width` stays genuinely optional.
- Docs: `tempui-desk-proc.md`'s (`_DESK_PROC_DOC` in
  `src/desk/temp_ui.py`) `deskproc.screenshot_widget`/`screenshot_desk`
  entries document the new parameter and its "scaled down
  proportionally, never up" behavior. New tempui changelog tag +
  `_NEW_FEATURES` entry (a new feature from an in-Desk agent's
  perspective, per the TODO's own instruction).

## Affected files

- `src/desk/shell/window.py`
- `widgets/desk_proc_runner/widget.py`
- `src/desk/shell/desk_mcp_server.py`
- `src/desk/temp_ui.py`
- `tests/verify/verify_desk_proc_screenshot.py` (existing coverage for
  this area) and/or a new dedicated verify script.

## Verification

Real `QPixmap`s (offscreen, no mocks): a capture wider than `max_width`
is scaled down to exactly that width with height adjusted
proportionally (aspect ratio preserved, not stretched); a capture
already narrower than `max_width` is saved unchanged (never scaled up);
omitting `max_width` entirely reproduces today's exact native-resolution
output byte-for-byte (regression); `screenshot_widget_instance`/
`screenshot_desk` both covered; `DeskProcApi` passes the parameter
through; the MCP tool's hand-written schema actually keeps `max_width`
optional (a call omitting it doesn't fail schema validation). Doc/tag
checks. Re-run `verify_desk_proc_screenshot.py`. Full `tests/verify/`
sweep. No browser launch needed.

## Status

Implemented as planned. One implementation-detail correction from the
plan's own wording: `QPixmap.scaledToWidth(max_width, ...)` already
preserves aspect ratio on its own (it only takes a target width plus a
transformation mode, unlike `.scaled(w, h, aspectMode)`), so there was
no separate `Qt.AspectRatioMode.KeepAspectRatio` to pass -- the plan's
mention of that mode was describing the *effect*, not an actual extra
parameter this API needs.

Verified: `verify_desk_proc_screenshot.py` (real `QPixmap`s, no mocks --
a wider capture scaled to exactly `max_width` with height adjusted
proportionally within a small tolerance, a narrower capture never
scaled up, omitting `max_width` byte-identical to the pre-existing
default, both screenshot methods covered, `DeskProcApi` passing the
parameter through, doc/tag checks), `verify_desk_mcp_server.py` (the
hand-written schema keeps `max_width` optional; both tools route it
through), `verify_desk_proc_runner_widget.py` (a real Desk Proc script
calling both methods with and without `max_width`) -- the latter two
needed their existing fake-window stand-ins updated to accept the new
parameter, since `DeskProcApi`/the MCP handlers now always pass it
positionally (`None` when omitted). All three run twice for flakiness.
Full `tests/verify/` sweep (159 scripts) passes. Browser launch not
needed.

This was the only TODO citing
`../FEEDBACK/FEEDBACK-DESK-screenshot-tools-no-downsampling-option-2026-09-18-2030.md`
-- moved to `../FEEDBACK/implemented/`.
`../FEEDBACK/FEEDBACK-DESK-widget-glitches-on-oversized-screenshot-json-2026-09-18-2140.md`
stays in place, still cited by the still-open TODO `f35466a` (part a).
