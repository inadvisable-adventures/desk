# Fix stale storage-persistence claim in the tempui doc set (TODO `e42469e`) (COMPLETED)

## Summary

TODO `a5f66cc` gave each `kind: "html"` widget instance (`ChromiumWidget`)
its own persistent `QWebEngineProfile`, rooted under
`.desk_temp/chromium-profiles/<instance_id>/`, deleted only when that
instance is permanently removed (`DeskWindow.close_widget`) -- not on
a Desk-switch, and not across an ordinary Desk restart. That work only
updated `design-docs/architecture.md` (Desk's own internal doc); it
never touched `src/desk/temp_ui.py`, whose templates are what actually
get materialized into `.desk_temp/*.md` and shown to Claude/agent
instances working *inside* Desk-managed projects. As a direct result,
`_CUSTOM_WIDGETS_DOC` (`tempui-custom-widgets.md`) now states something
false: that no browser storage (cookies/`localStorage`/`IndexedDB`)
persists a `kind: "html"` widget's page across a reload or a Desk
restart, and that `desk.self.getLocalStorage`/`setLocalStorage` is
"the only way" to persist state.

## Affected files

- `src/desk/temp_ui.py` -- the stale paragraph in `_CUSTOM_WIDGETS_DOC`,
  the `TEMPUI_DOC_VERSION` bump comment block, and a new entry in
  `_NEW_FEATURES_DOC`.
- `tests/verify/` -- no existing script asserts on the exact stale
  wording (confirmed via grep), so no existing test needs fixing; new
  coverage added here.

## Design decisions

- **Scope: fix the one now-false claim, nothing more.** Investigated
  and deliberately did *not* also add new documentation about the
  auth-token cookie mechanism itself (the other half of `a5f66cc`):
  the only widget-authoring path currently available to an agent
  working inside another project is `DefineWidget`, which is *always*
  a single, fully-inlined HTML document (materialized with no separate
  JS/CSS files at all) -- it structurally never makes the kind of
  relative-path sub-resource request the auth-cookie fix was for, so
  nothing about that fix is actionable or relevant from inside this
  doc set today. That only changes once `PARKINGLOT.md`'s already
  -parked "Reconsider `DefineWidget`'s single-inlined-file requirement"
  follow-up is implemented -- documenting the cookie mechanism belongs
  with *that* future work, not bolted on here as a tangent.
- **Correct the claim without overselling the new mechanism.** The new
  wording must not read as "use browser storage instead of
  getLocalStorage" -- `getLocalStorage`/`setLocalStorage` remains the
  right, *recommended* mechanism: its data lives in the portable
  `.desk` file itself (`WidgetState.state`, via
  `_get_widget_local_storage`/`_capture_desk_state`), so it travels
  with the project if the `.desk` file is copied/shared, and it's
  explicitly designed for this. The new per-instance profile storage
  is real and does persist, but it's `.desk_temp/`-scoped (tied to
  this specific checkout, not portable), and is wiped the moment the
  widget instance is permanently removed -- neither of which apply to
  `getLocalStorage`/`setLocalStorage`. The fixed wording states both
  facts plainly rather than picking one and hiding the other.
- **Version bump, not a silent text edit.** Per this doc set's own
  established convention (`TEMPUI_DOC_VERSION`'s bump-comment history,
  `_NEW_FEATURES_DOC`'s per-version entries), any content change here
  gets a version bump (26 -> 27) and a matching changelog entry, so
  the existing "your project's docs are stale, here's what changed"
  notification path (TODO `7c7b676`) actually surfaces this to
  projects already using an older doc version, instead of the fix
  silently landing invisibly next time their docs happen to refresh.
  Filed under `_NEW_FEATURES_DOC` (not `_BREAKING_CHANGES_DOC`): this
  doesn't break anything an agent was doing -- it corrects a doc
  inaccuracy in the agent's favor (more capability turns out to be
  available than previously stated), which is exactly the shape
  `_NEW_FEATURES_DOC`'s own past entries use for "here's a new-to-you
  fact/capability," not a behavior change requiring migration.

## Step-by-step implementation

1. In `_CUSTOM_WIDGETS_DOC`, replace the current paragraph (the
   "notably, **it's the only way to persist...**" sentence and its
   parenthetical) with corrected wording: real per-instance browser
   storage now does persist a `kind: "html"` widget's page across a
   reload and a Desk restart (per-instance `QWebEngineProfile`,
   TODO `a5f66cc`) -- but `desk.self.getLocalStorage`/`setLocalStorage`
   remains the recommended mechanism, since its data lives in the
   portable `.desk` file itself and survives a project being
   copied/shared, unlike the profile storage, which is tied to this
   specific `.desk_temp/` checkout and is deleted outright once the
   widget instance is permanently removed.
2. Bump `TEMPUI_DOC_VERSION` 26 -> 27, with a new comment block above
   the constant following the established format (`# TODO e42469e:
   bumped 26 -> 27 for ...`).
3. Add a `## Version 27` entry to `_NEW_FEATURES_DOC`, matching the
   tone/structure of the existing entries (old behavior stated, new
   behavior stated, what an author should actually do given both).
4. New verify coverage (see below); run the full `tests/verify/` suite.

## Key tradeoffs

- Not documenting the auth-cookie mechanism itself here is a
  deliberate scope cut, not an oversight -- see Design decisions
  above. Flagged in the TODO.md entry so it isn't mistaken for
  something already covered.

## Verification

New script `tests/verify/verify_tempui_storage_claim_fix.py`, real (no
mocking):
- `TEMPUI_DOC_VERSION` is bumped to at least 27.
- The stale claim's exact old phrasing ("no other storage available")
  no longer appears in `_CUSTOM_WIDGETS_DOC`.
- `_CUSTOM_WIDGETS_DOC` still recommends
  `getLocalStorage`/`setLocalStorage` as the primary/recommended
  mechanism (a plain removal without a replacement claim would be a
  regression -- confirmed the doc still guides authors there).
- `_CUSTOM_WIDGETS_DOC`'s corrected text mentions that the newer
  per-instance storage is tied to `.desk_temp`/gets removed with the
  widget instance (so an agent reading only the new paragraph doesn't
  come away thinking it's a portable alternative).
- `_NEW_FEATURES_DOC` has a `## Version 27` entry mentioning this
  change.
- `ensure_docs_current`'s existing stale-doc-detection/rewrite path
  still works correctly against the new version number (reuses the
  existing pattern from `verify_tempui_doc_versioning.py`/
  `verify_tempui_doc_upgrade_notification.py`, not duplicated wholesale
  -- just confirms the bump itself didn't break that mechanism).
- Full `tests/verify/` regression suite.
