# TempUI DSL: DiscussParkingLotItem

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
just covers the `DiscussParkingLotItem` keyword.

For having Desk kick off a **brand-new** `claude` session specifically
to discuss one item from this project's own `PARKINGLOT.md` (a parked,
not-yet-scoped idea or open question) -- rather than continuing the
current conversation, or expecting the current session to context
-switch onto it.

- The first line is `DiscussParkingLotItem <label>` — `label` is only
  used for the notification text, never sent to the new session.
- The next line is `Line <N>` — the 1-indexed line number, in the
  *current* `PARKINGLOT.md`, where the item you want discussed starts
  (its leading `- **Title**` bullet). Write the **line number**, not
  the item's own text — the new session reads `PARKINGLOT.md` itself to
  get the item's current, full text, rather than being handed a copy of
  it up front. (Don't paste the item's text into this file at all; the
  launch prompt built from a bare line number is short and reliable,
  where splicing in arbitrary, unbounded item text into the new
  session's launch command has caused real launch failures.)

Example:

```
DiscussParkingLotItem A way to end a claude widget's session
Line 533
```

Clicking the resulting notification places a **new** Claude (Desk) widget
with a fresh session (not the one that created this file) — its
initial prompt is the same "you're embedded in Desk" instructions
every Claude (Desk) widget gets, plus an instruction to read that line of
`PARKINGLOT.md` and discuss the item found there, **in this same new
session** (it's told explicitly not to kick off yet another new Desk
discussion of its own, e.g. by writing another `DiscussParkingLotItem`
file, unless the user actually asks it to). This is a one-shot trigger,
not a live-synced document like `Scratch` — there's no `Answer` line,
and once the new session starts there's nothing more Desk does with
this file.
