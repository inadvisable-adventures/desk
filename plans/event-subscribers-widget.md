# Event Subscribers widget (COMPLETED)

TODO `7505703`.

## Summary

A `kind: "python"` widget listing every widget instance currently
registered (subscribed to at least one name) on the event mediator
channel (TODO `6f9c51b`), each row showing a human-readable label plus
its subscribed event names, with a per-row eye-emoji button that
zooms/pans the Workspace Canvas to that specific widget instance —
the same visual affordance and `zoom_to_widget` action as the titlebar
eye button (TODO `33d3e8d`).

## Design

### Reading the live subscription state

`desk.event_mediator.EventMediator` gains one new read method:

```python
def list_subscriptions(self) -> dict[str, set[str]]:
    with self._lock:
        return {instance_id: set(names) for instance_id, names in self._subscriptions.items()}
```

A lock-protected shallow copy — cheap (in-memory dict, no I/O), safe
to iterate/mutate freely afterward without racing a concurrent
subscribe/unsubscribe. Reached the same way `widgets/event_log/
widget.py`'s `_clear_log` already reaches the mediator:
`current_context.get_event_mediator()` — no `bind_event_mediator`
needed here (unlike the Event Poster widget, TODO `dc557b2`), since
this widget only ever reads shared state, never needs its own sender
identity.

### Two new `current_context` hooks

Following the module's own established "one new minimal get/set pair
per new capability" pattern (`widget_path_resolver`, `discuss_starter`,
...):

- `widget_zoomer: Callable[[str], bool]` — bound to a new
  `DeskWindow.zoom_to_widget_by_instance_id(instance_id)`
  (`find_frame_by_instance_id` + `self.view.zoom_to_widget(frame)`,
  same "resolve then act, return whether found" shape as the existing
  `close_widget_by_instance_id`).
- `widget_display_name_resolver: Callable[[str], str]` — bound to the
  already-existing `DeskWindow._display_name_for_instance` (built for
  the introspect permission dialog, TODO `9767c1a` — "kind name (short
  id)", falls back to the bare instance id if the frame can't be
  found).

Both wired in `DeskWindow.__init__` alongside the other
`current_context.set_*` calls.

### UI

A `QListWidget` with one `_SubscriberRow` (a `QWidget` with a `QLabel`
— `"{display_name} — {names, comma-joined}"` — and a `👁` `QPushButton`
firing a `zoom_requested(instance_id)` signal) per registered instance
via `setItemWidget`, matching `widgets/event_log/widget.py`'s general
shape but needing per-row interactive content (so a plain
`QListWidgetItem` text row won't do). Rows sorted by display name for
a stable order. A status label above the list reports "N widget(s)
registered." / "No widgets are currently registered." / "Not yet
connected to the event channel." (mediator not yet available —
reusing the exact phrase `widgets/event_poster/widget.py` already
uses for the same underlying condition).

Refreshed on a `QTimer` (1000ms — cheap, in-memory-only work, no
subprocess/IO unlike `widgets/git_status/widget.py`'s 3000ms, but
still gated on `isVisible()` for a widget nobody's currently looking
at, matching that widget's own compute-burden-conscious pattern) since
the mediator has no signal-based "subscriptions changed" notification
to react to instead — polling is the only option.

Clicking a row's eye button calls
`current_context.get_widget_zoomer()(instance_id)`.

## Affected files

- `src/desk/event_mediator.py` — `EventMediator.list_subscriptions()`.
- `src/desk/shell/current_context.py` — `widget_zoomer`/
  `widget_display_name_resolver` hooks.
- `src/desk/shell/window.py` — `zoom_to_widget_by_instance_id`, wiring
  both new hooks in `__init__`.
- `widgets/event_subscribers/widget.json` — new manifest.
- `widgets/event_subscribers/widget.py` — the widget.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`):

- `EventMediator.list_subscriptions()` returns a correct, independent
  (mutating the returned dict doesn't affect the mediator) snapshot
  across subscribe/unsubscribe/unsubscribe_all.
- The widget's status/list correctly reflect: no mediator bound yet;
  mediator bound but nobody subscribed; one or more real subscribed
  instances, each row's label and event-name list correct, sorted.
- Clicking a row's eye button calls the bound `widget_zoomer` with the
  right instance id (a fake installed zoomer, then a real one).
- A full `DeskWindow` regression (pointed at this project's own
  already-provisioned directory, same reasoning as TODO `dc557b2`'s
  plan): `zoom_to_widget_by_instance_id` finds a real placed frame and
  actually changes the view's scale/center to bring it into view (and
  returns `False` for an unknown instance id, without crashing);
  `_display_name_for_instance` reachable via the new
  `widget_display_name_resolver` hook resolves a real placed
  instance's real kind name; a real Event Subscribers instance placed
  alongside a real subscribed instance (e.g. a placed Event Poster or
  a raw `EventSubscription`) shows the correct row and its eye button
  genuinely zooms the real `WorkspaceView` to the right widget.
- `discover_widgets` picks up the new manifest; a real
  `PythonWidgetHost` builds a working instance.

## Status

Implemented as planned. Same DeskWindow-regression deviation as TODO
`dc557b2`'s plan: pointed at this project's own already-provisioned
directory rather than a fresh temp directory, to avoid
`_provision_temp_ui`'s confirmation dialogs blocking a headless run.
Verified headlessly throughout, including a full `DeskWindow`
regression confirming a real eye-button click genuinely zooms the
real `WorkspaceView` to a real placed instance. See TODO `7505703`'s
own entry in `TODO.md` for the full summary.
