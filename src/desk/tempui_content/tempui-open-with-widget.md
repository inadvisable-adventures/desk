# TempUI DSL: OpenWithWidget

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file just
covers the `OpenWithWidget` keyword.

For placing *any* widget kind with a file pre-loaded — a fire-and
-forget instruction, not a question: there is no `Answer` line, and
Desk never writes back to this file. `OpenMarkdown`/`OpenImage`
(above/[tempui-image.md](./tempui-image.md)) are each a fixed,
one-keyword-per-widget special case; `OpenWithWidget` is the generic
form, for any other widget kind that supports being opened with a
file. This is a *pointer* to an existing file elsewhere on disk, the
same shape as `OpenMarkdown`/`OpenImage`.

- `OpenWithWidget<TAB>widget_id<TAB>path[<TAB>label]` — the first (and
  normally only) line, **tab-separated** (like `DefineWidget`), since `path` may
  itself contain spaces. `widget_id` is a real, currently-discovered
  widget id (the same id `desk.workspace.getState()`/
  `desk_list_widget_instances` report per instance, or a `DefineWidget`
  keyword once placed at least once) — an unknown or misspelled one is
  a silent no-op, not an error, so double-check it against a live
  instance or the widget's own `widget.json`/`DefineWidget` line if
  nothing happens. `path` is the file to open, absolute or relative to
  the current Desk's own directory. The optional fourth field, `label`,
  is the text shown in the notification (otherwise it reads `Open
  <path>`). Use it when the widget doesn't actually consume a file --
  e.g. to just place the Microservices widget, give `path` any
  existing path and a `label` like `New microservice` so the
  placeholder path isn't what the user sees.

Example:

```
OpenWithWidget	sheet	./derived/results.tsv
```

Clicking the notification places a new instance of `widget_id`,
centered in the current view, with `path` already loaded — exactly as
if you'd placed it yourself and used its own Open dialog (a
`kind: "python"` widget implementing `set_file`) or read it back via
`desk.self.getOpenedFile()` (a `kind: "html"` widget, TODO 83427f4).
**Only works for a widget kind that actually supports one of those two
mechanisms** — a widget with neither is placed with nothing loaded,
the same as placing it any other way.
