# Plan: TODO 8d4826c (COMPLETED) — new Event Recorder widget

## Summary

Motivated directly by TODO `3846190`'s own fix: the user still sees a
trackpad two-finger-scroll gesture "getting missed" by widgets even
after that fix, and wants a way to empirically observe *exactly* which
raw Qt events actually reach a widget during a real gesture, rather
than guessing further (this environment is headless/offscreen and
can't reproduce real trackpad hardware input at all — a real,
interactively-placed widget is the only way to actually answer this).
A "two-finger scroll" is usually a `QEvent.Type.Wheel` on most
platforms, but some drivers/OSes report it as a `NativeGesture`
`PanNativeGesture` instead of (or alongside) a wheel event — TODO
`3846190`'s own fix never considered `PanNativeGesture` at all, only
`ZoomNativeGesture` (pinch). This widget doesn't guess which is
actually happening; it just shows the user everything that's real.

New `widgets/event_recorder/` (`kind: "python"`).

## Behavior

- A **"Record for 5s"** button, plus a status label. Clicking it:
  - Disables the button, starts a live countdown in the status label
    ("Recording… 5s left" → … → "Recording… 1s left").
  - Swaps the widget's own results view out for a large, blank
    recording surface (`_RecordingSurface(QWidget)`) filling the rest
    of the widget's content area — a `QStackedLayout` between "results"
    and "recording", matching the same page-swap shape Image Viewer's
    raster/vector views already use (TODO `4d21e7c`).
  - `_RecordingSurface` overrides `event(self, event) -> bool` (the
    single generic dispatch point every event type passes through —
    the same shape `WorkspaceView.event()` already uses for its own
    `NativeGesture` handling) and, while recording is active, appends
    every event it sees to an in-memory list before calling
    `super().event(event)` (preserving completely normal Qt behavior —
    this is a passive observer, not a filter). No allowlist/blocklist:
    *everything* is recorded, deliberately — filtering by "which event
    types seem relevant" is exactly the kind of guess this tool exists
    to avoid. Each recorded entry: `(elapsed_ms, event.type(),
    short_detail)`, where `short_detail` is a small, type-specific
    one-line summary (wheel: `pixelDelta`/`angleDelta`; mouse:
    button/position; native gesture: `gestureType`/`value`; touch:
    point count; anything else: no extra detail beyond the type name).
  - After 5 real seconds (`QTimer.singleShot`), recording stops, the
    stacked layout swaps back to the results view, and the raw event
    list is collapsed (see below) and shown.

- **Collapsing**: a straightforward run-length encoding over the raw,
  time-ordered event list — consecutive events sharing the same
  `event.type()` merge into one group, *regardless of their individual
  payload* (a `QEvent.Type.MouseMove` with a different position each
  time still merges with its neighbors). A group only ever holds
  chronologically-adjacent events of the same type; a different type
  appearing in between starts a new group even if that same type
  recurs later. Each collapsed group shows: type name, count, elapsed
  -time range, and the first and last entry's own short detail (a
  quick sense of "what changed over the run" without needing to drill
  into every individual event). Groups are **not expandable** — this
  is a one-way summary, not an accordion; the point is a readable
  overview, not a full raw log browser.
- Results shown in a `QTableWidget` (Type / Count / Elapsed range /
  First → Last detail), matching Event Log widget's own established
  table shape (TODO `0d2ebc1`/`6f9c51b`).
- **Widget-local storage** (TODO `fb76057`): after a recording
  completes, the collapsed groups (not the raw per-event list — kept
  reasonably small) plus a `recorded_at` timestamp are persisted via
  `get_widget_local_storage`/`set_widget_local_storage`, so the last
  recording's results survive a Desk reload, matching "recording them
  in the widget's state" — this project's own established term for
  exactly this per-instance persistence mechanism.

## Non-Goals

- No attempt to fix or even guess at the underlying two-finger-scroll
  gap itself — this widget is purely a diagnostic instrument the user
  runs interactively; whatever it reveals informs a *follow-up* TODO,
  not this one.
- No raw-event drill-down/export — the collapsed summary is the whole
  point; if per-event detail turns out to be needed later, that's a
  future addition, not assumed necessary now.
- No event *filtering* (allowlist/blocklist) in the first pass — see
  above.

## Verification

- Real, headless: constructing the widget, calling
  `_RecordingSurface.event(...)` directly with a handful of synthetic
  events (mixed types, including deliberately noisy back-to-back runs
  of the same type) while `_recording` is True confirms they're
  captured in order; not captured before start / after stop.
- Collapsing: a hand-built raw event list with several
  adjacent-same-type runs (including two separated, non-adjacent runs
  of the *same* type) collapses into the expected number of groups,
  each with the right count/first/last detail — confirms the "adjacent
  only, not a full type-bucket" rule specifically.
- `get_widget_local_storage`/`set_widget_local_storage` round-trip: a
  fresh instance restores a previously-completed recording's collapsed
  groups into its results table.
- Full `tests/verify/` regression suite (`git stash` before/after).
