# Redo promoted-widget staleness detection and reload (TODO `4eb3d9e`)

## Summary

Cites `../FEEDBACK/FEEDBACK-DESK-promoted-widgets-no-stale-marker-2026-09-15-1744.md`.
A promoted custom widget (`source="desk"`, a real `desk_widgets/<name>/`
source directory recorded in `CustomWidgetDefinition.source_path`) has
no working way today to detect or reflect an edit to its own source
files: `tempui-custom-widgets.md`'s documented post-promotion workflow
(re-run `.desk_temp/build_widget.py desk_widgets/<name>`) is silently
rejected by `_register_custom_widget`'s `existing_source != source`
guard (`"desk"` vs. `"tempui"`), logged but never surfaced anywhere a
user or agent can see it, and the rebuilt content is never picked up.
The report's own follow-up found Desk-switch isn't a working escape
hatch either: it re-registers and correctly marks instances `[STALE]`,
but the content served afterward is still the old version.

This item redoes the mechanism entirely so a promoted widget's source
gets the same live experience a still-`.desk_temp`-sourced
`DefineWidget` custom widget already has: Desk itself watches the
widget's own source directory; a detected change marks every
already-placed instance `[STALE]` (the existing titlebar button,
`WidgetFrame.set_stale`); clicking it asks for confirmation
(`_confirm_stale_reload`'s existing dialog shape); confirming rebuilds
(`desk.custom_widgets.build_from_source`, the existing on-demand
compile path) and reloads. No dependency on `build_widget.py` being
re-run against an already-promoted widget at all -- editing
`desk_widgets/<name>/`'s real source files directly is enough on its
own.

Along the way, this also fixes a second, independently-confirmed bug
that would otherwise make "rebuild and reload" lie about actually
having updated anything: `ServerHandle.mount_html_widget` never
replaces an existing route for the same `widget_id`, only shadows it
behind a new one that Starlette's own route-resolution order never
reaches -- confirmed directly (see "Design decisions" below) to be the
real cause of the report's "`[STALE]` shown, but stale content served
anyway" observation, not the `outDir`/`.build` cache-mismatch the
report could only guess at without re-tracing it.

## Affected files

- `src/desk/server/runner.py` -- `ServerHandle.mount_html_widget` now
  removes any existing Starlette route for `widget_id` before mounting
  the new one, instead of appending a route that permanently shadows
  behind the first one ever registered for that id.
- `src/desk/custom_widgets.py` -- new `source_watch_exclusions(widget_dir)`
  helper: the directories under a widget's source tree that
  `build_from_source` itself writes/reads as build output
  (`SOURCE_BUILD_CACHE_DIRNAME` always, plus `tsconfig.json`'s own
  `outDir` when discoverable) -- a source-file watcher must ignore
  changes under these or the rebuild it triggers would immediately
  retrigger itself.
- `src/desk/shell/promoted_widget_source_watcher.py` (new) --
  `PromotedWidgetSourceWatcher(QObject)`, one instance per `DeskWindow`
  for the app's lifetime, same shape as the existing
  `SchemaFileWatcher`: `watch(keyword, widget_dir)` /
  `stop_watching(keyword)` / `stop_all()`, a `changed = pyqtSignal(str)`
  (the keyword) debounced per-keyword via `threading.Timer` (same
  0.3s convention as `TempUiManager`/`SchemaFileWatcher`), built on the
  shared `desk_services.file_watcher` service (`recursive=True`,
  filtering out `source_watch_exclusions` in the callback).
- `src/desk/shell/window.py`:
  - Constructs/wires `_promoted_widget_source_watcher` in `__init__`,
    same pattern as `_schema_file_watcher`.
  - `_register_custom_widget` starts (or restarts) watching a promoted
    widget's source directory at its existing tail, right after
    `_refresh_stale_indicators_for` -- the one choke point every
    registration path for a `source="desk"`, source-backed widget
    already funnels through (startup, Desk switch, promotion,
    `_resolve_promotion_source`, and this item's own confirm-triggered
    rebuild).
  - New `_on_promoted_widget_source_changed(keyword)`: marks the
    keyword dirty and force-`set_stale(True)`s every already-placed
    instance, independent of the hash-diff `_refresh_stale_indicators_for`
    uses (there's no fresh hash yet -- nothing has been rebuilt).
  - `_on_widget_stale_clicked` branches to a new
    `_on_promoted_widget_stale_clicked` when the clicked instance's
    keyword is in the dirty set, instead of the existing hash-diff
    early-return (which would see `current_hash == frame.placed_content_hash`
    -- nothing rebuilt yet -- and wrongly conclude there's nothing to do).
  - New `_on_promoted_widget_stale_clicked(frame, keyword)`: confirms
    via a new `_confirm_promoted_widget_rebuild`, then rebuilds via the
    existing `_register_custom_widget(definition, source="desk")` (which
    calls `build_from_source`, recomputes the hash, remounts, and
    refreshes every sibling instance's own stale flag against the new
    hash), then reloads and clears staleness for the specific clicked
    instance -- same "per-instance choice" philosophy
    `_on_widget_stale_clicked` already documents for the existing path.
  - New `_confirm_promoted_widget_rebuild`/
    `_notify_promoted_widget_rebuild_failed` dialogs, split out the same
    way as `_confirm_stale_reload`/`_confirm_widget_error_dismissed` so
    headless verification can monkeypatch them.
  - `_place_widget`'s existing "a fresh placement is always current"
    block also checks the dirty set, so a widget placed *while* its
    source is known-dirty starts `[STALE]` too, instead of silently
    looking current.
  - Desk-switch teardown (`switch_desk`, alongside the existing
    `_custom_widget_sources.clear()` block) also calls
    `_promoted_widget_source_watcher.stop_all()` and clears the dirty
    set, so watches and stale flags don't leak across Desks.
- `src/desk/temp_ui.py` -- `TEMPUI_DOC_VERSION` 43 -> 44;
  "Authoring from real source" in `_CUSTOM_WIDGETS_DOC`'s "Once
  promoted ..." paragraph corrected (no more re-running
  `build_widget.py` against `desk_widgets/<name>/` -- Desk now watches
  it directly); new version-44 entries in `_NEW_FEATURES_DOC` (the new
  watch/`[STALE]`/confirm/rebuild behavior) and `_BREAKING_CHANGES_DOC`
  (the old re-run instruction no longer applies and never actually
  worked -- flagged there so an agent that remembers the old docs
  knows why).
- `tests/verify/verify_promoted_widget_source_staleness.py` (new) and
  `tests/verify/verify_server_runner.py` (or wherever `ServerHandle`
  already has coverage, extended) -- see Verification below.

## Design decisions

- **Watch raw source files, not a rebuilt-output file.** The
  `.desk_temp` `DefineWidget` case watches the *build's own output*
  (a `DefineWidget` tempui file, already fully rebuilt by hand before
  it's dropped) -- there's no equivalent "rebuild, then drop a file"
  step for a promoted widget once promoted (that's exactly the
  documented-but-broken workflow this item removes the need for), so
  the only thing left to watch is the real `.ts`/`widget.html`/
  `widget.json`/`tsconfig.json` source tree itself, via
  `desk_services.file_watcher`'s existing `recursive=True` support.
- **Detecting a change never rebuilds; only a confirmed click does.**
  Matches the literal ask exactly: watch -> mark `[STALE]` -> click ->
  confirm -> *then* rebuild+reload. This is also cheaper (no `tsc`
  invocation on every autosave) and keeps the interaction identical in
  shape to the existing hash-diff path from the user's perspective --
  same button, same confirm-dialog shape, just a different trigger for
  *why* it's stale. A dedicated `_promoted_widget_source_dirty: set[str]`
  tracks "known stale, not yet rebuilt" state per keyword, since the
  existing hash-diff mechanism (`current_hash != frame.placed_content_hash`)
  can't represent "stale, but no new hash exists yet to diff against."
- **The confirmed rebuild reuses `_register_custom_widget` wholesale,
  not a bespoke rebuild call.** `_register_custom_widget(definition,
  source="desk")` already does exactly what's needed -- calls
  `build_from_source`, recomputes `content_hash`, remounts on the live
  server, and calls `_refresh_stale_indicators_for` for every
  already-placed sibling instance of the same keyword (so a second
  placed instance the user hasn't clicked yet correctly stays `[STALE]`,
  reflecting the real hash-diff now that one exists) -- reusing it
  keeps this item's own new code to "when to call it and how to react
  to the click," not a second implementation of the build/mount/hash
  bookkeeping that already exists.
- **Error surfacing on a failed rebuild is deliberately generic.**
  `build_from_source` already logs a specific message
  (`SourceBuildError`'s text) but only via `logger.error` -- invisible
  to a user or agent, the same "silent failure" pattern the report
  calls out for the *other* bug this item fixes. A full plumb-through
  of the exact compile error into the UI would mean changing
  `build_from_source`'s established `Path | None`-and-log-only
  contract for every existing caller, or adding a parallel verbose
  variant purely for this one call site. Scoped down deliberately: the
  new failure dialog says a rebuild failed and to check Desk's own log
  output, which is still a real, visible signal where today there is
  none at all -- richer inline error text is a reasonable, deliberately
  -deferred follow-up, not required by this item's own literal ask.
- **The `mount_html_widget` fix is in scope, not a tangent.** Confirmed
  directly (a standalone repro script against a real `ServerHandle`,
  not just re-reading the report's own unverified hypothesis): mounting
  a *different* directory for an already-mounted `widget_id` silently
  keeps serving the *first*-ever-mounted directory forever, because
  Starlette's `Router.mount` only appends routes and resolves them in
  registration order. The `.desk_temp` `DefineWidget` path never
  surfaces this (`materialize()` always reuses the exact same fixed
  cache directory, so "remounting" the same path with fresher bytes on
  disk works by accident), and an ordinary in-place promoted-widget
  rebuild (`build_from_source` also writes to a fixed, stable
  `desk_widgets/<name>/.build/` path across rebuilds) mostly works by
  the same accident too -- but the very first registration after
  promotion (moving from whatever pre-promotion tempui-materialized
  path a widget's `[TEMPUI]` button used, or the pre-relocation
  `.desk_temp/widgets/<name>/` source path, to the post-promotion
  `desk_widgets/<name>/.build/` path) genuinely changes the mounted
  directory -- exactly matching the report's own "`[STALE]` shown, but
  stale content served anyway" symptom, without needing the
  `outDir`/`.build` mismatch the report could only guess at. Fixed by
  having `mount_html_widget` remove any existing route named
  `f"widget-{widget_id}"` before mounting the new one -- Starlette
  routes carry a `name`, already set to exactly this on every mount, so
  no new bookkeeping is needed to find the one to replace. Also fixes a
  latent cross-Desk leak `switch_desk`'s own comment already flags as
  merely "harmless" today (an orphaned mount from a Desk just switched
  away from is never actually unschedulable via this app -- with the
  fix, the *next* Desk that registers the same widget-id keyword
  correctly takes over the route instead of being silently shadowed by
  the old Desk's stale content).
- **Single choke point for starting the watch.** Every path that
  registers a `source="desk"`, source-backed widget already funnels
  through `_register_custom_widget` (startup, Desk switch, promotion,
  `_resolve_promotion_source`'s candidate-adoption path, and this
  item's own confirm-triggered rebuild) -- adding the
  watch-start/restart call at its existing tail means no call site has
  to remember to wire this up itself, and a `source_path` relocation
  (promotion, or a future re-relocation) automatically restarts the
  watch pointed at the new location the next time that widget is
  registered, with no separate invalidation logic.
- **A widget with no `source_path` (hand-authored, inline-only,
  `html_b64`-baked) is never watched at all.** There's no source tree
  to watch -- `_register_custom_widget` only starts a watch when
  `definition.source_path is not None`, matching TODO `13f4ad5`'s own
  existing "only a source-backed definition skips baking `html_b64`"
  distinction exactly.
- **Debounced per keyword, not globally, mirroring `TempUiManager`/
  `SchemaFileWatcher`.** A single logical save can still fire more than
  one raw watchdog event (this codebase's own established gotcha,
  documented in both existing watchers) -- same 0.3s
  `threading.Timer`-per-key shape, emitting the Qt signal (safe across
  threads via Qt's own queued-connection marshaling, the same pattern
  every watcher in this codebase already relies on) only once the
  burst settles.
- **Doc/changelog updates are required, not optional, here.**
  `development-process.md`'s "Keep the tempui changelog docs current"
  applies directly: this changes what an in-Desk agent needs to know
  about promoted-widget editing (the old re-run-`build_widget.py`
  instruction is now actively wrong to follow, and a new automatic
  behavior exists that nothing previously documented).

## Verification

New coverage:

- `tests/verify/verify_promoted_widget_source_staleness.py`:
  - `source_watch_exclusions` returns `.build` always, plus a
    tsconfig-declared `outDir` when present, and degrades to just
    `.build` for a missing/malformed `tsconfig.json` rather than
    raising.
  - `PromotedWidgetSourceWatcher.watch(keyword, dir)` + a real file
    write under that directory fires `changed` with that keyword
    (after the debounce interval); a write under an excluded
    subdirectory does not; `stop_watching`/`stop_all` actually stop
    future events from firing.
  - `_register_custom_widget` starts a watch for a `source="desk"`,
    source-backed definition and does not for a `source="tempui"` one
    or a `source="desk"` one with no `source_path`.
  - `_on_promoted_widget_source_changed` marks every already-placed
    instance of that keyword `[STALE]` and adds the keyword to the
    dirty set.
  - `_on_widget_stale_clicked` routes a dirty keyword to
    `_on_promoted_widget_stale_clicked` instead of the existing
    hash-diff early return.
  - `_on_promoted_widget_stale_clicked`: declines (monkeypatched
    confirm returns `False`) leaves the instance stale and dirty;
    confirms + a successful rebuild (monkeypatched/faked
    `build_from_source`) clears the dirty flag, reloads the clicked
    instance, and clears its own `[STALE]`, while a second placed
    instance of the same keyword that hasn't been clicked yet stays
    `[STALE]` (per-instance reload, matching the existing philosophy);
    confirms + a failing rebuild shows the failure dialog and leaves
    the instance stale/dirty so it can be retried.
  - `_place_widget` marks a freshly-placed instance `[STALE]`
    immediately when its keyword is already known-dirty.
  - Desk-switch clears `_promoted_widget_source_dirty` and stops every
    active promoted-widget watch.
- `ServerHandle.mount_html_widget` coverage (new or extended, wherever
  `ServerHandle` already has any): mounting a second, *different*
  directory for the same `widget_id` actually serves the new
  directory's content on the next request, not the first-mounted one
  -- a real `start_server`/HTTP-fetch round trip (this is the exact
  bug confirmed via a standalone repro during design; the regression
  test locks it down for real, not just at the Python-object level).

Run the full `tests/verify/` suite and compare the failing set against
the pre-existing baseline (`git stash`, rerun, diff) to confirm nothing
else regressed. `tsc`-dependent behavior (`build_from_source` itself)
is exercised the same way the rest of this codebase already does for
it -- with a minimal, real, throwaway TypeScript source tree under a
temp directory, matching whatever existing `build_from_source` test
coverage already does, not a hand-decoded HTTP round trip against a
real Chromium widget. Real mouse-hover/click behavior and an actual
`tsc`-driven rebuild triggered from a live, interactively-driven Desk
window are not exercised by the headless suite; note in this plan's
"Verification results" whether a manual check was possible this
session or was skipped.
