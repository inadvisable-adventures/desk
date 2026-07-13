# Fix [TEMPUI] button visibility and spawn-menu exclusion to track actual promotion status (COMPLETED)

TODO `6857997`, TODO `2b2a642`.

## Summary

Two reported bugs in the tempui custom-widgets feature (TODO
`91b3f42`), both traced to the same root cause:

1. The `[TEMPUI]` titlebar button was shown for *every* custom widget
   instance, `.desk`-file-sourced ones included — it should only show
   while the widget's definition still lives in `.desk_temp` (not yet
   promoted).
2. A promoted custom widget never appeared in the "Add widget"
   spawn-menu catalog, even after a full app reload — it should, once
   promoted: the whole point of promoting a widget is that it becomes
   a permanent, first-class part of the Desk, placeable the normal way
   from then on, not just re-invokable via tempui.

## Diagnosis

`WidgetInfo.tempui_only` was **hardcoded to `True`** in
`DeskWindow._register_custom_widget`, regardless of the `source`
argument actually passed in (`"tempui"` or `"desk"`). This broke both
things at once:

- `_place_widget` showed the `[TEMPUI]` button for `widget_id in
  self._custom_widget_definitions` — true for *any* custom widget,
  promoted or not (bug 1).
- `WorkspaceView.contextMenuEvent`'s spawn-menu filter excludes
  anything with `tempui_only=True` — true for a promoted widget too,
  since `_register_custom_widgets_from_desk` (run at startup and on
  Desk switch) calls `_register_custom_widget(definition,
  source="desk")`, which still built a `tempui_only=True`
  `WidgetInfo` despite the `"desk"` source. This is exactly why the
  bug reproduced "even after reloading the app" — a fresh registration
  from the `.desk` file's own saved list still got the wrong flag
  (bug 2).

Separately, *live* promotion within a running session
(`_on_tempui_promote_requested`) never touched the already-registered
`WidgetInfo` at all — it only updated `self._custom_widget_sources`
and appended to `Desk.custom_widgets`, leaving the stale
`tempui_only=True` object in `self._widgets` untouched even within the
same session, and never refreshed the spawn-menu-visible catalog to
reflect it.

## Fix

- `_register_custom_widget`: `tempui_only=(source == "tempui")` instead
  of a hardcoded `True`. This alone fixes bug 2's "even after
  reloading the app" case, since a fresh `source="desk"` registration
  now correctly produces `tempui_only=False`.
- `_place_widget`: show the button only when `self.
  _custom_widget_sources.get(widget_id) == "tempui"`, not merely
  `widget_id in self._custom_widget_definitions`. Fixes bug 1 for both
  freshly-placed instances and restored ones.
- `_on_tempui_promote_requested`: on a successful promotion, flips the
  *existing* `WidgetInfo.tempui_only` to `False` in place (mutating the
  same object already referenced by `self._widgets` — no need to
  rebuild it, since `materialize`/mounting/etc. are all unchanged by
  promotion), refreshes the spawn-menu-visible catalog (`self.view
  .set_widget_catalog(self._widgets)`), and hides the button on that
  frame (`frame.set_tempui_promotable(False)`) so it disappears
  immediately without needing a reload.

The existing "already part of the Desk" informational-message branch
in `_on_tempui_promote_requested` is left in place as a defensive
fallback (a hidden `QWidget` shouldn't be reachable via the normal
click-handling path at all once its button is hidden, but there's no
reason to remove a harmless guard against some future change
reintroducing a stale-visibility edge case).

## Affected files

- `src/desk/shell/window.py` -- `_register_custom_widget`,
  `_place_widget`, `_on_tempui_promote_requested`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, a real
`WorkspaceView` for the placement/catalog-visibility checks; unbound
-method-on-a-fake-double for the rest):

- `_register_custom_widget(definition, source="desk")` now produces a
  `WidgetInfo` with `tempui_only=False`; `source="tempui"` still
  produces `tempui_only=True` (regression check).
- `_place_widget` shows the `[TEMPUI]` button only for a
  `source="tempui"` instance, never for a `source="desk"` one --
  covering both a fresh placement and a simulated "restored from a
  reloaded .desk file" placement (registering from `desk.custom_widgets`
  first, matching startup order, then placing).
- End-to-end promote flow: before promotion, the placed instance's
  button is visible and the widget's catalog entry is `tempui_only`
  (excluded from a spawn-menu-style filter); after promoting, the same
  frame's button is hidden, the catalog entry is no longer
  `tempui_only` (included in a spawn-menu-style filter), and the
  catalog was actually refreshed (not just mutated silently) --
  reproducing bug 2's exact "not showing up in the add-widget menu"
  symptom being fixed, not just asserting the flag flipped.
- Full scratchpad regression suite re-run, including the existing TODO
  `91b3f42` verification suite (some of whose assertions -- e.g. the
  `[TEMPUI]` button always showing for any custom widget -- encoded the
  very behavior being changed here; updated to match the corrected
  behavior, not left describing the bug).

## Status

Implemented exactly as diagnosed: `_register_custom_widget`'s
`tempui_only=(source == "tempui")`, `_place_widget`'s button-visibility
check keyed on `self._custom_widget_sources.get(widget_id) ==
"tempui"`, and `_on_tempui_promote_requested` flipping the existing
`WidgetInfo.tempui_only` to `False` in place, refreshing the catalog,
and hiding the frame's button on a successful promotion -- all in
`src/desk/shell/window.py`.

Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real `QApplication`,
a real `WorkspaceView` for placement checks): sanity-checked the fix
actually matters first -- `git stash`-ing just `window.py` and
re-running the new `source="desk"` registration test reproduces bug 2
directly (`tempui_only` stays `True` even for a fresh `source="desk"`
registration). With the fix: `source="desk"` registration (fresh, as
happens on every app startup from `Desk.custom_widgets`) produces
`tempui_only=False`; `_place_widget` shows the button only for a
still-`"tempui"`-sourced instance, never for a `"desk"`-sourced one
(covering a promoted widget's fresh placement, matching the "even
after reloading the app" symptom) nor an ordinary `kind: "html"`
widget; the end-to-end promote flow confirms the button is visible
and the widget is `tempui_only` *before* promoting, and immediately
afterward the same `WidgetInfo` is no longer `tempui_only`, the
spawn-menu-visible catalog was actually refreshed (not just mutated
silently -- checked via an explicit before/after refresh-count, not
just the shared-object-reference value), and the frame's own button
was told to hide. Updated the existing TODO `91b3f42` verification
suite's button-visibility test (it previously only exercised a
`source="tempui"` case, which still needed one more case: a
`source="desk"` instance never showing the button) and its
`test_register_custom_widget_success` neighbor. Re-ran the full
scratchpad regression suite -- same three pre-existing, unrelated
failures as every recent prior TODO, none touching any file edited
here.

No `LEARNINGS.md` entry -- this was a straightforward "a flag was
hardcoded instead of derived from an argument already available"
bug, not a surprising API/library behavior worth recording for a
future reader.
