# Development Process

This file describes the development process for this project.

## Design Docs

Design docs in `design-docs/` should be kept up-to-date as the system's architecture evolves. When a change affects the design, update the relevant design doc(s) and commit them together with the associated `TODO.md`, plan, and code changes, rather than as a separate, later commit.

## Learnings

`LEARNINGS.md` records unexpected corner cases, non-obvious library/API behavior, and mistakes worth not repeating. It's written for a future developer or agent working in this codebase — not a note-to-self — so an entry should stand on its own: what happened, why it's surprising, and what to do instead (or how to recognize it next time), not just "we hit bug X."

### What belongs here

- Something that violated a reasonable assumption (an API that doesn't behave the way its shape or name suggests).
- A root cause that took real investigation to find, especially if a plausible-looking fix would have been wrong.
- A mistake made once that's likely to be made again without a note, because it isn't discoverable just by reading the code.

### What doesn't

- Anything already evident from reading the code, its docstrings, or `design-docs/`.
- One-off typos or slips that don't reflect a real gap in understanding.

### Workflow

Add an entry as soon as something like this turns up — most often during verification/debugging (see "Working on TODO Items" step 5 below) — and commit it together with the change that surfaced it, the same way `design-docs/` updates are committed alongside their change rather than separately.

## Item IDs

TODO items are **not** numbered sequentially. Each item has a permanent, opaque id: 7 lowercase hex digits (e.g. `2c36b01`), generated once from the item's description when it's first added, and never recomputed or reassigned afterward — even if the item is later edited, reordered, or completed. Refer to an item as **"TODO `<id>`"** (e.g. "TODO 2c36b01") in commit messages, plan files, other TODO items, chat, etc.

**Priority is the item's physical position in `TODO.md`, top to bottom, full stop.** The id carries no ordering information whatsoever — it's just a stable handle for referring to the item. Don't infer priority, age, or anything else from an id's value.

### Generating an id for a new item

Run `python3 scripts/todo_item_ids.py new "<the item's description>"` and use the printed 7-hex-digit result as the item's id (`<id>. <description>`, replacing the old `N.` numbering style). If the description is shorter than 10 characters the script hashes a random string instead (a very short description alone doesn't hash well) — this is handled automatically, nothing extra to do.

## Planning

Before implementing any significant feature or change, a plan is written and stored in the `plans/` directory. Each TODO item in `TODO.md` gets its own plan file.

### Workflow

1. For each TODO item, create a plan file in `plans/` with a descriptive kebab-case filename (e.g., `plans/bake-layer.md`).
2. The plan should include:
   - A summary of what needs to be built
   - The affected files
   - A step-by-step implementation approach
   - Any key design decisions or tradeoffs
3. After writing a plan, add a note at the end of the corresponding TODO item in `TODO.md` in the form: `[planned: plan-name.md]` where `plan-name.md` is the filename (not the path) of the plan.
4. Commit the plan file and the updated `TODO.md` together.

## Working on TODO Items

TODO items in `TODO.md` are worked through in the order they are listed.

### Rules

- New TODO items may be added at any time, with or without an associated plan.
- A TODO item must have an associated plan before it is implemented.
- Work through items in listed order, skipping any marked `PENDING`.
- When a thought or potential TODO item surfaces during work on something else, add it to `PARKINGLOT.md` rather than interrupting the current task. Items in the parking lot are not prioritized or planned; move them to `TODO.md` when ready to act on them.

### Workflow

1. Take the first TODO item that is not marked `PENDING` (or if it is marked `PENDING`, check to see if related questions have been answered, if they have then take the item).
2. If the item lacks a plan, write one first (see [Planning](#planning) above).
3. If the item cannot be implemented without answers to open questions:
   a. Add a **Status** section at the end of the plan file describing what is blocked and why.
   b. Add the question(s) to `QUESTIONS.md`.
   c. Mark the TODO item as `PENDING` in `TODO.md`.
   d. If there are local changes beyond `QUESTIONS.md`, `TODO.md`, and the plan file, commit those other changes to a branch, note the branch name in the Status section of the plan file, then commit `QUESTIONS.md`, `TODO.md`, and the plan file.
   e. Move on to the next non-`PENDING` item.
4. Otherwise, implement the item according to its plan.
5. Verify the changes as described in the plan. If a step of the verification requires launching the browser, make a note in the plan that it was skipped.
6. Update the TODO.md to mark the item as `COMPLETED`.
7. Update the plan file to indicate in the title (not the filename) that the item is completed.
8. Commit the changes, TODO.md, and the plan file.

## Prioritizing TODO Items

The user can ask to prioritize a TODO item (e.g. "prioritize foo") to have it worked on sooner. This means moving that item up in `TODO.md` — reordering it earlier, ahead of items that would otherwise be worked on first — without otherwise changing its content, plan, or status. Since ids are permanent and carry no ordering information (see "Item IDs" above), reordering is just moving the item's whole text block to its new position — no renumbering, and no cross-references to update. Commit the reordered `TODO.md` on its own.
