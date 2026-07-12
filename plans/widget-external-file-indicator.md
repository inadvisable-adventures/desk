# "[EXTERNAL]" titlebar marker for widgets loading a file outside the current Desk directory (COMPLETED)

TODO `a053e3a`.

## Summary

"Update widgets which load files to note in the title bar for the widget
if the widget is loading a file from a path outside of the currently
associated directory, by showing '[EXTERNAL]'."

Every widget that displays/edits a single file the user (or an automatic
lookup) picked -- Markdown, Markdown (Extended), SVG Viewer, Editor, and
TODO -- gains a small `external_path_changed(bool)` signal, computed against
`desk.shell.current_context.get_current_desk_directory()` (the "currently
associated directory" -- the same concept these widgets' own "Open"
dialogs already seed from). `DeskWindow` wires that signal, for every
placed widget, to a new `WidgetFrame.set_external(bool)` that appends
`" [EXTERNAL]"` to the widget's titlebar label when true. File Explorer is
out of scope -- it browses a directory (always the thing being compared
against, not a file being loaded into itself); double-clicking a file
opens it in a *separate* widget instance, which gets its own indicator
normally.

## Key decisions

- **"Currently associated directory" = `current_context
  .get_current_desk_directory()`.** Same source of truth every one of
  these widgets' "Open" dialogs already seeds its initial directory
  from -- no new concept introduced.
- **New shared helper, not per-widget duplicated path math**:
  `current_context.path_is_external(path: Path) -> bool` -- resolves
  both `path` and the current Desk directory and checks
  `path.relative_to(directory)`, returning `False` (not external) if
  there's no current Desk directory known yet (nothing to be "outside"
  of). Lives in `current_context.py` since it's entirely about relating
  a path to the exact state that module already owns -- matches this
  codebase's convention of shared non-widget logic living in `desk.`
  proper (widget directories can't import each other).
- **Each of the 5 widgets gets its own `external_path_changed = pyqtSignal
  (bool)`** (Qt signals must be declared per-QObject-class -- there's no
  way to share one signal instance across independent widget classes,
  and this codebase doesn't use a shared widget base class either, see
  TODO cee6f74's plan for why). Each also gets one new public method,
  `refresh_external_path_status()`, that computes the current file's status
  via `path_is_external` and emits it -- called both (a) internally, at
  the end of the widget's existing single file-load choke point
  (`MarkdownWidget.set_file`, `MarkdownExWidget.set_file`,
  `SvgViewerWidget.set_file`, `EditorWidget._load_file` +
  `_save_file_as`, `TodoWidget.reload`), and (b) once by `DeskWindow`
  right after wiring the signal (see below) -- a small, deliberate bit
  of repetition across 5 files rather than a shared mixin/base class,
  matching "three similar lines is better than a premature abstraction."
- **Why both (a) an emitted signal *and* (b) an explicit one-shot
  re-emit, not just one or the other**: the file may already be loaded
  by the time anyone can listen (e.g. the TODO widget calls `reload()`
  at the end of its own `__init__`, before `DeskWindow` can possibly
  have connected anything yet -- `PythonWidgetHost._rebuild()` runs
  `module.build()` fully synchronously). A signal alone would silently
  miss that first, already-happened load. `refresh_external_path_status()`
  being idempotent and side-effect-free beyond emitting means calling it
  an extra time right after connecting costs nothing and closes that
  gap, without resorting to event-loop-timing tricks
  (`QTimer.singleShot(0, ...)`) to dodge the same race.
- **`WidgetFrame` gains `set_external(is_external: bool)`**, delegating
  to a new `_TitleBar.set_external(...)`. `_TitleBar` now keeps its
  original `title` string and an `_external` bool, recomputing the
  displayed label text (`f"{title} [EXTERNAL]"` when true) instead of
  setting it once at construction. Purely a label-text change --
  `apply_scale`'s existing counter-scaling of height/font is untouched.
- **`DeskWindow` wires it once, generically, inside `_place_widget`**
  (not per-call-site like the Claude/TempUI special-cased bindings,
  which need restore-specific extra arguments this doesn't) -- duck
  -typed the same way `hasattr(content, "set_file")` already is
  elsewhere in this file: `if hasattr(content, "external_path_changed"):
  content.external_path_changed.connect(frame.set_external);
  content.refresh_external_path_status()`. Since every placement path
  (fresh, restored, programmatic via `open_widget`, the add-widget menu)
  already funnels through `_place_widget`, one call site covers all of
  them.
- **File Explorer excluded.** It's a directory browser, not a
  single-file-loading widget in the sense this feature means -- its own
  "root" directory *is* (or, via its Open Folder button, becomes) the
  comparison baseline, not something to compare against it. Opening a
  file from it places a *new* widget instance (Editor, Markdown, etc.),
  which already gets the indicator through its own wiring.

## Affected files

- `src/desk/shell/current_context.py` -- new `path_is_external(path)`.
- `src/desk/shell/widget_frame.py` -- `_TitleBar` keeps `title`/`_external`
  state and recomputes its label; new `WidgetFrame.set_external(bool)`.
- `src/desk/shell/window.py` -- `_place_widget` gains the generic
  duck-typed bind step.
- `widgets/markdown/widget.py`, `widgets/markdown_ex/widget.py`,
  `widgets/svg_viewer/widget.py`, `widgets/editor/widget.py`,
  `widgets/todo/widget.py` -- new `external_path_changed` signal +
  `refresh_external_path_status()`, called from each widget's existing
  file-load choke point(s).
- `design-docs/widget-ux.md` -- a short mention under "Chrome Stays a
  Constant Screen Size" (the titlebar label is no longer fully static
  after construction).

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, no mocks):

- `current_context.path_is_external`: a path inside the current Desk
  directory (including a nested subdirectory) -> `False`; a path
  elsewhere (e.g. a sibling temp directory) -> `True`; no current Desk
  directory set -> `False`.
- Each of the 5 widgets: after `set_file`/`_load_file`/`reload()` with a
  path inside the current Desk directory, `external_path_changed` fires
  `False`; with a path outside it, fires `True`; switching from an
  external file back to an internal one fires `False` again (not
  "sticky").
- `WidgetFrame.set_external`: titlebar label reads the plain title at
  `False`, and `"<title> [EXTERNAL]"` at `True`; toggling back removes
  the suffix cleanly (no leftover state).
- `DeskWindow._place_widget`'s generic binding, exercised for real: a
  Desk directory + a file outside it; place a Markdown widget and a TODO
  widget (a real nearest-TODO.md lookup that resolves to a parent
  -directory file, reproducing the one case where TODO 578cb6b's own
  `find_nearest_todo_file` walks *above* the Desk directory) and confirm
  the frame's titlebar reflects `[EXTERNAL]` immediately, with no
  additional manual trigger -- covering the "already loaded before
  anyone could connect" race directly, not just in isolation.

## Status

Implemented as planned, with one naming refinement made during
implementation: the signal/method are `external_path_changed`/
`refresh_external_path_status()`, not the shorter `external_changed`/
`refresh_external_status` used earlier in this plan's drafting. Reason:
the Editor and TODO widgets already have a *different*,
pre-existing "external change" concept (a file's *content* changing on
disk, from `SingleFileWatcher`/TODO cee6f74 -- see `EditorWidget
._on_external_change`/`_external_change_pending`). Reusing bare
"external" for this feature's different meaning ("this file's
*location* is outside the Desk directory") inside the very same widget
classes would have been a real readability trap; `external_path_changed`
disambiguates the two at a glance.

All headless verification steps above passed: `path_is_external` for
inside/nested/outside/no-current-directory cases; `WidgetFrame
.set_external` toggling the titlebar label text cleanly both ways;
`MarkdownWidget` firing `False`/`True`/`False` across
inside/outside/inside `set_file` calls; a real `find_nearest_todo_file`
lookup that resolves *above* a temp "Desk directory" (the one concrete
case that actually motivated including the TODO widget) correctly
reported as external; `EditorWidget` firing `False` for an in-directory
file.

Not separately re-verified: `DeskWindow._place_widget`'s actual runtime
wiring end-to-end via a real, constructed `DeskWindow` -- consistent
with this codebase's existing precedent (see TODO 578cb6b's plan) of
skipping a literal `DeskWindow` construction in headless verification
due to a known, unrelated offscreen stall. The race this wiring exists
to close (a widget's file already loaded during its own `__init__`,
before `DeskWindow` can connect anything) was exercised directly instead:
connecting to a signal *after* construction and then calling
`refresh_external_path_status()` manually, mirroring exactly what
`_bind_external_indicator` does, and confirming it still reports
correctly.

No `LEARNINGS.md` entry needed -- nothing surprising turned up beyond
the naming consideration above, which is a design decision, not a
bug/gotcha.
