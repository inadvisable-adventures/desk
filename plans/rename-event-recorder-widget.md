# Plan: TODO d9a46b6 — rename Event Recorder's display name to "Qt UI Event Recorder"

## Summary

A display-name-only rename, per direct user request. `widget_id`
(`event_recorder`) is derived from the widget's directory name at
discovery time (`desk.widgets.discover_widgets`: `widget_id =
manifest_path.parent.name`), entirely independent of `widget.json`'s
`"name"` field — so this change doesn't touch the directory, any
already-placed widget instance's `widget_id` in a `.desk` file, or any
code referencing the widget by id.

## Changes

- `widgets/event_recorder/widget.json`: `"name": "Event Recorder"` ->
  `"name": "Qt UI Event Recorder"`.
- `widgets/event_recorder/widget.py`: update the module docstring's
  opening reference to the widget's own name, for consistency.
- `design-docs/architecture.md`: update the numbered widget-list
  entry's bolded name.
- `src/desk/shell/canvas.py`: one comment mentions "the Event
  Recorder" descriptively — update for consistency.

## Explicitly not touched

Historical record, describing what was true when written, not
retroactively renamed:
- `TODO.md`'s own completed entries (TODO `8d4826c`'s original text and
  every later entry's mentions of "Event Recorder").
- `PARKINGLOT.md`'s narrative mentions (describing past investigation
  findings).
- Already-`COMPLETED` plan files (`plans/event-recorder-widget.md`,
  `plans/widget-wheel-pinch-always-wins.md`,
  `plans/wheel-event-accept-no-fallthrough.md`).

## Verification

- Grep confirms no `tests/verify/*.py` script hardcodes the display
  name "Event Recorder" as a string literal (confirmed before writing
  this plan) — no test changes needed.
- Full `tests/verify/` regression suite.
