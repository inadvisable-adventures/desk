# Markdown renderer widget (file-watched) (COMPLETED)

TODO `6bf83a9`.

## Summary

"Add a markdown renderer widget which puts a file watcher on a markdown
file and renders it." A new `kind: "python"` widget (`widgets/markdown/`)
that opens a Markdown file, renders it, and auto-reloads when that file
changes on disk.

## Key decisions

- **Rendering: `QTextBrowser.setMarkdown()`** — Qt 6.11 renders
  CommonMark + GitHub tables natively into a `QTextDocument`. No
  Markdown library is installed and `CLAUDE.md` says to avoid adding
  dependencies / prefer bespoke solutions, so this native path is the
  right fit (no hand-rolled parser, no new dep). `QTextBrowser` is
  read-only and supports link navigation; `setOpenExternalLinks(True)`
  so links open in the system browser.
- **File selection: an "Open" button**, mirroring the editor widget's
  shape (an `Open` button + a filename label in a small toolbar above
  the view). The Open dialog's initial directory seeds from the current
  Desk's directory via `desk.shell.current_context` (falling back to
  `Path.home()`), exactly like `EditorWidget._last_dir`. Starts on a
  placeholder ("No file open — click Open…") until a file is chosen.
- **No cross-reload persistence of the chosen file** (matches the
  editor widget, which also doesn't persist its open file): the widget
  contract has no per-instance custom state payload, and adding one is a
  broad, separately-parked architectural question. Out of scope here;
  logged as a follow-up in `PARKINGLOT.md` alongside that question.
- **File watching: extract a reusable `desk.file_watch.SingleFileWatcher`**
  rather than hand-roll a fourth ad-hoc watcher. The TODO widget already
  has a correct single-file watcher (`_SingleFileHandler` /
  `_start_file_watcher`) that bakes in two hard-won gotchas from
  `LEARNINGS.md` — FSEvents reports symlink-*resolved* paths (so both
  the target and each event path must be `.resolve()`d), and an atomic
  write lands as a `FileMovedEvent` whose meaningful path is
  `dest_path`, not `src_path`. Extracting a clean, self-contained
  `SingleFileWatcher(QObject)` (a `changed` signal, `watch(path)`,
  `stop()`) into `desk.` proper (importable by widgets, same as
  `desk.terminal_widget`) makes that correctness reusable and keeps a
  new watcher from silently repeating those bugs. The existing TODO
  widget watcher is left as-is for now (its self-write-suppression is
  coupled to its state dict); consolidating it onto the shared helper is
  noted as a follow-up in `PARKINGLOT.md`.

## New/affected files

- `src/desk/file_watch.py` (new) — `SingleFileWatcher(QObject)`:
  `changed = pyqtSignal()`, `watch(path)` ((re)starts a `watchdog`
  `Observer` on the file's parent dir, only if the path changed),
  `stop()` (stops the observer; safe to call from a teardown closure —
  touches only the watchdog `Observer`, no Qt state). Encapsulates the
  resolve-both-paths and `FileMovedEvent`/`dest_path` gotchas, with the
  same 0.3s debounce as the TODO widget's watcher.
- `widgets/markdown/widget.json` (new) — `{name: "Markdown", kind:
  "python", entry: "widget.py", capabilities: [], default_size: 560x640}`.
- `widgets/markdown/widget.py` (new) — `MarkdownWidget(QWidget)`:
  toolbar (`Open` button + filename label), a `QTextBrowser`,
  `_open_file` (QFileDialog filtered to Markdown, seeded from the Desk
  dir), `_load_current`/`_reload` (`setMarkdown(path.read_text())`, or a
  "file no longer exists" note if it was deleted, still watching so a
  recreate reloads), `_show_placeholder`, and a `SingleFileWatcher`
  whose `changed` triggers `_reload`. `destroyed` connects to a closure
  that stops the watcher (mirroring the TODO widget's teardown pattern —
  capture the watcher in a local, don't touch `self`). `build() ->
  MarkdownWidget()`.
- `design-docs/architecture.md` — new component entry for the Markdown
  Widget (and note the shared `desk.file_watch`).

## Verification

Headless, against a real temp Markdown file:
- `setMarkdown` renders a file's content (assert the rendered
  `QTextBrowser.toPlainText()` reflects the source, e.g. heading/bold
  text present, markdown syntax stripped).
- `SingleFileWatcher`: pointed at a real temp file, an external
  `write_text` fires `changed` (within a short wait), and after
  `stop()` it no longer fires. Both a plain write and an
  atomic-write (scratch-name-then-`os.rename`) are detected (the
  `FileMovedEvent`/`dest_path` path), and pointing it at a path inside a
  `tempfile.mkdtemp()` symlinked dir still matches (the resolve gotcha).
- `MarkdownWidget` end-to-end: `_load_current` on a chosen file renders
  it; editing the file on disk and pumping the event loop auto-updates
  the rendered content via the watcher; the placeholder shows before any
  file is chosen; a deleted file shows the "no longer exists" note
  without crashing.
- A full-app `DeskWindow` regression: place a real `markdown` widget and
  confirm it builds/renders a file.

## Status

**Completed.** Implemented and verified headlessly as described above:
`SingleFileWatcher` (plain write, atomic-write/rename, symlinked-tempdir
resolve, unrelated-file ignore, `stop()`, restart); the `MarkdownWidget`
(placeholder, render-a-file, external-edit auto-reload, deleted-file
note, recreate-reloads); and a full-app `DeskWindow` regression
confirming the widget is discovered, placeable, and renders.
`design-docs/architecture.md` gained a Markdown Widget entry; two
follow-ups logged in `PARKINGLOT.md` (per-instance file persistence tied
to the broader widget-state-payload question, and consolidating the TODO
widget's watcher onto the shared `desk.file_watch`).
