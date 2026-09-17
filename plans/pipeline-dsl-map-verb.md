# Pipe-chained verb DSL: `map` verb (TODO `e4d73dc`)

## Summary

Adds a `map` stage to the pipe-chained verb DSL (TODO `63bfd42`,
`src/desk/pipeline_dsl.py`): `map +| verb1 | verb2 |+`. Everything
between the `+|`/`|+` delimiters is a full sub-pipeline, written in the
DSL's own existing grammar (verb stages, `py:` stages, and -- since
nothing about the grammar prevents it -- a nested `map` of its own).
`map` takes the previous stage's output, requires it to be a list (or
tuple, treated the same way -- see "Key design decisions"), runs the
sub-pipeline once per item with that item as the sub-pipeline's own
first piped value, and recombines the per-item results, in order, into
a new list as `map`'s own stage output.

This is additive to the existing grammar/interpreter, not a redesign --
Sections 1-6 of `plans/pipe-chained-verb-dsl.md` and the "Result
contract"/fail-fast semantics of `plans/pipe-chained-verb-dsl-
implementation.md` are unchanged for every stage kind that isn't `map`.

## Affected files

- **Modified: `src/desk/pipeline_dsl.py`** -- the tokenizer/grouping
  step gains map-aware nesting (Sec. "Grammar and tokenizing" below),
  `_ParsedStage` gains a `sub_stages` field for `kind == "map"`, the
  stage-execution loop (refactored into a reusable `_execute_stages`
  helper so a `map` stage can recursively call it once per item) gains
  a `map` branch.
- **Modified: `src/desk/shell/desk_mcp_server.py`** -- the
  `desk_run_pipeline` tool's own description string gains the `map`
  syntax, so an agent discovers it without needing to read source.
- **Modified: `src/desk/temp_ui.py`** -- bump `TEMPUI_DOC_VERSION` to
  45 with a matching `_NEW_FEATURES_DOC` entry (new agent-facing
  syntax on an existing MCP tool).
- **Modified: `tests/verify/verify_pipeline_dsl.py`** -- new coverage
  for `map` (grammar, nesting, fail-fast, the list/tuple acceptance
  rule, a real end-to-end run against the fake window).

## Grammar and tokenizing

### Why this needs more than the existing tokenizer

The existing tokenizer (`_tokenize`, Sec. 1 of `pipe-chained-verb-dsl.md`)
treats bare `|` as the only stage-separator punctuation. A naive
"split on every bare `|`" grouping pass would incorrectly slice a `map`
stage's own sub-pipeline apart at the top level:
`list_widget_instances | map +| reveal_widget | screenshot_widget abc |+`
would wrongly become three top-level stages instead of two. The `|`s
*inside* a `+| ... |+` span must stay with the `map` stage that owns
them; only genuinely top-level `|`s should split top-level stages.

### `+|`/`|+` are not new punctuation characters

Adding `+` to `shlex`'s own `punctuation_chars` (so `shlex` merges `+|`/
`|+` into single tokens itself) was considered and rejected: `shlex`
punctuation characters split on *every* occurrence, not just adjacent
runs at word boundaries -- confirmed directly (`shlex.shlex("...",
punctuation_chars="+|")` splits `arg+withplus` into three tokens,
`arg`/`+`/`withplus`). That would corrupt any existing verb argument or
`py:` base64 payload containing a literal `+` (base64's own alphabet
includes `+`) — a real regression, not a hypothetical one, since
`plans/pipe-chained-verb-dsl-implementation.md`'s own base64 handling
already exercises `+`/`/` bytes. `punctuation_chars` stays `"|"`, exactly
as before.

### Recognizing `+|`/`|+` at the stage-grouping step instead

`_tokenize`'s output already gives `+` and `|` as separate tokens
whenever they're whitespace-separated in the source text (confirmed:
`"map +| verb1 | verb2 |+"` tokenizes to `['map', '+', '|', 'verb1',
'|', 'verb2', '|', '+']`) -- and stays fused to adjacent word
characters otherwise (`"map+|verb1"` tokenizes to `['map+', '|',
'verb1']`, never producing a standalone `+`). So a standalone `+`
token immediately followed by a standalone `|` token, or vice versa,
only ever occurs at an intentional `+|`/`|+` boundary written with the
documented spacing -- never inside a fused word or an unspaced base64
payload.

The stage-grouping pass (replacing the old flat `_group_stages` with
`_group_top_level_stages`) recognizes these pairs *contextually*, not
globally, to avoid a second, narrower ambiguity: a `+` token
immediately followed by a `|` token only opens a map sub-pipeline when
it directly follows a `map` token that itself began a (sub-)stage --
tracked with two small pieces of scan state, `at_stage_start` (is the
next token in the verb-name position of some stage, top-level or
nested?) and `just_saw_map_keyword` (was the token just appended a
`map` keyword appearing at a stage-start position?). This means a
verb's own ordinary argument that happens to be `map` (e.g. `some_verb
map + | other_verb`, an argument literally spelled "map") is never
misread as a `map` stage, because `just_saw_map_keyword` is only set
when `map` itself occupied the stage's leading (verb-name) slot, not
merely the last-appended token. Verified by hand-tracing both this
case and the real nested-map case token-by-token (see "Verification"
below) before writing any code.

A `|` token immediately followed by a `+` token closes the
*innermost* currently-open map span (`map_depth -= 1`) unconditionally
-- no matching "was this `+` meant literally" ambiguity exists for
closes the way it does for opens, since a close only fires while
`map_depth > 0` (inside an already-open span) and single-character
-bracket depth-counting (no stack needed -- there is only one bracket
*type*) is suffient given properly balanced input; an unbalanced
`map_depth != 0` at the end of the scan raises `ValueError` immediately
(`"unmatched 'map +|' -- missing closing '|+'"`), the same "structural,
validated upfront" treatment Sec. 6 of the design plan already gives
unknown verbs and malformed `py:` prefixes.

A bare `|` token encountered while `map_depth > 0` (i.e., inside an
open span, and not part of a `|`+`+` close) is *kept in place* in the
current top-level stage's own flat token list, rather than splitting a
new top-level stage -- it's the sub-pipeline's own internal separator,
resolved when that `map` stage's inner tokens are recursively
re-grouped (see below).

**Known, deliberate limitation:** a bare `+` token immediately
followed by a bare `|` token *right after a literal `map` argument at a
stage-start position* always opens a map span -- there's no escape
syntax for "I really meant the literal argument `map` followed by a
separate `+` argument, then a new stage." Given `map` is a reserved
stage-leading keyword now (exactly like `py:` is a reserved stage
-leading prefix already), and no verb in the built-in catalog takes an
argument that could plausibly be the literal string `map`, this is
accepted as a documented restriction rather than solved with escaping
machinery a real use case hasn't asked for.

### Parsing a stage group

`_parse_stage_group(group, registry)` gains one more branch alongside
the existing `py:`-prefix and verb-name checks: `group[0] == "map"`
requires `group[1] == "+|"` and `group[-1] == "|+"` (otherwise
`ValueError("malformed map stage -- expected 'map +| ... |+'")`,
upfront); the tokens strictly between them (`group[2:-1]`) are
recursively parsed by the *same* `_parse_stages_from_tokens` used for
the outer pipeline (itself just `_group_top_level_stages` + a
per-group dispatch loop) -- nesting, including a `map` inside a `map`,
falls out for free rather than needing separate code, since the
grouping pass already tracks `map_depth` generally, not just
one-level-deep. An empty sub-pipeline (`map +||+`, no stages between
the delimiters) is `ValueError("map's sub-pipeline is empty")`,
upfront, same treatment as an empty top-level pipeline.

## Execution

`run_pipeline`'s existing per-stage loop is extracted, unchanged in
behavior, into `_execute_stages(stages, piped_value, registry) ->
dict` (the same result-contract dict Sec. 6 already specifies) so it
can be called recursively -- `run_pipeline` itself becomes `_parse_stages(text,
registry)` then `_execute_stages(stages, None, registry)`.

A `map`-kind stage's execution (`_run_map_stage`):

1. The piped value must be a `list` or `tuple` (see "Key design
   decisions" for treating both the same) -- anything else is a
   `TypeError` raised from this function, caught by the shared
   per-stage `try/except` in `_execute_stages` exactly like any other
   verb's own raised exception (Sec. 6's ordinary runtime-failure
   path -- no special case needed there).
2. For each item, in order, call `_execute_stages(stage.sub_stages,
   item, registry)` -- the item, not the outer pipeline's own
   original piped value or `None`, is what the sub-pipeline's first
   stage receives as *its* piped value, matching every other stage's
   "receives the previous stage's real output" rule (Sec. 3) applied
   one level down.
3. **Fail-fast, one level up:** if any item's sub-pipeline run doesn't
   succeed (`sub_result["ok"]` is `False`), immediately raise
   `RuntimeError(f"map item {index}: {failing_stage['error']}")` (where
   `failing_stage` is that sub-run's own last, failing stage entry) --
   this propagates out of `_run_map_stage` and is caught by
   `_execute_stages`'s own per-stage `try/except`, making the *whole*
   `map` stage a single failed stage in the outer pipeline's result,
   consistent with the base design's fail-fast philosophy (Sec. 6:
   "the first stage whose call raises ... stops the pipeline right
   there") rather than inventing a second, partial-results failure mode
   only `map` would have.
4. On full success, the recombined `list` of each item's own
   `sub_result["value"]`, in order, becomes `map`'s stage output --
   fed to whatever stage comes after `map` in the outer pipeline the
   same way any other stage's output is.

`map`'s own entry in the top-level result's `stages` list uses the
existing shape unchanged: `"kind": "map"`, `"verb": None`, `"args":
None` (matching how a `"py"`-kind entry already reports `None` for
both -- `map`'s real "argument" is the sub-pipeline, not a string
list), `"output"` is the recombined list on success, `"error"` is the
`RuntimeError`'s own message on failure. No new top-level result-schema
fields -- a failed `map` stage looks, from the outer pipeline's
perspective, exactly like any other failed stage; the *reason* just
happens to name which item and what went wrong underneath.

## Key design decisions

- **`map` is a reserved stage-leading keyword, not a registry entry.**
  It needs `stage.sub_stages` and the current `registry` for recursion
  -- shapes no plain `Callable` in `VERB_REGISTRY` has -- so it's
  dispatched structurally in `_parse_stage_group`/`_execute_stages`
  exactly the way the `py:` prefix already is, rather than being added
  to `VERB_REGISTRY` as a special-cased callable. This also means `map`
  can never be shadowed by a same-named registry entry, matching the
  existing precedent that `py:` isn't a "verb name" a registry could
  redefine either.
- **List and tuple both accepted as `map`'s input, output is always a
  `list`.** Every value flowing through this DSL is meant to be
  JSON-serializable (Sec. 3 of the design plan); JSON has exactly one
  sequence type. Accepting a Python `tuple` too (rather than only
  `list`) costs nothing and avoids a surprising failure for a verb that
  happens to return a tuple; always emitting a `list` back out avoids
  `map`'s own output shape depending on which one the input happened to
  be.
- **A failed item stops the whole `map` stage (and thus the whole outer
  pipeline), no partial results.** Considered returning `{"ok": False,
  "results": [...]}` with per-item outcomes instead. Rejected: it would
  give `map` its own bespoke, one-off failure shape nothing else in the
  language has, and silently produces a *shorter* list than the input
  on partial failure with no obvious signal besides carefully reading
  each item's own `ok` -- a likely source of a confused caller assuming
  the recombined list is complete when it isn't. Fail-fast with a clear
  "which item, which reason" message is the same contract every other
  stage already gives.
- **Nesting `map` inside `map` needs no special-casing** -- the
  grouping pass's `map_depth` counter and the parse/execute functions'
  own recursion both already generalize past one level; only the
  hand-traced ambiguity checks above are one-level-specific concerns
  (and were checked against a nested case directly, not assumed to
  generalize).

## Verification

`tests/verify/verify_pipeline_dsl.py`, extending the existing suite:

- **Grammar/tokenizing:** the exact `list_widget_instances | map +|
  reveal_widget | screenshot_widget abc |+ | after_verb` shape groups
  into the right three top-level stages (asserted via `run_pipeline`'s
  own `stages` output, not by reaching into private grouping
  internals); a `map` missing its `|+` raises `ValueError` upfront; an
  empty `map +||+` raises `ValueError` upfront; the "known limitation"
  case (`some_verb map + | other_verb`, a literal `map` argument *not*
  in stage-leading position) is confirmed to run as two ordinary
  stages, not a misparsed `map`.
- **Nesting:** a `map` containing a nested `map` runs correctly end
  -to-end against a small hand-built list-of-lists case with a plain
  `py:` verb doing the inner transform (no fake window needed for this
  one).
- **Value flow:** each sub-pipeline invocation receives its own item
  (not `None`, not the outer piped value) as its first stage's piped
  value -- checked with a custom recording verb.
- **Type acceptance:** a `list` and a `tuple` piped value both succeed
  and both produce a `list` back out; a non-sequence (e.g. a `dict` or
  `int`) piped value is a per-stage `TypeError` failure, not a crash.
- **Fail-fast:** one failing item (e.g. a sub-pipeline stage that
  itself returns `{"ok": False}`) fails the whole `map` stage, naming
  the failing item's index and reason in the outer stage's own `error`,
  with no partial `output`.
- **Real end-to-end run** against the existing `_FakeWindow`: `map`
  over a list of instance ids, each sub-pipeline calling
  `reveal_widget`, recombining into a list of `{"ok": ...}` dicts.

Full `tests/verify/` regression suite run afterward to confirm nothing
else regressed.
