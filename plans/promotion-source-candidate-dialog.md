# Plan: TODO 9613bb0 (COMPLETED) — promotion-time messaging for a missing recorded source

## Summary

`_on_tempui_promote_requested` (`src/desk/shell/window.py`) silently
keeps a promoted widget's `html_b64` baked into the `.desk` file
whenever `CustomWidgetDefinition.source_path` is `None` or names a
directory that no longer exists — correct behavior for a genuinely
hand-authored, inline-only `DefineWidget`, but the same silent
fallback also fires for a widget that *was* authored "from real
source" (`temp_ui.py`'s "Authoring from real source") whose
`SourcePath` line was simply never recorded. The real source directory
is very likely still sitting under `.desk_temp/widgets/`, almost
always under a differently-cased/separated variant of the widget's
`keyword` (the same PascalCase-vs-kebab-case mismatch TODO `13f4ad5`
already had to account for, for the *recorded*-path case).

Fix: before falling back to baking `html_b64`, look for a plausible
source directory and put the decision in front of the user instead of
choosing silently — adopt a found candidate, keep the widget inline
anyway (explicit now, not silent), or cancel the promotion.

## Affected files

- `src/desk/custom_widgets.py` — new `LikelySourceCandidate` dataclass
  and `find_likely_source_candidates(project_dir, keyword)`.
- `src/desk/shell/window.py` — new `_resolve_promotion_source`,
  `_confirm_promotion_no_source`, `_confirm_promotion_source_candidate`
  methods; `_on_tempui_promote_requested` calls the first right after
  its existing "Promote to Desk" confirm, before mutating any promotion
  state.
- `tests/verify/verify_relocate_promoted_widget_source.py` — `_FakeWindow`
  gains test-controllable stand-ins for the two new dialog methods;
  existing no-source-path / missing-source-path tests updated for the
  new (now explicit, dialog-gated) behavior; new tests for the
  candidate-found path (exact `widget.json` keyword match, and a bare
  case-variant directory-name match) and the no-candidates-found path.

## Key design decisions

- **Where candidates are searched**: only `.desk_temp/widgets/`
  (`TEMP_UI_DIRNAME/CUSTOM_WIDGET_SRC_DIRNAME`) — the one documented
  location "Authoring from real source" ever writes a not-yet-promoted
  widget's source to. Not `desk_widgets/` (already-promoted widgets
  register their own `source_path` at load time, so they aren't in
  this no-source-path situation at all) and not an arbitrary project
  -wide search, which risks false positives outside the one convention
  this feature is about.
- **What counts as a candidate directory**: only a `.desk_temp/widgets/`
  subdirectory that itself contains a `widget.json` — an unrelated
  scratch subdirectory someone left under `.desk_temp/widgets/` should
  never surface as a false match just because its name happens to
  resemble the keyword.
- **Two independent match signals, either is sufficient**:
  1. `widget.json`'s own `"keyword"` field equals `definition.keyword`
     exactly — the strong signal (unambiguous, matches
     `build_widget.py`'s own manifest contract).
  2. The directory's name, normalized (strip everything but
     letters/digits, lowercase), equals the keyword normalized the
     same way — catches PascalCase/camelCase/kebab-case/snake_case
     variants of the same conceptual name without hand-listing each
     convention, per the user's own ask. A single normalization
     function handles every casing convention at once rather than
     generating and checking a fixed list of variant spellings.
- **Trigger condition**: not just "`source_path is None`" — also a
  *recorded* `source_path` whose directory no longer exists, since
  that's the same "nothing usable to build from" situation and
  deserves the same visibility rather than staying a silent INFO-only
  no-op.
- **UI shape**: follows the existing `_confirm_stale_reload`/
  `_confirm_widget_error_dismissed` precedent exactly — a plain
  `QMessageBox` built directly (not `self._confirm_fn`, which is
  yes/no-only) inside its own small method, so headless verification
  can monkeypatch just that method instead of driving a real modal.
  One button per candidate (labeled with its relative path) plus
  "Keep as Base64" and "Cancel" when candidates exist; "Promote
  Anyway"/"Cancel" when none were found. Closing the dialog without
  clicking a button behaves like "Cancel" (`clickedButton()` is
  `None`, matches neither the candidate buttons nor the accept
  button).
- **Where the resolved `source_path` plugs in**: `_resolve_promotion_
  source` only ever mutates `definition.source_path` (to a chosen
  candidate's path) before the rest of `_on_tempui_promote_requested`
  runs — `_relocate_promoted_widget_source` and the final "strip
  `html_b64` for a source-backed definition" block are both already
  driven entirely by `definition.source_path`, so they need no changes
  at all to pick up a candidate the same way they'd pick up a
  `SourcePath` line that was recorded at authoring time.
- **Labels not user-selectable**: per `CLAUDE.md`, dialog button/title
  text stays non-selectable (`QMessageBox` default); no change needed
  there, same as every existing dialog in this file.

## Step-by-step

1. **`custom_widgets.py`**: add `import json`, `import re`,
   `from dataclasses import dataclass`; import `CUSTOM_WIDGET_SRC_DIRNAME`,
   `TEMP_UI_DIRNAME` from `desk.temp_ui` alongside the existing import.
   Add `_normalize_widget_name(name: str) -> str` (strip non-alphanumerics,
   lowercase), `LikelySourceCandidate` (`path: Path`, `matched_by:
   Literal["keyword", "name"]`), and `find_likely_source_candidates
   (project_dir: Path, keyword: str) -> list[LikelySourceCandidate]`
   per the matching rules above. Returns `[]` if
   `.desk_temp/widgets/` doesn't exist. A malformed/unreadable
   `widget.json` is treated as "no keyword match" (falls through to
   the name-variant check), not an error.
2. **`window.py` imports**: add `CUSTOM_WIDGET_SRC_DIRNAME` to the
   existing `from desk.temp_ui import (...)` block; add
   `LikelySourceCandidate, find_likely_source_candidates` to the
   existing `from desk.custom_widgets import build_from_source,
   materialize` line.
3. **`window.py`: `_resolve_promotion_source(self, definition) -> bool`**
   — the new orchestration. No-op (`return True`) if
   `definition.source_path` is set and that directory exists. Otherwise
   calls `find_likely_source_candidates`; if it finds any, calls
   `_confirm_promotion_source_candidate` (returns `(proceed, chosen)`);
   if none, calls `_confirm_promotion_no_source` (returns `proceed`,
   `chosen=None`). Returns `False` (abort, nothing mutated) if the user
   didn't proceed; otherwise sets `definition.source_path =
   chosen.path.relative_to(project_dir).as_posix()` when a candidate was
   chosen, and returns `True`.
4. **`window.py`: `_confirm_promotion_no_source(self, definition) -> bool`**
   — `QMessageBox` naming the widget, noting the stale recorded path if
   there was one, explaining the baked-`html_b64` consequence; "Promote
   Anyway" (`AcceptRole`) / "Cancel" (`RejectRole`).
5. **`window.py`: `_confirm_promotion_source_candidate(self, definition,
   candidates) -> tuple[bool, LikelySourceCandidate | None]`** —
   `QMessageBox` listing every candidate's relative path and which
   signal matched it (`informativeText`), one `AcceptRole` button per
   candidate plus `ActionRole` "Keep as Base64" and `RejectRole`
   "Cancel"; maps the clicked button back to `(True, candidate)`,
   `(True, None)`, or `(False, None)`.
6. **`window.py`: `_on_tempui_promote_requested`** — call
   `self._resolve_promotion_source(definition)` right after the
   existing `_confirm_fn("Promote to Desk", ...)` check, before
   `self.current_desk.custom_widgets.append(definition)`; `return` if
   it's `False`. No other line in this method changes — relocation and
   the `html_b64`-stripping block already key off `definition.
   source_path` alone.

## Verification

Extend `tests/verify/verify_relocate_promoted_widget_source.py`:

- `_FakeWindow` gains `no_source_choice: bool` and
  `source_candidate_choice: LikelySourceCandidate | None | "cancel"`
  attributes plus overrides for `_confirm_promotion_no_source`/
  `_confirm_promotion_source_candidate` that consult them (defaulting
  to "proceed, keep inline" so unrelated tests don't need to opt in).
- No source_path, no candidate on disk: dialog shown (assert via a
  recorded-call list on the fake), "Promote Anyway" keeps `html_b64`
  baked (update `test_no_recorded_source_path_is_a_noop_with_an_info_log`
  accordingly) — and choosing cancel aborts the whole promotion (new
  test: `.desk` file's `custom_widgets` list unchanged, tempui file not
  deleted).
- Recorded `source_path` whose directory is missing: same dialog now
  fires (update `test_recorded_source_path_missing_is_a_noop`).
- A `.desk_temp/widgets/<variant-name>/widget.json` whose own
  `"keyword"` matches exactly: found as a `matched_by="keyword"`
  candidate even when the directory name itself doesn't resemble the
  keyword at all.
- A `.desk_temp/widgets/pdf-viewer/` with no matching `widget.json`
  keyword, promoting keyword `PdfViewer`: found as a `matched_by="name"`
  candidate (PascalCase vs. kebab-case). Choosing it relocates the
  source and strips `html_b64` exactly like a normally-recorded
  `SourcePath` would (reuses `test_source_backed_promotion_rebuilds_
  and_strips_html_b64`'s own `_fake_build_from_source` monkeypatch).
- An unrelated `.desk_temp/widgets/` subdirectory with no `widget.json`
  at all never surfaces as a candidate.
- Full `tests/verify/` regression suite afterward.
