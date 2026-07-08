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

