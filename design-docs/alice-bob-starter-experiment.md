# Desk — The Alice/Bob/Starter Experiment

A worked example of the event mediator message channel
(`desk.event_mediator`, TODO `6f9c51b`) built directly in this project's
own Desk, using nothing but the Bridge API's `events.*` calls — three
tempui-DSL-defined (`DefineWidget`) widgets passing a number back and
forth with no direct knowledge of each other. Kept here as documentation
of the pattern and as a concrete regression case (it's what surfaced
TODO `f693275`'s Bridge API custom-widget capability-resolution bug);
the widgets themselves are **not** checked into source control (see
[Where the widgets actually live](#where-the-widgets-actually-live)
below).

## What it is

Three `DefineWidget` tempui widgets (see `tempui-custom-widgets.md`, not
`widgets/`-directory Python widgets):

- **Alice** and **Bob** each subscribe to one event name,
  `a_and_b.number`, via `desk.events.subscribe(["a_and_b.number"])` and
  `desk.events.onMessage(...)`.
- **Starter** has a single button that publishes the seed event:
  `desk.events.publish("a_and_b.number", { number: 0 })`.

## The rule

On receiving `a_and_b.number` with an integer `number` payload less
than 10, react by publishing `a_and_b.number` again with `number + 1`.

- **Alice** applies this rule unconditionally (any integer `< 10`).
- **Bob** applies an *additional* condition: `number` must also be
  positive (`> 0`).

## Why Bob's extra condition exists

The event mediator excludes only the **sender** of a publish from
receiving it back — every *other* current subscriber still gets it.
Starter is neither Alice nor Bob, so when Starter publishes the seed
`0`, **both** Alice and Bob receive it (neither is the sender).

Without Bob's positive-only filter, both would react to `0` — Alice
publishing `1` *and* Bob publishing `1`, a duplicate branch that breaks
the intended single back-and-forth chain. Restricting Bob to positive
integers means only Alice ever reacts to the seed event; from `1`
onward, Alice and Bob really are each other's only other subscriber
(the sender-exclusion rule then does all the alternating work by
itself), so the chain stays a single line.

This is the general lesson worth taking from the specific example: a
publish reaches *every* other subscriber, not "whichever one you had in
mind" — a widget reacting to a broadcast needs its own filtering logic
whenever a given message name might legitimately arrive from more than
one source, sender-exclusion alone only rules out one specific sender
at a time.

## The resulting chain

```
Starter --0--> (Alice reacts, Bob does not: 0 is not > 0)
Alice   --1--> (Bob reacts)
Bob     --2--> (Alice reacts)
Alice   --3--> (Bob reacts)
...
Bob     --10-> (neither reacts: 10 is not < 10 — chain stops here)
```

Every integer 1 through 10 is published exactly once, alternating
Alice/Bob, with no duplicate branch — confirmed directly (via the real
Bridge API, not just the widgets' own JS) while building this.

## Declaring the `events` capability

Each of the three `DefineWidget` files includes:

```
Capability	events
```

right after its `Size` line. This is TODO `f693275`'s addition to the
`DefineWidget` DSL — without declaring the matching capability, calling
`desk.events.*` (or any other capability-gated Bridge call) from a
`DefineWidget` widget fails with a `403`. This is also the trio that
surfaced TODO `f693275`'s actual bug: before that fix, the Bridge API
couldn't resolve a tempui-DSL-defined custom widget for *any*
capability check at all (a `400 Unknown widget id`, not a `403`) — if a
`DefineWidget` widget you've built hits that exact error, it's very
likely this same, now-fixed gap (check the Desk version you're running
actually includes TODO `f693275`, since this fix only takes effect on a
restart).

## Where the widgets actually live

`DefineWidget` widget definitions are tempui files living in a Desk
directory's own `.desk_temp/` — per-directory, gitignored runtime
content, the same way a `.desk` file itself is (see
`design-docs/architecture.md`'s Desk Model). There is no checked-in
copy of Alice/Bob/Starter's exact HTML in this repository; this
document describes the pattern and behavior, not a specific artifact to
diff against. To build your own version, see `tempui-custom-widgets.md`
(`.desk_temp/tempui-custom-widgets.md` in any provisioned Desk
directory) for the full `DefineWidget` DSL, including the `Capability`
line and the "Sending and receiving named messages" section covering
`desk.events.*` in full.
