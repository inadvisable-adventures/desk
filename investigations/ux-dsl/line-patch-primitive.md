# Expanding on open question 1: formalizing the line-patch primitive

> **Superseded, 2026-10-15 — see `grammar-ast-live-pane.md`.** A follow-on
> design conversation reframed this whole direction: the regex-based line-patch
> primitive sketched below turned out to be a special case of a bigger and more
> useful idea — a grammar-defined, AST-producing parser engine backing a live
> -code pane, which also subsumes the richer hand-rolled parsers already found
> in the raycaster DSL (not just `world-timelines`' flat lines) and unifies
> with the separate interactive-Mermaid thread. Kept below as a historical
> record of the narrower framing this started from — the evidence and
> reasoning in it are still accurate, just no longer the active direction.

Elaborates on `dsl-for-agent-widgets.md`'s open question 1 ("Formalize the
line-patch primitive already proven in the wild"). That doc states the question
in one paragraph; this one spells out what already exists, what's still
hand-written per field, and what "formalizing" it would actually look like, in
enough detail to prototype against later. Not a plan, not filed as a TODO item —
pre-design elaboration, same status as the rest of this investigation.

## What exists right now

`world-timelines/.desk_temp/widgets/_shared/shared.ts` treats `wt.dsl` as one
shared text blob — lines like `filter category: person, place` / `pin: id1,
id2` / `laneset continents`. Two generic helpers operate on it (see
`widget-case-studies.md`'s `world-timelines` section for the full citations):

```ts
setDslLine(dsl: string, pattern: RegExp, newLine: string | null): string
// finds the line matching `pattern`; replaces it, inserts newLine at the
// top if no match, or deletes the line entirely if newLine is null/empty
// (the "absence of the line = default value" convention used throughout
// this project's own wt.dsl grammar)

setCategoryLine(dsl, selectedCategories): string
// a thin specialization of the above, just for the category filter
```

`setDslLine` itself is genuinely grammar-agnostic — it doesn't know or care what
the pattern or line content mean. That part is real, working, reusable prior
art, and needs no further generalization.

## What's not generic: the part hand-rewritten per field

Every widget that wants to bind one field to one DSL line writes its own
version of three things: *what regex matches my line*, *how do I turn my value
into a line of text*, and *how do I parse the line back into my value*. For
example, `query-engine.ts`'s pin/unpin buttons hand-build their own regex and
template string (`` `pin: ${ids.join(', ')}` ``) and call `setDslLine` directly;
`category-picker.ts` does the analogous thing for categories via
`setCategoryLine`. There is no single place that declares "here is the `pin`
field, here is its shape" — that knowledge is re-derived, by hand, at each call
site, which is exactly the kind of incidental, easy-to-get-subtly-wrong detail
this whole investigation's hypothesis is about.

## What "formalizing" it would look like

Turn that implicit, scattered knowledge into one declared spec per field:

```ts
interface DslField<T> {
  pattern: RegExp;                    // matches this field's line
  parse: (line: string) => T;         // line text -> typed value
  serialize: (value: T) => string | null;  // typed value -> line text, or
                                       // null to omit the line (= default)
  default: T;
}

const PIN_FIELD: DslField<string[]> = {
  pattern: /^\s*pin\s*:/i,
  parse: (line) => line.split(":")[1].split(",").map((s) => s.trim()),
  serialize: (ids) => (ids.length ? `pin: ${ids.join(", ")}` : null),
  default: [],
};
```

...plus a generic binding helper built on top of the existing `setDslLine`
that any field declaration could use for free:

- `read(dsl, field)` — find the matching line (or fall back to `field.default`
  if absent) and parse it.
- `write(dsl, field, value)` — serialize `value` and patch the blob via the
  existing `setDslLine`.
- `watch(field, callback)` — ideally fires only when *this specific field's*
  derived value actually changed, rather than every widget re-parsing the
  *whole* blob on every `wt.dsl` change the way all of today's widgets do (fine
  at this project's current scale, but a sign the abstraction isn't factored
  per-field yet).

Done well, adding a new field stops requiring a new hand-written parse/
serialize function at all — just a declaration. This is the same shape
`app_dsl`'s existing "state slots" item already uses for plain JS variables
(name, type, default → generates a setter; see
`investigations/app_structure_dsl_design.md`'s "Full DSL inventory," item 4),
just retargeted at "one line inside a shared, human-editable text blob" instead
of "a plain variable" — which is what keeps the state inspectable/editable as
text rather than becoming an opaque object, the whole point of `wt.dsl` being a
DSL in the first place.

A further, more speculative step (not sketched in code here, since it's a
bigger leap): a declared field's *type* could also drive which control
auto-renders for it — e.g. a `DslField<string[]>` with a known closed set of
valid values could auto-generate the chip-row UI `category-picker.ts` hand-wrote,
rather than every new field needing its own hand-built picker widget too. That
would start closing the gap with UX principle 2 as well as principle 1, but is
a separate, larger piece of work layered on top of the binding primitive above,
not a prerequisite for it.

## Why this is worth doing

It's the one piece of real, working prior art found anywhere in this sweep for
"declare a field, get synced read/write for free" — but it's currently proven
by exactly one call site (`query-engine`'s pin/unpin buttons), and every other
field in `world-timelines` still gets its matching/serializing logic
hand-written from scratch. Generalizing it is comparatively cheap, since the
hard part (the generic find/replace/insert/delete-on-empty operation) already
exists and works — what's missing is the declarative layer on top of it. Doing
this would remove a real, recurring source of the "remember to do this right"
risk that caused `file-tree`'s `DeskConsole`/`DirectoryTreeView` sync failures
elsewhere in `widget-case-studies.md`: a field declared once, with one generic
binding helper enforcing read/write/watch, has no "hand-rolled it slightly
differently in the second widget" failure mode to fall into in the first place.

## Related

`dsl-for-agent-widgets.md` (open question 1, the short version this doc
expands on), `widget-case-studies.md` (`world-timelines`'s `query-editor`/
`query-engine`/`_shared/shared.ts` write-ups, the full citations for every
claim above), `investigations/app_structure_dsl_design.md` (`app_dsl`'s state
-slots item, the closest existing analog for "declared field -> generated
accessor," just for a plain variable rather than a DSL text line).
