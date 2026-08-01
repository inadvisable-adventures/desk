# Plan: TODO a820354 — log when promoted-widget source relocation finds no source to move (COMPLETED)

From `../FEEDBACK/FEEDBACK-DESK-tempui-convention-drift-notification
-2026-07-30-1120.md`'s smaller, related gap:
`_relocate_promoted_widget_source` (`src/desk/shell/window.py:2049`)
treats a missing source directory at the *current* convention's
expected path (`.desk_temp/widgets/<keyword>/`) as a silent no-op — correct
for a hand-authored, inline-only widget that never had a source
directory, but indistinguishable from a widget whose source genuinely
exists, just at an *older* convention's path (e.g. this project's own
pre-version-14 `custom_widget_src/<name>/`) — which today gets the
exact same silent no-op, leaving the person promoting it to notice on
their own that nothing moved.

## Design

One-line addition, mirroring the `logger.warning` this function already
has for its sibling edge case (a pre-existing destination):

```python
def _relocate_promoted_widget_source(self, keyword: str) -> None:
    ...
    source_dir = self.current_desk.directory / TEMP_UI_DIRNAME / CUSTOM_WIDGET_SRC_DIRNAME / keyword
    if not source_dir.is_dir():
        logger.info(
            "No authoring source directory found for promoted widget %r at %s "
            "-- nothing to relocate (expected for a hand-authored, inline-only "
            "widget; if this widget's source exists at an older convention's "
            "location, it won't be found here)",
            keyword,
            source_dir,
        )
        return
    ...
```

`logger.info`, not `.warning` — per the feedback's own explicit framing,
this must stay quiet-by-default (the common case really is "nothing to
move," and warning-by-default would be noisy for every widget doing
nothing wrong); the destination-already-exists case is a `.warning`
because that one is *always* at least mildly surprising, this one
usually isn't.

## Verification

Extend `tests/verify/verify_relocate_promoted_widget_source.py` (already
the home for this method's own tests):

- Promoting a widget with no source directory logs an `INFO`-level
  message naming the widget and the path checked (via `caplog`-style
  capture or a temporary `logging.Handler`, matching however this
  repo's existing tests already capture log output, if any precedent
  exists — otherwise a direct handler attached to `desk.shell.window`'s
  logger for the duration of the test).
- The existing "pre-existing destination" `logger.warning` behavior is
  unchanged (regression check).
- The relocation itself is still a true no-op in this case (no
  exception, no directory created) — unchanged behavior, only the new
  log line is additive.
- Full `tests/verify/` regression suite.
