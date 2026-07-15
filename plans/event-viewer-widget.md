# Plan: TODO 0d2ebc1 — Event Viewer widget

## Summary

A new widget, `widgets/event_viewer/` (`kind: "python"`), that shows one
mediated event's full detail — timestamp, event name, sender instance id,
and its payload pretty-printed in full (not the Event Log's own truncated
single-line summary). Opened by double-clicking a row in the Event Log
widget (`widgets/event_log/`).

## New widget: `widgets/event_viewer/`

- `widget.json`: `{"name": "Event Viewer", "kind": "python", "entry":
  "widget.py", "capabilities": [], "default_size": {"width": 480,
  "height": 420}}`.
- `widget.py`: `EventViewerWidget(QWidget)`:
  - Four read-only, non-selectable `QLabel`s for timestamp/name/sender
    (mirroring `CrashLogWidget`'s label style), plus a read-only
    `QPlainTextEdit` for the payload, pretty-printed via
    `json.dumps(payload, indent=2)` (`None` payload shown as an empty
    string, matching `event_log.widget._format_payload`'s own `None`
    handling, but without that function's single-line
    `separators=(",", ":")` compaction — this widget wants the
    *opposite*, maximally readable form).
  - `set_event(event: MediatedEvent) -> None` — duck-typed the same way
    `set_file(path)` is on the Editor/Markdown widgets, so the opener
    doesn't need to import `EventViewerWidget` directly. Populates the
    four labels/payload text from the given event.
  - Placed standalone via the spawn menu (like any ordinary widget) with
    no event set yet: show a placeholder message ("No event selected —
    open this from the Event Log widget by double-clicking a row."),
    same shape as `MarkdownWidget`'s own `PLACEHOLDER_TEXT`/
    `_show_placeholder`.
  - No persistence (`getLocalStorage`/`WidgetState.state`) — this widget
    is a point-in-time detail view of one already-logged event, not
    something whose content should survive a reload the way an editor's
    open file does; reopening from the Event Log if you need to see it
    again is the deliberate design here, not a gap.
  - `build() -> QWidget: return EventViewerWidget()`.

## Event Log changes (`widgets/event_log/widget.py`)

- `_set_events` currently only stores formatted display strings per row.
  Keep the underlying `MediatedEvent` too, via `Qt.ItemDataRole.UserRole`
  on the row's first (`Timestamp`) column's `QTableWidgetItem` (mirrors
  how `widgets/questions/widget.py` stores its own `QuestionEntry` via a
  role on the list item, `ENTRY_ROLE`).
- Connect `self._table.itemDoubleClicked` (or `cellDoubleClicked`) to a
  new `_open_event_viewer(item)` handler: reads the event back off the
  role, calls `current_context.get_widget_opener()` (the exact same
  pattern `widgets/file_explorer/widget.py`'s `_open_index` already
  uses for the Editor widget), and if the opener returns a widget
  exposing `set_event`, calls it — guarded by a broad `except Exception`
  around the `set_event` call, matching `file_explorer`'s own
  "a broken hook must never propagate out of a Qt slot" reasoning
  (TODO 810a5d6), since this also runs inside a double-click slot.
- Not centering the opened widget in the view — `open_widget_content`'s
  own default (`pos or (0, 0)`) matches the File Explorer's own current,
  pre-existing double-click behavior; TODO efdad99/da4f9c0 are the ones
  that introduce centered placement as a deliberate, scoped change for
  their own fallback chain, not something to fold in here unasked.

## Verification

- `EventViewerWidget.set_event` populates all four fields correctly,
  including pretty-printed (multi-line, indented) JSON for a
  dict/list payload and an empty string for a `None` payload.
- Placed with no event set shows the placeholder text.
- `EventLogWidget`: double-clicking a row calls the widget opener with
  `"event_viewer"` and calls `set_event` with the correct `MediatedEvent`
  for that row (real `QTableWidget` + `QApplication`, not a fake
  double, since this is exercising real Qt signal wiring).
- A broken/missing `set_event` (opener returns `None`, or a widget
  without `set_event`) doesn't raise out of the double-click slot.
- Full scratchpad regression suite (`git stash` before/after).
