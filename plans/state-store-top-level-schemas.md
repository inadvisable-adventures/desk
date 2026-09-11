# State store top-level schema files (TODO `9aef267`) (COMPLETED)

## Summary

The second of three items split out of the original TODO `6e1c2fe`
(see `TODO.md`'s `af7898b` entry for that split's own reasoning).
Lets a `desk.state.*` schema be declared "top-level" -- in its own
standalone file, independent of any widget's manifest -- at two
watched locations: ephemeral `.desk_temp/schemas/` and a real,
git-tracked `./desk-schemas/` that Desk never creates eagerly, only
watches for and picks up immediately once it exists. A top-level
file's schema is permanently enforced from registration onward, the
same as a built-in widget's (never dormant). Depends on TODO
`af7898b` (COMPLETED) for `desk.schema_types`/`desk.schema_registry`
and `DeskWindow._schema_registry` -- this item is purely about a new
*source* of permanent registrations into that same registry, no
changes to the registry's own conflict-resolution logic.

Full design context, already had -- see
`investigations/app_structure_dsl_design.md`'s "Bookkeeping and call
sites" section.

## Affected files

- `src/desk/shell/schema_file_watcher.py` (new) -- `SchemaFileWatcher`,
  the directory-watching class for both locations.
- `src/desk/shell/temp_ui_manager.py` -- `TempUiManager.provision`
  creates `.desk_temp/schemas/` alongside its other subdirectories,
  returns enough for the caller to find it.
- `src/desk/shell/window.py` -- `DeskWindow` owns a `SchemaFileWatcher`,
  wires its `changed` signal to a new schema-file (de)registration
  handler, and re-provisions both on every desk open/switch.
- `src/desk/temp_ui.py` -- doc section on top-level schema files,
  `TEMPUI_DOC_VERSION` bump.
- `tests/verify/` -- new coverage.

## Design decisions

- **File format**: a top-level schema file is a plain JSON object,
  `{"<key>": "<type expression>", ...}` -- exactly `widget.json`'s own
  `state_schema` field's shape, reusing `desk.schema_types
  .parse_type_expression` directly with no new parsing code. Only
  `*.json` files in a watched directory are considered (anything
  else -- a stray `.DS_Store`, a README -- is ignored); a filename
  carries no meaning beyond that extension (unlike tempui's own
  UUID-named-file convention -- these are meant to be human/agent
  -authored with a meaningful name, e.g. `document-state.json`).
- **`.desk_temp/schemas/` is created eagerly** (a plain `mkdir`, no
  content seeded) by `TempUiManager.provision` -- but only when
  `.desk_temp` itself is actually being provisioned (the user can
  decline that entirely; `provision` already returns `None` in that
  case, and this item adds nothing when it does). "Ephemeral" here
  means "not git-tracked" (`.desk_temp` is gitignored as a whole), not
  "wiped/regenerated" -- unlike `shared-components/`/`app_dsl/`, a
  schema file's content is never synced from anywhere and is never
  touched by Desk after the directory itself is created.
- **`./desk-schemas/` is never created by Desk** -- watched for via
  short-interval polling (`QTimer`, 2s) checking `.is_dir()`, not a
  live filesystem watch on the whole project root. A real recursive
  -into-project-root watch was considered and rejected: it would add a
  permanent watch over an arbitrary, potentially large user directory
  just to catch one specific subdirectory's birth, for a feature whose
  own design goal ("immediately picked up") is satisfied just as well
  by a short, bounded poll -- nothing in the original discussion
  actually required sub-second detection, just "no Desk restart
  needed." Once found, the poll stops and a real, live, push-based
  watch (`desk_services.file_watcher`) takes over for its contents,
  exactly like the ephemeral directory.
- **A top-level file's schema is permanently enforced** -- registered
  via the existing `SchemaRegistry.register_permanent`, with the
  file's own resolved path (as a string) as its `source_widget_id`.
  No new registry logic: `register_permanent`'s existing conflict
  -resolution, idempotent-same-source-update, and
  dormant-entry-replacement behavior all already generalize correctly
  to "source" meaning "a file path" instead of "a widget id" -- the
  registry never actually cared which.
- **Every relevant filesystem event (add/edit/remove) re-derives that
  file's own registrations from scratch**: `SchemaRegistry
  .clear_source(str(path))` first, then -- if the file still exists --
  parse it fresh and `register_permanent` each declared key again.
  This is the exact same "clear then re-derive fresh" shape
  `DeskWindow._refresh_builtin_schemas` (TODO `af7898b`) already uses
  for built-in widgets, applied to a different source kind. A missing
  file (deleted, or gone after a rename) just clears -- nothing to
  re-register.
- **A malformed file (invalid JSON, a non-object top level, a
  non-string type-expression value, or a key whose type expression
  itself fails to parse) is a loading error, not a crash** -- logged
  and surfaced via the same clickable-notification pattern
  `_check_schema_conflict`/`_refresh_builtin_schemas` already use
  (`WorkspaceView.notify_temp_ui`, keyed by the file's own `Path` so a
  fix-then-re-error cycle replaces the banner in place rather than
  stacking duplicates), reusing the existing `_show_schema_conflict_popup`
  click-handler as-is (it only ever needed a title and a message, never
  anything actually widget-specific). There is no `desk_widget_loading_errors`
  -equivalent persisted anywhere for a bare file (no manifest to attach
  it to) -- this mirrors the `af7898b` planning decision to keep
  loading-error surfacing live/in-memory-only rather than writing back
  into user-owned files.
- **Desk-switch isolation**: since `SchemaRegistry` is one shared
  instance for the whole server run (not per-Desk), `DeskWindow` tracks
  which registry sources currently came from a schema *file*
  (`self._known_schema_file_sources: set[str]`, updated alongside every
  `clear_source`/`register_permanent` call the new handler makes) and
  clears all of them before re-provisioning for a newly-opened/switched
  Desk's own two directories -- otherwise a previous project's
  top-level schemas would silently keep claiming keys in whatever
  project is opened next. Built-in widget schemas are a completely
  separate source-id namespace already handled by `_refresh_builtin_schemas`'s
  own `permanent_source_ids()`-based clearing -- this item's tracking
  set is additive, not a replacement for that.

## Step-by-step implementation

1. `schema_file_watcher.py`: `SCHEMA_FILES_DIRNAME = "schemas"`,
   `TOP_LEVEL_SCHEMAS_DIRNAME = "desk-schemas"`, `POLL_INTERVAL_MS =
   2000`, `DEBOUNCE_SECONDS = 0.3` (same constant/reasoning as
   `TempUiManager`'s own tempui-file debounce -- a single logical save
   can fire more than one raw watchdog event). `SchemaFileWatcher(QObject)`:
   - `changed = pyqtSignal(Path)` -- emitted for a `.json` file
     directly inside either watched directory, added/edited/removed
     alike (the receiver decides which via `path.is_file()`).
   - `provision(ephemeral_dir: Path | None, project_root: Path)`:
     stops any previous watches/poll timer; if `ephemeral_dir` is
     given, watches it (`recursive=False`) and does an initial scan
     (emits `changed` for every already-present `.json` file, so
     files already there when Desk opens get registered without
     needing a filesystem event to arrive first); resolves
     `top_level_dir = project_root / TOP_LEVEL_SCHEMAS_DIRNAME` --
     watches it the same way if it already exists, otherwise starts
     the `QTimer` poll that switches to watching it (plus the same
     initial scan) the moment `.is_dir()` becomes true.
   - Debounced dispatch per resolved path (mirrors `TempUiManager
     ._DirectoryHandler`'s own `threading.Timer`-per-filename shape),
     filtering to `.json`-suffixed paths whose parent is one of the
     two currently-watched directories.
2. `temp_ui_manager.py`: `TempUiManager.provision` gets one more line
   -- `(temp_dir / SCHEMA_FILES_DIRNAME).mkdir(exist_ok=True)` --
   inside the existing `want_temp_dir` branch, right alongside
   `sync_shared_components`/`sync_app_dsl_tool`. `provision`'s existing
   return value (`temp_dir` or `None`) already tells the caller
   everything it needs; no signature change.
3. `window.py`:
   - `self._schema_file_watcher = SchemaFileWatcher()` in `__init__`,
     `.changed.connect(self._on_schema_file_changed)`.
   - `self._known_schema_file_sources: set[str] = set()` in `__init__`.
   - `_provision_temp_ui` (already the single call site for both boot
     and desk-switch provisioning) captures `TempUiManager.provision`'s
     return value, clears every tracked schema-file source first, then
     calls `self._schema_file_watcher.provision(temp_dir / SCHEMA_FILES_DIRNAME
     if temp_dir is not None else None, directory)`.
   - `_on_schema_file_changed(self, path: Path) -> None`: `source =
     str(path)`; `self._schema_registry.clear_source(source)`;
     `self._known_schema_file_sources.discard(source)`; return early if
     `not path.is_file()`; parse the file (catching `OSError`/
     `json.JSONDecodeError` and a non-dict top level as a loading
     error); for each key/value pair, error if the value isn't a
     string, else `register_permanent(key, value, source)`, catching
     `SchemaConflict`/`SchemaSyntaxError`; on any success or
     recoverable error for this file, `self._known_schema_file_sources.add(source)`
     (so a partially-successful file's other, valid keys still get
     cleared correctly next time).
   - `_notify_schema_file_error(self, path: Path, message: str) ->
     None`: `self.view.notify_temp_ui(path, f"Schema file error:
     {path.name}", lambda: self._show_schema_conflict_popup(path.name, message))`
     -- reuses TODO `af7898b`'s existing popup helper as-is.
4. `temp_ui.py`: extends the existing "Validated vs. non-validated
   keys" subsection (`_CUSTOM_WIDGETS_DOC`) with where a top-level
   schema file goes and its JSON shape; `TEMPUI_DOC_VERSION` bump 35 ->
   36 with a matching comment block and `_NEW_FEATURES_DOC` entry.
5. New/extended verify coverage (below); run the full `tests/verify/`
   regression suite.

## Key tradeoffs

- Polling (not a live watch) for `./desk-schemas/`'s own appearance is
  a deliberate, bounded-latency tradeoff against watching the entire
  project root -- see Design decisions above.
- No persisted, later-inspectable record of a schema file's own
  loading error (matches the equivalent `af7898b` decision for
  widget-declared schemas) -- the dashboard widget (TODO `6330249`) is
  where a durable, browsable view of this is meant to live, not this
  item.
- A malformed top-level schema file blocks only the keys it declares
  (or none, if the file itself doesn't even parse as JSON) -- it never
  affects any other file's or widget's own registrations.

## Verification

New checks, real (no mocking):
- `tests/verify/verify_schema_file_watcher.py`: a real
  `SchemaFileWatcher` against a real temp directory pair -- an already
  -present `.json` file at provision time is picked up via the initial
  scan; a file added/edited/removed after provisioning fires `changed`
  for the real, debounced path; a non-`.json` file in the same
  directory is ignored; the not-yet-existing `desk-schemas`-equivalent
  directory is polled and picked up (with a real live watch taking over
  afterward) once created mid-test.
- `tests/verify/verify_state_store_top_level_schemas.py`: a real
  `DeskWindow`-adjacent fake (mirroring `verify_state_store_schema_placement.py`'s
  own real-`_place_widget` pattern) -- a top-level schema file
  registers a permanently-enforced key; a second, conflicting file (or
  a conflicting widget-declared schema from TODO `af7898b`) is refused
  with a notification, no persisted error; editing a file to a
  different, non-conflicting schema replaces its own registration
  cleanly; deleting a file clears its registration entirely (a
  previously-blocked conflicting widget/file can now register); a
  provision() call for a *different* directory (simulating a desk
  switch) clears every previously-tracked schema-file source without
  touching a still-relevant built-in widget's own permanent schema.
- Full `tests/verify/` regression suite (118 scripts as of TODO
  `af7898b`, plus this item's new scripts).
