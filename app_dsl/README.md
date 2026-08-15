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
python3 .desk_temp/app_dsl/build.py <definition.json> <components_dir> <out_dir>
```

Writes `app-wiring.ts` (and `app-layout.css`, for a `"split"` layout)
into `<out_dir>`, importing your components from `<components_dir>`.
The generated files are real, ordinary TypeScript/CSS -- feed them
into whatever build you already have (a project's own `tsc`/bundler
for a standalone build, or Desk's own `build_widget.py` pipeline to
package as a `kind: "html"` widget). Nothing about the generated
output is Desk-specific unless your own escape-hatch handler code
makes it so.

## The DSL definition (`definition.json`)

A single JSON file with four top-level keys (`components`, `layout`,
`events`, `state`) plus an optional fifth (`handlers`, the escape
hatch).

### `components` -- the registry

```json
"components": [
  { "tag": "map-panel", "source": "map-panel.ts" }
]
```

`tag` is the custom element's tag name; `source` is its path, relative
to `<components_dir>`. The source file must `export default` a class
extending `HTMLElement` -- it does **not** need to call
`customElements.define` itself; codegen does that for you.

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
via `{"call": "escape:onWeirdCase", "method": "unused", "args": [...]}`
-- codegen imports the named export and calls it directly, positionally,
with the same `args` convention as a component method call. The
handler module itself is hand-written, ordinary TypeScript -- never
generated, never overwritten.

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
