# Plan: TODO d28885f — side-by-side widget container

## Summary

See the TODO item's own body for the architectural constraints already
confirmed by reading the current widget-hosting code (no existing
nested-widget precedent; instance ids mint 1:1 with `WidgetFrame`
construction; `EventMediator` is plain broadcast pub/sub with no
directed messaging). This plan pins down the remaining implementation
-level decisions.

New `widgets/side_by_side/` (`kind: "python"`). Two fixed "slots"
(identity 0/1, never renamed by swapping — see "Swap" below), each
optionally holding one `kind: "python"` child widget instance, laid out
in a `QSplitter` (gives a draggable divider and cheap orientation
-switching for free) with a small toolbar (Swap, Orientation) above it.

## Persistence: reuse widget-local storage, no new `WidgetState` field

`desk.desks.WidgetState` already has a generic `state: dict` field (TODO
`fb76057`, "widget-local storage") round-tripped via
`get_widget_local_storage()`/`set_widget_local_storage(data)` — the same
duck-typed hooks every other widget with its own persisted state (e.g.
Editor's open file) already implements. The container needs no new
`Desk`/`WidgetState` field at all: it persists everything (orientation,
left/right order, and each slot's `widget_id`/`instance_id`) through
this existing mechanism.

**Each slot's own child widget may itself have local storage** (e.g. an
Editor slot's open file path) — but the child never gets its own
top-level `WidgetFrame`, so `DeskWindow`'s per-frame save/restore loop
never sees it directly. The container must recurse into this itself:
its own `get_widget_local_storage()` calls the slot's live content's
`get_widget_local_storage()` (if it has one) and nests the result;
`set_widget_local_storage()` passes the nested dict back to the
rebuilt content's own `set_widget_local_storage()` the same way.

Shape:

```python
{
  "orientation": "horizontal" | "vertical",
  "order": [0, 1],  # which slot index is at splitter position 0/1 -- see Swap
  "slots": [
    {"widget_id": "editor", "instance_id": "a1b2c3d4", "local_storage": {...}},
    {"widget_id": None, "instance_id": None, "local_storage": {}},
  ],
}
```

## Two new `current_context` hooks

- `get_widget_catalog_provider()`/`set_widget_catalog_provider(fn)` —
  `fn() -> list[dict]`, each `{"id", "name", "path", "entry"}`, **`kind:
  "python"` only** (see Non-Goals). Wired once at `DeskWindow.__init__`
  (the catalog is discovered once at process start via
  `discover_widgets`, not per-Desk-switch, unlike the file type
  registry hook). Lets the container's per-slot picker enumerate
  choices and resolve a chosen id back to a `(path, entry)` pair,
  without needing to import `desk.widgets`/reach into `DeskWindow`
  itself.
- `get_hot_reload_broker()`/`set_hot_reload_broker(broker)` — the
  same app-wide `HotReloadBroker` instance `DeskWindow` already holds
  (`self._broker`), needed to construct a `PythonWidgetHost` directly
  (see below). Wired once at `DeskWindow.__init__` alongside the
  existing `current_context.set_event_mediator(...)` call.

The mediator itself needs no new hook — `current_context
.get_event_mediator()` already exists and is exactly what's needed here
too (same pattern `widgets/event_log/widget.py`'s Clear button already
uses).

## Reusing `PythonWidgetHost` directly

`desk.shell.python_widget.PythonWidgetHost(widget_id, widget_path, entry,
broker, parent=None)` is self-contained (imports `widget.py`, calls
`build()`, wires hot-reload via the given broker) — no dependency on
`DeskWindow` itself. The container constructs one per occupied slot
directly (not through `DeskWindow._place_widget`, since slot content
never gets its own canvas placement/`WidgetFrame`/`instance_id` minted
by that path) using `(path, entry)` resolved from the widget-catalog
hook's entries.

## Wiring a slot's content to the mediator

For a newly-built slot's `PythonWidgetHost.current`, if it exposes
`bind_event_mediator(instance_id, mediator)` (the same duck-typed hook
`DeskWindow._bind_event_mediator` already calls for top-level frames),
call it with the **slot's own instance id** (minted once, persisted,
reused verbatim across rebuilds/reloads — never the container's own
top-level instance id, and never re-minted just because hot-reload
rebuilt the hosted widget). Tear down via `mediator.unsubscribe_all
(instance_id)`:

- When the user actively **re-picks** a different widget type for an
  already-occupied slot (a fresh identity — mint a *new* instance id,
  unsubscribe the old one, clear that slot's local storage).
- When the container's own top-level instance is destroyed — captured
  as **plain values** (`mediator`, `slots`) in a closure connected to
  `self.destroyed`, *not* a bound method of `self`
  (`self.destroyed.connect(self._method)` silently never fires, a
  documented `LEARNINGS.md` gotcha) — mirrors the established
  `watcher = self._watcher; self.destroyed.connect(lambda: watcher.stop())`
  idiom used throughout this codebase.

A hot-reload rebuild of a slot's content (the broker firing because the
child widget's own source changed) does *not* need special handling
here beyond the above: `PythonWidgetHost` itself swaps in the freshly
-built `QWidget` for the *same* host, so the slot's `instance_id`/
mediator binding needs re-establishing against the *new* `.current`
after each rebuild — hook `PythonWidgetHost`'s existing hot-reload swap
indirectly by re-running the same "bind if the hook exists" step
whenever `.current` changes. Simplest correct approach: after
constructing the host, connect the *broker's* `widget_changed` signal
(already the mechanism that drives the rebuild) to a small handler that
re-binds this slot's `instance_id`/local-storage against
`host.current` when the changed widget id matches this slot's
`widget_id` — same signal the host itself already listens to, so this
just piggybacks a second connection alongside it for the container's
own separate bookkeeping.

## Swap / orientation

- `self._slots[0]`/`self._slots[1]` are **fixed identities** — swapping
  never touches which slot's data/instance-id lives at index 0 vs. 1
  (a slot's own instance id, and thus any bound mediator subscriptions
  or restored local storage, must never change just because the user
  clicked Swap). Instead, `self._order: list[int]` (initially `[0, 1]`)
  records which slot index currently occupies which **splitter
  position**; `Swap` just reverses it (`self._order =
  [self._order[1], self._order[0]]`) and re-lays-out the splitter
  (`QSplitter.insertWidget(position, widget)` natively re-parents/moves
  a widget already in the splitter, so this is a single small,
  reusable `_refresh_splitter_widgets()` used for the initial build,
  a slot being filled in for the first time, and Swap alike).
- `Orientation` just calls `self._splitter.setOrientation(...)` —
  doesn't touch widget assignment at all.
- Both are persisted (see the shape above) so they survive a Desk
  reload, not just session-only.

## Empty-slot picker UI

A plain placeholder `QWidget` (label + `QComboBox` populated from the
widget-catalog hook, filtered to `kind: "python"` + a "Choose" button)
occupies a splitter position until that slot has a widget_id — shown
via `_refresh_splitter_widgets()` picking the placeholder vs. the real
`PythonWidgetHost` per slot's current state, the same "swap the visible
page" shape used elsewhere in this codebase for stacked/alternate
content (e.g. Image Viewer's raster/vector `QStackedLayout`, TODO
`4d21e7c`) — here via `QSplitter.insertWidget` instead of a stacked
layout, since both positions are simultaneously visible side-by-side
rather than one-at-a-time.

## Non-Goals (first pass)

- `kind: "html"` children — nesting a `QWebEngineView`'s own browser
  -profile/process overhead inside another widget's layout is a
  separate, bigger concern; the catalog hook is filtered to `kind:
  "python"` only for now.
- A bespoke inter-widget message *protocol* between two specific widget
  types (e.g. the parked "editor-with-view" pairing) — this container
  only guarantees both slots are properly bound to the shared
  `EventMediator` with stable instance ids; any actual publish/subscribe
  contract between two specific widget kinds is those widgets' own
  future concern.
- Removing/clearing an already-filled slot back to empty (no "eject"
  button in the first pass) — not asked for; a slot's content can still
  be *replaced* via re-picking a different widget type from the same
  combo box shown once occupied (the combo/Choose UI stays available
  under/beside the hosted content, not just for an empty slot). Simple
  enough to keep uniform rather than special-casing "already filled."

## Verification

- Real `SideBySideWidget` (headless `QApplication`, real
  `HotReloadBroker`/`EventMediator`, real widget catalog from
  `discover_widgets`): choosing a widget type for each slot builds a
  real `PythonWidgetHost` showing that widget's actual content; Swap
  exchanges splitter positions without changing either slot's own
  instance id or rebuilding either host; Orientation toggles the
  splitter's orientation.
- Mediator wiring: choosing two widgets that both expose
  `bind_event_mediator` results in each bound with a distinct,
  persisted instance id; publishing an event from one's bound instance
  id is received by a *third*, independently-subscribed instance (proof
  the container's slots are genuinely on the shared bus, not an
  isolated one); re-picking a slot's widget type unsubscribes the old
  instance id (confirmed via `EventMediator.list_subscriptions()`).
- Persistence round-trip: `get_widget_local_storage()` →
  `set_widget_local_storage()` on a fresh instance restores
  orientation, order, both slots' widget ids/instance ids, and (for a
  slot whose content itself exposes local storage) that nested state
  too.
- `current_context.get_widget_catalog_provider()` returns only `kind:
  "python"` entries; `get_hot_reload_broker()` returns the same broker
  `DeskWindow` itself uses.
- Full scratchpad regression suite (`git stash` before/after).
