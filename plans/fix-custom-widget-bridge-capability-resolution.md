# Fix: Bridge API can't resolve a tempui-DSL-defined custom widget for any capability check

TODO `f693275`.

## Summary

Reported live: after restarting Desk, the `Alice`/`Bob`/`Starter`
tempui-DSL-defined widgets (built for TODO `6f9c51b`) all fail with
`subscribe failed: ... (400): {"detail":"Unknown widget id: 'Alice'"}`.

This is the exact gap already flagged in `PARKINGLOT.md` ("The Bridge
API's `require_caller` can't resolve a tempui-DSL-defined custom widget
kind at all"), surfaced back when TODO `5734529` built
`self.getLocalStorage`/`setLocalStorage` (deliberately *not* built on
`require_caller`, for exactly this reason) but left unfixed generally.
`require_caller`'s dependency (`src/desk/server/app.py`) resolves the
calling widget only via `discover_widgets(widgets_dir).get(x_desk_widget_id)`
— a pure filesystem scan of the real, on-disk `widgets/` directory. A
tempui-DSL-defined custom widget (TODO `91b3f42`) has no such directory;
its `WidgetInfo` only ever lives in the live `DeskWindow._widgets`
catalog (populated at registration time). So *any* capability-gated
Bridge call from a custom widget — `workspace.*`/`fs.*`/`widgets.*`, and
now `events.*` — 400s, not just `events`.

Separately, even a fixed lookup alone wouldn't be enough:
`_register_custom_widget` currently always registers a custom widget
with `capabilities=[]` hardcoded, since the `DefineWidget` tempui DSL
has no way to declare any capability at all.

## Design

### 1. `require_caller` falls back to the live, GuiBridge-reachable catalog

`require_caller`'s dependency becomes `async`: first tries
`discover_widgets(widgets_dir).get(x_desk_widget_id)` (fast, no
GUI-thread hop, works even without a `gui_bridge`); if that misses,
falls back to `await run_on_gui(lambda: gui_bridge.window.get_widget_info(x_desk_widget_id))`
— the same `run_in_executor` + `GuiBridge.call` pattern every other
GUI-thread-touching route already uses, so this is a genuine, correct
cross-thread read, not a raw unsynchronized attribute access from the
background thread. If `gui_bridge`/its window isn't available at all,
`run_on_gui` already raises a `503` (existing behavior) — a more
accurate error than a misleading `400` in that case, so it's left to
propagate rather than swallowed. New `DeskWindow.get_widget_info(widget_id) ->
WidgetInfo | None` accessor (`self._widgets.get(widget_id)`) added
rather than reaching into `gui_bridge.window._widgets` directly from
`app.py`, matching the existing `get_state_dict`/
`get_html_widget_local_storage`-style clean-accessor convention.

This single fix applies uniformly to every existing capability
(`workspace`/`fs`/`widgets`) and the new `events` capability at once —
not a narrow `events`-only patch — resolving the PARKINGLOT.md entry in
full, per its own framing.

### 2. A new `Capability` DSL line for `DefineWidget`

`CustomWidgetDefinition` gains `capabilities: list[str] = field(default_factory=list)`.
`parse_define_widget` collects zero or more `Capability<TAB>name` lines
(same tab-separated shape as `Size`) into that list.
`_register_custom_widget` passes `capabilities=definition.capabilities`
to the `WidgetInfo` it builds, instead of the current hardcoded `[]`.
`.desk`-file persistence (`desk.desks._load_custom_widget`/
`_custom_widget_dict`) round-trips the new field, defaulting to `[]` on
load for backward compatibility with a `.desk` file saved before this
existed.

### 3. Docs

`tempui-custom-widgets.md` (`_CUSTOM_WIDGETS_DOC` in
`src/desk/temp_ui.py`) documents the new `Capability` line next to
`Size`, and gets a short note under "The Desk Bridge API" section
clarifying that a `DefineWidget` widget must declare a capability the
same way a real `widgets/<id>/widget.json` does to use anything beyond
`self.*`. `TEMPUI_DOC_VERSION` bumped 7 -> 8 (a real new DSL line, per
that constant's own bump criteria).

`PARKINGLOT.md`'s "The Bridge API's `require_caller` can't resolve..."
entry is removed (moved to `TODO.md`/acted on, per that file's own
stated workflow).

### 4. Existing Alice/Bob/Starter tempui files

The three already-written `DefineWidget` files in this project's own
`.desk_temp/` get a `Capability\tevents` line added (edited in place —
`_register_custom_widget`'s existing "re-registering the same keyword
from the same source just refreshes it" behavior means no new UUID/
invoke step is needed once Desk picks up the edit). This requires a
Desk restart to take effect, same as any other change to `src/desk/**`
application code (unlike widget source, which hot-reloads; `src/desk/`
itself is only imported once at process startup).

## Affected files

- `src/desk/server/app.py` — `require_caller`'s fallback resolution.
- `src/desk/shell/window.py` — `get_widget_info` accessor,
  `_register_custom_widget`'s `capabilities=` fix.
- `src/desk/temp_ui.py` — `CustomWidgetDefinition.capabilities`,
  `parse_define_widget`'s `Capability` line, `_CUSTOM_WIDGETS_DOC`
  update, `TEMPUI_DOC_VERSION` bump 7 -> 8.
- `src/desk/desks.py` — `_load_custom_widget`/`_custom_widget_dict`
  round-tripping `capabilities`.
- `PARKINGLOT.md` — remove the now-resolved entry.
- `.desk_temp/` (untracked, this project's own live directory) —
  Alice/Bob/Starter's `DefineWidget` files gain `Capability\tevents`.

## Verification

Headless:

- `parse_define_widget`: zero, one, and multiple `Capability` lines
  all parse into the right list; a definition with none defaults to
  `[]` (unchanged existing behavior for every prior `DefineWidget`
  file, including ones with no idea this line exists).
- `_register_custom_widget` (via a real `DeskWindow`): a registered
  custom widget's `WidgetInfo.capabilities` reflects the definition's
  declared capabilities, not `[]`.
- `.desk` round-trip: save then load a `Desk` with a promoted custom
  widget declaring capabilities — survives intact; loading an
  old-shaped `.desk` file (no `capabilities` key at all in its
  `custom_widgets` entries) defaults to `[]` without raising.
- `require_caller`'s fallback, against a real running server + real
  `DeskWindow` with a registered custom widget declaring `events`: a
  Bridge call from that custom widget's id now succeeds (previously
  400); a custom widget with no matching capability still correctly
  403s (not a blanket bypass); an id that's unknown to *both* the
  on-disk catalog and the live GUI catalog still correctly 400s (the
  fix doesn't turn every miss into a false positive).
- End-to-end regression of the original Alice/Bob/Starter scenario
  (TODO `6f9c51b`'s own verification), rebuilt against real `DefineWidget`
  files that include `Capability\tevents`, through a real `DeskWindow` +
  real running server — confirms the exact originally-reported failure
  is gone and the full 0→10 chain still behaves correctly.

## Status

Not yet implemented — plan written first per `development-process.md`.
