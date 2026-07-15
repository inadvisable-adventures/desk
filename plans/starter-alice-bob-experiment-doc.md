# COMPLETED: Document the Alice/Bob/Starter experiment

TODO `1e75140`.

## Summary

`Alice`, `Bob`, and `Starter` (built live during TODO `6f9c51b`'s event
mediator work, then unblocked by TODO `f693275`'s Bridge API
custom-widget capability fix) are the first real, end-to-end exercise
of the event mediator message channel — three tempui-DSL-defined
(`DefineWidget`) widgets that ping-pong a number back and forth purely
over `desk.events.*`, with no direct knowledge of each other. Worth
writing up as a `design-docs/` document: it's a concrete worked example
of the mediator pattern in practice, a real regression case for the
capability-resolution fix, and useful prior art for anyone building
their own `DefineWidget` widget against the events channel.

## Design

New `design-docs/alice-bob-starter-experiment.md`, covering:

- **What it is**: three `DefineWidget` tempui widgets (not
  `widgets/`-directory Python widgets) demonstrating
  `desk.events.subscribe/publish/onMessage`.
- **The rule**: on receiving `a_and_b.number` with an integer payload
  `< 10`, publish it back incremented by 1. Alice applies this
  unconditionally; Bob additionally requires the number be positive
  (`> 0`).
- **Why Bob's extra condition exists**: `Starter`'s button publishes
  the seed event with `{number: 0}`. Since the mediator only excludes
  the *sender* from its own publish (not other subscribers), and
  neither Alice nor Bob is the sender of Starter's event, *both* of
  them receive `0` — without Bob's positive-only filter, both would
  react to it and publish a duplicate `1`, breaking the clean single
  -chain alternation. This is the concrete, worked illustration of a
  general fact about the mediator worth documenting on its own: a
  publish reaches every *other* subscriber, not just "the intended
  one," so a widget reacting to a broadcast needs its own filtering
  logic if a given message might legitimately come from more than one
  source.
- **The resulting chain**: `Starter` → `0` → Alice reacts → `1` → Bob
  reacts → `2` → ... → `10`, where the chain stops (neither reacts to
  `10`, since it's not `< 10`).
- **How they're built**: each is a self-contained HTML document (base64
  -encoded into a `DefineWidget` tempui file, per
  `.desk_temp/tempui-custom-widgets.md`), declaring the `events`
  Bridge API capability via the `Capability` DSL line TODO `f693275`
  added — called out explicitly, since a `DefineWidget` widget calling
  `events.*` (or any other capability-gated Bridge call) without
  declaring the matching `Capability` line 403s.
- **Regression relevance**: this exact trio is what surfaced TODO
  `f693275`'s bug (a tempui-DSL-defined custom widget couldn't resolve
  for *any* Bridge capability check, `events` included) — noted as a
  pointer for anyone debugging a similar "Unknown widget id" failure
  from their own `DefineWidget` widget.
- A short "try it yourself" pointer: the actual widget definitions live
  as tempui files in each Desk directory's own (gitignored) `.desk_temp/`,
  not in source control — this doc describes the pattern/behavior, not
  a checked-in copy of the exact HTML (which is disposable, per
  -Desk-directory content, the same way no other tempui-DSL example in
  this repo is checked in either).

## Affected files

- `design-docs/alice-bob-starter-experiment.md` (new).

## Verification

Read-only/documentation change — no code paths to exercise. Confirmed
the document accurately describes the actual, currently-live widget
behavior by re-reading the real `.desk_temp/` `DefineWidget` files'
decoded HTML (this project's own current Desk directory) rather than
relying on memory of what was built earlier in the session.

## Status

Implemented as designed above:
`design-docs/alice-bob-starter-experiment.md` written, covering what
the three widgets are, the reaction rule (Alice unconditional, Bob
positive-only), why Bob's extra condition is necessary (both Alice and
Bob receive Starter's seed `0` since neither is its sender —
sender-exclusion only rules out the one specific sender, not every
other subscriber), the resulting 0→10 chain, the `Capability events`
DSL line each widget declares (TODO `f693275`), that trio's role in
surfacing that TODO's bug, and a pointer to where `DefineWidget`
widgets actually live (a Desk directory's own gitignored `.desk_temp/`,
not source control).

Re-read the actual, currently-live `.desk_temp/` `DefineWidget` files
(this project's own Desk directory) before writing, confirming all
three still declare `capabilities=['events']` and their stated sizes,
so the document describes the real, current deployed behavior rather
than a stale memory of what was built earlier in the session.
