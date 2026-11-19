# TempUI DSL: OpenMarkdown and Markdown

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
just covers the `OpenMarkdown` and `Markdown` keywords.

## OpenMarkdown

For telling Desk to open a Markdown file in the Markdown widget — a
fire-and-forget instruction, not a question: there is no `Answer`
line, and Desk never writes back to this file. This is a *pointer* to
an existing file elsewhere on disk — if you want to give Desk markdown
content directly instead, use `Markdown` below.

- `OpenMarkdown <path>` — the first (and normally only) line. `path`
  is the file to open, absolute or relative to the current Desk's
  directory. Like `Question <text>`, everything after the first space
  is one opaque value, so a path containing spaces needs no escaping.

Example:

```
OpenMarkdown ./diagrams.md
```

Clicking the notification opens `path` in a new Markdown widget
instance, centered in the current view.

## Markdown

For giving Desk markdown *content* directly, rendered in the Markdown
widget — unlike `OpenMarkdown` above, there is no separate target file:
this file's own content *is* the markdown. Fire-and-forget, same as
`OpenMarkdown`: there is no `Answer` line, and Desk never writes back
to this file.

- The first line is `Markdown <label>` — `label` is used for the
  notification text; it is *not* used for anything saved to disk.
- Every line after that, verbatim, is the markdown to render (not
  further parsed here — write real markdown, including fenced
  ` ```mermaid ` blocks if you want a diagram).

Example:

```
Markdown Investigation summary
# Investigation summary

Found the bug in `file_watch.py` line 42.
```

The resulting widget shows a **"Save As"** button in place of "Open"
(there's nothing to "open" — its content already comes from this
file, not a chosen path): saving defaults to the project root, with a
filename derived from the *rendered content's own first line*
(kebab-case-slugified, e.g. `# Investigation summary` becomes
`investigation-summary.md`) — not from `<label>` above. Saving opens
the new file in a separate, ordinary Markdown widget instance; this
tempui-bound instance stays open, unaffected.

## Supported Mermaid subset

A fenced ` ```mermaid ` block above renders through Desk's own,
hand-rolled Mermaid support -- a real but partial implementation, not
the full Mermaid language. Anything outside this subset falls back to
showing the raw source as plain text instead of rendering it or
erroring.

- **Flowchart** (`flowchart`/`graph`, any of the five directions):
  five node shapes -- rect `id[Label]`, rounded `id(Label)`, diamond
  `id{Label}`, circle `id((Label))`, stadium `id([Label])` -- no other
  extended shapes (subroutine, cylinder, hexagon, ...). Edge styles
  `-->`, `---`, `-.->`, `-.-`, with a label either piped
  (`A -->|label| B`) or unpiped/inline (`A -- label --> B`,
  `A -. label .-> B`, and the arrow-less equivalents `---`/`-.-`).
- **Node styling** (flowchart): `classDef name fill:#f96,stroke:#333,
  stroke-width:4px,color:#fff` defines a class (comma-separate several
  names to define them at once; a class named `default` applies to every
  node), `class A,B name` or the `A:::name` shorthand assigns it, and
  `style A fill:#f96` styles one node directly (applied after its
  classes). Drawn properties: `fill`, `stroke`, `stroke-width`,
  `stroke-dasharray` (any value draws dashed), `color` (label text);
  colors may be `#rgb`, `#rrggbb`, a color name, or `rgb(r,g,b)`. Other
  properties are accepted and ignored. Order doesn't matter, and a
  `class`/`style` naming an unknown node or an undefined class is
  ignored. `linkStyle` and `click` lines are still skipped.
- **Subgraphs** (flowchart): `subgraph id [Title] ... end` (also
  `subgraph id["Title"]`, or `subgraph Title`) draws a labeled box around
  the nodes first mentioned inside it; subgraphs may nest. A node
  belongs to the innermost subgraph it is first mentioned in. `direction`
  lines inside a subgraph are ignored (the whole diagram uses one
  direction). **Not supported:** an edge to or from a subgraph itself
  (`A --> mySubgraph`) -- that diagram falls back to plain text; connect
  to a node inside it instead.
- **State diagram** (`stateDiagram`/`stateDiagram-v2`): flat only --
  `[*]` start/end pseudostates, `A --> B` / `A --> B : label`
  transitions, `A : label` descriptions. A composite/nested `state X {
  ... }` block is skipped (not an error), not rendered.
- **Quoting:** any label -- inside a shape or on an edge -- may be
  double-quoted (`id["a [b] c"]`) so it can contain its own shape's
  delimiter characters literally. There is no other escaping mechanism
  (no backslash escapes, no HTML entities), and quoting is optional --
  a label with nothing special in it doesn't need it.
- **Unsupported entirely:** any other diagram type (sequence, class,
  ER, gantt, pie, ...), thick edges (`==>`), `linkStyle`/`click`, any
  node shape beyond the five above, and a composite `stateDiagram` block's own nested content
  (skipped, never rendered, not an error).

**This renders via a transform, not logic built directly into the
widget** -- a flowchart via the `mermaid_flowchart_svg` transform, a
state diagram via `mermaid_state_svg`. Both ship bundled with Desk
itself and are discovered automatically in every project, with nothing
to add and nothing copied into your project. A project can still
override either one with its own same-id transform (in its own
`desk_transforms/`, or `.desk_temp/transforms/` for TypeScript/
JavaScript only) if it wants different rendering; the project's own
copy always wins. When rendering still doesn't happen, the plain-text
fallback names why, distinguished by its own note:

- *"no `'mermaid_flowchart_svg'`/`'mermaid_state_svg'` transform
  found"* -- only reachable in an unusual install with no bundled
  transforms at all, or a project that deliberately overrode one with
  something that doesn't actually work; add or fix the transform (see
  `transforms` in the Bridge API capability list,
  `tempui-custom-widgets.md`) rather than assuming the diagram's own
  syntax is wrong.
- *"Mermaid syntax error: ..."* -- the diagram itself doesn't parse;
  fix the syntax per the subset above.
- *"unsupported Mermaid diagram type"* -- this diagram type has no
  transform at all, ever (not a per-project gap).
- *"Mermaid rendering failed: ..."* / *"produced invalid SVG output"*
  -- the transform ran but something else went wrong; the message
  names what.
