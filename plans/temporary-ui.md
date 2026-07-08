# Temporary UI (COMPLETED)

## Summary

TODO a02b001: a means for an external agent process to create ad hoc UI
on the canvas by dropping a small DSL file into a per-Desk-directory
`.desk_temp/` folder. To start, the DSL supports one interaction shape —
a question with multiple-choice options — rendered as a new "Question
Widget"; answering it appends the choice back to the same file. Desk
watches `.desk_temp/` and surfaces new/changed files as clickable
notifications rather than silently auto-placing widgets.

This is the largest item in the current batch by a wide margin — several
new subsystems (a DSL + parser, a new widget kind, a directory watcher
distinct from the two that already exist, a notification HUD, directory
-provisioning with permission prompts, `.gitignore` management, and a
new problem neither existing subsystem had to solve: giving a
placed widget instance a durable link back to *which file* it belongs
to, since `build() -> QWidget` takes no arguments and there's no
existing per-instance custom-payload slot in `WidgetState`).

## Scope decisions (the item's wording leaves these open)

- **Temp file naming**: literally "files with uuid names" — bare UUID
  strings as filenames (`550e8400-e29b-...`), no required extension.
  Validity check: `uuid.UUID(name)` succeeds. This also naturally
  excludes `desk-temporary-ui.md` from being treated as a temp-ui file
  without a special-case exclusion — it just doesn't parse as a UUID.
- **DSL line parsing**: `keyword param1 param2...` — for the three
  starting keywords, everything after the keyword is natural-language
  text (a question, an option label, a chosen answer), not meant to be
  further tokenized. Each line is split into `(keyword, rest_of_line)`
  by the *first* whitespace run only. Unknown keywords are silently
  ignored (forward-compatible — "to start, the only keywords are..."
  implies more later). Multiple `Question`/`Answer` lines: last one
  wins (simplest, no need to error on a malformed file). `Answer` only
  ever gets *appended*, never edited in place.
- **"ensure... is in any `.gitignore` file"**: interpreted as the
  associated directory's git root's own top-level `.gitignore` (reusing
  the same git-root lookup the TODO widget already has, now extracted
  to a shared `desk.git_utils.find_git_root` since it's needed a second
  time). If no git root, there's nothing to gitignore — skipped
  entirely, no prompt. If a git root exists but has no `.gitignore` yet,
  one is created as part of satisfying "ensure... is in" (can't ensure
  membership in a file that doesn't exist).
- **Widget↔file association, including across app restarts**: every
  Question Widget instance's Desk `instance_id` is set equal to its
  source file's UUID (both `open_widget`/`open_widget_content` and
  `_place_widget` already accept an explicit `instance_id`). This makes
  "does a live widget for file X already exist" a plain
  `find_frame_by_instance_id(uuid)` lookup, and — critically — lets a
  Question Widget rebuilt from a saved `Desk.widgets` entry (app
  restart, or hot-reload) recover its own source file *without* any
  change to the fixed `build() -> QWidget` contract every other widget
  kind relies on: `DeskWindow._load_desk_widgets`/`_place_widget`
  special-cases `widget_id == "question"` (already special-cases `kind`
  there; one more targeted case is consistent with that method's
  existing shape) to call the widget's own `set_source_file(path)` with
  `.desk_temp/{instance_id}` right after building it — mirroring exactly
  how `ScratchWidget.set_label` (TODO d25e557) is called post
  -construction by whoever places it, just from `DeskWindow` instead of
  another widget. If the file no longer exists at that point (deleted
  externally between sessions), the widget shows a small "this question
  no longer exists" placeholder instead of crashing.
- **Live content refresh**: the item only asks that clicking an "edited"
  notification *center the view* on an already-placed widget for that
  file, not that the widget's displayed content live-refreshes to match
  a since-changed file. Implementing exactly that (center only, no
  forced re-render) — noted as a minor, deliberate limitation in
  `PARKINGLOT.md` rather than built speculatively.
- **Self-write suppression for the Question Widget's own answer
  -append**: reusing the established `current_context` module-level
  -hook pattern (TODO d25e557's widget-opener) rather than accepting a
  spurious "edited externally" notification every time a question is
  answered — cheap to add given the infrastructure already exists, so
  not skipped as a papercut.
- **Multiple simultaneous notifications**: stacked vertically in the
  upper-right corner, keyed by file path (a new notification for a
  file already showing one replaces it in place, per the item's literal
  wording, rather than stacking duplicates for the same file).

## Design

### `desk.git_utils` (new, extracted)

`find_git_root(path) -> Path | None` — moved out of
`widgets/todo/widget.py` (`_find_git_root`, byte-identical logic) into a
shared home now that a second, independent caller needs it. The TODO
widget imports it from here instead of defining its own copy.

### `desk.temp_ui` (new)

Pure logic, no Qt:
- `TEMP_UI_DIRNAME = ".desk_temp"`, `DOC_FILENAME = "desk-temporary-ui.md"`.
- `is_temp_ui_filename(name: str) -> bool` — `uuid.UUID(name)` success.
- `@dataclass TempUiDocument: question: str | None; options: list[str]; answer: str | None`.
- `parse_temp_ui(text: str) -> TempUiDocument` — per-line `(keyword,
  rest)` split, per the parsing rules above.
- `append_answer(path: Path, answer: str) -> str` — appends `f"Answer
  {answer}\n"`, returns the full resulting file text (so a caller can
  record it for self-write suppression without a second file read).
- `DOC_TEMPLATE` — the contents written to `desk-temporary-ui.md`,
  describing the directory's purpose, the UUID-filename convention, and
  the DSL (`Question`/`Option`/`Answer`) with a worked example.
- `ensure_gitignore_entry(git_root: Path, ask: Callable[[], bool]) ->
  None` — checks `git_root/.gitignore` for a `.desk_temp` line (matching
  either `.desk_temp` or `.desk_temp/`); if missing, calls `ask()`
  (a caller-supplied confirmation callback, matching `DeskWindow`'s
  existing `Confirm` callable pattern) and appends `.desk_temp/` (with a
  trailing newline, creating the file first if absent) only if it
  returns `True`.

### `desk.shell.temp_ui_manager` (new)

`TempUiManager(QObject)`, owned by `DeskWindow` (one instance for the
window's lifetime, like `HotReloadBroker`):

- `file_added = pyqtSignal(Path)`, `file_edited = pyqtSignal(Path)`.
- A small dedicated `watchdog` observer (same debounced-per-path shape
  as the TODO widget's own watcher, generalized to a whole directory
  like `desk.widgets.WidgetWatcher`): distinguishes watchdog's
  `FileCreatedEvent` vs `FileModifiedEvent` to know whether to consider
  emitting `file_added` or `file_edited`; ignores any path failing
  `is_temp_ui_filename`; `.resolve()`s both sides of the path comparison
  (the confirmed macOS symlinked-tempdir gotcha, now hit a third time —
  see `LEARNINGS.md`).
- Self-write suppression: `record_own_write(path: Path, text: str)`
  (the hook wired into `current_context`, see below) records the exact
  text just written; the watcher's debounced callback reads the file
  fresh and skips emitting anything if it matches the last recorded
  self-write for that path — identical in shape to the TODO widget's
  `last_written_text` mechanism (TODO d25e557), now the third
  independent instance of it.
- `provision(directory: Path, ask_create_dir: Confirm, ask_gitignore: Confirm) -> Path | None`:
  called at boot and whenever the current Desk's directory actually
  changes (tracked via a simple "last-provisioned directory" guard so
  the same directory isn't re-prompted every time a Desk is merely
  saved). Ensures `.desk_temp` exists (prompting via `ask_create_dir`
  first if it doesn't; returns `None` and does nothing further if
  declined), ensures `desk-temporary-ui.md` exists inside it
  (unconditional, no prompt — only directory *creation* and the
  `.gitignore` edit are called out as needing permission in the TODO
  item's own wording), and calls `ensure_gitignore_entry` with
  `ask_gitignore`. Restarts the watcher pointed at the resulting
  directory (stopping any previous one), returning the directory (or
  `None` if provisioning didn't happen/was declined).

### `desk.shell.temp_ui_notifications` (new)

A small corner-pinned HUD, following the exact `DeskPicker`/
`ZoomControl` pattern (plain `QWidget` child of `self.viewport()`,
manually positioned, needing the same `scrollContentsBy` treatment TODO
82d66c0 just added):

- `TempUiNotificationStack(QWidget)`: vertical stack of small banner
  widgets, each showing a short label (derived from the file's parsed
  question text if parseable, else the bare filename) and a close ("x")
  affordance; `notify(path, clicked_callback)` adds/replaces the entry
  for that path; clicking anywhere on a banner (other than its own close
  button) invokes `clicked_callback` and removes the banner (the item
  says "persistent" meaning it doesn't auto-dismiss on a timer, not that
  it survives being clicked).
- `WorkspaceView` gains a `self.temp_ui_notifications =
  TempUiNotificationStack(self.viewport())`, positioned top-right
  (mirroring `_position_zoom_control`'s bottom-right math), reasserted
  in the same `resizeEvent`/`scrollContentsBy` hooks as the other two
  HUD widgets.

### `widgets/question/` (new)

`kind: "python"`. `QuestionWidget(QWidget)`:
- Starts empty/placeholder until `set_source_file(path: Path)` is
  called (mirroring `ScratchWidget.set_label`'s "configure after
  construction" shape) — shows "this question no longer exists" if the
  path doesn't exist at that point.
- Renders the parsed question text (non-selectable `QLabel`) and one
  `QPushButton` per option, vertically stacked. If already answered,
  all buttons are disabled and the chosen one is visually marked (bold
  label prefix); otherwise clicking an option calls the shared
  `desk.temp_ui.append_answer`, records the result via
  `current_context`'s temp-ui write hook (if installed) for self-write
  suppression, and re-renders in the answered state.

### `current_context` (extend)

One more minimal get/set pair, same shape as the widget-opener hook:
`set_temp_ui_write_recorder`/`get_temp_ui_write_recorder`, a
`Callable[[Path, str], None]` that `DeskWindow` wires at construction to
`self._temp_ui_manager.record_own_write`.

### `DeskWindow` (extend)

- Owns one `TempUiManager`; connects `file_added`/`file_edited` to
  handlers that call `self.view.temp_ui_notifications.notify(path, ...)`
  with a callback that either centers on the existing
  `find_frame_by_instance_id(uuid)` frame (if present) or places a new
  Question Widget with `instance_id=uuid`, `pos` = current view center
  (`self.view.mapToScene(self.view.viewport().rect().center())`, same
  expression `get_view_state` already uses), then calls
  `.set_source_file(...)` on the returned content widget (via
  `open_widget_content`, already returning the built widget instance).
- Calls `provision(...)` once at the end of `__init__` (boot) and again
  inside `change_current_desk_directory`/`switch_desk` after the
  directory actually changes, using `self._confirm_fn(...)`-built
  confirmation callables for the two permission prompts (matching the
  existing "Switch Desk"/"Remove Widget" confirmation style).
- `_load_desk_widgets`: for any placed widget with `widget_id ==
  "question"`, after building, calls `.set_source_file(directory /
  TEMP_UI_DIRNAME / instance_id)` on the built content (via the same
  `frame.content.current` access `open_widget_content` uses) so a
  restored Desk reconnects each Question Widget to its file.

## Affected files

- `src/desk/git_utils.py` (new, extracted from `widgets/todo/widget.py`).
- `src/desk/temp_ui.py` (new).
- `src/desk/shell/temp_ui_manager.py` (new).
- `src/desk/shell/temp_ui_notifications.py` (new).
- `widgets/question/widget.json`, `widgets/question/widget.py` (new).
- `src/desk/shell/current_context.py` (extend).
- `src/desk/shell/canvas.py` (extend — notification HUD wiring).
- `src/desk/shell/window.py` (extend — provisioning, notification
  click-handling, restore-on-load binding).
- `widgets/todo/widget.py` (`_find_git_root` → shared `git_utils`).
- `PARKINGLOT.md` (note: Question Widget doesn't live-refresh its
  content if its file changes after being placed).

## Verification

Entirely headless throughout:

1. `desk.temp_ui`: DSL parsing (question/options/answer, unknown
   keywords ignored, last-Question/last-Answer-wins), `is_temp_ui_filename`,
   `append_answer`'s file effect, `ensure_gitignore_entry` (missing file
   created + entry added when confirmed; declined leaves it untouched;
   no-op if already present).
2. `TempUiManager`: a real `watchdog` `Observer` against a real temp
   directory — creating a new UUID-named file fires `file_added`;
   editing it fires `file_edited`; a non-UUID filename (including
   `desk-temporary-ui.md` itself) fires neither; a self-recorded write
   (`record_own_write`) is correctly suppressed. `provision()`: creates
   `.desk_temp`+doc+gitignore-entry when confirmed; declining directory
   creation does nothing further (no doc, no gitignore edit, watcher
   not started); re-provisioning the same directory doesn't re-prompt.
3. `QuestionWidget`: renders parsed question/options; clicking an
   option appends the answer to the real file and re-renders answered
   -and-disabled; `set_source_file` on a missing path shows the
   placeholder instead of crashing.
4. Regression: a real `WorkspaceView`'s notification HUD stays pinned
   through resize/pan/zoom exactly like the Desk picker/zoom control
   (TODO 82d66c0's fix covers it automatically, confirmed directly
   rather than assumed).
5. Full-app regression via a real `DeskWindow`: boot-time provisioning
   prompt flow (accept/decline), a notification click placing a new
   Question Widget centered in the current view with a working
   `instance_id`-based binding, answering it, and — the actual point of
   the `instance_id`-as-uuid design — simulating an app restart by
   constructing a fresh `DeskWindow` from a saved `Desk` containing that
   Question Widget's state and confirming it reconnects to the correct
   file and shows the already-given answer.
6. Regression: `widgets/todo/widget.py`'s existing git-commit behavior
   is unaffected by the `_find_git_root` → `desk.git_utils` move.

## Status

Implemented and verified, entirely headlessly:

1. `desk.temp_ui`: DSL parsing (question/options/answer, unknown
   keywords ignored, last-Question/last-Answer-wins), `is_temp_ui_filename`,
   `append_answer`'s file effect, `ensure_gitignore_entry` (creation,
   idempotency, declining, already-present cases).
2. `TempUiManager`: a real `watchdog` `Observer` against a real temp
   directory -- creating a UUID-named file fires `file_added`; editing
   it fires `file_edited`; a non-UUID filename (`desk-temporary-ui.md`
   included) fires neither; a self-recorded write is suppressed.
   `provision()`: declining directory creation does nothing further; a
   confirmed run creates the directory/doc and (when a git repo exists)
   the `.gitignore` entry; re-provisioning the same directory doesn't
   re-prompt. Found and fixed a real bug during this step: a brand-new
   file was always misclassified as "edited" rather than "added" (see
   LEARNINGS.md) -- fixed by classifying from "has this filename ever
   been seen before" instead of the raw watchdog event type.
3. `QuestionWidget`: renders parsed question/options; clicking an
   option appends the answer to the real file and re-renders answered
   -and-disabled with the chosen option marked; `set_source_file` on a
   missing path shows a placeholder instead of crashing.
4. Regression: the new notification stack stays correctly pinned
   top-right through panning, confirming TODO 82d66c0's
   `scrollContentsBy` fix covers it automatically.
5. Full-app regression via a real `DeskWindow` (confirm dialogs
   short-circuited to avoid a real modal `QMessageBox` in a headless
   run): boot-time provisioning, a real notification firing for a
   newly-created file, clicking it to place a bound `QuestionWidget`
   centered in the view, re-activating an already-placed one (no
   duplicate), answering it, and -- the actual point of the
   `instance_id`-as-uuid design -- constructing a fresh `DeskWindow`
   over the same saved Desk and confirming it reconnects the
   `QuestionWidget` to its file and shows the already-given answer.
6. Regression: `widgets/todo/widget.py`'s existing git-commit test
   suites all still pass after the `_find_git_root` → `desk.git_utils`
   move.
