# Wire widget-local storage save/restore through the Desk Bridge API for html-kind widgets (COMPLETED)

TODO `5734529`.

## Summary

An agent building a tempui-DSL-defined custom widget (TODO `91b3f42`,
entirely `kind: "html"`) reported: "state persistence (no
widget-local-storage wiring — the Desk Bridge API exists for html
widgets but nothing implements save/restore for one yet)." Confirmed
directly: "widget-local storage" (TODO `fb76057` --
`get_widget_local_storage()`/`set_widget_local_storage()`, `WidgetState
.state`) is a duck-typed contract only ever checked against
`PythonWidgetHost` content (`_bind_widget_local_storage`/`_get_widget_
local_storage` in `window.py` both `isinstance(frame.content,
PythonWidgetHost)`-gate) -- for a `ChromiumWidget`-backed frame (any
`kind: "html"` widget, tempui-defined or not), both always no-op /
contribute `{}`. There is genuinely no way today for an HTML widget's
own JS to persist anything across a Desk reload.

This is a real, general gap (not specific to tempui-defined widgets --
any `kind: "html"` widget has the same problem), fixed by extending
widget-local storage to `kind: "html"` widgets via two new Bridge API
calls, `self.getLocalStorage()`/`self.setLocalStorage(data)`, and
documenting the (now-updated) Bridge API in `desk-temporary-ui.md` so
an agent authoring a `DefineWidget` widget can actually discover and
use it from that one doc, rather than needing to read Desk's own
source/design docs to learn it exists (per the report: "this Claude
instance had access to Desk's source, so it likely learned about the
Bridge API from the plans or design docs" -- not from the one doc it's
actually handed when building a tempui widget).

## Diagnosis: a second, necessary gap -- no per-instance identity in the Bridge API at all

Widget-local storage is inherently **per-instance** (`WidgetState
.state` is keyed by `instance_id`, not just widget kind -- two placed
instances of the same kind have independent state). But the Bridge
API's client library (`desk.server.bridge_client
.render_bridge_client`) only ever embeds the calling widget's *kind*
id (`WIDGET_ID`, baked into `ChromiumWidget.__init__` from
`_place_widget`'s `widget_id` argument) -- there is no notion anywhere
of *which instance* of a kind is making a given Bridge call. Two
side-by-side instances of the same custom widget kind are
indistinguishable to the server today. This had to be fixed as part of
implementing save/restore at all, not a separate, optional
improvement -- there's no way to answer "get/set *my own* local
storage" without knowing which "me" is asking.

## Fix

**Thread `instance_id` through the same path `widget_id` already
takes**, end to end:

- `ChromiumWidget.__init__` gains an `instance_id: str` parameter
  (stored as `self.instance_id`, alongside the existing
  `self.widget_id`).
- `render_bridge_client(widget_id, instance_id, token)` embeds a new
  `INSTANCE_ID` constant; the client's shared `call()` helper sends it
  as a new `X-Desk-Instance-Id` header on every Bridge request,
  alongside the existing `X-Desk-Token`/`X-Desk-Widget-Id`.
- `DeskWindow._place_widget`'s `kind: "html"` branch resolves a
  concrete `instance_id` *before* constructing `ChromiumWidget`
  (matching the existing Claude-widget special case's own "generate a
  concrete id upfront, don't leave it to `WidgetFrame`'s own internal
  default" shape) -- the Bridge client script's source is baked in at
  `ChromiumWidget.__init__` time, so the id has to be known before
  that call, not set retroactively afterward.

**New Bridge API routes**, requiring no capability (the same reasoning
`self.getManifest` already uses -- a widget can only ever touch *its
own* per-instance storage, keyed by an id it can't spoof its way into
someone else's meaningfully more than it already trusts itself; no
broader resource is at stake):

- `GET /api/bridge/self/getLocalStorage` → `{"data": {...}}`.
- `POST /api/bridge/self/setLocalStorage` `{"data": {...}}` → `{"ok":
  true}`.

Both resolve the calling instance purely from the `X-Desk-Instance-Id`
header -- deliberately **not** via `require_caller`'s existing
`discover_widgets(widgets_dir).get(x_desk_widget_id)` lookup, which
only ever finds *real, on-disk* `widgets/<id>/` directories and would
raise `400 Unknown widget id` for any tempui-defined custom widget
kind (a separate, real, pre-existing gap affecting every *other*
Bridge capability for custom widgets too -- out of scope for this
specific fix, parked in `PARKINGLOT.md`).

**`DeskWindow` gains `self._html_widget_local_storage: dict[str,
dict]`** (instance_id → state), plus public `get_html_widget_local_
storage(instance_id)`/`set_html_widget_local_storage(instance_id,
data)` methods the Bridge routes call via `GuiBridge.call` (same
cross-thread pattern as `workspace.getState`/`widgets.open`/`close`).
`_bind_widget_local_storage`/`_get_widget_local_storage` (the existing
generic hooks `_load_desk_widgets`/`_capture_desk_state` already call
for every placed frame) gain a `ChromiumWidget` branch reading from/
writing to this dict, alongside the existing `PythonWidgetHost`
branch -- same pull-based shape (`_get_widget_local_storage` is read
fresh only at actual save time, never pushed eagerly on every widget
-side change).

On restore (`_load_desk_widgets`), the persisted `state.state` is
seeded into `_html_widget_local_storage[instance_id]` *before* the
widget's page has any chance to call `getLocalStorage()` (the seed
happens synchronously in Python; the page's own JS only runs
asynchronously after `ChromiumWidget.load()` returns), so a widget
calling `getLocalStorage()` from its own startup code always sees the
restored data, not a race.

`switch_desk` clears `_html_widget_local_storage` alongside the
existing custom-widget-registration cleanup -- per-Desk-directory,
per-instance state that's meaningless once `view.clear_widgets()` has
already destroyed the frames it belonged to (avoids an unbounded
in-memory accumulation of stale entries across many Desk switches in
one long-running session).

## `desk-temporary-ui.md` documentation (version bump required)

New section describing the full, now-updated `window.desk.*` Bridge
API surface available to any `kind: "html"` widget's own JS --
`self.getManifest`/`getLocalStorage`/`setLocalStorage`,
`workspace.getState`, `fs.readFile`/`writeFile`, `widgets.list`/
`open`/`close` -- written for an agent about to write JS for a
`DefineWidget`-defined widget, with the new local-storage calls
highlighted as *the* mechanism for a custom widget to actually persist
anything across a reload. This is a real, agent-meaningful content
change (the doc previously said nothing about the Bridge API at all),
so `TEMPUI_DOC_VERSION` (TODO `f7b1611`) bumps from 1 to 2 --
`ensure_doc_version_current` picks this up and refreshes any
already-provisioned Desk's stale copy the next time it's opened,
preserving its custom-widgets section exactly as that mechanism
already guarantees.

## Affected files

- `src/desk/server/bridge_client.py` -- `INSTANCE_ID`, the new header,
  `self.getLocalStorage`/`setLocalStorage` client methods;
  `render_bridge_client`'s new parameter.
- `src/desk/shell/chromium_widget.py` -- `instance_id` parameter/
  attribute.
- `src/desk/shell/window.py` -- `_place_widget` resolves a concrete
  `instance_id` before constructing `ChromiumWidget`;
  `_bind_widget_local_storage`/`_get_widget_local_storage` gain the
  `ChromiumWidget` branch; new `_html_widget_local_storage` dict +
  `get_html_widget_local_storage`/`set_html_widget_local_storage`;
  `switch_desk` clears the dict.
- `src/desk/server/app.py` -- the two new routes.
- `src/desk/temp_ui.py` -- `TEMPUI_DOC_VERSION` bump, new Bridge API
  doc section in `DOC_TEMPLATE`.
- `design-docs/architecture.md` -- Bridge API REST-surface mention
  updated with the new routes and the `instance_id` addition.
- `PARKINGLOT.md` -- new entry: `require_caller`'s
  `discover_widgets(widgets_dir)`-based lookup can't resolve a
  tempui-defined custom widget kind at all, breaking every *other*
  Bridge capability (`workspace`/`fs`/`widgets`) for one.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`; a real
FastAPI `TestClient`/running server where the actual HTTP routes
matter; unbound-method-on-a-fake-double for `DeskWindow`-dependent
logic):

- `get_html_widget_local_storage`/`set_html_widget_local_storage`:
  round-trip; unknown instance id returns `{}`, not an error.
- `_bind_widget_local_storage`/`_get_widget_local_storage`: a
  `ChromiumWidget`-backed frame round-trips through the new dict; a
  `PythonWidgetHost`-backed frame's existing behavior is unchanged
  (regression check).
- `_place_widget`: a freshly placed `kind: "html"` instance's
  `ChromiumWidget.instance_id` matches its `WidgetFrame.instance_id`
  exactly (no mismatch/race), for both an explicit and an
  auto-generated instance id.
- `render_bridge_client`: the rendered script embeds `INSTANCE_ID` and
  sends `X-Desk-Instance-Id` from `self.getLocalStorage`/
  `setLocalStorage` calls (and every other call, unconditionally).
- The two new HTTP routes end to end (`self_get_local_storage`/
  `self_set_local_storage` wired to a fake `GuiBridge.window`):
  `setLocalStorage` then `getLocalStorage` round-trips; a
  never-set instance id's `getLocalStorage` returns `{"data": {}}`,
  not a 400/500.
- A full save → reload round trip: place an html widget, simulate its
  JS calling `setLocalStorage`, save the Desk, reload it, confirm
  `getLocalStorage` for the restored instance returns the persisted
  data (not a fresh instance's empty default) -- proves the seed
  -before-page-load ordering actually works, not just the two halves
  in isolation.
- `TEMPUI_DOC_VERSION` bumped to 2; `parse_doc_version`/
  `ensure_doc_version_current` still behave correctly against the new
  value (regression check against TODO `f7b1611`'s own suite).
- Full scratchpad regression suite re-run.

## Status

Implemented exactly as planned: `instance_id` threaded through
`render_bridge_client`/`ChromiumWidget`/`_place_widget`; the two new
routes (`self.getLocalStorage`/`setLocalStorage`) in `src/desk/server
/app.py`, deliberately not built on `require_caller`; `DeskWindow
.get_html_widget_local_storage`/`set_html_widget_local_storage` +
`_html_widget_local_storage`; `_bind_widget_local_storage`/`_get_
widget_local_storage` gained the `ChromiumWidget` branch (the latter
is no longer a `@staticmethod`, since it now needs `self`);
`switch_desk` clears the new dict alongside its existing custom-widget
cleanup. `TEMPUI_DOC_VERSION` bumped 1 → 2 with the new Bridge API
section in `DOC_TEMPLATE`. `design-docs/architecture.md`'s Bridge API
section and `PARKINGLOT.md` updated as planned.

Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real `QApplication`,
a real running `uvicorn` server via `desk.server.runner.start_server`
for the two new routes' end-to-end check, a real `WorkspaceView` for
the `_place_widget` instance-id-matching check): sanity-checked the
fix is real first (`git stash`-ing all five touched source files and
re-running the new suite fails immediately, as expected, on
`DeskWindow` simply not having the new methods yet — confirming the
suite isn't just testing already-true assertions). With the fix: doc
version is 2 and documents the new calls; `render_bridge_client`
embeds `INSTANCE_ID` and sends `X-Desk-Instance-Id`; get/set round-trip
per instance, unknown instance is `{}`; the `ChromiumWidget` branch of
`_bind_widget_local_storage`/`_get_widget_local_storage` round-trips
correctly; `_place_widget` never produces a
`ChromiumWidget.instance_id`/`WidgetFrame.instance_id` mismatch, for
both an explicit and an auto-generated id; the two new HTTP routes
round-trip over real HTTP with per-instance isolation (run on a
background thread while the main thread pumps `app.processEvents()`,
since `GuiBridge.call`'s queued signal needs the GUI event loop
actually spinning to dispatch — doing the HTTP calls synchronously on
the same thread as the "GUI" would have deadlocked); and a full
save → reload simulation confirms persisted `kind: "html"` widget
state survives and reseeds correctly before any page JS could
plausibly run.

Two pre-existing scratchpad scripts needed small updates (not left
broken): `verify_widget_local_storage.py`'s unbound
`DeskWindow._get_widget_local_storage(frame)` call needed a `None`
`self` argument added now that the method is no longer a
`staticmethod`; `verify_new_desk_flow.py`'s `_OrderTrackingWindow` fake
needed `_html_widget_local_storage = {}` added alongside its existing
custom-widget dict fakes, since the real `switch_desk` it exercises now
touches that too. Full scratchpad regression suite re-run — same three
pre-existing, unrelated failures as every recent prior TODO, none
touching any file edited here.

No `LEARNINGS.md` entry -- the one genuinely non-obvious mechanical
detail from this work (`GuiBridge.call` needs the GUI thread's event
loop actively spinning, so a test driving it must run the HTTP side on
a background thread while pumping `app.processEvents()`, not call it
synchronously from the "GUI" thread) is a **test-infrastructure**
gotcha specific to how this was verified, not a surprise about the
production code/API itself — recorded directly in the test's own
docstring instead, where whoever next needs this pattern will actually
see it.
