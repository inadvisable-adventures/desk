# Pipe-chained verb DSL: syntax and semantics (TODO `765bd2a`) (COMPLETED)

## Summary

This item's own scope is explicitly the *language* -- grammar, verb/
argument shape, how values flow between stages, the escape hatch's own
denotation, and error/partial-failure semantics -- **not** how an
instance of it gets delivered to Desk (a `Job`/`DeskProc` tempui file's
`Script` line, an MCP tool argument via TODO `a762501`, or anything
else), and explicitly not implementation ("Not designed in full or
planned yet -- intentionally left unplanned per explicit instruction
not to implement yet"). This plan **is** the deliverable: a complete,
self-consistent language spec, resolving every "open, undecided
question" the TODO item lists, each with its own stated rationale so a
later reader can revisit a specific call rather than re-litigate the
whole design. No code is written as part of this item -- see
"Affected files" and "Verification" below.

A future TODO item (not this one) picks a transport, writes an actual
parser/interpreter (`src/desk/pipeline_dsl.py`, by the naming
convention this plan assumes throughout), and wires up a real verb
catalog's backing implementations (most likely thin wrappers over the
existing `deskproc.*` methods and/or `a762501`'s `desk_*` MCP tools --
see "Illustrative starter verb catalog" below, which is deliberately
non-binding).

## Affected files

None. This item produces only this plan file (the design itself) and
its `TODO.md` completion note -- no source, test, or doc-content
changes. (Contrast with a normal plan's "Affected files" list, which
names what a later *implementation* commit touches; there is no
implementation commit for this item.)

## The design

### 1. Grammar

```
pipeline    ::= stage ("|" stage)*
stage       ::= py_stage | verb_stage
py_stage    ::= "py:" base64_text            ; no internal whitespace
verb_stage  ::= verb_name (WS argument)*
verb_name   ::= identifier from the current verb registry (Sec. 4)
argument    ::= shell-quoted token (Sec. 2)
```

A `pipeline` is one string, top to bottom left to right, `|`-delimited.
Leading/trailing whitespace around each `|` is insignificant. There is
no line-continuation, no comments, no variables/bindings beyond the
implicit piped value (Sec. 3) -- this is deliberately a small
expression language, not a scripting language; anything that needs
real control flow, loops, or named intermediate values belongs in a
`py:` stage (Sec. 5) instead of being bolted onto the pipeline syntax
itself.

**Splitting a pipeline string into stages** must respect quoting --
`reveal_widget 'a | b'` is one stage with one argument containing a
literal `|`, not two stages. The precise algorithm: tokenize the whole
pipeline string with `shlex.shlex(text, posix=True)` configured with
`whitespace_split = True` and `|` added to `wordchars`'s complement (a
punctuation character, not folded into surrounding word tokens) --
equivalently, drive `shlex.shlex` token-by-token and start a new stage
each time an unquoted, standalone `|` token is produced. `py:` stages
never contain whitespace or `|` (base64's alphabet has neither), so
they always tokenize as exactly one token and are recognized by their
literal `py:` prefix before general verb-stage parsing runs.

### 2. Argument parsing -- shell-style, not the tempui DSL's "rest of
   the line is one opaque value" convention

The TODO item explicitly notes this DSL need not inherit the tempui
keyword convention (`Question <text>`, `Option <text>`, ...) where
everything after the keyword is a single natural-language string --
that convention exists because tempui values are prose (a question, an
answer); this DSL's arguments are structured, positional, and often
more than one per verb (`screenshot_widget abc123 shots/x.png` is two
arguments, not one). **Decision:** split each verb stage's text after
the verb name with `shlex.split(rest, posix=True)` -- ordinary
shell-style quoting (`screenshot_widget abc123 "shots/with spaces.png"`),
already a familiar convention elsewhere in this codebase
(`widgets/claude/widget.py`'s own `shlex.quote`/PTY-command
construction).

**Type coercion:** a verb is just a plain Python function (Sec. 4);
its parameters may be annotated `str`/`int`/`float`/`bool`. Before
calling a verb, each parsed string argument is coerced to its
parameter's annotation (`int(x)`, `float(x)`, `bool` via a
case-insensitive `{"true": True, "false": False}` lookup -- not
Python's own truthy-any-nonempty-string `bool(x)`, which would make
`bool("false")` wrongly `True`); an unannotated parameter (or one
annotated `str`) is passed the raw string. This is intentionally a
small, ad hoc primitive-only coercion table, **not** a reuse of
`desk.schema_types`' full type-expression parser (`parse_type_expression`/
`coerce`, used by `desk.state.set`'s `type_hint`) -- that parser exists
for rich schema strings (`"list<string>"`, structured records); every
verb argument here is a single shell token, so the extra generality
would be unused complexity for this DSL specifically. A coercion
failure (`int("abc")`) is that stage's own runtime failure (Sec. 6),
not a separate error category -- see Sec. 6's "parse-time vs. runtime
errors" split.

Wrong argument count (too few/many for the verb's signature) is also a
per-stage runtime failure (a `TypeError` from the underlying Python
call), not validated ahead of time -- consistent with the same
parse-time/runtime split.

### 3. Value flow between stages

**Every verb function's first positional parameter is the previous
stage's output** (its "piped value"), always, even when a given verb
doesn't use it (name it `_` and ignore it in that case) -- one uniform
calling convention (`fn(piped_value, *parsed_args)`) that needs no
per-verb introspection to know whether it "wants" the piped value. The
first stage in a pipeline receives `None` as its piped value.

**Values pass as real Python objects, never forced through a string
round-trip**, per the TODO item's explicit "do not convert values into
strings needlessly" instruction -- a `dict`, `list`, `bool`, or raw
`bytes` returned by one stage is handed directly to the next stage's
call as the same in-memory object, since a pipeline evaluates entirely
in-process (a `functools.reduce`-shaped call chain under the syntax,
not literal OS pipes/subprocesses). This only holds within one
pipeline's own execution; see Sec. 4's return-shape convention for how
a verb crosses an actual process/file boundary when it needs to (e.g.
a screenshot's PNG bytes).

### 4. Verb registry and return-shape convention

**Decision: a single fixed, curated built-in catalog, not an
extensible/plugin registry.** The TODO item raises "something a
widget/domain package could extend?" as an open question; this plan
resolves it against extensibility, for now -- nothing in the item's
own "Suggested direction" examples needs one, and designing an
extension mechanism speculatively (who registers a verb, from where,
with what trust level, name-collision handling) is exactly the kind of
work-for-a-hypothetical-future-requirement this project's own
`CLAUDE.md` says to avoid. A real need for widget-contributed verbs is
a clean, separate future TODO with its own trust/API-surface design;
bolting it onto this one now would be premature. A verb registry is
therefore just `VERB_REGISTRY: dict[str, Callable]` in one module, a
plain lookup with no discovery mechanism.

**Return-shape convention:** a built-in verb's own Python function may
return any JSON-serializable value, but a verb that has a natural
success/failure outcome (mirroring `deskproc.reveal_widget`/
`screenshot_widget`'s own existing `-> bool`) should return a `dict`
carrying a literal `"ok"` key (e.g. `{"ok": False}`, or `{"ok": True,
"path": "shots/x.png"}`) rather than a bare `bool`, specifically so:
- downstream stages can consistently extract fields from a dict
  (`py:`-stage code doing `piped["path"]`, say) instead of some verbs
  returning bare scalars and others returning dicts with no fixed
  shape;
- the pipeline runtime's own failure detection (Sec. 6) has one
  unambiguous signal (`isinstance(output, dict) and output.get("ok")
  is False`) that doesn't accidentally treat an ordinary falsy value
  (an empty list, `0`, `False` returned *as data* by some other kind of
  verb) as a pipeline failure.
A verb with no natural success/failure concept (a pure transform) just
returns its value directly -- the `"ok"`-dict convention is opt-in,
only for verbs where "did this actually do the thing" is itself part
of what the next stage, or the pipeline's own caller, needs to know.

**Crossing a process/file boundary:** per the TODO item's "use temp
files as makes sense" guidance, a verb whose natural output is large,
binary, or needs to be opened by something outside the pipeline itself
(a screenshot's PNG bytes, handed to the Image Viewer) takes an
explicit destination-path argument and returns a small descriptor dict
(`{"ok": True, "path": ...}`), the same shape
`deskproc.screenshot_widget(instance_id, path)` already established --
this is a verb-authoring convention, not a DSL mechanic, so it's
documented here for consistency but isn't itself part of the grammar.

#### Illustrative starter verb catalog (non-binding)

Grounding the abstract rules above against real, already-existing
capabilities -- **not** a commitment about which verbs exist first or
how they're implemented; a verb's own backing implementation (Bridge
API call, `deskproc.*`, a direct `desk.shell.window` call, a future
`a762501` MCP tool, ...) is an implementation detail of *that verb*,
entirely outside this language-design item's scope:

| verb | mirrors | signature | return |
|---|---|---|---|
| `reveal_widget` | `deskproc.reveal_widget` | `(_, instance_id: str)` | `{"ok": bool}` |
| `screenshot_widget` | `deskproc.screenshot_widget` | `(_, instance_id: str, path: str)` | `{"ok": bool, "path": str}` |
| `screenshot_desk` | `deskproc.screenshot_desk` | `(_, path: str)` | `{"ok": bool, "path": str}` |
| `list_widget_instances` | `deskproc.list_widget_instances` | `(_)` | `list[dict]` |
| `open_image` | (new -- no existing equivalent) | `(piped: dict)` | `{"ok": bool}` |

`open_image`'s example usage (from the TODO item's own suggested
direction) shows the "consumes only the piped value, no plain args of
its own" shape: `screenshot_widget abc123 shots/x.png | open_image`
reads `piped["path"]` from `screenshot_widget`'s own return dict.

### 5. The escape hatch: `py:<base64>`

A stage written as `py:` immediately followed (no separating
whitespace) by base64 text (`base64.b64decode(text.encode("ascii"),
validate=True).decode("utf-8")`, the same decode call
`desk_proc.py`/`jobs.py`/`custom_widgets.py` already use for their own
`Script`/`Html` lines) is a single Python **expression**, not a
script -- one `eval()` call, not `exec()`. Resolving "a single
expression or function" (the TODO item's own phrasing) into one
concrete rule:

1. `eval()` the decoded source in a fixed namespace (builtins only --
   no automatic `deskproc`/Bridge-API-style injected object; a `py:`
   stage that needs to call back into Desk should be expressed as an
   ordinary verb stage instead, keeping this escape hatch limited to
   local, functional data manipulation, which is what it's for).
2. If the result is callable, call it with exactly one argument -- the
   piped value -- and *that* return value becomes the stage's output
   (covers the "function" half: `py:<base64 of "lambda instances:
   [i for i in instances if i['kind'] == 'editor']">`).
3. Otherwise, the evaluated value itself is the stage's output
   directly, and the piped value is ignored for this stage (covers the
   "expression" half -- a `py:` stage as a pipeline's first stage,
   producing a constant/computed starting value with nothing to pipe
   in yet).

This single eval-then-maybe-call rule needs no separate stage-syntax
variant for "expression" vs. "function" -- which one it is falls out
of whether the evaluated value happens to be callable.

### 6. Error / partial-failure semantics

**Parse-time vs. runtime errors.** Anything structural -- an unknown
verb name, a malformed `py:` prefix (bad base64), unbalanced quoting
in the shlex split -- is validated for the *entire* pipeline before any
stage runs, and raises immediately (a `ValueError`), so a typo never
causes partial side effects. Everything else (a coercion failure, wrong
argument count, a verb's own logic raising, an escape-hatch `eval()`
raising) is a **per-stage runtime failure**, captured in the structured
result below rather than propagating as a raw exception to the
pipeline's caller.

**Execution is fail-fast:** the first stage whose call raises, or
(Sec. 4) returns an "ok"-dict with `"ok": False`, stops the pipeline
right there -- no further stages are attempted. Continuing past a
failed stage would just feed a later stage an undefined/`None` piped
value it almost certainly can't use meaningfully (see the TODO item's
own example: `screenshot_widget`'s output is exactly what `open_image`
depends on).

**Result contract**, returned by running any pipeline (this is the
"structured per-stage result value, at minimum" the TODO item asks
for) -- deliberately shaped like the existing `Job`/`DeskProc`/
Installed-Job `{"ok", "stdout", "stderr", "traceback"}` convention
(swapping `stdout`/`stderr` for a per-stage breakdown, since a
pipeline's real "output" is structured data, not captured console
text):

```python
{
    "ok": bool,              # True iff every stage completed without failing
    "stages": [
        {
            "stage": 1,                 # 1-based index
            "kind": "verb" | "py",
            "verb": "reveal_widget" | None,   # None for a "py" stage
            "args": ["abc123"] | None,        # None for a "py" stage
            "ok": bool,
            "output": <value> | None,   # None when ok is False
            "error": "<short message>" | None,  # None when ok is True
        },
        ...   # only stages actually attempted -- execution stops at the first failure
    ],
    "value": <final stage's output> | None,   # None if the pipeline didn't complete
    "traceback": "<full traceback text>" | None,  # set only if the failing stage raised
}
```

`error` is a short, human-readable message: `str(exc)` prefixed with
the exception's type name for a raised exception (e.g. `"ValueError:
invalid literal for int() with base 10: 'abc'"`), or a fixed message
("verb reported ok: false") for the "ok"-dict-`False` case. `traceback`
is the full `traceback.format_exc()` text, matching how `Job`/
`DeskProc`/Installed Jobs already surface a traceback -- present only
when the failing stage actually raised (not for an "ok": False result,
which isn't an exception).

## Worked examples

Walking each through the grammar/semantics above by hand (this plan's
own "verification" -- see below):

1. **The TODO item's own suggested example**, assuming the starter
   catalog above:
   ```
   reveal_widget abc123 | screenshot_widget abc123 shots/x.png | open_image
   ```
   Stage 1: `reveal_widget(None, "abc123")` -> `{"ok": True}`. Stage 2:
   `screenshot_widget({"ok": True}, "abc123", "shots/x.png")` (piped
   value ignored by this verb) -> `{"ok": True, "path":
   "shots/x.png"}`. Stage 3: `open_image({"ok": True, "path":
   "shots/x.png"})` reads `piped["path"]` -> `{"ok": True}`. Result:
   `{"ok": True, "stages": [...3 entries, all ok...], "value": {"ok":
   True}, "traceback": None}`.

2. **Escape hatch filtering a list**, showing the "function" half of
   Sec. 5's rule:
   ```
   list_widget_instances | py:<base64("lambda ws: [w for w in ws if w['kind'] == 'editor'])>
   ```
   Stage 1 -> `list[dict]` of every placed widget. Stage 2 evaluates to
   a `lambda`, which is callable, so it's called with stage 1's list
   and returns just the `"editor"`-kind entries.

3. **A stage that fails, showing fail-fast + the result contract**:
   ```
   reveal_widget does-not-exist | screenshot_widget does-not-exist shots/x.png
   ```
   Stage 1: `reveal_widget(None, "does-not-exist")` -> `{"ok": False}`
   (no matching instance -- mirrors `deskproc.reveal_widget`'s own
   documented "returns whether a matching instance was found"). Per
   Sec. 6 this counts as a stage failure even though nothing raised.
   Stage 2 never runs. Result: `{"ok": False, "stages": [{"stage": 1,
   "kind": "verb", "verb": "reveal_widget", "args":
   ["does-not-exist"], "ok": False, "output": None, "error": "verb
   reported ok: false"}], "value": None, "traceback": None}`.

## Key decisions (summary, with the "why" each lives in its own
   section above)

- Shell-style (`shlex`) multi-token arguments, not the tempui DSL's
  "rest of line is one value" convention -- Sec. 2.
- Primitive-only (`str`/`int`/`float`/`bool`) coercion via a verb's own
  parameter annotations, not the full `desk.schema_types` type
  -expression parser -- Sec. 2.
- Real in-process Python object passing between stages, never a string
  round-trip -- Sec. 3.
- Fixed built-in verb catalog, not an extensible/plugin registry, to
  avoid designing for a hypothetical future requirement -- Sec. 4.
- An opt-in `{"ok": ...}`-dict return convention for verbs with a
  natural success/failure outcome, used as the one unambiguous
  pipeline-failure signal alongside a raised exception -- Sec. 4.
- The escape hatch is `eval()`, never `exec()`, of one expression; a
  callable result is invoked with the piped value, a non-callable
  result is used as-is -- Sec. 5.
- Structural errors (unknown verb, malformed `py:`) are validated
  upfront and raise immediately; everything else is a per-stage
  runtime failure captured in a structured result -- Sec. 6.
- Fail-fast execution -- a failed stage stops the pipeline rather than
  feeding later stages an undefined value -- Sec. 6.
- The result contract mirrors `Job`/`DeskProc`/Installed Jobs'
  existing `{"ok", ..., "traceback"}` shape rather than inventing an
  unrelated one -- Sec. 6.

## Explicitly out of scope (per the TODO item itself)

- Which transport(s) carry a pipeline string to Desk (a tempui `Job`/
  `DeskProc` `Script` line, an `a762501` MCP tool argument, or
  anything else) -- a separate, later TODO, deliberately decoupled so
  the language comes out the same regardless.
- Writing the actual parser/interpreter -- this plan specifies it
  precisely enough to implement directly, but no such code is written
  here.
- Verb extensibility beyond the fixed built-in catalog (Sec. 4) --
  deferred as a distinct future design question, not decided against
  forever, just not designed now without a concrete need driving it.
- Backing implementations for the illustrative starter catalog (Sec.
  4) -- verb-by-verb implementation detail for whoever writes the
  interpreter.

## Verification

Not applicable in the usual "run `tests/verify/...`" sense -- this
item produces a design document, not executable code. This plan's own
"Worked examples" section is the verification: each example is walked
by hand against every rule in Secs. 1-6 to confirm the grammar and
semantics are actually self-consistent (no rule contradicts another,
every construct the TODO item's own suggested direction uses is
covered) rather than just individually plausible-sounding. A future
implementation TODO should turn these same worked examples into its
first `tests/verify/verify_pipeline_dsl.py` cases directly.
