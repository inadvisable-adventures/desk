# Plan: TODO 13f4ad5 (COMPLETED) — durable source paths for promoted widgets

## Summary

`_relocate_promoted_widget_source` (`src/desk/shell/window.py`)
currently reconstructs a promoted widget's authoring source directory
from its DSL `keyword` (e.g. `PdfViewer`), but the real directory
(created by `.desk_temp/build_widget.py`) is named after the
kebab-case `<name>` argument it was built from (e.g. `pdf-viewer`) —
almost never the same string, so promotion silently fails to relocate
the source for nearly every real-source widget.

Fix: record the source directory as a durable, project-relative path
at registration time (a new `SourcePath` tempui line /
`CustomWidgetDefinition.source_path` field, persisted in the `.desk`
file), and use that recorded path instead of guessing from the
keyword. As a consequence, a promoted source-backed widget no longer
needs to bake its compiled HTML (`html_b64`) into the `.desk` file —
it can be rebuilt on demand from its now-durably-known source
directory into a gitignored `.build/` cache.

Three parts, matching the TODO's own three items.

## Affected files

- `src/desk/temp_ui.py` — `CustomWidgetDefinition` gets `source_path`;
  `parse_define_widget` parses a new `SourcePath` line;
  `_BUILD_WIDGET_SCRIPT` emits it; doc content/version bump +
  changelog entries.
- `src/desk/custom_widgets.py` — new `build_from_source` (compiles a
  source-backed widget straight to `.build/index.html`, no
  base64/tempui-file round trip).
- `src/desk/desks.py` — `_load_custom_widget`/`_custom_widget_dict`
  round-trip `source_path`.
- `src/desk/shell/window.py` — `_register_custom_widget` builds from
  source when a definition has a `source_path` and no baked
  `html_b64`; `_relocate_promoted_widget_source` uses the recorded
  path; `_on_tempui_promote_requested` strips `html_b64` and
  re-registers (rebuild + remount) for a source-backed promotion.
- `.gitignore` — new `**/.build/` pattern.
- `tests/verify/verify_relocate_promoted_widget_source.py` — cover the
  actual bug (mismatched keyword vs. directory name) and the new
  no-baked-html_b64 behavior.

## Step-by-step

1. **`CustomWidgetDefinition.source_path: str | None = None`**
   (`temp_ui.py`) — project-directory-relative, POSIX-style path to
   the widget's current authoring source directory. `None` means "no
   known source directory" (hand-authored inline-only widget, or a
   definition that predates this field).

2. **`parse_define_widget`** — parse an optional `SourcePath<TAB>path`
   line into `source_path`.

3. **`_BUILD_WIDGET_SCRIPT`** — `build_widget()` emits a
   `SourcePath\t{widget_dir.as_posix()}` line (the directory it was
   literally invoked with — normal usage always passes a
   project-relative path per its own `Usage:` docstring). Update the
   in-file docstring/usage text to mention it.

4. **`desks.py`** — `_load_custom_widget` reads `source_path` (default
   `None`, for `.desk` files saved before this TODO); `_custom_widget_dict`
   writes it.

5. **`custom_widgets.py`: `build_from_source(project_dir, source_path)`**
   — the TS-compile-and-package half of `_BUILD_WIDGET_SCRIPT`'s
   `build_widget()` (tsconfig read, `tsc -p`, ordered/unordered
   concatenation, marker substitution), reimplemented here (not
   imported — the generated script is deliberately self-contained with
   no `desk` package dependency, so some duplication vs. that template
   is inherent) but producing a real `index.html` written to
   `<project_dir>/<source_path>/.build/index.html` instead of a
   base64 tempui line. Returns the `.build` directory, or `None`
   (logged) on any build failure (missing `tsc`, compile error,
   missing marker, ...) — one bad/stale source shouldn't take the app
   down.

6. **`window.py: _register_custom_widget`** — when
   `definition.source_path is not None and not definition.html_b64`
   (the new "source-backed, nothing baked" shape), call
   `build_from_source` instead of `materialize`, and hash the built
   `index.html`'s bytes for `content_hash` instead of `html_b64`. Both
   branches otherwise converge on the same `WidgetInfo`/mount code
   already there.

7. **`window.py: _relocate_promoted_widget_source`** — look up
   `self._custom_widget_definitions.get(keyword)`; if it (or its
   `source_path`) is `None`, log the existing "nothing to relocate"
   INFO message (now phrased around "no recorded source path" rather
   than a guessed path) and return. Otherwise resolve
   `self.current_desk.directory / definition.source_path`; if that
   directory doesn't exist, same INFO no-op. Destination is
   `PROMOTED_WIDGET_SRC_DIRNAME / source_dir.name` (the real directory
   name, not the keyword — matters for exactly the same
   keyword-vs-directory-name mismatch this TODO fixes). On a
   successful move, update `definition.source_path` in place to the
   new location so it's correct for the very next save.

8. **`window.py: _on_tempui_promote_requested`** — reorder so
   `_relocate_promoted_widget_source` (and, for a source-backed
   definition, a same-source re-registration that rebuilds from the
   just-relocated directory and remounts — the documented "same
   keyword, same source" refresh path `_register_custom_widget`
   already supports) happen *before* `save_current_desk()`, so the
   save captures the post-relocation `source_path` and the
   now-stripped `html_b64`. For a source-backed definition, set
   `definition.html_b64 = ""` before that re-registration — this is
   the "no baked html_b64 for source-backed widgets" behavior; a
   hand-authored (no `source_path`) definition is untouched and keeps
   baking `html_b64` exactly as today.

9. **`.gitignore`** — add `**/.build/` near the existing `**/build/`
   entry.

10. **Doc content** (`temp_ui.py`) — bump `TEMPUI_DOC_VERSION` 41 -> 42;
    update "Authoring from real source"/"Promoting a defined widget to
    the Desk" to describe the `SourcePath` line and the rebuilt-on
    -demand `.build/` cache (and that this means `tsc` must be
    available wherever a Desk with a source-backed promoted widget is
    subsequently opened); add a `## Version 42` entry to both
    `_BREAKING_CHANGES_DOC` (rebuild-on-demand needs `tsc` at load
    time, not just at author time) and `_NEW_FEATURES_DOC` (the
    durable `SourcePath` record and the bug it fixes).

## Verification

Extend `tests/verify/verify_relocate_promoted_widget_source.py`:

- A definition whose `source_path` names a directory *not* matching
  its `keyword` (the actual confirmed bug: e.g. keyword `PdfViewer`,
  source dir `pdf-viewer`) is still correctly relocated on promotion,
  to `desk_widgets/pdf-viewer/` (not `desk_widgets/PdfViewer/`).
- No `source_path` at all (hand-authored inline-only widget) — still
  a quiet no-op, `html_b64` still saved into the `.desk` file.
- A recorded `source_path` whose directory is missing — still a quiet
  no-op (regression check, now driven by the recorded path rather
  than a guessed one).
- After promoting a source-backed widget, the resulting
  `CustomWidgetDefinition` in `win.current_desk.custom_widgets` has
  `html_b64 == ""` and an updated `source_path` pointing at
  `desk_widgets/<name>/`.
- Existing three tests (moved-on-promotion, pre-existing-destination,
  doc-content) keep passing.

New/extended checks in a `custom_widgets`-focused script (or a new
`verify_build_from_source.py`, mirroring `verify_build_widget.py`'s
own structure) for `build_from_source`: successful build produces
`.build/index.html`; missing `tsc` / a compile error / a missing
`widget.html` all return `None` and log rather than raise.

Full `tests/verify/` regression suite afterward (`tsc`-dependent new
checks skip gracefully, matching `verify_build_widget.py`'s own
precedent, if `tsc` isn't on `PATH` in this environment).
