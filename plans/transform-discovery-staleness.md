# Fix transform discovery staleness (TODO `7c11fe0`) (COMPLETED)

## Summary

Per
`../FEEDBACK/FEEDBACK-DESK-transform-discovery-staleness-2026-08-04-1301.md`:
`TransformsService.discover()` is only ever called from `DeskWindow
._refresh_transforms()` (Desk startup/Desk-switch). A transform added
or edited while a Desk is already open (the normal case for an agent
doing transform-based work) stays invisible to `desk.transforms.run`
until something happens to trigger a fresh discovery -- `_require`
fails immediately with a `Unknown transform: ... (call discover()
first)` message the caller has no way to act on. Even when discovery
*does* re-run (e.g. the Transform Manager widget's Refresh button), an
already-imported Python transform module stays cached forever --
`_run_python` only calls `_load_transform_module` when
`self._python_modules.get(info.id)` is empty, and `discover()` never
touches `self._python_modules`, so re-discovering only helps a
*newly-added* transform, not an *edited* one.

## Affected files

- `src/desk_services/transforms/service.py`
- `tests/verify/` -- new coverage.

## Design decisions

- **`_require` retries `discover()` once on a lookup miss, before
  raising.** Needs `desk_temp_dir`/`project_dir` available at that
  point -- store them on `self` the same way `self._transforms`
  itself is already stored, at the end of `discover()`, so `_require`
  can call `self.discover(self._desk_temp_dir, self._project_dir)`
  directly without every call site needing to pass them through. If
  the id is still missing after the retry, raise as today.
- **Track each Python transform's source mtime at load time**, and on
  every `_run_python` call, compare the source's *current* on-disk
  mtime against what was recorded when the cached module was loaded;
  if it's newer, drop the cached module (and its recorded mtime) and
  reload before running. This mirrors `_resolve_js_entry`'s own
  `source_path.stat().st_mtime > compiled_entry.stat().st_mtime`
  check for the JS/TS path (`service.py:118-120`), giving Python
  parity with what that path already partially does for itself.
- **mtime of `info.path / info.entry` specifically** (the transform's
  own entry file), not the whole directory or its manifest -- matches
  what actually changes when someone edits a Python transform's logic.
  Not attempting content-hash-based staleness detection (the FEEDBACK
  item mentions this as a "more robust" option, for touch-without
  -change/fast-successive-edits-within-one-mtime-tick cases) --
  mtime-only is consistent with the existing JS/TS precedent this is
  mirroring, and adding hash-based detection on top would be a bigger
  change than this item's own scope calls for.
- **No change to the `_require`-retry behavior for a transform whose
  *manifest* changed** (e.g. its `entry` field) -- out of scope, per
  the FEEDBACK item's own framing ("that's narrower than real
  staleness tracking... but has no Python equivalent at all" was about
  source-content staleness specifically, not manifest-shape changes,
  which would need a full re-`discover()` regardless of any per
  -transform mtime tracking).

## Step-by-step implementation

1. `TransformsService.__init__`: add `self._desk_temp_dir: Path | None
   = None`, `self._project_dir: Path | None = None`, and
   `self._python_module_mtimes: dict[str, float] = {}`.
2. `discover()`: store the two directory args onto `self` before/after
   the existing `discover_transforms_with_errors` call.
3. `_require`: on a lookup miss, call `self.discover(self
   ._desk_temp_dir, self._project_dir)` once, then re-check
   `self._transforms.get(transform_id)` before raising.
4. `_run_python`: before reusing a cached module, stat `info.path /
   info.entry`'s current mtime; if `self._python_module_mtimes.get
   (info.id)` is missing or older than the current mtime, drop the
   cached module (`self._python_modules.pop(info.id, None)`) and fall
   through to the existing reload branch; after a (re)load, record the
   current mtime in `self._python_module_mtimes[info.id]`.
5. New verify coverage (see below); run the full `tests/verify/` suite.

## Key tradeoffs

- One extra `stat()` call per Python transform invocation -- real but
  negligible cost, and only on the already-somewhat-expensive
  "actually run a transform" path, not a hot loop.
- The retry-once-on-miss behavior means a genuinely unknown
  `transform_id` (a real typo) now does one extra, wasted `discover()`
  call before raising -- an accepted, cheap cost for making the common
  "I just added this" case work without manual intervention.

## Verification

New checks in `tests/verify/verify_transforms_service.py` (extending
the existing file, same `check()`/real-fixture-directory pattern
already used there), real (no mocking):
- A transform written to disk *after* an initial `discover()` call
  (simulating "added while Desk was already open") is found and runs
  successfully via `run()` alone, with no explicit second `discover()`
  call from the test.
- A Python transform's `run()` is edited on disk (new source content,
  same file, newer mtime) after it was already discovered and invoked
  once; a second invocation picks up the new behavior, not the
  cached-module's old one.
- A genuinely unknown `transform_id` still raises `Unknown transform`
  after the retry (not swallowed/hung).
- Full `tests/verify/` regression suite.
