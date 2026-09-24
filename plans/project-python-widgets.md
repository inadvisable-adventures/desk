# Project-authored `kind: "python"` widgets under `desk_widgets/` (TODO 99eb1bc) -- COMPLETED

## Summary

Allow a project to author a real, first-class `kind: "python"` widget
package directly at `desk_widgets/<name>/` (project root) -- the exact
same `widget.json`/`entry` shape Desk's own built-in `widgets/<id>/`
directories use -- discovered and merged into the live widget catalog
automatically, with no tempui `DefineWidget`/promote round-trip needed.
This is the escalation of a pre-existing, already-parked idea
(PARKINGLOT.md's "Default to authoring an explicitly-requested widget
as a real project widget", sourced from
`../FEEDBACK/FEEDBACK-DESK-promoted-widget-source-of-truth-2026-08-04-1321.md`
finding 3), which proposed a second `discover_widgets(project_dir /
"desk_widgets")` call -- but that item only ever discussed `kind:
"html"`. This TODO is scoped to `kind: "python"` only, per direct user
request; `kind: "html"` stays with the existing parked item, since
serving it needs Local Web Server route wiring this doesn't touch.

`kind: "python"` widgets run in-process with full, unsandboxed access
to Desk's own Python (see `design-docs/architecture.md`'s Security
Considerations) -- previously an accepted tradeoff only for Desk's own
reviewed, bundled `widgets/`. This change extends that same trust
level to *project*-authored code (the same extension Installed Jobs
and `desk_hmsvc/` already made), which is exactly what the paired
PARKINGLOT item added by this same change asks to revisit later: a
narrower, Bridge-API-style capability surface instead of full direct
access.

## Affected files

- `src/desk/widgets.py` -- new `discover_project_widgets(widgets_dir,
  *, kinds=("python",))`, lenient/kind-agnostic-on-purpose scanning
  that coexists with `desk_widgets/`'s older tenant (a promoted
  tempui widget's source, whose `widget.json` has no `"kind"` key).
- `src/desk/shell/window.py` -- new `DeskWindow._load_project_widgets`
  merges discovered project widgets into `self._widgets`, tracks their
  ids (`self._project_widget_ids`) for per-Desk cleanup on
  `switch_desk`, and owns a second `WidgetWatcher`
  (`self._project_widget_watcher`) pointed at the current Desk's own
  `desk_widgets/`. Hooked into `__init__`, `switch_desk`, and
  `_on_widget_changed_refresh_catalog` (the existing hot-reload
  catalog-refresh handler).
- `design-docs/architecture.md` -- new "Project widgets" bullet in
  "Widget Model", new bullet in "Security Considerations".
- `src/desk/temp_ui.py` -- new tag
  `"project-authored python widgets in desk_widgets #473197"` (added
  to `CURRENT_TAGS`, `_NEW_FEATURES`), new "## Project widgets" section
  in `DOC_TEMPLATE` (the generated `desk-temporary-ui.md`). Required by
  `development-process.md`'s "Keep the tempui changelog docs current"
  -- this is a new capability an in-project agent needs to know about.
- `tests/verify/verify_project_python_widgets.py` -- new verify script.
- `TODO.md`, `PARKINGLOT.md` -- this item (prioritized to the top per
  direct user request) and the paired isolation follow-up.

## Design decisions

- **Distinguishing the two `desk_widgets/` conventions.** A
  subdirectory's `widget.json` is treated as "ours" only if it has a
  `"kind"` key at all; one with `{"keyword", "label", "width",
  "height"}` and no `"kind"` (a promoted `DefineWidget` widget's
  source, TODO 59c5a70) is silently skipped as belonging to that other,
  pre-existing convention. This is the only signal available, and it's
  reliable -- the two shapes are structurally disjoint on that one key.
- **Leniency, unlike `discover_widgets`.** Desk's own `widgets/` is
  reviewed, bundled content -- `_parse_manifest`'s `ValueError` on a bad
  `kind` is allowed to propagate and would abort Desk startup/hot
  -reload. A project's own `desk_widgets/` is arbitrary, unreviewed
  content off in someone else's project; `discover_project_widgets`
  catches malformed JSON and invalid `kind` values per-directory,
  logging a warning and skipping just that one entry, so a typo in one
  project never breaks widget discovery (built-in or otherwise) for
  every open Desk.
- **`kind: "html"` explicitly rejected (for now), not silently
  ignored.** `discover_project_widgets`'s `kinds` parameter defaults to
  `("python",)`; an `html`-kind entry is skipped with an explanatory
  warning naming why (unserved from an arbitrary project directory
  today) rather than either silently doing nothing (confusing) or
  being merged into a catalog that can't actually render it (broken).
  Extending this later is a one-line change at the single call site.
- **Collision policy: built-ins and tempui customs win.** A project
  widget id that collides with an existing catalog entry is refused
  (logged, not registered) -- mirrors
  `DeskWindow._register_custom_widget`'s existing "refuse to shadow an
  existing id" posture for the same reason: predictable, and a project
  can't accidentally (or maliciously) shadow a shipped widget.
- **Per-Desk lifecycle, not global.** `desk_widgets/` is project
  -relative, so a project widget's `WidgetInfo` is dropped from
  `self._widgets` on `switch_desk` (mirroring
  `self._custom_widget_definitions`' own per-Desk cleanup) and
  rediscovered fresh for whichever Desk is now current. The second
  `WidgetWatcher` is stopped and recreated only when the target
  directory's `Path` actually changes (comparing `WidgetWatcher
  .widgets_dir`), not on every refresh.
- **Must run before `_load_desk_widgets`.** A saved widget instance in
  the `.desk` file resolves its `widget_id` against `self._widgets`
  (`_load_desk_widgets`); `_load_project_widgets` runs immediately
  before it (in both `__init__` and `switch_desk`) so a saved instance
  of a project widget still restores. `_refresh_builtin_schemas()` is
  re-run in between, so a project widget's own `state_schema` (if any)
  is registered before any instance is placed -- otherwise it would
  only take effect after the first later hot-reload.
- **Known limitation, accepted for v1:** a `desk_widgets/` directory
  that doesn't exist yet when a Desk is opened/switched to only starts
  being watched at that moment (`WidgetWatcher.start()`'s own
  `is_dir()` guard) -- if it's created for the very first time while
  that same Desk stays open with no switch in between, it isn't picked
  up live. Every subsequent edit inside an already-discovered
  `desk_widgets/` does hot-reload live, and any full reopen/switch
  always picks up a first-time directory. Not worth extra polling
  infrastructure for this one first-creation edge case.

## Verification

`tests/verify/verify_project_python_widgets.py`:
- `discover_project_widgets`: a valid `kind: "python"` entry is
  discovered with the right `entry`/`kind`; a tempui-style
  no-`"kind"` `widget.json` is silently skipped; a `kind: "html"`
  entry is skipped (not merged); an invalid `kind` value and malformed
  JSON are both skipped without raising; a missing directory returns
  `{}`.
- `DeskWindow._load_project_widgets` (via a lightweight fake window,
  matching `verify_desk_widgets_build_gitignore.py`'s `_FakeWindow`
  pattern -- binding the real unbound method onto a minimal stand-in
  rather than constructing a full `DeskWindow`): a fresh project widget
  merges into `self._widgets` and is tracked in
  `self._project_widget_ids`; an id colliding with an existing catalog
  entry is refused and the original entry is left untouched; a second
  call against the same directory reuses the same `WidgetWatcher`
  instance (no needless stop/restart); a call against a *different*
  directory (simulating a Desk switch) stops the old watcher and
  starts a new one pointed at the new path.
- End-to-end: a real `PythonWidgetHost` (`desk.shell.python_widget`)
  successfully builds a `QWidget` from a `widget.py` living outside
  Desk's own repo tree, confirming the existing in-process loader
  needed no changes to support an arbitrary project path.
- `desk.temp_ui`: the new tag is present in `CURRENT_TAGS` and
  `_NEW_FEATURES`; `write_tempui_docs` renders a fresh `.desk_temp/`
  whose `desk-temporary-ui.md` contains the new "Project widgets"
  section and whose `tempui-new-features.md` contains the new tag's
  entry.

Full `tests/verify/` regression suite run after implementing: 165/165
non-`disabled_` scripts pass (164 pre-existing + this 1 new file).
Two pre-existing scripts (`verify_new_desk_flow.py`,
`verify_tempui_custom_widgets.py`) initially broke on the first run --
both use a lightweight fake-window harness bound to real `DeskWindow`
unbound methods (`switch_desk`/`_on_widget_changed_refresh_catalog`),
and neither fake had the new `_project_widget_ids`/
`_project_widget_watcher`/`_load_project_widgets` state those methods
now touch. Fixed by updating both fakes (added the missing attributes/
stub, plus an ordering assertion in `verify_new_desk_flow.py` covering
where `_load_project_widgets` now sits in `switch_desk`'s call order) --
not a pre-existing/unrelated failure, a real regression from this
change, now resolved. Second full run: 165/165 pass, 0 failures.

Browser-launch verification step: skipped (no UI-visible behavior this
plan introduces needs a running browser to check; the "Add widget"
menu picking up a project widget is exercised indirectly by
`_load_project_widgets` populating `self._widgets`/`self.view
.set_widget_catalog`, already covered above).
