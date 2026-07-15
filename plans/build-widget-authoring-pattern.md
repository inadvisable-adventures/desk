# Plan: TODO b324217 — `scripts/build_widget.py` + DefineWidget authoring pattern

See design-docs/custom-widget-authoring.md section 1 for the full
rationale. This plan covers turning that into working code + docs.

## Summary

Add a generic, stdlib-only `scripts/build_widget.py` that compiles a
per-widget TypeScript + template-HTML source directory into a
`DefineWidget` tempui file under `.desk_temp/`, seed that script into new
projects the same way `scripts/todo_item_ids.py` already is, and document
the authoring pattern in `tempui-custom-widgets.md`.

## Source directory convention

Deliberately **not** under `widgets/` — that directory is scanned by
`desk.widgets.discover_widgets`, which calls `_parse_manifest` on every
`widgets/<id>/widget.json` unconditionally and raises `ValueError` if
`kind` isn't `"python"`/`"html"` (see `desk/widgets.py`). A DefineWidget
authoring manifest has a different shape (`keyword`/`label`/`width`/
`height`, no `kind`) — putting it under `widgets/` would make ordinary
widget discovery crash on it. Convention: `custom_widget_src/<name>/`, a
new top-level directory the script itself doesn't hardcode (it takes any
directory path as its argument) but that the doc will recommend.

Per-widget directory contents (four files, matching the design doc):

- `<name>.ts` (must match the directory's own name) — hand-authored.
- `widget.html` — hand-authored, with a `<template id="<name>-template">`
  and a `<script>` containing exactly one line, the marker comment
  `/* BUILD:COMPILED_JS */`.
- `tsconfig.json` — hand-authored; must set `compilerOptions.outDir`.
- `widget.json` — hand-authored: `{"keyword": str, "label": str, "width":
  int, "height": int}`.

## `scripts/build_widget.py`

Self-contained like `scripts/todo_item_ids.py` (no `desk` package import,
since a destination project won't have it installed) with a single
`main`:

```
python3 scripts/build_widget.py custom_widget_src/<name>
```

Steps:

1. Resolve the widget directory from `argv[0]`; read `widget.json`,
   validate the four required keys are present.
2. Confirm `<name>.ts` (directory name + `.ts`) exists in that directory —
   clear error naming the expected filename if not.
3. Confirm `tsc` is on `PATH` via `shutil.which` — clear error pointing at
   installing TypeScript if missing (feedback: bare `npx tsc` without
   TypeScript installed silently resolves to an unrelated abandoned npm
   package also called `tsc` — don't fall back to `npx`, only ever invoke
   `tsc` directly, so a missing compiler fails loudly instead of doing
   something unrelated).
4. Read `tsconfig.json` as JSON to get `compilerOptions.outDir` (needed to
   know where to collect compiled output from); run
   `subprocess.run(["tsc", "-p", str(widget_dir)], check=False)` and exit
   non-zero with `tsc`'s own output on failure (don't swallow compiler
   errors).
5. Collect every `*.js` file under `outDir`, sorted by path, concatenate
   their contents in that order.
6. Read `widget.html`; replace the exact line `/* BUILD:COMPILED_JS */`
   with the concatenated JS. Error clearly if the marker isn't found
   (exactly once).
7. Base64-encode the resulting document (`ascii` alphabet, no line
   wrapping from `base64.b64encode` itself).
8. Chunk the base64 text into fixed-width (2000 char) lines for
   readability in the written file; write:
   `DefineWidget<TAB>keyword<TAB>label`, `Size<TAB>width<TAB>height`, then
   one `Html<TAB>chunk` line per chunk — to `.desk_temp/<uuid4>` (creating
   `.desk_temp/` if missing), matching `desk.temp_ui.parse_define_widget`'s
   expected shape exactly.
9. Print the written path.

No `Capability` lines emitted by default (widget.json doesn't carry them
in this plan — capabilities are rare enough, and easy enough to hand-edit
into the generated file after the fact, that inventing a fifth manifest
field isn't worth it yet).

## Seeding into new projects

Mirror `DeskWindow._seed_todo_item_ids_script` exactly: add
`_seed_build_widget_script(self, directory: Path)` (same
copy-if-source-exists-and-destination-doesn't, `scripts/` dir creation,
`0o755` chmod) and call it alongside the existing
`self._seed_todo_item_ids_script(directory)` call at TODO c458012's call
site (`_create_new_desk` around window.py line ~1062-1063).

## Documentation

In `src/desk/temp_ui.py`'s `_CUSTOM_WIDGETS_DOC`, add a new section after
the existing `DefineWidget` line-format section (before "Invoking a
defined widget"): "## Authoring from real source (TypeScript + a build
script)", covering the `custom_widget_src/<name>/` four-file layout and
`python3 scripts/build_widget.py custom_widget_src/<name>` — condensed
from design-docs/custom-widget-authoring.md section 1. Bump
`TEMPUI_DOC_VERSION` by 1.

## Verification

- Unit-style script test (no real `tsc` dependency assumed present,
  handled by checking `shutil.which` — if `tsc` is genuinely on `PATH` in
  this dev environment, run the real end-to-end flow with a tiny fixture
  widget; otherwise verify steps 1-3's error paths and 6-9 with
  pre-written fake "compiled" JS standing in for `tsc`'s output).
- Confirm the generated `.desk_temp/<uuid>` file round-trips through
  `desk.temp_ui.detect_temp_ui_kind`/`parse_define_widget` correctly.
- Confirm `TEMPUI_DOC_VERSION` bump + doc content via
  `write_tempui_docs`/`ensure_docs_current`.
- Confirm `_seed_build_widget_script` copy-if-missing/never-overwrite
  behavior with a `_FakeWindow`-style direct call (mirroring how
  `_seed_todo_item_ids_script` itself would be tested, if a prior test for
  it exists to model against).
