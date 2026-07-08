# How to convert a numbered TODO.md to permanent hash ids (one-time)

A reusable procedure for switching a project's `TODO.md` from sequential
numeric item ids (`1.`, `2.`, ...) to permanent, content-derived 7-hex
-digit ids (see `development-process.md`'s "Item IDs" section for the
scheme itself). Follow this exactly once per project, when asked to make
this switch.

## Before you start

- Confirm the file actually uses a numbered-list format where each
  top-level item starts a line with `N. ` (digits, period, space, no
  leading whitespace) — this procedure assumes that shape. If items are
  numbered some other way, adapt step 2 accordingly.
- Check `git status` — this touches `TODO.md` (and a couple of other
  files); make sure there's nothing uncommitted you'd lose track of.

## Steps

1. **Get or write the conversion script.** If this repo already has
   `scripts/todo_item_ids.py`, use it as-is. Otherwise write it fresh —
   it needs two things:
   - `make_item_id(description) -> str`: hash the description to 7
     lowercase hex digits (`hashlib.sha256(text.encode()).hexdigest()[:7]`
     is fine); if the description is under 10 characters, hash
     `secrets.token_hex(8)` instead (a very short description doesn't
     hash distinctively). This is the *only* place randomness enters —
     everything else is deterministic.
   - A `convert(path)` pass that:
     a. Finds every top-level item (`^\d+\.\s` at column 0 — anchor
        strictly at line start so indented continuation/bullet lines
        inside an item's body never match).
     b. For each item, computes its id from the item's **full body text**
        (everything from just after its own `N. ` up to, but not
        including, the next item's start line) — not just the first
        line. This is "the initial description" the scheme refers to:
        whatever the item's text is *right now*, at conversion time, not
        an attempt to reconstruct history via `git log`.
     c. Builds a `{old_number: new_id}` map from that.
     d. Rewrites each item's own leading `N.` to `<id>.`.
     e. Rewrites cross-references elsewhere in the file: both the
        singular form (`item 12`) and any plural/slash-separated form
        your project's items happen to use (`items 12/13`, `items
        12/13/14`) — check for both; this project's `TODO.md` had real
        examples of each. Use `\s+` between the word and the number/list
        in the regex, not a literal single space — a reference can be
        word-wrapped across a line break in prose (confirmed directly:
        `...checks done when item\n    10 was built` is a real example
        that a literal-space regex misses silently).
   - Give it a `new "<description>"` mode too (prints one id, for adding
     future items) — cheap to add alongside `convert`, and it's what
     `development-process.md` tells people to run afterward for new items.

2. **Dry-run against a copy first.** Never run `convert` directly on the
   real file first:
   ```
   cp TODO.md /tmp/TODO_test.md
   python3 scripts/todo_item_ids.py convert /tmp/TODO_test.md
   ```
   Inspect the result (read the whole file, not just a diff) before
   touching the real one. Specifically check for:
   - Every item got a 7-hex-digit id (`grep -c '^[0-9a-f]\{7\}\. '`
     should equal the original item count).
   - No duplicate ids (`grep -o '^[0-9a-f]\{7\}\.' file | sort | uniq -d`
     should print nothing).
   - No leftover un-converted references
     (`grep -n 'item [0-9]\|items [0-9]\|item$\|items$'` should print
     nothing — the trailing-`$` patterns catch the line-wrapped case).
   - Skim for any reference *style* your regexes didn't anticipate
     (this project needed two passes: singular `item N`, then a separate
     plural `items N/M/...` pass, discovered only by actually reading the
     converted output and noticing what didn't change).

3. **Fix the script, not the output.** If step 2 finds a gap, fix the
   regex/logic and re-dry-run from scratch — don't hand-patch the test
   output and consider it done; the real file needs the corrected script
   too.

4. **Run it for real** on the actual `TODO.md`, then re-run all of step
   2's checks against the real file.

5. **Cosmetic cleanup pass.** Collapsing a wrapped `item N` reference into
   one `TODO <id>` token can leave that one line noticeably longer than
   the file's usual wrap width (the replacement has no newline in it).
   Find these with e.g. `awk '{ if (length($0) > 90) print NR }'` and
   manually re-wrap the worst offenders — purely cosmetic, but worth a
   couple minutes for a file people read regularly.

6. **Add the id-generation instructions to the project's development
   -process doc** (see this project's `development-process.md`'s "Item
   IDs" section for the wording to adapt): the id format, that ids never
   change once assigned, that priority is physical file position (not the
   id), and how to generate an id for a *new* item going forward (the
   script's `new` mode). Also simplify any "renumber the list" instruction
   elsewhere in that doc (e.g. a "Prioritizing" section) — permanent ids
   mean reordering is just moving a text block, no renumbering step.

7. **Commit everything together**: the script, the process-doc update,
   the converted `TODO.md`, and this how-to doc itself if it didn't
   already exist. One commit — this is a single, one-time mechanical
   change, not a multi-step feature.

## Things that will bite you if skipped

- **Anchoring the item-start regex at column 0.** Without this,
  indented sub-bullets or continuation lines that happen to start with
  digits get misidentified as separate top-level items.
- **Computing every id before rewriting anything.** Rewrite passes
  (renumbering headers, substituting cross-references) must all read
  from one `{old_number: new_id}` map computed up front from the
  *original* text — never recompute an id mid-rewrite, and never let one
  item's rewrite affect another item's hash input.
- **`\s+`, not a literal space, in cross-reference regexes.** Prose
  wraps; a reference spanning a line break is real and silent to miss.
- **Checking for every reference *shape* actually used**, not just the
  one you first think of. Grep broadly (`item[s]? [0-9]`) before
  declaring the conversion complete, and actually read a full dry-run
  output rather than trusting a clean diff summary.
