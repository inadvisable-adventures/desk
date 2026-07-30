# Plan: TODO 3b1ef3d — seed a reusable UI mini-component library, starting with an HSV color picker

From `../FEEDBACK/FEEDBACK-DESK-color-picker-mini-component-library-2026-07-22-1811.md`:
`DefineWidget`/browser-kind widgets are self-contained HTML with no
module system and a hard "avoid adding dependencies, prefer bespoke
solutions" constraint (CLAUDE.md) — so a non-trivial UI control (a color
picker, here) gets redesigned from scratch, in every project, with no
canonical reference. Per direct user instruction:

1. Look at the real, already-shipped implementation in the peer
   `../necro-4x/` project (`custom_widget_src/terrain-color-initializer/`)
   rather than re-deriving the design from the feedback's own prose.
2. Store components as real, individually-subdirectoried source files
   under `./shared-components/` in this repo (checked into git, "for
   building this app" — a permanent part of Desk's own source, not
   generated/gitignored content).
3. Copy the latest versions into `.desk_temp/shared-components/` on
   every Desk boot/open (mirroring `.desk_temp/build_widget.py`'s own
   "always fresh, never a one-time seed" convention, TODO `029047b`).
4. Each component gets its own `README.md` alongside its code.
5. `tempui-custom-widgets.md` gets a note that these exist, and that
   it's fine to either import them directly or copy+paste+modify.

## Source material

Read `../necro-4x/custom_widget_src/terrain-color-initializer/
terrain-color-initializer.ts` (538 lines) and its `widget.html` in
full. The color-picker-specific parts (generalizable, no dependency on
terrain/TSV/SVG-recoloring concerns) are:

- HSV/RGB/hex math: `clamp255`, `toHex2`, `rgbToHex`, `hexToRgb`,
  `clampPct`, `hsvToRgb`, `rgbToHsv`.
- The wheel + brightness-bar DOM structure and CSS (`.wheel`,
  `.wheel-hue` — a `conic-gradient` — `.wheel-sat-overlay` — a
  `radial-gradient` white-to-transparent — `.wheel-cursor`,
  `.brightness-slider`/`-track`/`-handle`, `.hex-row`/`#hex-input`).
- `bindDrag` (pointer capture wrapped in try/catch — a synthetic
  `PointerEvent` in a headless-Chrome test has no real pointer to
  capture, and capture failing shouldn't block applying the value),
  `bindWheel`/`bindBrightnessSlider` (the `+90°` screen-angle-to-CSS
  -angle correction reading the wheel's pointer position back into
  hue), `bindHexInput`, `applyHsv`/`renderWheelCursor`/
  `renderBrightnessSlider`.

Left behind entirely (terrain-specific, not part of a generic color
picker): TSV parsing/serialization, SVG recoloring/data-URI preview,
`desk.fs`/`desk.self.getLocalStorage` calls, terrain navigation
(prev/next/progress), the hex preview SVG.

## Design

### Component API (a genuine generalization, not a verbatim copy)

The original only ever calls its own internal `applyHsv`, with no
public API at all (it's a whole widget, not a reusable control) — a
reusable version needs one. `HsvColorPickerElement` (tag
`hsv-color-picker`):

- `value` property (getter/setter, hex string) — the supported way to
  get/set the color programmatically. Setting it does **not** dispatch
  `colorchange` (matches a native `<input>`: `el.value = "x"` in JS
  never fires `input`/`change`) — only a real user interaction
  (dragging the wheel/brightness bar, typing in the hex field) does.
  An optional `value="#rrggbb"` HTML attribute seeds the initial color
  once, read in `connectedCallback` (not a full `attributeChangedCallback`
  reflection loop — out of scope, `.value` covers ongoing use).
- `colorchange` `CustomEvent` (`detail: { hex: string }`,
  `bubbles: true, composed: true` so it crosses the shadow boundary) —
  fired from the three interactive paths only (wheel drag, brightness
  drag, hex input), via a shared `applyHsv(emit: boolean)`/
  `applyHexColor(hex, emit: boolean)` pair.
- No `window.desk` dependency at all (unlike the original) — a pure UI
  control, usable in a plain page with no Bridge API present.

### Files, under `shared-components/hsv-color-picker/`

- `hsv-color-picker.ts` — the custom element + math functions, adapted
  as above.
- `template.html` — just the `<template id="hsv-color-picker-template">`
  block (markup + scoped `<style>`, generalized class names, no
  terrain-specific styling) — meant to be pasted into a consuming
  widget's own HTML document, the same "look up the template by id"
  shape every `DefineWidget`-authored widget's own `.ts` already uses
  (see "Authoring from real source" in `tempui-custom-widgets.md`) —
  no new pattern invented.
- `README.md` — what it is, when to use it, both usage modes (`import
  "../shared-components/hsv-color-picker/hsv-color-picker"` if copying
  the whole directory as-is; or copy+paste+modify the two files
  directly into a widget's own source if the widget needs to diverge),
  the public API (`value`/`colorchange`), and a note that
  `template.html`'s `<template>` block must be pasted into the
  consumer's own HTML document either way (there's no bundler here to
  inline it automatically) — plus a credit line to the original
  `necro-4x` implementation this was extracted from.

Also `shared-components/README.md` (top-level, short): what this
directory is for, the one-subdirectory-per-component convention, and
that `.desk_temp/shared-components/` always mirrors it (never hand-edit
the copy).

### Syncing into `.desk_temp/` (`src/desk/temp_ui.py`)

New `SHARED_COMPONENTS_DIRNAME = "shared-components"` and
`sync_shared_components(temp_dir: Path) -> None`: locates this repo's
own `shared-components/` via `Path(__file__).resolve().parents[2] /
SHARED_COMPONENTS_DIRNAME` (the same "resolve relative to this
installed package's own source" approach already implicit in how this
whole app is always run from its own checked-out repo, editable-
installed — confirmed directly: `Path(desk.temp_ui.__file__).resolve()`
already resolves to this repo's real `src/desk/temp_ui.py`, not a
separate site-packages copy). If that source directory doesn't exist
(e.g. an unusual non-source install), no-op. Otherwise: remove
`temp_dir / SHARED_COMPONENTS_DIRNAME` if present, then
`shutil.copytree(source, destination)` — always a full, fresh mirror,
same "never let a stale copy linger" posture as `.desk_temp/
build_widget.py`, just via a real multi-file directory copy instead of
an embedded Python string constant (these are real TS/HTML/MD files, not
a single script — baking a growing component library into string
constants doesn't scale the way one script already did).

Called from `TempUiManager.provision`, right after the existing
`write_tempui_docs`/`ensure_docs_current` branch, unconditionally (not
gated by "already exists," unlike that branch) — every open/switch
re-mirrors it, per the user's "on boot/opening of a desk file" wording.

### Docs (`_CUSTOM_WIDGETS_DOC`)

New `## Reusable UI components` section, placed after "Authoring from
real source" (before "Invoking a defined widget") — the natural spot
for anything about building a widget from real TS source. States:
`.desk_temp/shared-components/` holds ready-made, dependency-free UI
components (starting with `hsv-color-picker`), refreshed automatically
alongside the rest of `.desk_temp`; explicitly says it's fine to either
`import` the component file directly or copy+paste+modify it — either
is an accepted, intended way to use it, not just a fallback. Bump
`TEMPUI_DOC_VERSION` (23) and add a matching `_NEW_FEATURES_DOC`
"## Version 23" entry, per `development-process.md`'s "Keep the tempui
changelog docs current" rule.

## Verification

New `tests/verify/verify_shared_components.py`:

- `sync_shared_components` copies `hsv-color-picker/`'s three files
  into a scratch `.desk_temp/shared-components/` correctly; a stale
  leftover file from a previous copy (simulating a removed component)
  is gone after a second sync (full mirror, not an additive merge); a
  missing source directory is a clean no-op (no exception).
  `TempUiManager.provision` (real instance, real scratch directory)
  results in `shared-components/hsv-color-picker/` actually present
  under the provisioned `.desk_temp/`.
- `TEMPUI_DOC_VERSION`/`_NEW_FEATURES_DOC` bump checks, matching this
  file's own existing test conventions (e.g.
  `verify_html_widget_local_storage.py`'s `test_doc_version_bumped_to_2`
  shape) — the new doc section text is present in the rendered doc set.
- **Real compile + real headless-Chrome interaction test** for
  `hsv-color-picker.ts` itself (not just "the files exist"): `tsc`
  -compile it (mirroring `necro-4x`'s own strict `tsconfig.json`)
  against a scratch copy, assemble a throwaway HTML page pairing the
  compiled JS with `template.html`'s own `<template>` block, load it in
  a real `QWebEngineView` (this repo's own established real-browser
  test harness, e.g. `verify_html_widget_local_storage.py`), and:
  - confirm `.value` reads back the default color correctly;
  - dispatch a real synthetic `PointerEvent` sequence on the wheel/
    brightness elements (confirming the try/catch around
    `setPointerCapture` doesn't block the value from applying, exactly
    the edge case the original code's own comment describes) and
    confirm `.value` changed and a `colorchange` event fired with a
    matching `detail.hex`;
  - confirm setting `.value` programmatically does **not** fire
    `colorchange` (the native-`<input>`-like convention this
    generalization deliberately adds).
- Full `tests/verify/` regression suite.
