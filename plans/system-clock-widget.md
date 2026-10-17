# System Clock built-in widget (TODO ba11954) -- COMPLETED

Recreates, as a built-in `kind: "python"` widget, the HTML System Clock a Claude instance in
`ae_samothrace` wrote as a real-source `DefineWidget` (`../FEEDBACK/FEEDBACK-DESK-system-clock-widget-source-2026-10-16-2122.md`).
The user liked its styling, so that is kept as-is.

## Summary

`widgets/system_clock/` (`widget.json` + `widget.py`, no capabilities, default 360x220): `HH:MM:SS`
(56 px, demi-bold, 3 px letter spacing, `#7cfc9a`), the long-form date including the weekday (15 px,
1 px spacing, `#9fb3a8`) and `<IANA zone> (system clock)` (11 px, `#5f7268`), centered on `#111418`, in a
monospace stack (`SF Mono`, `Menlo`, `Courier New`). Pure client-side state, nothing persisted.

## Affected files

- new `widgets/system_clock/widget.json`, `widgets/system_clock/widget.py`
- new `tests/verify/verify_system_clock_widget.py`

Built-in widgets are discovered from `widgets/`; no registry edit.

## Approach

- Three non-selectable `QLabel`s (palette colours, pixel-sized fonts, `QFont` letter spacing) in a
  vertical layout with stretches above and below, replacing the HTML's flex centering. No stylesheet.
- Refresh every 200 ms like the original, but only while visible (same pattern as the HUD Manager);
  labels are only touched when their text changes.
- Date: the locale's long format, with `dddd, ` prepended when that format lacks the weekday (Qt's
  en_US long format is `October 16, 2026`, whereas the HTML showed `Friday, October 16, 2026`).
- Zone: `QTimeZone.systemTimeZoneId()`, the same IANA name `Intl.DateTimeFormat` reported.
- `refresh(now)` takes an optional `QDateTime` so the test can fix the time.

## Decisions

- Sizes stay fixed pixel sizes as in the HTML; the canvas zoom scales them. Not made to scale with
  resizing the frame, so a frame narrower than about 300 px clips the clock, as the original did.
- No custom painting: plain labels suffice and keep text crisp under proxy scaling.

## Verification

`verify_system_clock_widget.py` (11 checks): zero-padded time, weekday in the date, zone line,
non-selectable labels, sizes/colours/background kept, ticking only while visible, manifest. A rendered
offscreen screenshot was compared by eye against the HTML's description. User-confirmed in the live app.

## Status: COMPLETED 2026-10-16
