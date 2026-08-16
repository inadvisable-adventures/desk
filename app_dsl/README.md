# App-structure DSL

A declarative schema + codegen tool for the wiring/layout code of a
multi-component app -- generalized from `world-timelines`'s own
hand-written `app-root.ts` (see
`../plans/app-structure-dsl.md`/`../investigations/app_structure_dsl_design.md`
in the Desk repo this was authored alongside, for the full design
discussion). Every individual component stays plain TypeScript+HTML+CSS
with zero awareness of this tool or of Desk -- all the integration
work happens here, in the DSL definition + this codegen, never in
component source.

This directory is mirrored fresh into `.desk_temp/app_dsl/` on every
Desk-project open (never hand-edited there -- it's regenerated, the
same way the rest of `.desk_temp/` is).

## Usage

```
python3 .desk_temp/app_dsl/build.py <definition.json> <components_dir> <out_dir> [--mode=module|global]
```

Writes `app-wiring.ts` (and `app-layout.css`, for a `"split"` layout)
into `<out_dir>`. The generated files are real, ordinary TypeScript/CSS
-- nothing about the generated output is Desk-specific unless your own
escape-hatch handler code makes it so. Which build pipeline can
actually consume the output depends on `--mode`:

- **`--mode=module`** (the default) -- real ES modules (`import`/
  `export`). Your component source uses ordinary `export default
  class Foo extends HTMLElement { ... }`. Feed the output into a
  project's own `tsc`/bundler for a **standalone build** -- no Desk
  involvement at all.
- **`--mode=global`** -- no `import`/`export` anywhere; plain global
  `class`/`let`/`function`/`const` declarations instead. This is what
  `.desk_temp/build_widget.py`'s own `DefineWidget` packaging model
  needs -- it concatenates *non-module* scripts into one `<script>`
  tag (confirmed directly: a file using `export`/`import` always gets
  CommonJS-style `exports`/`require` boilerplate in its compiled
  output, regardless of the `module` compiler option -- there's no way
  to get plain global-script output from a file containing ES module
  syntax). Using this mode means your own **component and handler
  source files must also avoid `import`/`export`** -- plain global
  classes/functions, the same convention
  `shared-components/document-editor-base/document-editor-base.ts`
  already uses for exactly this reason. Your build's own
  `tsconfig.json` `"files"` array is what orders component files ahead
  of the generated `app-wiring.ts` (the same convention
  `build_widget.py` already uses for a multi-file `DefineWidget`
  source, e.g. a shared base class before a subclass) -- this tool
  doesn't (and can't) control that ordering itself.

Both modes accept the exact same DSL definition -- `--mode` only
changes *how* the same wiring gets emitted, never what it does.

## The DSL definition (`definition.json`)

A single JSON file with four top-level keys (`components`, `layout`,
`events`, `state`) plus an optional fifth (`handlers`, the escape
hatch).

### `components` -- the registry

```json
"components": [
  { "tag": "map-panel", "source": "map-panel.ts" },
  { "tag": "timeline-view", "source": "timeline-view.ts", "class_name": "MyTimelineClass" }
]
```

`tag` is the custom element's tag name; `source` is its path, relative
to `<components_dir>`. The source file must declare a class extending
`HTMLElement` -- it does **not** need to call `customElements.define`
itself; codegen does that for you. In `--mode=module` (the default),
`export default class Foo extends HTMLElement { ... }`; in
`--mode=global`, drop the `export default` -- just `class Foo extends
HTMLElement { ... }` as a plain global declaration.

`class_name` is optional and only matters for `--mode=global`: since
there's no `import` step left to rename anything, the generated code
needs to know your component's *real* declared class name to reference
it directly. Left unset, it's assumed to follow a simple derivation
from `tag` (each hyphen-separated part capitalized, concatenated, plus
an `Element` suffix -- `"map-panel"` -> `"MapPanelElement"`, matching
the example above); set it explicitly if your class isn't named that.
`--mode=module` never needs this field at all (the generated `import
... from "..."` picks whatever local name it wants, regardless of your
class's real name).

### `layout`

Three modes exist in the full design; **this pass implements mode 1
(`"split"`) in codegen** -- `"windowed"` is accepted by the parser but
`build.py` reports a clear error if you actually try to generate it
(not yet implemented). Mode 3 (raw HTML/CSS/TS) needs no DSL entry at
all -- since components are plain custom elements, just use them
directly in hand-written markup.

```json
"layout": {
  "type": "split",
  "variants": {
    "default": {
      "type": "hsplit",
      "children": [
        { "type": "pane", "widget": "map-panel" },
        { "type": "pane", "widget": "timeline-view", "min_size": 200 }
      ]
    }
  },
  "default_variant": "default"
}
```

- `type` is `"hsplit"`/`"vsplit"` (an internal node, with `children`)
  or `"pane"` (a leaf, naming a component tag via `widget`).
- `min_size`/`max_size` (pixels) are optional per-node resize clamps.
- `variants` is a **fixed set of named, static layout trees**, not a
  general runtime-computed tree -- switch between them at runtime via
  the generated `buildLayout(variantName)`. `default_variant` names
  which one `DEFAULT_LAYOUT_VARIANT` (also generated) points at.

Generated: `buildLayout(variant: string): HTMLElement` (constructs and
returns the tree's root element -- mounting it into the page is left
to your own bootstrap code, not assumed), plus `app-layout.css` (a
plain flexbox implementation of `hsplit`/`vsplit`/`pane`).

### `events` -- the event-wiring table

```json
"events": [
  {
    "event": "marker-selected",
    "from": "map-panel",
    "actions": [
      { "set": "selectedId", "from": "event.detail.id" },
      { "call": "timeline-view", "method": "highlightEvent", "args": ["event.detail.id"] }
    ]
  }
]
```

- `from` names the emitting component's tag (or a Worker -- see
  below).
- `actions` fan out to one or more actions, in order:
  - `{"set": "<state slot name>", "from": "<expression>"}` -- a state
    mutation. `from` is a raw JS/TS expression, evaluated in the
    generated listener's own scope (where `event` is the fired
    `CustomEvent`), emitted verbatim -- not a separate expression
    language.
  - `{"call": "<component tag>", "method": "<name>", "args": [...]}`
    -- calls a method on another component. `args` are also raw
    expressions, same convention.

**Workers are just another named component** -- no separate
mechanism. Declare a worker in `components` like anything else (its
`source` would be the worker's own bootstrap module); an inbound
worker message becomes an `events` entry with that name as `from`; an
outbound request is a `call` action targeting it.

### `state` -- app-level state slots

```json
"state": [
  { "name": "selectedId", "type": "string | null", "default": null }
]
```

Plain, directly-mutable slots. Generates `export let <name>: <type> =
<default>;` plus a setter (`setSelectedId(value)`) that `events`
actions call into. No derived/computed state in this pass.

### `handlers` -- the escape hatch

```json
"handlers": {
  "onWeirdCase": { "module": "handlers.ts", "export": "handleWeirdCase" }
}
```

For anything that doesn't reduce to the above (a cross-cutting
invariant, a small bit of bespoke logic). Reference it from an action
via `{"call": "escape:onWeirdCase", "method": "unused", "args": [...]}`.
`export` names the handler's real export/global function name
(imported in `--mode=module`, called directly by that name in
`--mode=global` -- the DSL's own local key, `"onWeirdCase"` here, is
never itself an identifier codegen emits, only a way to refer to the
entry from an action). The handler module itself is hand-written,
ordinary TypeScript -- never generated, never overwritten, and (like
components) must avoid `import`/`export` if you're using
`--mode=global`.

## What's not in this pass

- Layout mode 2 (`"windowed"`) codegen, and mode 1/2's "dump current
  layout to HTML/CSS/TS" eject feature.
- A visual layout-editing widget, a DSL editor widget (raw-text +
  structured-UI sync), and the separate, Desk-core shared
  project-scoped state store (`desk.state.*`) -- each its own,
  separate piece of work.
- Derived/computed state, and the field&lt;-&gt;DSL-text-line
  bidirectional sync sub-DSL and cache/data-source declarations from
  the original design's full inventory -- deliberately deferred to
  hand-written code via the escape hatch above, revisited only if a
  second real use case justifies generalizing them.
