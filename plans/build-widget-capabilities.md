# Plan: TODO 31db3f6 (COMPLETED) — `build_widget.py` reads `capabilities` from `widget.json`

Source: `../FEEDBACK/FEEDBACK-DESK-build-widget-capabilities-2026-07-16-1010.md`.
`.desk_temp/build_widget.py` (generated from `_BUILD_WIDGET_SCRIPT` in
`src/desk/temp_ui.py`) never reads a `capabilities` key out of a
`DefineWidget`-authored widget's `widget.json`, silently dropping it --
forcing a hand-edit of the *generated* tempui file after every build
that's easy to forget (confirmed twice in the reporting project: once
for `LifeforceHeart`/`LifeforceControl` needing `events`, once for
`TerrainTypesEditor` needing `fs`/`editor`, the second time silently
producing a widget with an empty table and no error surfaced anywhere
beyond the widget's own devtools console).

## Design

Read the feedback's primary suggested fix directly, not the fallback
(mismatch-warning) option — there's no reason found to prefer the
fallback here; the field already exists in practice (three widgets in
the reporting project already added `"capabilities"` to their
`widget.json` unofficially, by direct analogy with a real `kind:
"python"`/`"html"` widget's own manifest) and reading it directly
closes the single-source-of-truth gap completely, not just partially.

- **`_BUILD_WIDGET_SCRIPT`** (`src/desk/temp_ui.py`): `build_widget()`
  reads `manifest.get("capabilities", [])` (optional, defaults to `[]`
  so a `widget.json` with no such key keeps working exactly as today —
  no `REQUIRED_MANIFEST_KEYS` change) and emits one `Capability\t<name>`
  line per entry, right after the `Size` line — the exact position
  `Capability<TAB>name`'s own DSL doc example already shows, and the
  same shape `parse_define_widget` already parses (confirmed directly:
  `Capability\t` lines are scanned independently of position, but
  matching the documented example ordering is still the right call for
  consistency). The script's own module docstring's `widget.json`
  field list gets the same update.
- **`tempui-custom-widgets.md`'s "Authoring from real source" section**
  (`_CUSTOM_WIDGETS_DOC`): its own `widget.json` field-list line
  (`{"keyword", "label", "width", "height"}`) gets the same addition,
  noting `capabilities` is optional and maps to `Capability` lines the
  same way a hand-written `DefineWidget` file's own lines already do.
- Bump `TEMPUI_DOC_VERSION` and add a `_NEW_FEATURES_DOC` entry — this
  changes the generated build script's own behavior, a new capability
  from the perspective of an agent authoring a `DefineWidget` widget in
  any project using tempui, per `development-process.md`'s standing
  tempui-changelog rule.

## Verification

Extend the existing `tests/verify/verify_build_widget.py` (same
real-`tsc`, real-generated-script pattern already established there --
loads the actual `_BUILD_WIDGET_SCRIPT` content via `write_tempui_docs`,
not a copy/mock):

- A `widget.json` declaring `"capabilities": ["fs", "editor"]` produces
  a generated tempui file that `parse_define_widget` recovers with
  exactly `capabilities == ["fs", "editor"]` (real round-trip through
  the real parser, mirroring the existing keyword/label/size checks).
- A `widget.json` with no `capabilities` key at all still produces
  `capabilities == []` (backward compatible, no behavior change for
  every widget that doesn't use this).
- Full `tests/verify/` regression suite.
