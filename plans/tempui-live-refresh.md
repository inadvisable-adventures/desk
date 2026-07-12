# General live-refresh for already-placed tempui-bound widgets

TODO `67ab2df`.

## Summary

Surfaced while implementing TODO 9743419: I described the new
Markdown tempui capability as "rendered live and watched for changes,"
but checking the actual code showed this was never true for *any*
tempui-bound widget kind. `PARKINGLOT.md` already documents this
precisely for Question ("doesn't live-refresh if its `.desk_temp` file
changes after being placed... minor, deliberate scope limitation"),
and `plans/temporary-ui.md` confirms it was an explicit, deliberate
choice at the time ("the item only asks that clicking an 'edited'
notification *center the view*... not that the widget's displayed
content live-refreshes"). The user asked me to revisit that decision
with a **general** fix, then audit for every other place something is
supposed to be "live" but isn't, verify the general fix actually
covers each one (adjusting the general design if it doesn't), and only
then queue the individual fixes behind it.

## Investigation: what's actually supposed to be live, and is it?

Grepped `plans/`, `PARKINGLOT.md`, `design-docs/` for "live"/"refresh"
and cross-checked each hit against current behavior:

- **Question** (`widgets/question/`) -- documented gap (see above).
  `_render` derives all displayed state (including "already answered")
  fresh from the file's own content every time it's called -- confirmed
  by reading it: re-invoking `set_source_file`/`_reload` at any point
  is fully idempotent, including after an answer was already given
  (buttons render disabled with a checkmark, not re-answerable). No
  local editable state exists to clobber. **Safe for a blind
  re-render.**
- **LightningRound** (`widgets/lightning_round/`) -- same underlying
  mechanism as Question (not separately called out in `PARKINGLOT.md`,
  but inherits the identical gap: `_activate_temp_ui` centers instead
  of refreshing, kind-agnostically). `_render` derives "next unanswered
  item" fresh from the file's current items list every call --
  confirmed idempotent the same way. **Safe for a blind re-render.**
- **Scratch** (`widgets/scratch/`, TODO f8d9cec) -- my own plan for it
  already noted "no live refresh... same limitation the existing
  Question/LightningRound kinds already have." Unlike the two above,
  this one **isn't** safe for a blind re-render: `_bind_temp_ui_content`
  calls `content.body.setPlainText(body)` unconditionally, and unlike
  Question/LightningRound, Scratch's body is a real, user-editable
  `QPlainTextEdit` the user may already be typing into. A blind
  re-render here would clobber in-progress user edits -- **this is the
  concrete case where the naive general solution doesn't apply, and
  had to be extended** (see Key Decisions).
- **Markdown (`Markdown <label>` tempui content, TODO 9743419)** --
  same shape as Question/LightningRound: `set_tempui_content` is a
  pure `QTextBrowser`-based re-render with no local editable state.
  **Safe for a blind re-render.**
- **OpenMarkdown** -- *not* part of this audit: it already has real,
  independent live-refresh today, via the *target* file's own
  `SingleFileWatcher` (built into `MarkdownWidget.set_file`) -- a
  completely different, already-working mechanism, since `OpenMarkdown`
  points at an external file rather than rendering the tempui file's
  own content.
- **Everything file-backed** (Markdown, Editor, TODO widget) already
  has real live-refresh via `SingleFileWatcher`/`TempUiManager`'s own
  watching (TODO 578cb6b/cee6f74) -- not part of this audit, which is
  specifically about tempui-*file*-mediated widgets going through
  `DeskWindow`'s notification path, a separate mechanism.
- Also checked `PARKINGLOT.md`'s "editor-with-view live preview" note
  -- a different, not-yet-built, much bigger feature (needs a
  side-by-side container widget first); out of scope here, left alone.

Confirmed no other tempui-mediated "supposed to be live" gaps exist
beyond these four.

## Key decisions

- **Reuse the existing generalized dispatch (`_bind_temp_ui_content`)
  for the refresh itself, not a new per-kind mechanism.** It already
  correctly routes to whichever method each kind needs
  (`set_source_file`/`set_label`+`body`/`set_tempui_content`), reads
  the file fresh every call, and is already used for both fresh
  placement and Desk-restore -- a live refresh is just a third
  situation calling the exact same function.
- **New optional duck-typed guard: `has_unsaved_local_edits() -> bool`.**
  This is the actual generalization needed once Scratch's case was
  checked against the naive design: a widget with local editable state
  that a blind refresh could clobber implements this (checking
  `QPlainTextEdit`/similar `.document().isModified()` -- confirmed
  directly that `setPlainText()` always resets `isModified()` to
  `False` while real user edits set it `True`, so this is a reliable,
  zero-cost signal). A widget that doesn't implement it (Question,
  LightningRound, the Markdown tempui case) is treated as always safe
  to refresh -- **zero code changes needed for those three**; only
  Scratch needs the new method. This is what makes the general
  solution actually apply to *all four* cases, not just the three
  stateless ones.
- **Wired centrally, once, in `DeskWindow`**: `_on_temp_ui_file_edited`
  first tries `_refresh_live_temp_ui(path)` -- if an already-placed
  frame exists for that instance and (a) it's a `PythonWidgetHost` with
  real content and (b) that content doesn't report unsaved local edits,
  re-invoke `_bind_temp_ui_content` directly and skip the usual
  notification (the widget already visibly updated, so a banner saying
  the same thing would be redundant). Otherwise (no frame yet, or local
  edits blocked the refresh), fall through to the existing
  `_notify_temp_ui` behavior unchanged -- so a blocked Scratch refresh
  still surfaces a notification the user can act on later, rather than
  silently doing nothing.
- **Notification-click behavior (`_activate_temp_ui`'s "center if a
  frame already exists") is left unchanged.** The new mechanism handles
  the "make it live" requirement at the moment of the actual edit;
  clicking an already-shown notification still just centers the view,
  keeping this change surgical rather than compounding multiple
  behavior changes into one step.
- **Individual per-widget TODOs (`f668aef`/`091bc27`/`9ee505f`/
  `6fbae42`) are resolved by this same implementation**, not built
  separately -- Question/LightningRound/Markdown-tempui need zero
  additional code (the central wiring alone fixes them, verified
  directly for each); Scratch needs its own `has_unsaved_local_edits`
  method, included here since it's what makes the general mechanism
  *correct*, not an optional enhancement layered on top.

## Affected files

- `src/desk/shell/window.py` -- `_on_temp_ui_file_edited` gains
  `_refresh_live_temp_ui(path) -> bool` (checked first); no changes to
  `_bind_temp_ui_content` itself (reused as-is).
- `widgets/scratch/widget.py` -- new `has_unsaved_local_edits()`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks):

- Question: a real placed instance, tempui file edited externally
  (new question text) -> widget's displayed question updates without
  any notification click.
- Question, already answered: editing the file again afterward doesn't
  let the widget become re-answerable (still disabled/checkmarked) --
  confirms the reused idempotent `_render` stays correct under the new
  trigger path too.
- LightningRound: same live-update check, plus confirms mid-session
  (one item already answered) state isn't disturbed by an external
  edit adding more items.
- Markdown tempui content: a real placed instance, tempui file content
  edited externally -> the rendered content updates live.
- Scratch, no local edits yet: tempui file edited externally -> body
  text updates (safe to refresh).
- Scratch, *with* unsaved local edits (simulated real typing, not
  `setPlainText`) -- confirms `document().isModified()` is `True` in
  that state: tempui file edited externally -> body text is **not**
  clobbered, `has_unsaved_local_edits()` correctly blocks the refresh.
- No frame placed yet for a given tempui file: an edit still falls
  through to the existing `_notify_temp_ui` notification path
  unchanged (regression check).

## Status

Not yet implemented.
