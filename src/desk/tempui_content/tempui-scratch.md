# TempUI DSL: Scratch

See `desk-temporary-ui.md` (in this same directory) for this
directory's own overview and its current set of tags -- this file
just covers the `Scratch` keyword.

For giving Desk arbitrary free-form notes to show in a Scratch widget —
a fire-and-forget instruction, not a question: there is no `Answer`
line, and Desk never writes back to this file.

- The first line is `Scratch <label>` — `label` becomes the widget's
  title (`Scratch: <label>`).
- Every line after that, verbatim, becomes the widget's initial body
  text (not further parsed — write whatever you want here).

Example:

```
Scratch Investigation notes
Found the bug in file_watch.py line 42.
Still need to check the TempUiManager path.
```

If the user says "scratch" in conversation, this capability is almost
certainly what's meant — not some other, more generic sense of the
word — unless a clearly more pressing local meaning has already been
established earlier in the current conversation.
