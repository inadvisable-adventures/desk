# Fix `build_widget.py` concatenation order (TODO `3fc5331`) (COMPLETED)

## Summary

`_concatenate_compiled_js` in `_BUILD_WIDGET_SCRIPT` (embedded in
`src/desk/temp_ui.py`, generated out to `.desk_temp/build_widget.py`)
currently concatenates a widget's compiled `.js` files via `sorted
(out_dir.rglob("*.js"))` — plain alphabetical filename order. Since
these widgets compile as global scripts (no `import`/`export`), a
subclass whose file happens to sort before its base class's throws
`ReferenceError: Cannot access '<Base>' before initialization` at
runtime. Fix: respect the author-declared order in the widget's own
`tsconfig.json` `"files"` array instead of re-sorting the output
directory.

This also unblocks cleaning up `document-editor-base`'s and
`_CUSTOM_WIDGETS_DOC`'s "copy the source directly into your own file"
hazard warnings, which exist solely to work around this bug — that
cleanup is called out as a follow-up in TODO `3fc5331` itself, and
belongs in *this* change once the ordering is actually fixed (same
commit, since leaving the warnings in place after the hazard is gone
would immediately be stale documentation).

## Affected files

- `src/desk/temp_ui.py` — the embedded `_BUILD_WIDGET_SCRIPT` string
  (the actual logic; this is the source of truth) and the doc/comment
  cleanup described above (`_CUSTOM_WIDGETS_DOC`'s "Reusable UI
  components" section).
- `shared-components/document-editor-base/README.md` — remove the
  "Recommended: copy directly" hazard-avoidance framing.
- `.desk_temp/shared-components/document-editor-base/README.md` and
  `.desk_temp/build_widget.py` — regenerated copies; touched by running
  the existing doc-refresh path (`ensure_docs_current`/`write_tempui_docs`),
  not hand-edited. Confirm they pick up the change rather than editing
  them directly.
- `.desk_temp/tempui-custom-widgets.md` — should document the `"files"`
  array as the way to declare multi-file compile order (currently only
  says `tsconfig.json` "must set `compilerOptions.outDir`", with no
  mention of ordering or multi-file widgets at all).
- New `tests/verify/verify_build_widget_concat_order.py`.
- `TODO.md` — mark `3fc5331` `COMPLETED` with a verification writeup.

## Design decision: match by basename, not by replicating `rootDir` inference

The robust-in-general fix would replicate `tsc`'s own `rootDir`
inference (the longest common path of all inputs) to compute each
source file's exact emitted path under `outDir`, then match on that
full relative path. That's real complexity to reimplement correctly
(and to keep correct across `tsc` versions) for a build script that
only ever needs to support this project's own widget-authoring
convention: a `.ts` file per component, each with a distinct basename,
no `import`/`export` (global scripts), no directory-structure-dependent
naming collisions.

Instead: read the ordered list of source file paths from
`tsconfig.json`'s top-level `"files"` array, take each entry's
basename stem (filename without `.ts`), and use that ordered list of
stems to sort the already-discovered compiled `.js` files (matched by
their own basename stem) instead of alphabetically. This is a much
smaller, easier-to-verify change and matches exactly what TODO
`3fc5331` itself asked for ("respecting author-declared order").

Fallback behavior when `tsconfig.json` has no `"files"` key: keep the
current `sorted()` behavior. This is the common case today (a single
`<name>.ts` file, where any deterministic order is correct) and keeps
the change additive rather than requiring every existing/future
single-file widget to add a `"files"` array it doesn't need.

Error handling, since silently dropping or misordering compiled output
would be a worse bug than the one being fixed:
- A `"files"` entry whose basename stem has no matching compiled `.js`
  file under `out_dir` → `BuildError` naming the missing file.
- A compiled `.js` file under `out_dir` whose basename stem isn't in
  the ordered list → `BuildError` naming the unlisted file (this means
  `tsc` pulled in something not explicitly declared, which the ordering
  logic can't place correctly).
- Two `"files"` entries (or two compiled outputs) sharing the same
  basename stem in different directories → `BuildError`, since basename
  -only matching can't disambiguate them. Not expected to occur given
  this project's flat-per-widget-directory convention, but must fail
  loudly rather than silently pick one.

## Step-by-step implementation

1. In `_BUILD_WIDGET_SCRIPT` (`src/desk/temp_ui.py`):
   - Add `_read_tsconfig(widget_dir) -> dict` that parses
     `tsconfig.json` once (currently `_read_out_dir` does this parse
     itself); have `_read_out_dir` take the parsed dict instead of the
     path, and add a sibling `_read_ordered_stems(tsconfig: dict) ->
     list[str] | None` that returns the ordered list of basename stems
     from `tsconfig["files"]` if present, else `None`.
   - Change `_concatenate_compiled_js(out_dir: Path, ordered_stems:
     list[str] | None) -> str`:
     - Discover `.js` files exactly as today (`sorted(out_dir.rglob
       ("*.js"))` — `sorted()` kept here only as a deterministic base
       before reordering, not as the final order).
     - If `ordered_stems` is `None`, behavior is unchanged (return in
       that discovered order).
     - Otherwise, build a `stem -> Path` dict from the discovered
       files, validate the two error conditions above (missing /
       unlisted / duplicate stems), then return the join in
       `ordered_stems` order.
   - Update `build_widget()`'s call sites accordingly.
2. Regenerate `.desk_temp/build_widget.py` by confirming
   `ensure_docs_current`'s version bump picks up the change (bump
   `TEMPUI_DOC_VERSION` if the generation path requires it for staleness
   detection — check how the last split-doc content change,
   `029047b`/`e57ce5f`, handled this) so the on-disk copy in this repo's
   own `.desk_temp/` reflects the fix, not a stale pre-fix copy.
3. Update `.desk_temp/tempui-custom-widgets.md`'s (and the embedded
   `_CUSTOM_WIDGETS_DOC` in `src/desk/temp_ui.py`) "Authoring from real
   source" section: document that `tsconfig.json`'s `"files"` array,
   when present, is the multi-file-widget mechanism for declaring
   compile/concatenation order — base classes before subclasses.
4. Remove the now-resolved hazard warnings:
   - `shared-components/document-editor-base/README.md`'s "Recommended:
     copy `document-editor-base.ts`'s contents directly..." section —
     replace with guidance to add it as a second `tsconfig.json`
     `"files"` entry ahead of the widget's own file.
   - The matching note in `_CUSTOM_WIDGETS_DOC`'s "Reusable UI
     components" section (`src/desk/temp_ui.py`).
   - Confirm the `.desk_temp/`-mirrored copies pick up both edits via
     the normal doc-refresh mechanism rather than being edited by hand.
5. Add `tests/verify/verify_build_widget_concat_order.py`: a real (not
   mocked) `tsc` compile of a small fixture pair of `.ts` files — a
   base class and a subclass — with a `tsconfig.json` `"files"` array
   listing the base first, deliberately named so alphabetical order
   would put the subclass first (reproducing the exact failure this
   TODO describes), confirm:
   - Old behavior would have failed (documented in a comment, not
     re-asserted as a live check) / new behavior concatenates
     base-before-subclass.
   - Running the concatenated output via `node` actually succeeds (no
     `ReferenceError`) and produces the expected result.
   - The three new error paths (missing/unlisted/duplicate stem) each
     raise `BuildError` with a clear message.
   - The no-`"files"`-key fallback path still behaves exactly as before
     (existing single-file widgets unaffected).
6. Run the full `tests/verify/` suite to confirm no regressions.

## Key tradeoffs

- Basename-stem matching over full relative-path/`rootDir` replication:
  simpler, matches this project's actual authoring convention, at the
  cost of not generalizing to a widget with two same-named files in
  different subdirectories (explicitly rejected with a clear error
  instead of silently mishandled).
- `"files"` array chosen over some new bespoke ordering key in
  `widget.json` (e.g. an explicit `"compileOrder"` list): `"files"` is
  already a real `tsconfig.json` field with exactly the right meaning
  (this is genuinely why it's listed, in this order, for `tsc` itself),
  so this needs no new authoring surface — just stops discarding
  information the widget author already provided.
