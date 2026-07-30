# shared-components

A small library of reusable, self-contained, dependency-free UI
mini-components for `DefineWidget`/browser-kind widget authors — for
whenever a widget needs something more involved than a bare
`<input>`, and it's not worth re-deriving from scratch.

One subdirectory per component. Each has its own `README.md`
explaining what it does and how to use it, plus its own source — a
ready-to-use custom element (a `.ts` file and a `template.html`
fragment), or a base class to extend (see e.g. `document-editor-base/`)
— no shared build step, no npm, no runtime dependency between
components or on anything else. This matters here specifically because
a `DefineWidget`/browser-kind widget can never depend on anything at
runtime beyond what's inlined into its own HTML (see
`tempui-custom-widgets.md`'s "Authoring from real source") — the value
of this directory is a canonical, already-debugged starting point, not
a package to install.

This directory (the source of truth, checked into this repo) is
mirrored automatically into every project's own `.desk_temp/
shared-components/` on every Desk open/switch (see
`sync_shared_components` in `src/desk/temp_ui.py`) — never hand-edit
the copy under `.desk_temp/`, it's regenerated fresh every time and any
local edits there will be silently overwritten.

## Available components

- [`hsv-color-picker/`](hsv-color-picker/README.md) — an HSV color
  wheel + brightness bar + hex field.
- [`document-editor-base/`](document-editor-base/README.md) — a base
  class for a title-to-path, auto-load/auto-save file-backed document
  editor.
