# desk.mermaid: quoted edge labels (TODO 21fc736) (COMPLETED)

## Summary

Node labels may be double-quoted and the quotes are stripped, but `A -->|"label"| B` rendered the literal quote
marks (SVG `&quot;label&quot;`). Make edge labels behave like node labels. Cites
`../FEEDBACK/FEEDBACK-DESK-desk-mermaid-strips-a-quoted-node-label-s-delimiters-but-not-2026-11-06-1831.md`.

## Affected files

- `src/desk/mermaid.py`: `_EDGE_RE`, `_edge_match_info`, new `_unquote`, state transition labels.
- `tests/verify/verify_mermaid_parser_grammar.py`: new cases.

## Approach

- Piped labels: `|(?:"(?P<label_q>[^"]*)"|(?P<label>[^|]*))|`, quoted alternative first -- otherwise the unquoted
  class stops at a `|` inside the quotes. This also makes `-->|"a|b"|` work (the one case where quoting is needed).
- Unpiped labels (`-- "x" -->`) and state transition labels (`A --> B : "x"`, the feedback's side question: it had
  the same asymmetry) go through `_unquote`, which strips one matched pair of surrounding quotes.

## Status

Implemented; headless-verified only.
