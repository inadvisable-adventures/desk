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

(Answer: )

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

(Answer: )

(Answer: )

