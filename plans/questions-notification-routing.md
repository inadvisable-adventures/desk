# tempui QUESTIONS.md notification routing (COMPLETED)

TODO `a801180`.

## Summary

Two parts, per the TODO's own text:

1. Document, in `desk-temporary-ui.md` (the doc seeded into every
   Desk's `.desk_temp/`, read by any agent working inside a Desk
   project via the tempui mechanism -- not this project's own
   `development-process.md`, which is a different, narrower audience:
   *my own* workflow for managing *this* repo's TODO.md), that an
   open-ended question for the user belongs in `QUESTIONS.md`, not a
   new `.desk_temp/<uuid>` file.
2. Make Desk actually notice a newly-added `QUESTIONS.md` entry and
   surface it as a top-right notification, matching the existing
   `.desk_temp` notification's own look/feel -- clicking it either
   focuses an already-open Questions widget (TODO `7a086ba`) or opens
   and focuses a new one.

## Key decisions

- **A separate, `DeskWindow`-owned `SingleFileWatcher` for
  `QUESTIONS.md`, not reuse of `TempUiManager`.** `TempUiManager`
  watches a whole *directory* of freshly-created uuid-named files;
  `QUESTIONS.md` is one specific, already-existing file whose *content*
  changes -- the exact shape `SingleFileWatcher` already exists for
  (the same class every file-backed widget, including the Questions
  widget itself, already uses). The only twist is that this instance
  is owned by `DeskWindow` itself, not a widget instance, since the
  notification must fire even when no Questions widget is currently
  open -- mirroring the `.desk_temp` mechanism's own "notify regardless
  of whether a widget exists for it yet" behavior.
- **Notify only for genuinely *new* entries, not every file change.**
  An existing entry being *answered* is itself a `QUESTIONS.md` write
  (by the Questions widget) and must not re-trigger a "new question"
  notification. `_ensure_questions_watcher` seeds a baseline set of
  `tuple(entry.todo_ids)` keys whenever the resolved path changes
  (boot, desk switch, directory change -- the same three call sites
  `_provision_temp_ui` already had, since this piggybacks directly onto
  it); `_on_questions_file_changed` diffs the freshly-parsed entries'
  keys against that baseline, updates it, and only notifies for keys
  not seen before. (`SingleFileWatcher`'s own self-write-echo
  suppression already means a write the Questions widget made itself
  never even reaches `_on_questions_file_changed` in the first place --
  this new-keys diff is an *additional* filter on top, for the case of
  a real external edit that both answers an old entry and adds a new
  one in the same write.)
- **Notification text**: the new entry's own title if there's exactly
  one, else a count ("N new questions in QUESTIONS.md") -- avoids
  either an empty-feeling generic banner for the common one-at-a-time
  case, or an unreadably long banner if several land at once.
- **Reused `WorkspaceView`'s existing `notify_temp_ui` banner
  mechanism verbatim**, keyed by the `QUESTIONS.md` path itself
  (instead of a per-file uuid, since there's only one `QUESTIONS.md`
  path in play) -- a second new question before the first is
  dismissed/clicked just replaces the banner in place (the stack's
  existing per-path dedup behavior), which is the right default here
  too.
- **Click handler (`_focus_questions_widget`)**: a new small
  `_find_frame_by_widget_id` helper (search `self.view._frames` for a
  `PythonWidgetHost` whose `.widget_id` matches, using the same
  `frame.content.widget_id` field `_capture_desk_state` already reads)
  since, unlike tempui-bound widgets, a Questions widget instance isn't
  addressable by a source-file uuid `instance_id` -- there's normally
  at most one, found by kind instead. Mirrors `_activate_temp_ui`'s own
  "center if it exists, otherwise create it centered in the current
  view" shape exactly.
- **Doc change is additive, not a replacement of `Question`/
  `LightningRound`.** Those remain the right tool for a single quick
  multiple-choice decision; the new section explicitly frames
  `QUESTIONS.md` as the answer for open-ended, possibly-multi-question,
  free-text-answer cases instead, and defers to a project's own
  `development-process.md` (if any) for *when* to ask -- this doc is
  only about *where* the question text lives.

## Affected files

- `src/desk/temp_ui.py` -- `DOC_TEMPLATE` gains a new
  "Questions for the user: use QUESTIONS.md, not this DSL" section,
  right after the intro paragraph (before the first DSL section, since
  it's about *which* mechanism to reach for, not one more DSL itself).
- `src/desk/shell/window.py` -- new `QUESTIONS_WIDGET_ID` constant;
  `_questions_watcher` (a `SingleFileWatcher`), `_questions_path`,
  `_known_question_keys` state in `__init__`; `_ensure_questions_watcher`
  (called from `_provision_temp_ui`, so it's covered by all three of
  that method's existing call sites automatically);
  `_on_questions_file_changed`; `_find_frame_by_widget_id`;
  `_focus_questions_widget`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`), against
the exact unbound-`DeskWindow`-method-on-a-fake-double pattern used
throughout this session for `DeskWindow`-dependent logic (constructing
a real `DeskWindow` stalls headlessly):

- `_ensure_questions_watcher` seeds the baseline key set from a real
  temp `QUESTIONS.md` and hands the resolved path to the watcher; with
  no `QUESTIONS.md` findable, it stops the watcher and clears the
  baseline instead.
- `_on_questions_file_changed`: adding one new entry fires exactly one
  notification carrying that entry's title and the file's own path;
  answering an existing entry (no new entries) fires none.
- `_find_frame_by_widget_id` / `_focus_questions_widget`: with an
  existing Questions-widget frame present, centers on it and does not
  place a new one; with none present, places a new one (via the real
  `_place_widget`-shaped call, recorded by a stub) and centers on the
  newly-placed frame.
- Regression pass: re-ran the existing tempui-live-refresh verification
  script (`verify_tempui_live_refresh.py`) -- unaffected, all still
  passing.

## Status

Implemented and verified as above. No `LEARNINGS.md` entry needed --
nothing here was a surprising platform/library behavior, just new
application logic composed from already-established patterns
(`SingleFileWatcher`, the `.desk_temp` notification banner, the
unbound-method-on-a-fake-double test pattern).
