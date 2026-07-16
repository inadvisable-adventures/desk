# Plan: TODO 41088da (COMPLETED) — Event Log widget shows the events log's relative path, not absolute

## Summary

`EventLogWidget._ensure_watching` (`widgets/event_log/widget.py`) sets
its status label to `str(self._log_path)`, the events log's *absolute*
path (`directory / TEMP_UI_DIRNAME / LOG_FILENAME`, where `directory`
is the current Desk directory). Show it relative to the current Desk
directory instead — the absolute prefix is long, machine-specific, and
adds nothing a user watching their own open Desk doesn't already know.

## Design

`self._log_path` is always constructed directly as `directory /
TEMP_UI_DIRNAME / LOG_FILENAME`, so `self._log_path.relative_to(directory)`
always succeeds (no need for `.resolve()` or a `try`/`except` — it's a
direct child by construction). Change `_ensure_watching`:

```python
self._log_path = directory / TEMP_UI_DIRNAME / LOG_FILENAME
self._status_label.setText(str(self._log_path.relative_to(directory)))
```

`self._log_path` itself stays absolute (still used for the actual file
watch/read/write) — only the displayed label text changes.

## Verification

- Update `tests/verify/verify_relocate_event_log.py`'s "Event Log
  widget's status label shows the new path" check: assert the label
  shows the relative form (`.desk_temp/MEDIATED-EVENT-LOG.tsv`) and no
  longer contains the temp directory's own absolute prefix.
- Full `tests/verify/` regression suite.
