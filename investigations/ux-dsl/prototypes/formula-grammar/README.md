# Pressure test: a declarative grammar for the raycaster formula DSL

See `../../grammar-ast-live-pane.md` for the full context and decision this
tests. Short version: `draw-with-desk`'s raycaster formula DSL already has a
real, independently hand-written tokenizer + recursive-descent syntax checker
(`oracle.ts`, copied verbatim from the real project). This directory declares
the same grammar in a dedicated `.peg` notation (`formula.peg`) instead,
compiles it with a small generic engine (`peg-engine.ts`), layers the same
semantic rules on top as a separate AST tree-walk (`semantic-check.ts`), and
checks the result agrees with the real hand-rolled checker on a battery of
valid/invalid formulas (`run-pressure-test.ts`).

## Running it

```sh
tsc -p .
node dist/run-pressure-test.js
```

Prints one `PASS`/`FAIL` line per case plus two direct checks that AST nodes
carry real source-text spans, then a final tally; exits non-zero if anything
failed. As of 2026-10-15: 27/27 passing.

## Files

- `peg-engine.ts` -- the generic PEG grammar-description parser + interpreter.
  Grammar-agnostic; nothing in here knows about formulas specifically.
- `formula.peg` -- the formula grammar, declared in that notation.
- `oracle.ts` -- ground truth: the real hand-rolled checker, copied verbatim.
- `semantic-check.ts` -- the "which names are allowed where" rules, as a
  tree-walk over the AST `peg-engine.ts` produces, deliberately kept separate
  from parsing.
- `run-pressure-test.ts` -- the comparison harness.
- `node-shims.d.ts` -- the handful of Node.js ambient declarations this needs,
  hand-written rather than pulling in `@types/node` as a dependency.

## What this did and didn't prove

Proved: the declarative-grammar-plus-generic-engine approach can express this
real grammar faithfully (same accept/reject behavior as the hand-rolled
version, one deliberately-noted divergence in *mechanism* only -- see
`semantic-check.ts`'s `checkName`), and the engine's AST nodes carry real,
checked source-position spans, which is the property this whole direction
was chosen for in the first place (see `grammar-ast-live-pane.md`'s "What this
decision requires of the engine").

Found, and worth keeping in mind for anyone extending this engine: writing
the grammar-*description* parser itself (`peg-engine.ts`'s `parseGrammarText`)
hit a real, non-obvious bug on the very first real grammar fed into it --
generic whitespace-skipping doesn't have a single correct behavior; it needs
to behave differently depending on whether the caller is hunting for "the
next real token, wherever it is" (safe to cross a newline into the next
rule's own header) or trying to decide "has the current rule's sequence
ended" (must NOT cross that same newline, or it silently absorbs the next
rule's name as one more term of the current one). See `peg-engine.ts`'s
`peekAtRuleBoundary` and the comment above it for the fix and the full
story -- a real example of exactly the kind of parsing subtlety this whole
investigation's premise says is "well-trodden ground," while also being a
genuine, specific thing to get right, not just hand-waved past.

Not yet attempted: error recovery beyond whole-line accept/reject (no
partial-parse tolerance tested), and nothing visual/pane-shaped yet -- this
was scoped to "does the grammar-to-AST engine work at all, with real source
positions," per `grammar-ast-live-pane.md`'s own stated next step. The live
-pane rendering and the Mermaid-interactivity unification are still ahead.
