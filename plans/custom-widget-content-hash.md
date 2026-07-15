# Plan: TODO 5995ffd — custom widget content-hash staleness detection

See design-docs/custom-widget-authoring.md section 3 for the full
rationale.

## Summary

A placed `DefineWidget` instance never re-fetches its HTML just because
the registered definition changed later — reasonable, but there's
currently no way to tell, from outside, whether a specific placed
instance predates the currently-registered definition. Add a content
hash at registration time, expose it live (`desk.self.getManifest()`),
and track it per placed instance so Desk's own chrome can show a passive
`[STALE]` marker without requiring a widget author to write any code.

## Data model

- `desk.widgets.WidgetInfo` gains `content_hash: str | None = None` --
  `None` for every ordinary `widgets/<id>/widget.json`-backed widget
  (never set by `_parse_manifest`), populated only for a tempui-DSL
  -defined custom widget.
- `desk.desks.WidgetState` gains `placed_content_hash: str | None = None`
  -- the definition's content hash *at the moment this specific instance
  was placed*, threaded through `desk_state_dict`/`load_desk`/
  `save_desk` the same way `locked` already is (a chrome-level concept,
  not routed through the widget-local-storage `state` dict).

## Computing the hash

In `DeskWindow._register_custom_widget`, alongside the existing
`materialize` call: `hashlib.md5(definition.html_b64.encode("ascii"))
.hexdigest()[:12]` -- hashing the already-available base64 text directly
(equivalent to hashing the decoded HTML, since it's a deterministic
encoding of it, and avoids a second decode). Store in a new
`self._custom_widget_content_hash: dict[str, str]` (keyword -> hash) and
on the `WidgetInfo.content_hash` field.

## Bridge API exposure

`desk/server/app.py`'s `_widget_info_dict` (used by both `getManifest`
and `widgets.list`) gains `"content_hash": widget.content_hash` in its
returned dict -- a `DefineWidget` widget's own JS can call
`desk.self.getManifest()` and get the currently-registered definition's
hash without decoding base64 or spinning up a separate headless browser.

## Per-instance tracking + passive chrome indicator

- `WidgetFrame` gains a `placed_content_hash: str | None = None`
  attribute (set at `__init__`) and a `set_stale(is_stale: bool)` method
  that forwards to `_TitleBar.set_stale`, mirroring `set_external`/
  `set_locked`'s existing shape exactly.
- `_TitleBar` gains `set_stale`: appends `" [STALE]"` to the title label
  (same mechanism as `set_external`'s `" [EXTERNAL]"`) and sets a tooltip
  on the label explaining what it means and what to do (close and re
  -invoke, or use the `[TEMPUI]` promote flow's own reasoning about
  re-placement) when stale; clears both when not.
- `DeskWindow._place_widget`: for a **fresh** (non-restore) placement
  whose `widget_id` has a registered content hash, set
  `frame.placed_content_hash` to the current hash and `frame.set_stale
  (False)` -- a fresh placement is always current by construction.
- `DeskWindow._load_desk_widgets`: for a **restored** widget whose saved
  `state.placed_content_hash` is not `None`, set
  `frame.placed_content_hash = state.placed_content_hash` and compare
  against the live `self._custom_widget_content_hash.get(state
  .widget_id)`, calling `frame.set_stale(...)` accordingly -- this is the
  main case that matters (a Desk reopened after the widget's source
  changed since the instance was last saved).
- `DeskWindow._capture_desk_state`: include `placed_content_hash=frame
  .placed_content_hash` when building each `WidgetState`.
- New `DeskWindow._refresh_stale_indicators_for(keyword: str) -> None`:
  called at the end of `_register_custom_widget` (every registration,
  fresh or a same-source refresh) -- looks up the keyword's current hash
  and, for every already-placed frame whose `content.widget_id ==
  keyword` and whose `placed_content_hash` is not `None`, recomputes and
  applies `set_stale`. This is what catches the *live* case from the
  feedback: editing an already-registered `DefineWidget` file while an
  instance is already on the canvas immediately marks that instance
  stale, without needing a restart.

## Verification

- `WidgetInfo.content_hash`/`WidgetState.placed_content_hash` round-trip
  through `desk_state_dict`/`load_desk`/`save_desk`.
- `_register_custom_widget` populates `self._custom_widget_content_hash`
  and `WidgetInfo.content_hash`; re-registering with different
  `html_b64` changes the hash.
- Bridge API: `_widget_info_dict` includes `content_hash` (a small
  `create_app`-level check, or a unit check of `_widget_info_dict`
  directly).
- On a real `WorkspaceView` (mirroring the pattern used for TODO
  5ff02d2's own verification): a fresh placement is never stale; editing
  the definition afterward while the instance is still placed marks it
  stale live, with the titlebar showing `[STALE]`; a restored instance
  whose saved hash matches the current one is not stale, and one whose
  saved hash predates the current one is.
- Full scratchpad regression suite (`git stash` before/after to confirm
  no pre-existing-vs-new conflation).
