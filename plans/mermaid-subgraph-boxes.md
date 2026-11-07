# desk.mermaid: subgraph containment boxes (TODO a8931c8) (COMPLETED)

## Summary

`subgraph id [Title] ... end` was skipped, so there was no way to show that nodes belong together (the Pipeline
widget's `map` sub-pipeline and am-rules-dsl's override trace both hand-rolled synthetic-node workarounds). Draw a
labeled box around a subgraph's nodes, nestable. Cites the same FEEDBACK file as TODO a509077.

## Affected files

- `src/desk/mermaid.py`: `Subgraph`, `Diagram.subgraphs`, `SubgraphLayout`, `LayoutResult.subgraphs`; parser; layout; `_add_subgraph_box`.
- `src/desk/temp_ui.py`, `diagrams.md`, `design-docs/architecture.md`, `tests/verify/verify_mermaid_styling_subgraphs.py`.

## Approach

- Grammar: `subgraph id [Title]`, `subgraph id["Title"]`, `subgraph Title` (title doubles as id); `end`; nesting;
  `direction XX` inside is ignored. A node belongs to the innermost subgraph it is *first* mentioned in; a later
  mention elsewhere doesn't move it. Empty subgraphs draw nothing. Duplicate ids, a bare `subgraph`, and an edge
  to/from a subgraph id (which would otherwise silently create a stray node) raise `MermaidParseError`, so the
  caller falls back to plain text. Unclosed `subgraph` / stray `end` are tolerated.
- Layout: the old per-rank left-to-right packing becomes a "skyline" pack over *items* (nodes and subgraph blocks).
  A block spans the ranks of its descendants and is placed at the first cross offset clear of everything already
  placed in every rank it spans, reserving one contiguous cross-axis lane. So a non-member in a middle rank is pushed
  past the lane instead of landing in the box. A block's width is its inner pack plus padding (and, for TD/BT, at
  least its title width; for LR/RL the title strip is added to the cross-start padding). Items sort by first-seen
  node order, so with no subgraphs this is exactly the old layout (verified identical on TD/LR/BT/RL samples).
- Boxes: cross extent = the reserved lane; main extent hugs member nodes / child boxes bottom-up (so a parent
  strictly encloses its children), padded, with the title strip on top. The rank gap grows with nesting depth so
  boxes in adjacent ranks don't touch. The scene is shifted so boxes that stick out past the nodes start at the margin.
- Rendering: translucent rounded box + elided title, drawn before nodes/edges, outer before inner.

## Limitations (documented)

Edges to a subgraph itself; per-subgraph `direction`; subgraph styling (`style sg ...`) is not drawn.

## Verification

`verify_mermaid_styling_subgraphs.py`: parse cases and, for TD/BT/LR/RL on a nested + sibling + cross-edge diagram,
that boxes contain their members, no non-member intersects a box, nesting and sibling boxes behave, and everything
is inside the scene. Rendered a PNG and inspected it. Desk GUI not launched.

## Status

Implemented and verified headless.
