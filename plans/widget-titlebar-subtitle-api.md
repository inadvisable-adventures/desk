# Add `desk.self.setSubtitle` Bridge API call (TODO `3cd90cf`)

## Summary

Per
`../FEEDBACK/FEEDBACK-DESK-widget-titlebar-subtitle-api-2026-08-03-1830.md`:
a widget's titlebar text is fixed at construction
(`_TitleBar.__init__`, `src/desk/shell/widget_frame.py:291`) and never
changes except the existing `[EXTERNAL]` suffix, toggled externally by
`DeskWindow`, never by the widget's own code. A `kind: "html"` widget
whose whole purpose is "edit one particular thing, chosen by the user
at runtime" (the FEEDBACK item's concrete example: `necro-4x`'s
`DomainAnalysis` widget) has no titlebar-level way to surface *which*
thing a given instance is showing -- every instance of a widget kind
shows the identical, static kind label. Add
`desk.self.setSubtitle(text: string | null)` to the Bridge API so an
instance can put its own state into its own titlebar, composing with
the existing `[EXTERNAL]` suffix the same way `[STALE]`/`[ERROR]`/
`[TEMPUI]` (separate clickable buttons, not part of the label text)
already don't need to worry about.

## Affected files

- `src/desk/server/bridge_client.py` -- `self: {...}` gets
  `setSubtitle`.
- `src/desk/server/app.py` -- new `SetSubtitleRequest` model and
  `POST /api/bridge/self/setSubtitle` route.
- `src/desk/shell/window.py` -- new `DeskWindow.set_widget_subtitle`.
- `src/desk/shell/widget_frame.py` -- new `WidgetFrame.set_subtitle`/
  `_TitleBar.set_subtitle`, `_update_label_text` composes title +
  subtitle + `[EXTERNAL]`.
- `src/desk/temp_ui.py` -- doc text, `TEMPUI_DOC_VERSION` bump,
  `_NEW_FEATURES_DOC` entry.
- `tests/verify/` -- new coverage.

## Design decisions

- **Mirrors `getLocalStorage`/`setLocalStorage`'s shape exactly**:
  `self`-scoped, gated only by `require_instance_id` (no capability
  check) -- matches that pair's own precedent comment in `app.py`
  ("need no broader capability at all... a widget can only ever touch
  its own [state]"). Setting your own titlebar subtitle is exactly as
  non-privileged and instance-scoped as those two.
- **Composition format**: `f"{title} — {subtitle}"` (em dash) before
  the `[EXTERNAL]` suffix, verbatim per the FEEDBACK item's own
  suggested `_update_label_text` shape. `None` or an empty string
  clears it back to the bare title -- covers a widget instance that
  starts unconfigured (e.g. before the user has picked a document).
- **`DeskWindow.set_widget_subtitle` is a tolerant no-op for an
  unknown instance id**, not an error -- same shape as
  `start_dom_snapshot`'s target-not-found handling and
  `zoom_to_widget_by_instance_id`'s `find`-then-`if None: return`
  pattern elsewhere in this same class, appropriate here since a
  request racing a just-closed widget shouldn't surface as a Bridge
  -level failure to the caller.
- **`kind: "python"` widgets explicitly out of scope**, per the
  FEEDBACK item's own framing -- `current_context` has no obvious
  existing per-instance-id hook a `python`-kind widget's own code
  could use the same way `getLocalStorage`/`setLocalStorage` do for
  `kind: "html"`; investigating that is real, separate work.

## Step-by-step implementation

1. `bridge_client.py`: add `setSubtitle: (text) =>
   call("POST", "/api/bridge/self/setSubtitle", { text: text ?? null
   }),` to the `self: {...}` object.
2. `app.py`: add `class SetSubtitleRequest(BaseModel): text: str |
   None`; add `POST /api/bridge/self/setSubtitle`, gated by
   `require_instance_id` only (mirroring `self_set_local_storage`),
   calling `gui_bridge.window.set_widget_subtitle(instance_id,
   body.text)`.
3. `window.py`: add `DeskWindow.set_widget_subtitle(self, instance_id:
   str, text: str | None) -> None` -- resolves via
   `find_frame_by_instance_id`, no-ops if not found, otherwise calls
   `frame.set_subtitle(text)`.
4. `widget_frame.py`:
   - `_TitleBar.__init__`: add `self._subtitle: str | None = None`.
   - `_TitleBar.set_subtitle(self, subtitle: str | None) -> None`:
     stores it, calls `_update_label_text()`.
   - `_TitleBar._update_label_text`: compose `title` + (subtitle, if
     truthy, via the em-dash format above) + (`[EXTERNAL]`, if set) in
     that order.
   - `WidgetFrame.set_subtitle(self, subtitle: str | None) -> None`:
     delegates to `self._titlebar.set_subtitle(subtitle)` -- same thin
     -delegation shape as `set_external`/`set_stale`.
5. `temp_ui.py`: document `desk.self.setSubtitle` in the Bridge API
   section (`_CUSTOM_WIDGETS_DOC`, alongside `getLocalStorage`/
   `setLocalStorage`/`getManifest`); bump `TEMPUI_DOC_VERSION`, add the
   matching comment block and `_NEW_FEATURES_DOC` entry.
6. New verify coverage (see below); run the full `tests/verify/`
   suite.

## Key tradeoffs

- No length cap or sanitization on `text` -- matches `setLocalStorage`
  (`data: dict`, no validation) and `getManifest`'s existing fields;
  a widget author fully controls their own titlebar text the same way
  they already fully control their own widget content. A pathologically
  long subtitle is a widget-author UX bug, not a Desk-level concern
  worth guarding against here.
- Not persisted anywhere (unlike `getLocalStorage`/`setLocalStorage`)
  -- a fresh Desk reload starts every instance back at its bare title
  until the widget's own JS calls `setSubtitle` again (e.g. right after
  restoring its own state via `getLocalStorage`). This matches the
  FEEDBACK item's own framing (a titlebar reflection of current state,
  not a second persistence mechanism) and keeps this change additive
  -only to the existing `.desk`-file schema.

## Verification

New checks, real (no mocking), in a new
`tests/verify/verify_widget_titlebar_subtitle.py`:
- `_TitleBar.set_subtitle`/`_update_label_text`: bare title with no
  subtitle; title + subtitle; title + subtitle + `[EXTERNAL]` (all
  three composed in the right order); subtitle cleared back to the
  bare title via `None` and via `""`.
- `WidgetFrame.set_subtitle` delegates correctly (same pattern as the
  existing `set_external`/`set_stale` coverage elsewhere).
- `DeskWindow.set_widget_subtitle`: a real `find_frame_by_instance_id`
  round trip updates the right frame's titlebar label text; an unknown
  instance id is a silent no-op (no exception).
- A real HTTP round trip through a real `start_server` instance +
  `SetSubtitleRequest`: `POST /api/bridge/self/setSubtitle` with a
  known instance id returns `{"ok": true}` and the label actually
  updates; no `X-Desk-Widget-Id`/capability needed (only
  `X-Desk-Instance-Id`), confirmed by omitting the widget-id header
  entirely and still succeeding, the same way
  `verify_html_widget_local_storage.py`/an equivalent already covers
  for `setLocalStorage`.
- `bridge_client.py`'s rendered template declares
  `self.setSubtitle` (string containment check, same shape as
  `test_bridge_client_declares_editor_namespace` in
  `verify_bridge_api_editor_or_scrap.py`).
- `TEMPUI_DOC_VERSION` bumped, with a matching changelog entry;
  `_CUSTOM_WIDGETS_DOC` documents `desk.self.setSubtitle`.
- Full `tests/verify/` regression suite.
