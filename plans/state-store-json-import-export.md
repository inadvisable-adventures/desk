# Shared state store: save/load as JSON (TODO `297f1a6`) (COMPLETED)

## Summary

Lets a Desk user export the entire current `desk.state.*` store (every
key's value, edit, and history) to a JSON file, and import one back --
a snapshot/restore pair, not a per-key operation. Exposed through the
State Manager widget (TODO `6330249`) as "Save State..."/"Load
State..." toolbar actions, since that's already the widget for deep
insight into shared state and already has the file-picking/status-line
conventions this needs.

## Affected files

- `src/desk/shell/window.py` -- `export_state_json`/`import_state_json`
  methods.
- `src/desk/shell/current_context.py` -- two new provider hook pairs.
- `widgets/state_manager/widget.py` -- "Save State..."/"Load State..."
  toolbar actions.
- `tests/verify/` -- new coverage.

## Design decisions

- **Whole-store snapshot, not per-key** -- matches the literal ask
  ("save/load shared state," not "a shared state key"); a per-key
  export/import can be a later, separately-scoped addition if it turns
  out to be wanted.
- **File shape mirrors `Desk.state`'s own persisted shape exactly**
  (`desk.desks._state_entry_dict`/`_load_state_entry`'s `{"value",
  "edit", "history": [{"value", "edit"}, ...]}` per key) -- reusing the
  existing helpers directly means the export format is never a second,
  drifting definition of what a `StateEntry` looks like as JSON.
- **Import is all-or-nothing**: every key in the file is validated
  against any *currently*-active schema (its current, latest value
  only -- history entries are trusted as-is, they're what genuinely
  happened, not being newly written) before anything is applied; if
  even one key fails, the whole import is refused with a message
  listing every offending key, rather than partially applying a
  snapshot and leaving the store in a mixed, surprising state. A key
  the file doesn't currently have a schema for imports unchanged, same
  as any other non-validated write.
- **Import replaces, not merges, each key's entry wholesale**
  (value + edit + full history) -- this is a restore, not an
  incremental write, so it doesn't go through `set_state`'s
  single-entry FIFO-append path. A key present in the current store
  but *absent* from the imported file is left untouched (importing a
  partial snapshot -- e.g. one exported before some keys existed --
  doesn't delete anything).
- **Every changed key publishes `desk.state.changed`** after a
  successful import (once per key, with its new current value) so
  every live subscriber (including the State Manager widget's own
  other instances, if more than one is somehow placed) refreshes,
  matching `set_state`'s existing live-update guarantee.
- **No file-format versioning/migration** -- the shape is simple
  enough (and shared with `.desk` files themselves) that this isn't
  worth speculative-proofing against a future shape change that hasn't
  been designed yet.

## Step-by-step implementation

1. `window.py`:
   - `export_state_json(self, path: Path) -> str | None` -- builds
     `{key: _state_entry_dict(entry) for key, entry in
     self.current_desk.state.items()}` and writes it
     (`json.dumps(..., indent=2)`) to `path`. Returns an error message
     (e.g. a real `OSError` writing the file) or `None`.
   - `import_state_json(self, path: Path) -> str | None` -- reads and
     parses `path` (JSON/OSError errors reported, not raised); rejects
     a non-dict top level; for each key, uses `desk.desks
     ._load_state_entry` to parse its `StateEntry`, validating the
     entry's current `value` against `self._schema_registry.get(key)`
     if active; collects every validation failure and, if any exist,
     returns a single combined error message without applying
     anything; otherwise replaces `self.current_desk.state[key]` for
     every key in the file and publishes `desk.state.changed` for each.
2. `current_context.py`: `set_state_exporter`/`get_state_exporter`
   (`Callable[[Path], str | None]`), `set_state_importer`/
   `get_state_importer` (same signature) -- same one-hook-per
   -capability shape as every existing pair.
3. `widgets/state_manager/widget.py`: "Save State..." (`QFileDialog
   .getSaveFileName`, `.json` filter) and "Load State..." (`.getOpenFileName`)
   toolbar buttons, calling the two new hooks and showing the result
   (including a real confirmation dialog before import, since it can
   overwrite currently-live values) via the existing status label;
   `refresh()` after a successful import.
4. New/extended verify coverage (below); run the full `tests/verify/`
   regression suite.

## Key tradeoffs

- Whole-store only, no per-key export/import in this pass.
- All-or-nothing import -- a 99-good/1-bad snapshot imports nothing at
  all rather than the 99 good keys; simpler and safer than partial
  application, at the cost of an all-or-nothing failure mode for a
  large snapshot with one stale/incompatible entry.

## Verification

New checks, real (no mocking):
- `tests/verify/verify_state_store_json_import_export.py`: export
  writes a real file whose shape round-trips through
  `import_state_json` back to the exact same `Desk.state` (value, edit,
  history, for multiple keys); importing a file with a key that
  violates a currently-active schema is refused entirely, and no other
  key from that same file is applied either; importing a file
  containing a key the store doesn't currently have a schema for
  succeeds unchanged; a key present in the current store but absent
  from the imported file survives the import untouched; a real
  subscribed instance receives `desk.state.changed` for each key an
  import actually changes; malformed JSON/a non-dict top level is a
  real, non-crashing error message.
- Full `tests/verify/` regression suite (122 scripts as of TODO
  `6330249`, plus this item's new script).
