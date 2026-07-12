# Paste clipboard content from the widget menu (COMPLETED)

TODO `f74945e`.

## Summary

A "Paste" entry at the top of the right-click widget-add menu, shown
only when the clipboard actually has content. Clicking it writes the
pasted material into a new `.desk_temp/<uuid>` tempui file and opens
it immediately in whichever widget the content calls for: the new
`Markdown <label>` DSL entry (TODO `9743419`) for markdown text, the
existing `Scratch <label>` DSL entry (TODO `f8d9cec`) for any other
text, or -- since binary content can't be represented in the
line-based tempui DSL at all -- a real file saved directly into the
project directory as `PASTED-ITEM-<timestamp>.<ext>` for anything
that isn't text.

## Key decisions

- **Detecting "is the pasted text markdown."** There's no reliable
  general way to *sniff* whether arbitrary text is "meant as markdown"
  -- a line starting with `#` is just as often a comment or a heading
  in something else entirely. Rather than guess with a fragile
  heuristic, this checks for an explicit `text/markdown` MIME flavor
  on the clipboard (`QMimeData.hasFormat("text/markdown")`, RFC 7763)
  -- some markdown-aware apps populate it, most don't, so this is a
  deliberately conservative signal: **text without it defaults to the
  Scratch (plain-text) bucket**, not silently misclassified as
  markdown. This is a real, testable technical criterion, not a
  guess -- if it turns out too conservative in practice, broadening
  the detection is a separate, later change with real usage data to
  inform it, not a upfront speculative heuristic.
- **Text (markdown or not) is written as a tempui file and opened
  immediately**, not left for the user to click a notification banner
  for -- the TODO's own text says "attempt to open it," and Paste is
  itself already a deliberate, explicit user action (unlike an agent
  silently dropping a file the user hasn't asked about yet, which *is*
  the right case for a notification banner). `record_own_write` (the
  same mechanism `TempUiManager` already uses to suppress a spurious
  self-echo notification) is called with the freshly-written content
  right after writing, so this immediate placement doesn't *also*
  trigger a redundant "New question: <uuid>" banner once the
  directory watcher notices the same file a moment later.
- **Placed at the right-click position, not view-center.** The Paste
  entry lives in the exact same right-click menu as "Add Widget"
  entries, which place at the click's scene position
  (`widget_add_requested`) -- for consistency, pasted content should
  land there too, not jump to wherever the view happens to be
  centered. This means a few lines of placement logic parallel to (not
  reused from) `_activate_temp_ui`'s own "else" branch, which
  deliberately centers instead (right for a notification click, where
  there's no "where the user clicked" concept) -- the two have
  genuinely different placement semantics, not an accidental fork.
- **DSL label**: the pasted text's own first non-empty line
  (`#`/whitespace-stripped), falling back to a plain "Pasted content"
  if the text is all blank lines -- reuses the same "derive something
  human-readable from the content's own first line" idea the Markdown
  widget's save-as filename derivation already uses, just for the
  DSL's notification-text label instead of a filename.
- **Binary (image) content**: `QClipboard.image()` (a `QImage`) saved
  as `PASTED-ITEM-<YYYYmmdd-HHMMSS>.png` directly in the project
  directory -- not opened in any widget, matching the TODO's own
  wording for this case exactly (it describes saving, not opening,
  unlike the markdown/text cases). PNG is used unconditionally rather
  than sniffing a "real" source format, since clipboard image data
  doesn't reliably carry one and PNG loses nothing.
- **Menu changes are additive and minimal**: a new `_paste_item`
  (outside the existing Active/Deprecated `QTreeWidgetItem` groups,
  inserted first) on `WidgetSpawnMenu`, a `paste_requested` signal,
  and `_visible_entries()`/keyboard-nav extended to include it --
  filtering by typed text still only touches the widget-catalog
  groups, so Paste stays pinned at the top regardless of what's typed.

## Affected files

- `src/desk/shell/widget_spawn_menu.py` -- `_paste_item`,
  `paste_requested` signal, activation/keyboard-nav handling.
- `src/desk/shell/canvas.py` -- `WorkspaceView.paste_requested` signal,
  wired in `contextMenuEvent` alongside `widget_add_requested`.
- `src/desk/shell/window.py` -- `_on_paste_requested`, wired in
  `__init__`.

## Verification

Headless (`QT_QPA_PLATFORM=offscreen`, real `QApplication`, a real
clipboard via `QApplication.clipboard()` -- offscreen platform still
supports an in-process clipboard):

- `WidgetSpawnMenu`: with clipboard text set, the menu shows a Paste
  item first and emits `paste_requested` on activation; with an empty
  clipboard, no Paste item appears at all.
- `DeskWindow._on_paste_requested` (unbound method on a fake double,
  the established pattern for `DeskWindow`-dependent logic): clipboard
  text with a `text/markdown` flavor writes a `Markdown <label>`
  -prefixed tempui file and opens the markdown widget at the click
  position; plain clipboard text (no such flavor) writes a
  `Scratch <label>`-prefixed file and opens the scratch widget;
  clipboard image data writes a real `PASTED-ITEM-*.png` file into the
  project directory and opens no widget; an empty clipboard is a
  no-op.
- Confirms `record_own_write` is called with the exact written text so
  the directory watcher's own notification path doesn't also fire for
  the same paste.

## Status

Implemented as planned: `WidgetSpawnMenu._paste_item`/`paste_requested`
in `src/desk/shell/widget_spawn_menu.py`; `WorkspaceView.paste_requested`
in `src/desk/shell/canvas.py`; `DeskWindow._on_paste_requested`/
`_paste_text_as_temp_ui`/`_paste_image_as_project_file` in
`src/desk/shell/window.py`. Also updates `design-docs/widget-ux.md`'s
Add Widget Menu section.

Verified headlessly (`QT_QPA_PLATFORM=offscreen`, real `QApplication`
and a real `QApplication.clipboard()` -- the offscreen platform
supports an in-process clipboard): the menu shows/hides the Paste item
based on real clipboard state and emits `paste_requested` on
activation; `DeskWindow._on_paste_requested` run unbound against a
fake double (the established pattern for `DeskWindow`-dependent logic)
covers clipboard text with a `text/markdown` flavor (writes and opens
a `Markdown <label>`-prefixed file at the click position), plain text
(writes and opens a `Scratch <label>`-prefixed file), a clipboard
image (saves a real `PASTED-ITEM-*.png` project file, opens no
widget), and an empty clipboard (no-op) -- also confirms
`record_own_write` is called with the exact written text.

One thing caught during verification, fixed in both call sites: on the
offscreen platform (used here, and plausibly some other headless
environments), `QApplication.clipboard().mimeData()` can return `None`
for a genuinely empty clipboard rather than an empty-but-real
`QMimeData` -- both `WidgetSpawnMenu.__init__` and
`DeskWindow._on_paste_requested` now guard for `None` before calling
any `QMimeData` method.

Regression-checked: re-ran the tempui-live-refresh, Questions
-notification, drag-and-drop, new-Desk-seeding, and the existing
`WidgetSpawnMenu` grouping/keyboard-nav verification scripts -- all
still pass unaffected.
