# Version-stamp desk-temporary-ui.md's static content, refresh it in place when stale (COMPLETED)

TODO `f7b1611`.

## Summary

`desk-temporary-ui.md` (`DOC_TEMPLATE` in `src/desk/temp_ui.py`) is
only ever written **once**, when `.desk_temp` is first provisioned for
a directory (`TempUiManager.provision`: `if not doc_path.is_file():
write it`). As `DOC_TEMPLATE`'s own static content evolves over time
(new DSL sections, corrected wording -- most recently TODO `91b3f42`'s
`DefineWidget` section), a Desk directory provisioned *before* that
change keeps its stale copy forever; nothing ever revisits it. TODO
`91b3f42` already solved the analogous problem for the *dynamic*
"registered custom widgets" section (patched in place via marker
comments), but the *static* main content had no equivalent mechanism.

Fix: a manually-bumped integer version number, noted in an HTML
-comment line right under the doc's own H1 title (`# Temporary UI`).
Before opening a Desk (the existing `_provision_temp_ui` call, run at
app startup and on every Desk switch), if `desk-temporary-ui.md`
already exists, its version is checked against the current
`TEMPUI_DOC_VERSION`; a mismatch (**including no version note at
all**, per the request -- an unversioned file is always treated as
out of date) rewrites just the static content in place, leaving the
custom-widgets section (if present) untouched.

## Key decisions

- **The version lives in an HTML comment, not real prose** — `<!--
  desk-temporary-ui.md version: N -- ... -->`, the same
  machine-parseable-marker style TODO `91b3f42` already established
  for the custom-widgets section (`CUSTOM_WIDGETS_SECTION_START/END`).
  Consistent with the rest of the file's own convention, and reads
  clearly as "generated/internal," not a line an agent should treat as
  DSL content or edit by hand.
- **Manual, not derived from anything** — a plain `TEMPUI_DOC_VERSION =
  N` integer constant in `desk/temp_ui.py`, bumped by whoever edits
  `DOC_TEMPLATE`'s static content meaningfully (a new section, a
  correction that would matter to an agent reading it) — never
  recomputed or auto-incremented. There's no reliable way to detect
  "did this edit change the doc's *meaning*" automatically (a typo fix
  and a new DSL section are very different in importance, and either
  could touch the same number of lines) — a human decides at edit
  time, the same spirit as this project's own permanent TODO item ids
  (assigned once, never recomputed). A code comment right next to the
  constant spells this out explicitly, per the request.
- **No version note at all means out of date, unconditionally** — an
  explicit part of the request, and also just the correct behavior for
  every file that predates this TODO entirely (there's no version
  before there's a version).
- **Refresh replaces everything *outside* the custom-widgets section,
  not the whole file** — extracts the existing
  `CUSTOM_WIDGETS_SECTION_START`...`_END` block verbatim (if present)
  before rewriting, and re-appends it unchanged after the fresh static
  content. "Be certain not to clobber the DSL extensions" is handled
  structurally, the same way `sync_custom_widgets_doc_section` already
  avoids clobbering arbitrary user edits elsewhere in the file — this
  is the mirror-image operation (preserve the *inside* of the markers
  while replacing the *outside*, instead of the reverse). If a file
  predates the custom-widgets feature too (no markers at all), there's
  nothing to preserve — it's just fully rewritten, and `_sync_
  tempui_doc` (already called right after, in `_register_custom_
  widgets_from_desk_temp`'s/`_register_custom_widgets_from_desk`'s
  wake in `window.py`) inserts a fresh custom-widgets section moments
  later regardless, so this is safe even considered in isolation.
- **Placeholder substitution via plain string `.replace()`, not
  `str.format()`** — `DOC_TEMPLATE` currently has no literal `{`/`}`
  in its body, but Markdown prose (especially future additions, e.g. a
  JSON example) could introduce one later, and `.format()` would
  silently misinterpret it as a field reference. A unique, unlikely
  -to-collide placeholder token (`{{TEMPUI_DOC_VERSION}}`, replaced via
  plain string substitution, not `.format()`'s own double-brace
  escaping) avoids that fragility entirely.
- **Hooked into `TempUiManager.provision`, not a new call site** — this
  *is* "before opening a Desk" in this app's own terms (already called
  at `DeskWindow.__init__` and every `switch_desk`, before
  `_load_desk_widgets`). `provision`'s existing per-directory
  already-provisioned-this-session guard (`if directory == self.
  _provisioned_directory: return`) means the version check runs at
  most once per directory per app run, not on every redundant call —
  intentionally left as-is: version staleness doesn't change mid
  -session, so nothing is lost by not re-checking on a same-directory
  revisit within one run.

## Implementation

`src/desk/temp_ui.py`:

- `TEMPUI_DOC_VERSION = 1` (with the explanatory comment above).
- `DOC_TEMPLATE` gains a `<!-- desk-temporary-ui.md version:
  {{TEMPUI_DOC_VERSION}} -- do not edit this line by hand; Desk uses
  it to detect when this file's own main content is out of date and
  needs refreshing. See TEMPUI_DOC_VERSION in src/desk/temp_ui.py.
  -->` line right under the `# Temporary UI` title.
- `render_static_doc() -> str`: `DOC_TEMPLATE` with the placeholder
  substituted for the current `TEMPUI_DOC_VERSION`. Replaces
  `TempUiManager`'s direct reference to the raw `DOC_TEMPLATE`
  constant at its one call site.
- `parse_doc_version(text: str) -> int | None`: extracts the version
  integer from the note line via a regex anchored to its own fixed
  prefix; `None` if the line is missing or malformed.
- `ensure_doc_version_current(doc_path: Path) -> None`: no-ops if the
  file doesn't exist (nothing to refresh -- first-creation is
  `TempUiManager.provision`'s job) or its version already matches;
  otherwise rewrites it per the "preserve the custom-widgets section"
  design above.

`src/desk/shell/temp_ui_manager.py`: `provision`'s doc-handling block
becomes `if not doc_path.is_file(): write render_static_doc() else:
ensure_doc_version_current(doc_path)`.

## Affected files

- `src/desk/temp_ui.py` -- version constant, template placeholder,
  `render_static_doc`/`parse_doc_version`/`ensure_doc_version_current`.
- `src/desk/shell/temp_ui_manager.py` -- `provision`'s doc-handling
  block.
- `design-docs/architecture.md` or `widget-ux.md` -- brief mention
  alongside the existing tempui-doc/custom-widgets description (final
  location decided during implementation, wherever the existing
  `desk-temporary-ui.md`/custom-widgets material already lives).

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication` where
`TempUiManager`/Qt is involved; plain function tests for the pure
parsing/rendering pieces):

- `parse_doc_version`: current version note -> the right integer; no
  note at all -> `None`; a malformed/non-numeric note -> `None`.
- `render_static_doc`: placeholder substituted correctly; output round
  -trips through `parse_doc_version` back to `TEMPUI_DOC_VERSION`.
- `ensure_doc_version_current`: missing file -> no-op (doesn't create
  it); current-version file -> byte-for-byte untouched; a file with no
  version note at all -> rewritten to the current version; a file
  with an old/different version number and a real custom-widgets
  section -> rewritten to the current version with that section
  preserved verbatim; same case but no custom-widgets section at all
  -> rewritten with just the fresh static content, no section
  fabricated.
- `TempUiManager.provision`: first-creation path writes a doc that
  already carries the current version (regression check against the
  pre-TODO behavior); an existing, differently-versioned doc gets its
  static content refreshed on the next `provision()` call for that
  directory, preserving a real custom-widgets section already present.
- Full scratchpad regression suite re-run.

## Status

Implemented exactly as planned: `TEMPUI_DOC_VERSION` (with its
explanatory comment), `_DOC_VERSION_PLACEHOLDER`/`_DOC_VERSION_RE`,
`DOC_TEMPLATE`'s new version-note line, `render_static_doc`/
`parse_doc_version`/`ensure_doc_version_current` all added to
`src/desk/temp_ui.py`; `TempUiManager.provision`'s doc-handling block
in `src/desk/shell/temp_ui_manager.py` updated to call
`render_static_doc()` on first creation and `ensure_doc_version_current`
otherwise. `design-docs/architecture.md`'s Widget Model section
updated with a new paragraph right after the existing tempui-custom
-widgets description.

Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real `QApplication`,
a real `TempUiManager` for the integration checks): version
present/missing/malformed parsing; placeholder substitution leaves no
leftover token; `ensure_doc_version_current` no-ops on a missing file
and on an already-current one (byte-for-byte untouched), refreshes an
unversioned file, and refreshes an old-versioned file both with and
without a real custom-widgets section present (preserved verbatim when
present, nothing fabricated when absent); `TempUiManager.provision`
itself, end to end, writes an already-current doc on first creation
and refreshes a stale pre-existing one (with a real custom-widgets
section) on a later call. Full scratchpad regression suite re-run --
same three pre-existing, unrelated failures as every recent prior
TODO's plan, none touching any file edited here.

No `LEARNINGS.md` entry -- nothing here violated a reasonable
assumption or took real investigation; it's the same marker
-delimited-patch-in-place technique TODO `91b3f42` already established
for the custom-widgets section, applied to the mirror-image case
(preserve the *inside* of the markers while replacing the *outside*,
instead of the reverse).
