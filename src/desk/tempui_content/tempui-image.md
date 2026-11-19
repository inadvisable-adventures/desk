# TempUI DSL: OpenImage

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
just covers the `OpenImage` keyword.

For telling Desk to open an image file in the Image Viewer widget — a
fire-and-forget instruction, not a question: there is no `Answer`
line, and Desk never writes back to this file. This is a *pointer* to
an existing file elsewhere on disk, the same shape as `OpenMarkdown`
(see [tempui-markdown.md](./tempui-markdown.md)) — there is no
inline-content sibling keyword for images.

- `OpenImage <path>` — the first (and normally only) line. `path` is
  the file to open, absolute or relative to the current Desk's
  directory. Like `Question <text>`, everything after the first space
  is one opaque value, so a path containing spaces needs no escaping.

Example:

```
OpenImage ./screenshot.png
```

Clicking the notification opens `path` in a new Image Viewer widget
instance, centered in the current view.

Dropping an image file directly onto the Workspace Canvas uses this
same mechanism automatically: the dropped image is copied into this
directory first, then an `OpenImage` file pointing at the copy is
created and opened immediately (no notification needed for your own
just-performed drop).
