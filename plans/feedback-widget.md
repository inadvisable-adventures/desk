# Feedback widget: screenshots + UI-element picker

TODO `f2aede6`.

## Summary

A new `widgets/feedback/` widget: a text area for writing feedback,
a **Screenshot** button that captures the app's own window and embeds
it (a markdown image reference, inserted into the text) so "Save
Feedback" later writes both the `.md` and the attached PNG(s)
together, and a **Pick UI Element** button that shows a full-screen
overlay over the app's own window -- clicking any UI element through
it inserts a short, human-readable identifying path for that element
into the feedback text (at the current caret position if the text area
has one, else appended at the end).

## Key decisions

- **Two new `current_context` hooks**, matching the existing
  minimal-module-level-get/set-pair shape (`set_widget_opener`/
  `set_temp_ui_write_recorder`) rather than a one-off special case:
  - `set_main_window`/`get_main_window` -- the real `DeskWindow`
    instance, set once at construction. Gives the widget something to
    `.grab()` for a screenshot and something to parent the pick
    -overlay to, without importing `desk.shell.window` directly (kept
    decoupled the same way `get_widget_opener` already avoids that).
  - `set_widget_path_resolver`/`get_widget_path_resolver` -- a
    `Callable[[QPoint], str | None]` (global screen position -> a
    descriptive path, or `None` if nothing meaningful is there), set
    once by `DeskWindow` to a small wrapper around a new
    `WorkspaceView.describe_widget_at_global_pos` method.
- **Screenshot is "internal" -- `main_window.grab()`, not OS-level
  screen capture.** Matches the TODO's own "internal screenshots of
  the app" wording; also sidesteps needing any OS screen-recording
  permission a real screen-capture API would require.
- **Path resolution has to go through `WorkspaceView`'s own item
  -level hit-testing for anything embedded in a `WidgetFrame`.**
  Confirmed directly (see `LEARNINGS.md`) that `QApplication.widgetAt`
  does *not* resolve into `QGraphicsProxyWidget`-embedded content --
  it returns some generic internal Qt widget, not the actual embedded
  control -- the same category of gotcha already documented for
  `QApplication.focusChanged`. `describe_widget_at_global_pos` mirrors
  `_hit_test_chrome`'s own `itemAt` + `childAt` shape, generalized to
  *any* widget (not just recognized chrome types), and falls back to
  plain `childAt`/`parentWidget()` walking for anything that isn't a
  scene item at all (the floating HUD chrome -- Desk picker, zoom
  control, ...).
- **Path format is a plain, best-effort `" > "`-joined breadcrumb**
  of `ClassName["label"]` (using `.text()` when the widget has one,
  e.g. a button/label) from the resolved widget up to its `WidgetFrame`
  (labeled with the widget's own title) or the `WorkspaceView`/main
  window, whichever is reached first. Deliberately not a rigorous
  formal selector language -- this is meant to help a human reader
  identify roughly what was clicked, not to be replayed
  programmatically.
- **The overlay is a child of the main window, not a separate OS-level
  top-level window**, sized to the main window's own `rect()` --
  consistent with "internal"/scoped-to-the-app framing. A single left
  click resolves the path, emits it, and closes the overlay; Escape
  cancels (emits nothing).
- **Screenshot/path insertion point**: `QPlainTextEdit`'s own current
  text cursor -- inserting at the cursor position naturally lands "at
  the current caret position," and naturally lands "at the end" too
  when the cursor is already there (e.g. nothing has been clicked into
  yet) -- no separate "has a caret vs. hasn't" branch needed, since a
  `QPlainTextEdit`'s cursor always has *some* position.
- **Filenames locked in once, reused consistently.** The very first
  screenshot taken (or, if none, the moment Save Feedback runs)
  decides one `DESK-feedback-<timestamp>` base name, reused for the
  `.md` file and every `-screenshot-N.png` -- avoids generating a
  placeholder filename at insert time and having to rewrite it later
  to match the real save-time timestamp.
- **Written into the current Desk's directory (project root)**, not
  `.desk_temp` -- unlike a crash log (a private diagnostic artifact,
  moved *out* of the project root under TODO `7f51230`), feedback is
  explicitly meant to be reviewed/shared, the same target directory
  TODO `f74945e`'s binary-paste feature already uses for its own
  user-facing saved artifacts.
- **Re-checks the target `.md` path immediately before writing**
  (TODO `4716585`'s established "check right before create, treat
  already-exists as a normal branch" pattern) -- an exceedingly
  unlikely timestamp collision just means Save Feedback quietly
  doesn't overwrite, rather than silently clobbering something.

## Affected files

- `src/desk/shell/current_context.py` -- `set_main_window`/
  `get_main_window`, `set_widget_path_resolver`/
  `get_widget_path_resolver`.
- `src/desk/shell/canvas.py` -- `WorkspaceView
  .describe_widget_at_global_pos`.
- `src/desk/shell/widget_frame.py` -- `WidgetFrame.title` property
  (previously only accessible via the private `_titlebar._title`).
- `src/desk/shell/window.py` -- wires both new hooks in `__init__`.
- `widgets/feedback/widget.py` (new) -- `FeedbackWidget`,
  `_PickOverlay`.
- `widgets/feedback/widget.json` (new).

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, a real
`WorkspaceView` with an embedded `WidgetFrame` for the path-resolution
checks):

- `describe_widget_at_global_pos`: a global position over an embedded
  button resolves to a path ending in that button's own
  `ClassName["label"]`, prefixed by its `WidgetFrame`'s title; a
  position over nothing meaningful (blank canvas) returns `None`; a
  position over a floating HUD child (not a scene item) still resolves
  via the plain-widget fallback.
- `current_context`'s two new hooks round-trip correctly (set then
  get), matching the existing pair's own shape.
- `FeedbackWidget`: taking a screenshot (via a patched
  `current_context.get_main_window` returning a real, `.grab()`-able
  widget) inserts the correct image-reference text and records one
  pixmap; a second screenshot uses the same base name with an
  incremented index. Picking (via a patched path resolver) inserts the
  resolved path text; picking with a resolver returning `None`
  (cancelled/nothing there) inserts nothing. Save Feedback writes the
  `.md` and each screenshot PNG with matching, consistent filenames
  into a real temp directory (via a patched `current_context
  .get_current_desk_directory`), and a second Save Feedback call
  (after clearing) starts a fresh base name rather than reusing the
  old one. A pre-existing file at the resolved `.md` path (simulating
  the timestamp-collision edge case) is not overwritten.
- `_PickOverlay`: a synthetic left-click emits the resolved path (via
  a patched resolver) and closes itself; Escape emits nothing and
  closes.

## Status

Not yet implemented.
