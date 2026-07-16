# Plan: TODO dafbaab — remove `DefineWidget` auto-place-new-instance behavior

## Summary

TODO `5ff02d2` made a brand-new `DefineWidget` keyword (registered via
a live-added tempui file, never a re-save of an already-known keyword
or a bulk startup/Desk-switch rescan) automatically place one instance
of it, on the theory that `DefineWidget` was otherwise the only tempui
kind that could silently succeed with no visible next step. Per direct
user feedback, this proved too confusing in practice — revert it
entirely, keeping only the "louder docs" half of that original fix (the
callout that defining a kind never places an instance by itself).

## `src/desk/shell/window.py`

- `_on_temp_ui_file_added`: call `self._handle_define_widget_file(path)`
  — drop `is_new=True`.
- `_handle_define_widget_file`: drop the `is_new: bool = False`
  parameter entirely, the `keyword_already_known` local (only ever used
  to gate auto-place), and the
  ```python
  if is_new and not keyword_already_known:
      self._auto_place_new_custom_widget(definition.keyword)
  ```
  block. Rewrite the docstring to drop the `is_new`/auto-place
  explanation — it becomes a plain "register + sync the doc, nothing
  else" description.
- Delete `_auto_place_new_custom_widget` entirely (dead code once its
  only call site is gone).
- Drop the `_auto_place_new_custom_widget` mention from
  `open_widget_content_centered`'s docstring (window.py:644) — just
  `_place_discuss_claude_widget` remains as the example.
- `_on_temp_ui_file_edited` is untouched (it already never passed
  `is_new`).

## `src/desk/shell/current_context.py`

Drop the same `_auto_place_new_custom_widget` mention from
`set_centered_widget_opener`'s docstring (line 125).

## `src/desk/temp_ui.py`

- `_CUSTOM_WIDGETS_DOC`: rewrite the callout paragraph (currently "...
  Desk auto-places one instance the first time a brand-new keyword is
  registered this way ... but a `DefineWidget` file that only
  *redefines* an already-registered keyword places nothing...") to
  state plainly that `DefineWidget` **never** places an instance by
  itself, regardless of whether the keyword is brand-new or a re-save —
  always use a separate keyword-only invocation file (already documented
  in "Invoking a defined widget", unaffected).
- Bump `TEMPUI_DOC_VERSION` 17 → 18, with a new version-bump comment
  block (matching the existing running-log style) describing the
  revert.
- `_BREAKING_CHANGES_DOC`: new "## Version 18" entry — this is breaking
  from an in-Desk agent's perspective (an agent that had learned to
  rely on auto-placement for a brand-new keyword now needs to invoke it
  explicitly, same as every other tempui kind always required).
- `_NEW_FEATURES_DOC`'s existing "## Version 12" entry (which announced
  the now-removed feature) is left untouched — changelog entries are a
  dated historical record, not a currently-accurate feature list (same
  precedent as Version 14's own breaking change deferring to
  `tempui-breaking-changes.md` rather than being rewritten).

## `design-docs/custom-widget-authoring.md`

Section 2 ("Gap: `DefineWidget` registers a kind, it doesn't place an
instance") currently proposes a two-part fix (louder docs + auto-place).
Rewrite it to reflect the actual, current, single-part fix (louder docs
only) and add a note that auto-placing the first instance was tried
(TODO `5ff02d2`) and reverted (TODO `dafbaab`) for being too confusing
in practice — the same "we tried X, here's why it didn't work" pattern
already used elsewhere in this project's docs/LEARNINGS.md.

## `tests/verify/verify_define_widget_auto_place.py`

Rename to `verify_define_widget_no_auto_place.py` and flip every
assertion: a brand-new keyword registered via the live-added path now
places **zero** instances too, same as an edit-of-known-keyword, a bulk
rescan, or a failed registration — all four paths converge on the same
"registers only, never places" behavior, which is itself worth still
asserting explicitly (regression protection against reintroducing the
removed behavior by accident). Drop the `is_new` kwarg from every
`_handle_define_widget_file(...)` call and the
`_FakeWindow._auto_place_new_custom_widget = ...` binding (method no
longer exists). Keep `test_doc_callout_and_version`, updated for the
version bump and the callout's now-simpler wording.

## Verification

- Real, headless: registering a brand-new keyword via the live
  -added path (`_handle_define_widget_file`, no `is_new`) registers the
  widget kind but places zero instances; the other three paths
  (edit-of-known, bulk rescan, failed registration) are unaffected
  (already placed nothing before, still place nothing).
- `_auto_place_new_custom_widget` no longer exists on `DeskWindow`.
- Doc content: `TEMPUI_DOC_VERSION == 18`; `_CUSTOM_WIDGETS_DOC` no
  longer mentions auto-placing; `_BREAKING_CHANGES_DOC` has a new
  Version 18 entry.
- Full `tests/verify/` suite (`git stash` before/after) — expect the
  renamed test file itself to need updating (already handled above),
  and possibly other scripts with hardcoded doc-version assertions to
  need the same `>=`-style loosening already applied to several of them
  in the previous TODO batch.
