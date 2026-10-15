# From line-patching to a grammar-defined, AST-driven live-code pane

**Status:** open; direction decided 2026-10-15 (recorded below), pressure-test
against the raycaster formula DSL starting now. Supersedes
`line-patch-primitive.md` (kept as a historical record of the narrower framing
this grew out of) and resolves/unifies open questions 1 and 4 of
`dsl-for-agent-widgets.md`.

## The reframing

`line-patch-primitive.md` treated `world-timelines`'s `wt.dsl` + `query-editor`
pair as "a text blob plus a regex-based find/replace/insert/delete helper" and
asked how to formalize that into a declared-field-to-bound-control primitive.
That framing is too narrow. What `query-editor` actually is, in purpose, is a
small version of what *any* live-code tool or IDE editor pane already does:
continuously (re-)parse the text being edited into a structured
representation, and render, validate, and suggest from *that* structure rather
than from scattered regex matches over raw text. Parser-generation-from-a-
grammar is well-trodden ground — this DSL's parsing needs are modest compared
to a general-purpose programming language, so there's no need to invent new
techniques, just to apply existing ones Desk hasn't used for this purpose yet.

The most useful thing to build, inspired by this case study, isn't a
line-patch helper — it's **a live-code pane backed by machinery that builds an
AST from source text given a declared grammar**, with every other view (a
structured-fields panel, a rendered visualization, an error list) rendered
*from* that AST rather than from independently-parsed fragments of the same
text.

## Why this generalizes well beyond `wt.dsl`

Pulling on this thread and re-reading `draw-with-desk`'s raycaster DSL
directly (see `widget-case-studies.md`'s addendum to the `raycaster-formula`
write-up for full citations) turned up that `wt.dsl`'s flat `key: value` lines
are the *simplest* of three independently hand-rolled grammars already
sitting in just one project family:

1. **`wt.dsl`** (`world-timelines`) — flat lines, regex-matched. The case
   `line-patch-primitive.md` focused on exclusively.
2. **`parseCameraText`/`parseObjectsText`** (`raycaster-dsl.ts`) — a real
   line-oriented keyword grammar (`scene <id>`, `camera <x,y,z> [<x,y,z>]`,
   `montecarlo <N>`...), each line tokenized and validated per keyword, with
   errors tagged by line number.
3. **`FormulaSyntaxChecker`** (same file) — a genuine tokenizer feeding a real
   recursive-descent expression parser (precedence, parens, a vector literal
   syntax, dotted component access, mode-scoped variable names). Its own
   comment says it "exactly mirrors `main.py`'s own `_FormulaParser`" — **this
   grammar is hand-written twice, once in TypeScript and once in Python**,
   with nothing but developer discipline keeping the two in sync.

Three independently-reinvented parsers in one project alone, with the richest
one duplicated across two languages. A shared grammar-to-parser engine would
subsume all three tiers (a line-oriented record grammar and a flat-field
grammar are both just simple special cases of a general grammar), and would
have let the formula grammar be declared once and shared, rather than
hand-written twice with a standing drift risk.

## Unifying with the interactive-Mermaid thread

This also resolves open question 4 of `dsl-for-agent-widgets.md`, not just
question 1. An AST with **source-position information attached to every
node** is exactly the backbone the interactive-Mermaid experiment needs too:
click a rendered node → look up its source span → highlight/edit that part of
the text; edit the text → reparse → the AST changes → re-render the affected
nodes. Building the grammar/AST engine as a standalone, UI-agnostic piece
means a live DSL-editor pane and a clickable Mermaid diagram become two
different *renderers* over the same underlying engine, rather than two
separate pieces of infrastructure solving the same underlying problem twice —
exactly the kind of duplication this whole investigation keeps finding and
arguing against.

## Decision: a grammar-definition DSL compiled into a generated parser

Two real options were on the table for how the grammar itself gets expressed:

- **Parser combinators** — small, composable parsing functions assembled by
  hand into a parser. No new textual notation, no separate compile/generation
  step, and `FormulaSyntaxChecker` already proves that hand-writing a
  recursive-descent parser directly, with no generator at all, is perfectly
  viable at this grammar's actual scale. This is the more pragmatic choice,
  and the one that best fits `CLAUDE.md`'s "avoid adding dependencies, prefer
  bespoke solutions" with the least new machinery.
- **A declarative grammar-definition DSL, compiled into a generated parser** —
  more up-front machinery: a notation for describing a grammar, plus a
  generator that turns a grammar description into parsing code (or parse
  tables). More work than combinators for this problem in isolation.

**Decided: the grammar-definition-DSL-plus-generator path, deliberately,
despite combinators being the more pragmatic choice for this problem alone.**
The stated reasoning (recorded here rather than just the outcome, so a future
reader doesn't mistake this for "the generator was obviously the right
engineering call"): this investigation is also in service of the project
owner's own broader, separate interest in DSL design as a subject in its own
right, and building a real declarative grammar-definition language is more
directly in line with that broader goal than a pragmatic combinator library
would be — worth the extra up-front cost here specifically because the cost
buys something valuable beyond this one widget-UX problem. This is an
explicit, considered trade-off, not an oversight; a future reader revisiting
"why not just use combinators, that was clearly less work" should know the
answer was already asked and answered on purpose.

## What this decision requires of the engine

Carried over directly from the reframing above, now firm requirements rather
than open questions:

- **Source-position tracking per AST node is a hard requirement, not an
  add-later feature.** It's needed for both the live-pane use case (showing an
  error at the right spot in the raw text) and the Mermaid use case
  (click-to-source). Retrofitting position tracking into a parser/generator
  after the fact tends to be painful — design it in from the start.
- **Error recovery should match the scope all three existing hand-rolled
  parsers already settle on independently, without having coordinated with
  each other**: recover at statement/line boundaries, fail one
  line/statement without taking down the rest of the parse (`parseCameraText`'s
  per-line try/catch, tagging each error with its own line number, is the
  clearest existing example of this). Full incremental, error-tolerant
  parsing at the expression level (Tree-sitter/Lezer-style) is a much larger
  undertaking and isn't motivated by anything found in the case studies so
  far — out of scope unless a real need for it shows up.
- **A concrete grammar-definition notation still needs to be chosen** (an
  EBNF-like or PEG-like surface syntax are the obvious candidates) and a
  decision made about where the generator runs: a build-time step only (like
  `tsc`/`build_widget.py` today), or something invokable at runtime too (e.g.
  so an agent or a widget could define a small grammar on the fly without a
  separate compile step). Not yet decided — the formula-DSL pressure test
  below should surface a real opinion on this rather than deciding it in the
  abstract.

## Next: pressure-test against the formula DSL

The formula grammar (`FormulaSyntaxChecker` in `raycaster-dsl.ts`) is the
richest real grammar found in the case studies, and the one with the clearest
existing "ground truth" to check a new engine's output against: a real,
working, independently-written hand-rolled parser already exists for the exact
same grammar (in two languages, no less), so a new generated parser's
acceptance/rejection behavior can be checked directly against it rather than
against an abstract spec. Starting here next, scoped small: express the
formula grammar in the chosen grammar-definition notation, generate a parser
from it, and confirm it accepts/rejects the same inputs
`FormulaSyntaxChecker` does, with source positions attached to every node.

## Related

`dsl-for-agent-widgets.md` (the overview doc this resolves open questions 1
and 4 of), `widget-case-studies.md` (the `raycaster-formula` addendum this doc
is built on), `line-patch-primitive.md` (the superseded narrower framing),
`investigations/app_structure_dsl_design.md` (the sibling investigation about
multi-widget app *structure* rather than one widget's *content*).
