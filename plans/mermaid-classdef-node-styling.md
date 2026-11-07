# desk.mermaid: classDef/class/style node styling (TODO a509077) (COMPLETED)

## Summary

`desk.mermaid` skipped `classDef`/`class`/`style` lines, so every flowchart node rendered identically. Support them
(plus the `A:::name` shorthand) so nodes can be colored by role. Cites
`../FEEDBACK/FEEDBACK-DESK-desk-mermaid-ignores-standard-subgraph-classdef-two-independ-2026-11-06-1210.md`
(suggested fix #2: land styling first -- it is layout-independent). `linkStyle`/`click` stay skipped. Subgraphs are
TODO a8931c8.

## Affected files

- `src/desk/mermaid.py`: `Node.classes`/`Node.style`; parsing; `_styled` + `_parse_color`; `_make_node_item`.
- `src/desk/temp_ui.py`: tag, changelog entry, "Supported Mermaid subset" in `tempui-markdown.md`.
- `diagrams.md`, `design-docs/architecture.md`; `tests/verify/verify_mermaid_styling_subgraphs.py` (new, shared with a8931c8).

## Approach

- Grammar (matching official Mermaid): `classDef a,b k:v,k:v;`, `class n1,n2 name`, `style n k:v,...`, `id:::name`
  (added as an optional suffix to `_NODE_RE`, so it works on bare and shaped nodes inside edge chains).
- Property values are split on commas outside parentheses so `rgb(1,2,3)` survives.
- Assignments are collected during the parse and resolved at the end (`_resolve_node_styles`), so statement order
  doesn't matter. Precedence: `default` class, then assigned classes in order, then the node's `style` line.
  Unknown node ids / undefined classes are ignored (as in Mermaid).
- Drawn: `fill`, `stroke`, `stroke-width`, `stroke-dasharray` (any value -> dashed), `color` (label text). Colors:
  `#rgb`/`#rrggbb`, names, `rgb()`/`rgba()`. Other properties are parsed and ignored.
- The old prefix-skip tuple shrinks to `click `/`linkstyle`/`direction `.

## Verification

`verify_mermaid_styling_subgraphs.py` (parse results, precedence, order independence, SVG contains the custom
colors), plus the existing mermaid verify scripts. Layout is byte-identical for diagrams without subgraphs
(compared before/after on TD/LR/BT/RL samples).

## Status

Implemented and verified headless (offscreen Qt, rendered a PNG to eyeball it). The Desk GUI was not launched.
