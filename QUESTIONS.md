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

