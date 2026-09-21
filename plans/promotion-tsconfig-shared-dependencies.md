# Promotion handles a widget's tsconfig.json shared dependencies (TODO 8a09220) (COMPLETED)

## Summary

`DeskWindow._relocate_promoted_widget_source` moves one directory
(`.desk_temp/widgets/<name>/` -> `desk_widgets/<name>/`) and never reads
`tsconfig.json`. A widget authored per "Authoring from real source" may
list files outside its own directory in `tsconfig.json`'s `"files"` (a
shared base class, a shared DSL module, `shared-components/...`). After
promotion those relative paths no longer resolve, so the next rebuild
fails. Cites
`../FEEDBACK/FEEDBACK-DESK-promotion-doesnt-move-shared-multifile-deps-2026-09-14-1628.md`
and
`../FEEDBACK/FEEDBACK-DESK-promoted-widget-tsconfig-path-not-fixed-up-2026-09-18-1400.md`.

## Affected files

- `src/desk/promotion_deps.py` -- new, pure filesystem logic (no Qt).
- `src/desk/custom_widgets.py` -- factor a `_read_files_entries` helper
  out of `_read_ordered_stems` so both read the top-level `"files"` list
  the same way (`build_widget.py`'s convention).
- `src/desk/shell/window.py` -- `_relocate_promoted_widget_source` uses
  the new module; the promotion body is factored so an un-promoted peer
  can be promoted too.
- `src/desk/temp_ui.py` -- "Promoting a defined widget" doc text, a new
  changelog tag and a `_NEW_FEATURES` entry (agent-visible behavior).
- `tests/verify/verify_promotion_tsconfig_dependencies.py` -- new.

## Approach

1. **Resolve** each `"files"` entry lexically (`os.path.normpath`, no
   symlink resolution) against the widget's *old* directory. Entries
   inside the widget's own directory are ignored.
2. **Decide the file's final location**:
   - under `.desk_temp/widgets/` (disposable support territory) and not
     inside another widget's directory (one with a `widget.json`) ->
     `desk_widgets/<same relative path>` (mirrors how the widget's own
     directory moves);
   - anywhere else (already at its final place, e.g. `desk_widgets/...`,
     project files, or `.desk_temp/shared-components/`, a mirror Desk
     regenerates) -> stays put;
   - inside another widget's directory -> left alone, reported.
3. **Move each shared file once**: if the source exists and the final
   path doesn't, move it (creating parents). If the source is already gone
   but the final exists (an earlier promotion moved it) nothing to move,
   which is what dedupes across widgets. If both exist with identical
   bytes, nothing moved and the original is left so un-promoted peers keep
   working; if they differ, it is a conflict: nothing moved, the widget is
   pointed at the original, and the user is told.
4. **Rewrite the widget's `tsconfig.json`** after its directory has moved:
   each entry becomes the posix relative path from the *new* directory to
   the file's final location. This also covers "file already at its final
   place, only the relative path is now wrong". Edit by exact-string
   replacement to keep the author's formatting, re-parse to check, and
   fall back to re-dumping the JSON if that check fails.
5. **Tell the user** with one information box listing every file moved,
   every `tsconfig.json` rewritten, and any conflict or file that could
   not be found. Nothing is shown when there is nothing to report.
6. **Peers**: after moving files, scan the other directories under
   `.desk_temp/widgets/` whose `tsconfig.json` referenced a moved file.
   For each, ask: promote it too / fix its `tsconfig.json` / leave it.
   "Promote" is offered only when the peer is a registered, tempui-sourced
   custom widget (matched by `source_path`); it runs the same promotion
   path (factored out of `_on_tempui_promote_requested`) and flips the
   `[TEMPUI]` button on every placed instance. "Fix" rewrites the peer's
   entries relative to its own directory.
7. Only the top-level `"files"` array is handled (that is what
   `build_widget.py` and `build_from_source` read); `include`/
   `references` are not.
8. Agent-visible, so: new tempui changelog tag + `_NEW_FEATURES` entry,
   and a paragraph in the promotion section of `tempui-custom-widgets.md`.
9. Out of scope: TODO 3d792f8 (`outDir` normalization) and the
   first-class "shared library" abstraction floated in the feedback.

## Verification

Real temp project trees, real files, no mocks for the filesystem logic:
shared file under `.desk_temp/widgets/_shared/` moves once and two widgets
promoted in turn both end up with a valid tsconfig; already-final shared
file (report 2's `../../../desk_widgets/...` case) is rewritten without a
move; `shared-components` entry is rewritten to
`../../.desk_temp/shared-components/...` without a move; conflict and
identical-content cases; another widget's file is left alone; tsconfig
formatting/other keys preserved; a widget with no external files is
unchanged and shows no message; peer detection and both peer actions
(fix rewrites the peer's path, promote-too promotes it). Where `tsc` is
installed, also confirm a promoted widget actually rebuilds with
`build_from_source`. Re-run `verify_relocate_promoted_widget_source.py`,
`verify_promoted_widget_source_staleness.py` and the tempui doc scripts.

## Status

Implemented as planned. Notable details:

- `_on_tempui_promote_requested` was split into `_promote_custom_widget`
  (state changes) and `_finish_promotion` (UI: catalog refresh, and the
  `[TEMPUI]` button hidden on every placed instance of the kind, plus the
  triggering frame), so a peer can be promoted with no frame. The fake
  windows in `verify_relocate_promoted_widget_source.py` and
  `verify_tempui_custom_widgets.py` bind the new methods.
- The new verify script covers the pure module, promotion through
  `DeskWindow` (two widgets sharing a file, peer fix/promote/unregistered,
  no-external-files silence) and a real `tsc` rebuild of a promoted widget
  whose shared file moved. It ends with `os._exit`, like
  `verify_relocate_promoted_widget_source.py`, to dodge the known WebEngine
  shutdown segfault (LEARNINGS.md, TODO a5f66cc).
- Full `tests/verify/` sweep: all 153 scripts pass.
- Both feedback files stay in `../FEEDBACK/`: TODO 3d792f8 (`outDir`
  normalization) cites both, and the first also produced a PARKINGLOT entry
  (first-class shared-library concept).
- Browser launch skipped: the `[TEMPUI]` click and the QMessageBox dialogs
  (`_report_dependency_relocation` info box, `_choose_peer_dependent_action`)
  were exercised through their non-modal seams, not by clicking them.
