# Fix four small gaps adopting the development-process.md doc split (TODO `7f984ec`)

## Summary

Per
`../FEEDBACK/FEEDBACK-DESK-new-desk-in-existing-project-source-diving-2026-08-03-1506.md`,
four independent, small gaps found adopting Desk's shared/not-shared
`development-process.md` doc split (TODO `1a96c9f`/`c458012`) into an
existing project (`world-timelines`):

1. No breadcrumb when `_seed_development_process` seeds the two new
   peer files into a project that already has its own pre-existing,
   pre-split `development-process.md` (left untouched, never
   overwritten) -- nothing explains what the new files are or that the
   top-level file still needs a manual rewrite to reference them.
2. `how-to-convert-item-id-one-time.md` isn't seeded alongside
   `scripts/todo_item_ids.py`, even though the script's own docstring
   points at it for the one-time `convert` procedure.
3. `scripts/todo_item_ids.py`'s regexes don't handle three real
   reference shapes: `"TODO item N"` double-prefixing, en-dash ranges
   (`"items 6–8"`), and HTML-comment-embedded `1.`/`2.` lines colliding
   with `ITEM_START_RE`.
4. The `../FEEDBACK/` convention itself isn't documented anywhere in
   `shared_development_process.md`.

## Affected files

- `src/desk/shell/window.py` -- `_seed_development_process`,
  `_seed_todo_item_ids_script`, `new_desk`.
- `src/desk/shell/temp_ui_manager.py` -- new public breadcrumb-note
  method.
- `scripts/todo_item_ids.py` -- the three regex fixes. This file is
  seeded verbatim into other projects (never locally modified per its
  own docstring), so fixing it here is the only way a future project
  benefits.
- `shared_development_process.md` -- new `../FEEDBACK/` section.
- `tests/verify/` -- new/extended coverage.

## Design decisions

- **Breadcrumb via the same Scratch-note mechanism TODO `7c7b676`
  already established** (`TempUiManager._notify_docs_upgraded`) --
  factored its write-a-scratch-note body out into a small shared
  `_write_scratch_note` helper, reused by a new public
  `TempUiManager.notify_dev_process_peers_seeded(directory)`. Not
  folded directly into `_seed_development_process` itself: that method
  runs in `new_desk` *before* `switch_desk` provisions `.desk_temp`
  and starts the watcher, so there's nowhere yet to write the note at
  that point. Instead, `_seed_development_process` returns whether a
  breadcrumb is warranted (peer file(s) newly seeded *and* the
  top-level file already existed), and `new_desk` calls the new
  `notify_dev_process_peers_seeded` after `switch_desk` has run.
- **The condition for the breadcrumb** is specifically "at least one
  peer file (`shared_development_process.md`/
  `specifically-not-working-on-desk-itself-development-process.md`)
  was newly written, AND the destination already had its own
  `development-process.md`" -- not "any file was seeded." A
  brand-new project (nothing pre-existing at all) gets all three files
  with nothing to explain; the breadcrumb is only useful for the
  mixed case the FEEDBACK item actually hit.
- **`notify_dev_process_peers_seeded` is a no-op if `.desk_temp` isn't
  currently being watched for that directory** (e.g. `create_temp_ui`
  was declined) -- there's nowhere for the note to go, matching this
  project's general "nothing to do" tolerance elsewhere (e.g.
  `DeskWindow.set_widget_subtitle`'s unknown-instance no-op).
- **`how-to-convert-item-id-one-time.md` seeding is unconditional
  alongside the script**, same no-overwrite/no-op-if-missing-source
  posture as everything else `_seed_todo_item_ids_script` already
  does -- it's a plain doc file, not executable, so no chmod needed.
- **Regex fixes, not a rewrite**: minimal, targeted changes to the
  three specific shapes identified, since this script's own "verbatim,
  never customize" contract means the diff a future project actually
  benefits from should be small and easy to trust.
  - `"TODO item N"`: broaden the singular-reference regex to optionally
    consume a leading `TODO\s+` and replace the whole match (including
    that leading `TODO`) with `TODO <id>` -- so `"TODO item 16"` and
    `"item 16"` both become `"TODO <id>"`, never `"TODO TODO <id>"`.
  - En-dash ranges: a second plural pattern,
    `r"\bitems\s+(\d+)[-–](\d+)\b"` (hyphen or en dash), expanding
    to every integer in the inclusive range and joining with `/` the
    same way the existing slash-list pattern already does, so
    downstream rendering is consistent between `"items 6/7/8"` and
    `"items 6-8"`.
  - HTML comments: a new `_html_comment_line_indices` helper marking
    which line indices fall inside a (possibly multi-line) `<!-- ...
    -->` block; `_split_items` skips any `ITEM_START_RE` match on such
    a line. Deliberately line-based, not a full HTML parse -- matches
    the FEEDBACK item's own concrete example (a documentation comment
    whose own literal `1. ...`/`2. ...` example lines span multiple
    physical lines).
- **`../FEEDBACK/` section in `shared_development_process.md`**
  documents: what the directory is (a location sibling to this repo,
  shared across every project that adopted Desk, where a Claude
  instance working in a *different* project writes a
  `FEEDBACK-DESK-<slug>-<date>-<time>.md` file when something about
  Desk itself -- not that project -- caused friction); that acting on
  one means filing a TODO/PARKINGLOT entry citing it, the same way
  every existing TODO item sourced from one already does; and the
  existing (previously undocumented, confirmed via `ls
  ../FEEDBACK/implemented/`) convention of moving a FEEDBACK file into
  `../FEEDBACK/implemented/` once every TODO/PARKINGLOT entry it
  produced is `COMPLETED`.
- **Retroactive hygiene, done alongside this TODO**: this session's own
  six already-`COMPLETED` items from the same "small, concrete fixes"
  batch (`a8e4115`, `7c11fe0`, `47aaf73`, `1b7e500`, `e86a31b`,
  `3cd90cf`) each cite a `../FEEDBACK/` file that was never moved to
  `implemented/` -- now that this convention is actually documented,
  move all seven (those six plus this TODO's own source file) into
  `../FEEDBACK/implemented/` as part of finishing this item, so the
  freshly-documented convention doesn't start already out of sync with
  this session's own recent history. `../FEEDBACK/` is outside this
  git repo and not itself version-controlled -- a plain filesystem
  move, easily reversed by hand, not a destructive action.

## Step-by-step implementation

1. `temp_ui_manager.py`: factor `_notify_docs_upgraded`'s note-writing
   into `_write_scratch_note(temp_dir, title, body)`; add public
   `notify_dev_process_peers_seeded(directory)` using it, guarded by
   `self._watched_directory == directory / TEMP_UI_DIRNAME`.
2. `window.py`: `_seed_development_process` returns `bool` (breadcrumb
   warranted); `new_desk` captures that, calls
   `self._temp_ui_manager.notify_dev_process_peers_seeded(directory)`
   after `switch_desk` when true.
3. `window.py`: `_seed_todo_item_ids_script` also seeds
   `how-to-convert-item-id-one-time.md` next to the script (same
   no-overwrite/no-op posture).
4. `scripts/todo_item_ids.py`: the three regex fixes above.
5. `shared_development_process.md`: new `../FEEDBACK/` section.
6. Move the seven `../FEEDBACK/` files listed above into
   `../FEEDBACK/implemented/`.
7. New/extended verify coverage (see below); run the full
   `tests/verify/` suite.

## Key tradeoffs

- The breadcrumb note only fires for the specific "peer(s) seeded,
  top-level pre-existing" case -- not a general "your dev-process docs
  might be out of sync" recurring check on every Desk open. Matches
  the FEEDBACK item's own framing as a one-time-seed note, and this
  project's existing precedent (the tempui-doc-drift note is also
  one-shot, not recurring).
- `_html_comment_line_indices` is line-based, not a real HTML/Markdown
  parser -- a `<!--`/`-->` pair split across a *string* on the same
  line in an unusual way could confuse it, but this is a
  self-authored, internally-consistent doc file, not arbitrary
  external HTML, so the simpler line-based approach is proportionate.

## Verification

New checks, real (no mocking):
- `tests/verify/verify_dev_process_seeding.py` (extending the existing
  file): `_seed_development_process` returns `True` only when a peer
  file was newly written *and* the top-level file already existed;
  `False` for a brand-new project (nothing pre-existing) and for a
  project where nothing needed seeding at all. A real `new_desk` call
  (via the established `_FakeWindow`-style harness) against a
  directory with a pre-existing `development-process.md` results in a
  real Scratch note appearing in the new project's `.desk_temp/`
  (content mentions both peer filenames and
  `plans/fork-development-process-doc.md`); the same call against a
  brand-new directory (nothing pre-existing) produces no such note.
- `tests/verify/verify_seed_todo_item_ids_script.py` (extending the
  existing file): `how-to-convert-item-id-one-time.md` is seeded
  alongside the script; already-existing destination content is left
  untouched; missing source is a no-op, same as the script itself.
- A new `tests/verify/verify_todo_item_ids_script_regex_fixes.py`
  (subprocess-invokes the real script against real fixture text, the
  same shape `verify_seed_todo_item_ids_script.py` already uses):
  `"TODO item 16"` converts to `"TODO <id>"`, not `"TODO TODO <id>"`;
  an en-dash range `"items 6–8"` converts to three `TODO <id>`
  references, slash-joined; a `<!-- Item format: 1. ... 2. ... -->`
  -shaped multi-line comment's own `1.`/`2.` lines are not treated as
  real item boundaries, confirmed against a real numbered item
  elsewhere in the same fixture whose number matches one used inside
  the comment.
- `shared_development_process.md` mentions `../FEEDBACK/` and
  `implemented/` (a simple content check, run directly against the
  file -- no existing verify script currently covers this file's
  content at all).
- Full `tests/verify/` regression suite.
