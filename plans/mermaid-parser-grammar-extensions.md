# desk.mermaid parser: stadium nodes, unpiped edge labels, quoted labels (TODO 90dd6e6) (COMPLETED)

## Summary

`desk.mermaid` (`src/desk/mermaid.py`) implements a real but undocumented
subset of Mermaid flowchart syntax. Two common, standard constructs are
silently unsupported and both collapse into the same generic
"unrecognized" error, one of them actively misleading about where the
problem is:

1. **Stadium nodes**, `id(["label"])` -- `_NODE_RE` has no alternative
   for `([...])` at all.
2. **Unpiped inline edge labels**, `A -- label --> B` -- `_EDGE_RE` only
   recognizes the piped `-->|label|` form; the unpiped form isn't
   matched as an edge operator at all, so the label text gets folded
   into the *preceding node's* token instead, and the resulting error
   points at a token that was never meant to be a node.
3. **No shape tolerates its own delimiter character inside its label**,
   not even in quotes -- standard Mermaid supports `A["a [b] c"]` to
   escape exactly this case.

Cites `../FEEDBACK/FEEDBACK-DESK-mermaid-parser-rejects-standard-syntax-2026-09-18-2220.md`.
Out of scope (already its own TODO, `9fe03a1`): distinguishing a
`MermaidParseError` in the Markdown widget's own fallback UI.

## Approach

### 1. Stadium nodes

Add a `([...])` alternative to `_NODE_RE`, ordered *before* `rounded`'s
`(...)` alternative -- `rounded`'s own character class (`[^()]*`, no
parens excluded, but brackets allowed) would otherwise happily consume
`([label])` whole as a rounded node with the literal label `[label]`,
since regex alternation tries branches in written order and takes the
first one that lets the overall pattern match. Circle already sits
before rect for the same kind of reason (`((`'s two parens vs. `(`'s
one), unaffected.

New `Node.shape` value `"stadium"`. Sizing: same generic text-based
sizing as rect/rounded (no special-case needed in `_node_size`).
Boundary-clipping: falls into the existing rect/rounded bucket in
`_boundary_point` (already a rectangular approximation, fine for
rounded corners too). Rendering (`_make_node_item`): a true pill/capsule
-- `addRoundedRect` with `radius = height / 2` (fully round the short
ends), visually distinct from `rounded`'s moderate corner rounding.

### 2. Unpiped inline edge labels

`_EDGE_RE` gains alternatives for each of the four operator families,
label between an opening and closing token instead of after a literal
operator + `|...|`:

- solid arrow: `--` ... `-->`
- solid open: `--` ... `---`
- dotted arrow: `-.` ... `.->`
- dotted open: `-.` ... `.-` (with a negative lookahead for `>` so this
  doesn't also match the dotted-arrow-with-label case)

Each gets its own uniquely-named group pair (Python's `re` disallows
reusing a group name across alternatives), and a small helper picks
whichever pair actually matched and normalizes it to the same
`(op, label)` shape `_parse_flowchart`'s existing edge-construction
code already expects -- that code (arrow/dotted flags, label stripping)
is otherwise unchanged. Label content uses `.+?` (non-greedy, matches
the piped form's own permissiveness -- `[^|]*`) relying on the specific
required closing literal to disambiguate, the same way regex
backtracking already has to for the quoting below.

### 3. Quoted labels

Every shape's content becomes `"..."` (any character except a literal
`"`) *or* the existing unquoted-content class -- tried unquoted first
(the common case, and a minor perf win), falling back to the quoted
alternative via ordinary backtracking when the unquoted class can't
reach the shape's own closing delimiter (e.g. an unquoted rect attempt
against `["a [b] c"]` consumes up to the inner `[`, fails to find `]`
immediately after, and the engine backtracks to the quoted branch,
which matches the whole thing up to the closing `"`). `_parse_node_token`
checks each shape's quoted group before its plain one (`is None`, not
falsy, so an intentionally empty quoted label `""` isn't skipped).

### 4. Documentation

- `desk.mermaid`'s own module docstring: rewrite the flowchart bullet to
  list all five node shapes (stadium included) and both edge-label
  forms (piped and unpiped), plus a line on quoting -- and explicitly
  name what's still unsupported (extended shapes beyond these five,
  thick/`==>` edges, `%%` comments mid-diagram are already skipped
  as-is, subgraphs are skipped not rendered).
- `tempui-markdown.md` (`_MARKDOWN_DOC` in `src/desk/temp_ui.py`): a new
  "Supported Mermaid subset" section under the existing Markdown/
  OpenMarkdown coverage, self-contained (an agent reading this doc has
  no easy way to go read `desk/mermaid.py`'s source) -- the same shape
  list, edge forms, and quoting note. Guidance/phrasing content change
  -> mint a tempui changelog tag + `_NEW_FEATURES` entry.

## Affected files

- `src/desk/mermaid.py` -- `_NODE_RE`, `_EDGE_RE`, `_parse_node_token`,
  `_parse_flowchart`'s edge-info extraction, `_make_node_item`, module
  docstring, `Node.shape`'s comment.
- `src/desk/temp_ui.py` -- `_MARKDOWN_DOC`, tag, `_NEW_FEATURES`.
- `tests/verify/verify_mermaid_parser_grammar.py` -- new (no dedicated
  parser-only test file existed before this; the two existing mermaid
  verify scripts only exercise the transform layer).

## Verification

Direct `parse()` calls, no transform/widget involved: a stadium node
alone and mixed with other shapes; the feedback's own two motivating
lines (`Start(["Begin"])`-style stadium, and `Check -- yes --> Body`
unpiped-arrow-label, confirming the label lands on the *edge*, not
folded into a bogus node id); all four unpiped operator families,
including a dotted-open case right next to a dotted-arrow one on
adjacent lines to confirm the negative lookahead disambiguates them;
quoted labels for every shape including one with the shape's own
delimiter inside; an empty quoted label falling back to the node id;
regression -- every existing plain/piped-label/no-quotes case in
`verify_mermaid_svg_transforms.py`'s own `FLOWCHART_SOURCE` still
parses identically. Rendering smoke test: `build_scene`/`layout` don't
raise for a diagram using a stadium node and an unpiped-label edge.
Doc checks: the tag is in `CURRENT_TAGS`/`_NEW_FEATURES`, and
`_MARKDOWN_DOC` names stadium/unpiped/quoting. Re-run
`verify_mermaid_svg_transforms.py`, `verify_markdown_mermaid_transforms.py`,
`verify_pipeline_widget.py`. Full `tests/verify/` sweep. No browser
launch needed (headless `QT_QPA_PLATFORM=offscreen`, matching the
feedback's own reproduction method).

## Status

Implemented as planned. One adjustment found during verification: the
first draft of the new "Supported Mermaid subset" section in
`tempui-markdown.md` named `desk.mermaid` and `src/desk/mermaid.py`
directly -- `verify_tempui_doc_versioning.py`'s own
`test_no_doc_mentions_desk_repo_material` correctly caught this (the
tempui doc set is copied into arbitrary downstream projects, which have
no such file); reworded to describe the behavior without naming Desk's
own internal module/path.

Verified: the new `verify_mermaid_parser_grammar.py` (27 checks --
direct `parse()` calls covering stadium, all four unpiped operator
families including the negative-lookahead disambiguation between
dotted-open and dotted-arrow, quoted labels for all five shapes
including one combining both of a shape's own delimiter characters, an
empty quoted label falling back to the node id, a rendering smoke test,
and doc/changelog checks), run twice for flakiness (deterministic, no
Qt event timing involved). Re-ran `verify_mermaid_svg_transforms.py`,
`verify_markdown_mermaid_transforms.py`, `verify_pipeline_widget.py`,
`verify_tempui_doc_versioning.py`. Full `tests/verify/` sweep (159
scripts) passes. Browser launch not needed (headless, matching the
feedback's own reproduction method).

The cited feedback file stays in `../FEEDBACK/` -- TODO `9fe03a1`
(splitting the Markdown widget's Mermaid fallback message) also cites
it and is still open.
