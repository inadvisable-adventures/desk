# Promotion outDir normalization + stale build-cache clearing (TODO 3d792f8) (COMPLETED)

## Summary

`SOURCE_BUILD_CACHE_DIRNAME` (`.build`) is where Desk's own rebuild-on
-demand mechanism (`build_from_source`) writes a promoted widget's final
packaged `index.html` -- a literal constant, unrelated to whatever
`tsconfig.json`'s own `compilerOptions.outDir` says (the directory `tsc`
itself compiles raw `.js` into). An author who names that something else
(`out`, `build`, ...) ends up with two separate, differently-gitignored
build directories for one widget: `desk_widgets/**/.build/` is covered
by the existing gitignore-entry prompt, a hand-chosen `outDir` isn't,
and it also isn't cleared when the widget's directory moves at
promotion, which can crash a rebuild after a later tsconfig/dependency
fix (`out/` retains a stale, differently-pathed compile from before the
move, and `tsc`'s own no-cross-file-clean behavior lets both versions
coexist, tripping `_concatenate_compiled_js`'s "multiple compiled files
named X.js" collision guard -- the exact error the second report hit).
Cites
`../FEEDBACK/FEEDBACK-DESK-promotion-doesnt-move-shared-multifile-deps-2026-09-14-1628.md`
("Related finding") and
`../FEEDBACK/FEEDBACK-DESK-promoted-widget-tsconfig-path-not-fixed-up-2026-09-18-1400.md`.

## Approach

Both steps run once, at promotion, right after the existing TODO
8a09220 shared-dependency relocation (same secondary-bookkeeping
guarantees: best-effort, never fails the promotion itself, which has
already succeeded by this point).

1. **Clear the stale build cache unconditionally.** Read the (post-move)
   widget's own `tsconfig.json` `compilerOptions.outDir`; if that
   resolved directory already exists, delete it (`shutil.rmtree`) before
   anything else. It was compiled from the pre-move relative source
   layout (or a pre-fix one), so its contents can only be stale --
   whatever `outDir` ends up being named, the very next
   `build_from_source` call recreates it from scratch. Not gated behind
   a confirm: this is pure cleanup of Desk-owned, always-regenerated
   build output, the same category of thing `.build` itself already is.
2. **Offer to normalize `outDir` to `.build`.** If the (still-current, or
   just-cleared) `outDir` string isn't already `.build`
   (`SOURCE_BUILD_CACHE_DIRNAME`), ask via the same `_confirm_fn` pattern
   as the `.gitignore` prompt: "This widget's tsconfig.json builds to
   'X', but promoted widgets are rebuilt into '.build' -- update
   tsconfig.json to match?" On accept, rewrite `compilerOptions.outDir`
   in place (preserving the rest of the file, same exact-string-then
   -fallback-reparse approach as TODO 8a09220's `rewrite_files_entries`).
   Confirmed directly that `tsc`'s own raw output and
   `build_from_source`'s final `index.html` coexisting in one directory
   is fine (`_concatenate_compiled_js` only globs `*.js`). Declining
   leaves `outDir` as the author wrote it -- only the doc changes (next
   point) push new authors toward the right value from the start.
3. **Doc:** "Authoring from real source" in `tempui-custom-widgets.md`
   names `.build` as the specific recommended `outDir` value (not just
   "must set it to something"), so an author gets it right the first
   time and never sees the prompt. Since this also changes the tsconfig
   author's own `.gitignore` needs not at all (`desk_widgets/**/.build/`
   already covers it once `outDir` matches) -- a short note says so.
   Agent-visible guidance change -> new tag + `_NEW_FEATURES` entry.

## Affected files

- `src/desk/promotion_deps.py` -- `read_out_dir`, `clear_stale_build_output`,
  `rewrite_out_dir`.
- `src/desk/shell/window.py` -- `_relocate_promoted_widget_source` calls
  the new step; `_normalize_promoted_build_output` (confirm + report).
- `src/desk/temp_ui.py` -- doc text, tag, `_NEW_FEATURES`.
- `tests/verify/verify_promotion_outdir_normalization.py` -- new.

## Verification

Real temp trees, no mocks: a stale `out/` (or already-`.build`) directory
from before a move is deleted at promotion regardless of the outDir
decision; accepting the prompt rewrites `compilerOptions.outDir` to
`.build` and preserves the rest of the file's formatting/other keys;
declining leaves it untouched; already-`.build` widgets are never
prompted and nothing is deleted needlessly if nothing exists yet; a
missing/malformed tsconfig is a silent no-op, not an error. Where `tsc`
is installed, a real `build_from_source` rebuild succeeds after
`outDir` is normalized to `.build` (index.html and compiled `.js`
coexisting in one directory, confirming point 2's own compatibility
claim) and reproduces + fixes the second report's exact "multiple
compiled files" collision via the stale-cache clear. Re-run
`verify_relocate_promoted_widget_source.py`,
`verify_promotion_tsconfig_dependencies.py`,
`verify_promoted_widget_source_staleness.py`, `verify_build_from_source.py`.
Full `tests/verify/` sweep.

## Status

Implemented as planned, plus one clarification confirmed directly during
verification: `SOURCE_BUILD_CACHE_DIRNAME` (`.build`) is *always* where
`build_from_source` writes the final packaged `index.html`, regardless
of `tsconfig.json`'s own `outDir` -- `outDir` only controls where `tsc`
compiles raw `.js`. So declining the normalization prompt still leaves
Desk rebuilding correctly (the final artifact always lands in `.build`
either way); accepting it just means `tsc`'s own raw output and the
final `index.html` end up in the *same* directory, so there's only one
build directory to gitignore/clean instead of two. Both are covered by
tests.

Two independent steps, neither gated on the other: clearing a stale
build cache always happens (never behind a confirm -- it's pure
cleanup, the next rebuild recreates it), and normalizing the name is
offered via the same `_confirm_fn` pattern as the `.gitignore` prompt.

Verified: the new `verify_promotion_outdir_normalization.py` (real
temp trees, no mocks -- including real `tsc` rebuilds proving a stale
compile would otherwise leak into the packaged widget, and that it
doesn't once cleared), run twice for flakiness. Updated
`verify_relocate_promoted_widget_source.py`,
`verify_promotion_tsconfig_dependencies.py`, and
`verify_tempui_custom_widgets.py` to bind the new
`_normalize_promoted_build_output` method on their fake windows
(the first two needed a fix: the new step now also runs whenever a
source-backed widget is promoted, so one `verify_promotion_tsconfig
_dependencies.py` test's "tsconfig untouched" assertion was narrowed to
what its own TODO (8a09220) actually owns -- the `"files"` entries, not
the whole file's bytes). Full `tests/verify/` sweep (158 scripts)
passes. Browser launch not needed.

Moved `../FEEDBACK/FEEDBACK-DESK-promoted-widget-tsconfig-path-not-fixed-up-2026-09-18-1400.md`
to `../FEEDBACK/implemented/` (both TODOs it cited, 8a09220 and this
one, are now COMPLETED). Left
`../FEEDBACK/FEEDBACK-DESK-promotion-doesnt-move-shared-multifile-deps-2026-09-14-1628.md`
in place -- it also cites both, but still has an open PARKINGLOT.md
entry (the `desk_libs/<name>/` first-class shared-library idea).
