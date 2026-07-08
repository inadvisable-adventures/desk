# Generalized hot reload (COMPLETED)

## Summary

Item 9 (`python` widgets) and item 5 (`html` widgets) already generalized
*per-instance* source hot reload across both widget kinds: a single
`WidgetWatcher` watches the whole `widgets/` directory regardless of kind,
and both `PythonWidgetHost` and `ChromiumWidget` already react to the same
`HotReloadBroker.widget_changed` signal (rebuild vs. `reload()`
respectively) — see `design-docs/architecture.md`'s Hot Reload section,
which already describes this as kind-agnostic. Reading the current code
confirms this part of the TODO item's stated goal is already done.

The concrete gap that's *not* addressed: the **widget catalog** itself
(`discover_widgets()`'s result — what's offered in the right-click add
-widget menu, and what `DeskWindow` will recognize a `widget_id` as) is
only ever computed **once**, at app startup (`app.py`), and never
refreshed. A widget directory added, removed, or whose `widget.json`
changes (kind, name, capabilities, default size) while Desk is already
running has no effect until restart — the new/changed widget type simply
isn't offered or recognized. That's what "extend... to arbitrary manifest
-discovered widgets" means here: discovery itself needs to stay live, not
just already-open instances' source.

## Affected files

- `src/desk/shell/window.py` (edit) — `DeskWindow` gains a `widgets_dir`
  parameter and re-runs `discover_widgets()` on every `widget_changed`
  signal, refreshing the catalog.
- `src/desk/app.py` (edit) — pass `widgets_dir` through to `DeskWindow`.
- `design-docs/architecture.md` (edit) — note that catalog discovery is
  now live, not just per-instance source reload.

## Design

### Reuse the existing `widget_changed` signal — no new watcher plumbing

`WidgetWatcher`'s debounced handler already computes a `widget_id` from the
first path component under `widgets_dir` for *any* changed file and emits
`broker.widget_changed(widget_id)` — this already fires correctly for a
brand-new widget directory (`Path.relative_to` succeeds for any path under
`widgets_dir`, new or old; `watchdog`'s recursive observer already reports
newly-created subdirectories/files with no changes needed). So the exact
same signal that already drives per-instance reload is sufficient to also
drive catalog refresh — no new signal, no changes to `desk/widgets.py`.

`DeskWindow` additionally connects `broker.widget_changed` to a handler
that calls `discover_widgets(self._widgets_dir)` again and reassigns
`self._widgets`/`self.view.set_widget_catalog(...)`. Cheap (a handful of
small `widget.json` reads) and simple: no attempt to distinguish "was this
specifically a manifest change" from "was this a regular source change" —
re-scanning on every debounced widget event is negligible cost against the
benefit of not needing a second signal/code path.

### Existing per-instance widgets are unaffected

An already-placed `PythonWidgetHost`/`ChromiumWidget` instance keeps
running with whatever it last loaded; catalog refresh only changes what's
*offered* going forward (the add-widget menu) and what `_widgets.get(...)`
recognizes for `_on_widget_add_requested`. If a widget type's directory is
removed while an instance of it is still placed on the canvas, that
instance is left alone (explicitly out of scope — see Key Design
Decisions).

## Verification

All headless — using a real `WidgetWatcher`/`HotReloadBroker` pair against
a temporary widgets directory (creating/editing real files on disk and
waiting for the debounce), the same technique already used to verify
per-instance hot reload for items 5/9. No step requires a real,
visually-inspected window.

1. Start a `WidgetWatcher` + `HotReloadBroker` on an empty temp directory;
   confirm `discover_widgets()` initially returns nothing.
2. Create a brand-new widget directory + `widget.json` under it; wait past
   the debounce window; confirm `broker.widget_changed` fired and a
   `DeskWindow`-style catalog refresh (calling `discover_widgets()` again)
   now includes the new widget.
3. Edit an *existing* widget's `widget.json` (e.g. change `default_size`);
   confirm the refreshed catalog reflects the new value.
4. Delete a widget's directory entirely; confirm the refreshed catalog no
   longer includes it.
5. Regression: confirm a `PythonWidgetHost` instance still correctly
   rebuilds when only its `widget.py` source changes (item 9's existing
   mechanism, unaffected by the catalog-refresh addition).

## Key design decisions / tradeoffs

- **Re-scan the whole catalog on every widget-changed event, rather than
  adding a second, more targeted signal for "manifest changed
  specifically."** `discover_widgets()` is a cheap directory scan; a
  second signal/code path to distinguish manifest-only changes would add
  real complexity (the watcher would need to inspect *which* file changed,
  not just which widget directory) for a negligible performance gain.
- **No handling for a widget type's directory disappearing while an
  instance of it is still placed on the canvas.** The TODO item is about
  discovery staying live, not about lifecycle-managing widgets whose
  source vanished out from under a running instance — that's a distinct,
  separable concern (and arguably no worse than what already happens today
  if a `python` widget's `widget.py` is simply made invalid while running).

## Status

Implemented and verified, entirely headlessly (per instruction, anything
needing real-window/visual inspection would have been marked blocked
instead — nothing here did): using a real `WidgetWatcher`/
`HotReloadBroker` pair against a temporary widgets directory, creating/
editing/deleting real files on disk and pumping the Qt event loop past the
debounce window.

1. Confirmed a `DeskWindow` constructed with `widgets_dir` set picks up a
   brand-new widget directory + `widget.json` created after startup —
   `window._widgets` and `window.view._widget_catalog` both include it,
   with no restart.
2. Confirmed editing an existing widget's `widget.json` (`default_size`)
   is reflected in the refreshed catalog.
3. Confirmed deleting a widget's directory removes it from the catalog.
4. Regression: confirmed an existing `PythonWidgetHost` instance still
   correctly rebuilds when only its own `widget.py` source changes (item
   9's mechanism, unaffected by the catalog-refresh addition).

Also discovered and fixed a test-methodology-only gotcha along the way
(not a bug in the shipped code): `WidgetWatcher` silently never fires when
pointed at a raw `tempfile.mkdtemp()` path on macOS, because that path is
under the `/var/folders` → `/private/var/folders` symlink and `watchdog`'s
FSEvents backend reports the resolved path, breaking the handler's
`relative_to()` match. Recorded in `LEARNINGS.md`; the real app is
unaffected since `DEFAULT_WIDGETS_DIR` is already `.resolve()`'d.
