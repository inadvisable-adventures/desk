# Questions with optional answers

## TODO `b44e8ba`: segfault while interacting with the Desk picker -- need a reproduction

The reported crash (`Segmentation fault: 11`, no Python traceback) has
no captured repro steps beyond "interacting with the Desk picker" after
opening a `.desk` file. Code review (see
`plans/fix-desk-picker-segfault.md`) didn't turn up an obvious cause.

- What was the exact interaction right before the crash -- clicking the
  name label, clicking the directory label, just hovering, or something
  else (e.g. a trackpad gesture happening at the same time)?
- Does it reproduce consistently, or was it a one-off?
- Is there a macOS crash log for it (Console.app's "Crash Reports", or
  `~/Library/Logs/DiagnosticReports/`) with a real native stack trace?
  That would let this be root-caused directly instead of guessed at.

(Answer: )

## TODO `96013cf`/`858752b`: both name their rename target `markdown_old_basic` -- conflict

Two TODO items, added together, each rename a *different* widget to
the *same* new name:

- `96013cf`: rename `widgets/markdown/` (the plain Markdown widget) to
  `markdown_old_basic`.
- `858752b`: rename `widgets/markdown_ex/` (Markdown (Extended)) to
  `markdown_old_basic`.

Both can't be true -- two widget directories can't share one id/name.
Recorded verbatim as given rather than silently guessing which one was
meant, or inventing a different name for one of them.

- Which widget should actually become `markdown_old_basic`?
- Should the other one keep its current name, or get a different new
  name (e.g. something like `markdown_ex_old_basic`)? If so, what?

(Answer: good catch! markdown should become markdown_old_basic and markdown_ex should become markdown. we're replacing the old markdown widget with the new one, but we're keeping the old one around as deprecated.)

## TODO `9743419`: what makes a tempui file "markdown-based," and how should the save-a-copy filename be derived?

See `plans/markdown-rendering-doc-and-tempui-markdown.md` for full
context. Part 1 of this item (a Markdown-rendering-capabilities doc,
`markdown-rendering.md`) is done; parts 2/3 (Markdown (Extended)
rendering a tempui file directly, with a "save a copy" button) are
blocked on:

- Should "a tempui-based markdown file" be a **new explicit tempui
  keyword** (e.g. `Markdown <label>` as the first line, matching how
  `Scratch` -- TODO f8d9cec -- and `OpenMarkdown` already work), or
  should **any tempui file with no recognized keyword at all** fall
  back to being rendered as Markdown, instead of today's fallback to
  the Question widget? The second option changes existing,
  already-relied-upon fallback behavior for any malformed/typo'd
  tempui file, not just adding something new -- worth confirming
  before touching it.
- What's the actual filename-derivation algorithm for "a default file
  name derived from the first line of the markdown file" -- e.g. would
  `# My Investigation Notes` become `My Investigation Notes.md`
  verbatim, a slugified `my-investigation-notes.md`, or something else?

(Answer: option (a) -- a new explicit tempui DSL keyword, `Markdown
<label>`, matching Scratch/OpenMarkdown's shape. Unlike OpenMarkdown
(which points at an external target file), this one's own content
*is* the markdown to render, live, the same "render the tempui file
itself" pattern Question/LightningRound already use via
set_source_file -- not the fallback-for-any-unrecognized-keyword
option, which would have changed existing behavior. Placed on the new
default markdown widget (post-rename: markdown_ex becomes "markdown"),
since a tempui-bound instance shows a "Save As" button in place of
"Open" (no "open a different file" concept applies to a tempui-bound
instance). Saving writes the current content to a new file at the
project root, opens it in a *new*, ordinary file-backed markdown
widget instance, and leaves the original tempui-bound instance open
and still rendering live. The filename-derivation algorithm: slugified
to kebab-case, e.g. `# My Investigation Notes` -> `my-investigation
-notes.md`. "Save As" is scoped to just this widget for now --
generalizing something like it to other widgets is a separate, later
idea, not part of this TODO.)

## TODO `17ac2a8`: does anything reference the old basic markdown widget in a way that needs updating post-rename?

See `plans/audit-old-basic-markdown-widget-usage.md`. Searched the
whole codebase for any hardcoded markdown-widget-id reference (the
only way one widget opens another is `current_context
.get_widget_opener()("<widget_id>")`, since widget directories can't
import each other).

(Answer: only one real reference exists -- the TODO widget's "open
plan" button (`widgets/todo/widget.py`'s `_open_hovered_plan`),
`opener("markdown")` + `set_file(plan_path)`. It already used the
*id* `"markdown"`, not anything specific to the old plain widget, so
the TODOs 96013cf/858752b rename already transparently upgrades it to
the new, strictly-more-capable widget (TOC/folding/Mermaid) via the
same `set_file(path)` call both widgets share -- no code change
needed. Checked `plans/markdown-ex-widget.md` for any documented
downside of the new widget that might argue for deliberately keeping
this call site on the old one (e.g. slower on large files); found
none.)

