# Introduce the Desk concept (COMPLETED)

## Summary

Implement the **Desk** concept per the (clarified) TODO item: a named set
of widget instances with their state (position/size), associated with a
directory on disk, serializable to a `.desk` JSON file (by default stored
in that directory). Add a top-left HUD picker (mirroring `ZoomControl`'s
bottom-right placement) with two controls — an MRU dropdown for switching
desks, and a button for changing the current desk's associated directory
— collapsed by default to a half-alpha label showing the desk's name,
expanding to the two controls on hover. Confirms before switching away
from the currently-open desk. Formalizes and supersedes the old
"Workspace persistence" TODO item.

## Design

### Data model (`src/desk/desks.py`)

```python
@dataclass
class WidgetState:
    widget_id: str
    x: float
    y: float
    width: float
    height: float

@dataclass
class Desk:
    path: Path              # where this desk is/will be serialized
    widgets: list[WidgetState]
    pan_x: float = 0.0
    pan_y: float = 0.0
    scale: float = 1.0

    @property
    def name(self) -> str:
        return self.path.stem   # ".desk" stripped

    @property
    def directory(self) -> Path:
        return self.path.parent
```

- File extension: **`.desk`** (JSON content, self-documenting extension —
  matches how e.g. `.ipynb` is JSON with its own extension). A desk's
  *name* (shown in the picker/MRU) is its file's stem, per the TODO item
  ("the Desk's name is the filename of its serialized file").
- `default_desk_path(directory) -> Path`: `directory / "default.desk"` —
  used when no `.desk` file exists yet in a directory.
- `discover_desk_files(directory) -> list[Path]`: all `*.desk` files
  directly in `directory`, most-recently-modified first (used to pick a
  starting desk when launching Desk pointed at a directory that already
  has one, without an explicit MRU entry to fall back to).
- `load_desk(path) -> Desk`: reads/parses the JSON; a missing file is *not*
  an error here — the caller (`Desk.new(path)`) handles "doesn't exist yet"
  by constructing an empty `Desk` instead of calling `load_desk`.
- `save_desk(desk) -> None`: writes JSON to `desk.path`, creating parent
  directories if needed.

### MRU list (`src/desk/recent_desks.py`)

A small global (per-user, not per-project) "recently used desks" list,
independent of `desks.py`'s directory-scoped `discover_desk_files` (that
one only looks *within* a single directory; the MRU spans desks opened
from anywhere, which is what makes a "recently used" dropdown actually
useful across sessions/projects):

- Stored at `~/.desk/recent_desks.json` (reusing the `~/.desk/` convention
  already mentioned in `design-docs/architecture.md`'s Workspace
  Persistence section for exactly this kind of app-level state).
- `load_mru() -> list[Path]`, `add_to_mru(path) -> list[Path]` (dedupes,
  moves-to-front if already present, caps at `MAX_MRU_ENTRIES = 10`,
  persists, returns the updated list). Paths that no longer exist on disk
  are dropped when loading (a desk file the user deleted shouldn't linger
  in the dropdown).

### `DeskPicker` widget (`src/desk/shell/desk_picker.py`)

A HUD widget, structurally analogous to `ZoomControl` — a plain child
widget of `WorkspaceView.viewport()` (screen space, not a scene item),
anchored to the **top-left** corner this time. Unlike `ZoomControl` (always
either fully shown or fully hidden), this one has two *content* states in
the same fixed-position container:

- **Collapsed** (default): a single `QLabel` showing the current desk's
  name, styled at half-alpha (`background-color: rgba(40, 42, 46, 128)`).
- **Expanded** (on hover, via `enterEvent`/`leaveEvent`): the label is
  replaced by two controls side by side — a `QComboBox` (MRU entries, each
  showing the desk's name/stem, plus a trailing literal `"..."` entry) and
  a small `QPushButton` (opens a directory picker).

Signals: `desk_chosen(Path)` (an MRU entry was picked), `browse_requested()`
(the `"..."` entry was picked — the picker itself doesn't own a
`QFileDialog`; the caller, which owns confirmation/switching logic, does),
`directory_change_requested()` (the button was clicked). The picker is a
"dumb" UI component — it doesn't perform confirmation or the actual
switch/directory-change itself; `DeskWindow` does, in response to these
signals, since that's where the current-desk state and the canvas actually
live.

`set_current(name: str)` and `set_mru(entries: list[Path], current: Path)`
let the owner keep the picker's displayed state in sync.

### `DeskWindow` (edit)

Owns the single current `Desk` for this window (the TODO item's "each app
window can have only one Desk selected at a time" is satisfied simply by
this being one attribute, not a collection — no extra enforcement code
needed). New responsibilities:

- `_load_desk_widgets(desk: Desk)`: for each `WidgetState` in
  `desk.widgets`, look up `widget_id` in the discovered widget catalog
  (`self._widgets: dict[str, WidgetInfo]`, stored from the constructor
  arg) and instantiate the right host (`PythonWidgetHost`/`ChromiumWidget`,
  same branching as today), placed via `view.add_widget(..., pos=(x, y),
  size=(width, height))`. If `desk.widgets` is empty (a brand-new,
  never-saved desk), falls back to today's behavior — one instance of
  every discovered widget, auto-spaced — so a fresh desk in an empty
  directory still shows the demo widget out of the box.
- `_capture_desk_state() -> Desk`: reads `self.view._frames`
  (`WorkspaceView` already tracks these) and each one's
  `graphicsProxyWidget()` position/size, builds a fresh `Desk` (same
  `path`, freshly captured `widgets`/`pan_x`/`pan_y`/`scale`) to save.
- `save_current_desk()`: `save_desk(self._capture_desk_state())`, then
  `add_to_mru(self.current_desk.path)`.
- `switch_desk(path: Path, confirm=...)`: if `confirm(...)` (default: a
  real `QMessageBox.question`, injectable for testing) says yes —
  `save_current_desk()` (always save before switching, so "switch desks"
  can never lose data), `self.view.clear_widgets()`, load the new `Desk`
  (via `load_desk` if the file exists, else a fresh empty `Desk` for that
  path), `_load_desk_widgets(...)`, update `self.current_desk`, update the
  picker (`set_current`/`set_mru`), `add_to_mru(path)`.
- `change_current_desk_directory(new_directory: Path, confirm=...)`: like
  `switch_desk`, but keeps the *same widget state*, just re-pointing
  `self.current_desk.path` at `new_directory / old_path.name` and saving
  there (a "save to a new location," not a destructive move — the old
  file, if any, is left alone).
- Wires `DeskPicker`'s three signals: `desk_chosen` → `switch_desk`,
  `browse_requested` → open `QFileDialog.getOpenFileName(filter="Desk
  files (*.desk)")` then `switch_desk` with the result,
  `directory_change_requested` → open
  `QFileDialog.getExistingDirectory()` then
  `change_current_desk_directory` with the result.
- `app.aboutToQuit` (wired in `desk.app.main()`) calls
  `window.save_current_desk()`.

### `WorkspaceView` (edit)

- `clear_widgets()`: removes every tracked frame's proxy from the scene
  and clears `self._frames`, so `DeskWindow` can rebuild from a newly
  -loaded desk.
- `get_view_state() -> tuple[float, float, float]` / `set_view_state(pan_x,
  pan_y, scale)`: read/restore pan position (`self
  .horizontalScrollBar().value()`/`verticalScrollBar().value()`, or
  simpler — track pan via the view's own transform translation) and zoom
  scale, for `Desk.pan_x`/`pan_y`/`scale` round-tripping.

### `desk.app.main()` (edit)

- `initial_directory = Path.cwd()`.
- Determine the starting desk path: `discover_desk_files(initial_directory)`
  — if non-empty, use the most-recently-modified one; otherwise
  `default_desk_path(initial_directory)` (a path that may not exist yet —
  `DeskWindow` treats that as a brand-new empty desk).
- Pass this path into `DeskWindow`, which loads (or creates) the `Desk` at
  construction time, same as described above.

## Affected files

- `src/desk/desks.py` (new) — `WidgetState`, `Desk`, `default_desk_path`,
  `discover_desk_files`, `load_desk`, `save_desk`.
- `src/desk/recent_desks.py` (new) — `load_mru`, `add_to_mru`,
  `MAX_MRU_ENTRIES`, `MRU_PATH`.
- `src/desk/shell/desk_picker.py` (new) — `DeskPicker`.
- `src/desk/shell/window.py` (edit) — desk lifecycle (load/save/switch/
  change-directory), `DeskPicker` wiring, widget instantiation now driven
  by `Desk.widgets` instead of always placing one of every discovered
  widget.
- `src/desk/shell/canvas.py` (edit) — `clear_widgets()`,
  `get_view_state()`/`set_view_state()`.
- `src/desk/app.py` (edit) — determine the initial desk path from CWD,
  pass it to `DeskWindow`, connect `aboutToQuit` to
  `window.save_current_desk`.
- `design-docs/architecture.md` (edit) — replace the old "Workspace
  Persistence" section with the real Desk model (per
  `development-process.md`'s requirement to keep design docs current).

## Explicitly out of scope (for now)

- The widget *catalog* (available widget **types**, from
  `DEFAULT_WIDGETS_DIR`) stays the fixed repo `widgets/` directory,
  decoupled from a Desk's own associated directory. A Desk's directory is
  only about where its `.desk` file lives, not where widget types come
  from — noted as an open question for a future item (should widget
  discovery itself become directory-scoped, e.g. a per-project
  `widgets/` folder?).
- Continuous/debounced autosave. Desks are saved on quit and on any
  desk-switch/directory-change (which always saves first) — not on every
  individual drag/resize. Noted as future work if that granularity turns
  out to matter in practice.
- Multiple windows / multiple desks open at once (the TODO item itself
  scopes this to one window, one desk).
- Renaming a desk in place (its name is just its filename — renaming would
  be a file-rename, not a feature of the picker UI itself, for now).

## Verification

1. Headless: `save_desk`/`load_desk` round-trip — build a `Desk`, save,
   load, confirm the reloaded object matches (widgets, pan, scale).
2. Headless: `add_to_mru` — dedup/move-to-front/cap-at-`MAX_MRU_ENTRIES`
   behavior, and that `load_mru` drops entries whose files no longer
   exist.
3. Headless: `DeskPicker` — construct it, confirm it starts collapsed
   (label visible, controls hidden), simulate `enterEvent`/`leaveEvent`
   and confirm it toggles correctly; confirm `set_mru` populates the
   dropdown with the expected names plus a trailing `"..."`.
4. Headless: `DeskWindow._load_desk_widgets` — a `Desk` with a couple of
   `WidgetState`s (referencing the real `demo` widget id) produces frames
   at the expected positions/sizes; an *empty* `Desk` falls back to
   placing one of every discovered widget (today's behavior), so existing
   single-widget setups aren't disrupted.
5. Full-cycle: launch `python -m desk` in a throwaway empty directory
   (via `cwd=`), confirm it creates/places the demo widget same as always
   (fresh desk), quit it, confirm a `default.desk` file now exists in that
   directory with the demo widget's state captured, then launch again in
   the *same* directory and confirm it loads that saved state (e.g. a
   moved/resized widget from the first run reappears in the same spot on
   the second run) rather than re-placing a fresh default layout.
6. Confirm the app still starts/quits cleanly from the repo's own
   directory too (the common case, unaffected by this change beyond now
   also writing/reading a `default.desk` file there).
7. Visual confirmation of the picker's hover-expand behavior and directory
   -picker/file-picker dialogs themselves is expected to be **skipped**,
   per the precedent in `plans/desk-shell.md` and later plans (this
   environment can't drive real mouse hover or native file dialogs
   interactively) — the structural/logic pieces above are checked directly
   instead.

### Status (verification notes)

- Headless: `save_desk`/`load_desk` round-trip confirmed exact
  (widgets/pan/scale all match after a save+load cycle);
  `default_desk_path`/`discover_desk_files` confirmed correct.
- Headless: `add_to_mru` dedup/move-to-front/cap-at-10 and `load_mru`'s
  missing-file filtering all confirmed with a patched `MRU_PATH` (never
  touched the real `~/.desk/recent_desks.json` during this specific
  test).
- Headless: `DeskPicker` confirmed starting collapsed (label visible,
  controls hidden); `enterEvent`/`leaveEvent` correctly toggle it;
  `set_mru` populates the dropdown with names + trailing `"..."` and
  selects the current entry; `desk_chosen`/`browse_requested` signals
  fire correctly for MRU vs. `"..."` selections.
- Headless: `DeskWindow` with a real `WidgetInfo` catalog — an empty
  (never-saved) `Desk` falls back to placing one instance of every
  discovered widget (today's pre-Desk behavior preserved); a `Desk` with
  saved `WidgetState`s places exactly those, at the saved positions/sizes.
  **Found and fixed a real bug here**: `WidgetState.width`/`height` are
  floats (from `QSizeF`), but `QWidget.resize()` requires ints — fixed by
  rounding in `DeskWindow._load_desk_widgets`.
- Headless: `switch_desk` — declining confirmation is a no-op (no save,
  no switch); confirming saves the *previous* desk first (verified its
  file appears with the correct captured state), then loads the new one.
  `change_current_desk_directory` — confirmed it re-points `current_desk
  .path` at the new directory and saves there, keeping the same widget
  state.
- **Found and fixed a second real bug**: `QGraphicsView.centerOn()` is
  clamped by the scene's auto-computed bounding rect (derived from
  current items) — on a view with only a couple of widgets, requesting a
  saved pan point far from them silently landed somewhere else entirely.
  Fixed by giving `WorkspaceView` a large, fixed `sceneRect()`
  (±100,000) at construction, so pan restoration isn't constrained by
  wherever widgets currently happen to be. Re-verified the view
  -state round-trip afterward (works within ~1px of rounding), and
  re-ran the existing drag/resize and zoom-to-fit/reset regression
  checks from prior plans to confirm this didn't disturb them.
- Full-cycle: launched `python -m desk` in a throwaway empty directory;
  confirmed it placed the demo widget (fresh-desk fallback) and, on quit,
  wrote a `default.desk` file there capturing its state. Manually edited
  that file to a distinctive position, relaunched in the *same*
  directory, and confirmed (via a second quit) that the distinctive
  position was preserved — proving the saved state is actually loaded on
  the next launch, not silently regenerated.
- Confirmed the app still starts/quits cleanly launched from the repo's
  own directory too (the ordinary case), and that the `default.desk` it
  creates there is correctly excluded by `.gitignore` (added a `**/*.desk`
  entry) — cleaned up the test-generated file afterward.
- Visual confirmation of the picker's hover-expand animation and the
  native directory/file-picker dialogs themselves is, as anticipated,
  **skipped** — this environment can't drive real mouse hover or native
  dialogs interactively (same limitation noted throughout this project).

## Key design decisions / tradeoffs

- **`.desk` file extension, name = file stem.** Directly satisfies the
  TODO item's "the Desk's name is the filename of its serialized file"
  while keeping the extension self-documenting.
- **MRU is global (`~/.desk/recent_desks.json`), not per-directory.** A
  "recently used" list scoped to only the current directory would almost
  always contain just the one desk you're already looking at — the useful
  version of "recently used" spans directories/sessions, which is also
  the ordinary meaning of MRU in most apps (recent files list).
- **Confirmation dialog is injectable (`confirm=` parameter), not
  hardcoded to `QMessageBox`.** Lets the switch/change-directory logic be
  exercised headlessly (auto-confirm/auto-decline) without needing a real
  interactive dialog, while defaulting to a real one for actual use.
- **Always save-before-switch, rather than a three-way "save / discard /
  cancel" dialog.** Removes any possibility of silently losing widget
  layout changes, and keeps the confirmation itself a simple yes/no
  ("Switch to X?") matching the TODO item's literal ask ("with
  confirmation") without needing extra UI for a discard path nobody asked
  for.
- **Directory-change button re-saves to the new location rather than
  moving/deleting the old file.** Safer default (no data loss if the user
  picks the wrong directory) at the cost of potentially leaving a stale
  copy behind — acceptable for now; a real "move" could be added later if
  that clutter becomes a real problem in practice.
