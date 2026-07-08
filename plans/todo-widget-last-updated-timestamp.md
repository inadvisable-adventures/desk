# TODO widget: show the last committed/reloaded time (COMPLETED)

TODO `61141b3`.

## Summary

The TODO widget's bottom row currently holds a single `_status_label`
that alternates between showing the resolved `TODO.md` path and
transient status text ("Saving…", "Reprioritized -- commit
pending...", "No TODO.md found...", or the path with a "(saved, but not
a git repo -- not committed)" suffix). Add a second, right-aligned
label on that same row showing a human time (`HH:MM:SS`) for whichever
happened most recently: the file being (re)loaded, or a commit
finishing.

## Affected files

- `widgets/todo/widget.py` -- `TodoWidget`.

## Design

- New `self._timestamp_label` (a `QLabel`, right-aligned,
  non-selectable like `_status_label`), added to a new `QHBoxLayout`
  alongside the existing `_status_label` (which keeps a stretch factor
  so the timestamp is pushed to the lower-right), replacing the plain
  `layout.addWidget(self._status_label)` call.
- New `_touch_timestamp(self, verb: str) -> None` helper: sets
  `self._timestamp_label`'s text to `f"{verb} {HH:MM:SS}"` using
  `datetime.now()`.
- Call sites:
  - `reload()`: after a `TODO.md` is actually found and parsed --
    `_touch_timestamp("Reloaded")`. Not called for the "no TODO.md
    found" branch (nothing to timestamp).
  - `_on_external_change()`: after re-parsing an externally-changed
    file -- `_touch_timestamp("Reloaded")` (this is a reload too, just
    triggered by the file watcher instead of `reload()`'s initial
    call).
  - `_report_commit_status()`: `_touch_timestamp("Committed")` when
    `last_commit_ok`, `_touch_timestamp("Saved")` in the not-a-git-repo
    branch (still persisted to disk, just not committed -- "Committed"
    would be inaccurate there).
- Starts blank (no timestamp shown) until the first reload/commit
  happens.

## Verification

Headlessly, against a real `TodoWidget`:
- `reload()` against a real `TODO.md` sets the timestamp label to
  `"Reloaded HH:MM:SS"` matching the current time; the "no TODO.md
  found" path leaves it blank.
- A simulated external file change (driving `_on_external_change`
  directly, as the existing test suite for TODO d25e557 already does)
  updates it to `"Reloaded HH:MM:SS"` again.
- `_report_commit_status()` sets `"Committed HH:MM:SS"` when
  `last_commit_ok` is `True`, and `"Saved HH:MM:SS"` when `False`.
- Regression: `_status_label`'s own existing text (path / transient
  messages) is unaffected by any of the above.
- A full-app `DeskWindow` regression placing a real `todo` widget
  against a real `TODO.md` and confirming both labels render correctly
  side by side.

## Status

**Completed.** Implemented and verified headlessly exactly as described
above: initial `reload()`, the no-TODO.md-found blank case,
`_on_external_change()`, both branches of `_report_commit_status()`,
`_status_label`'s own text staying unaffected, and a full-app
`DeskWindow` regression with a real placed `todo` widget showing both
labels correctly.
