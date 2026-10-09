# `OpenWithWidget` optional label (TODO `f9e24e0`) (COMPLETED)

Cites `../FEEDBACK/FEEDBACK-DESK-hmsvc-discovery-friction-and-promoted-widget-capabilities-2026-10-09-1351.md`
(finding 1, last suggested-fix bullet).

## Summary

`OpenWithWidget<TAB>widget_id<TAB>path` always labelled its notification
`Open <path>`, leaking a meaningless placeholder path for a widget that
consumes no file. An optional fourth tab-separated field, `label`, is now
the notification text when present.

## Affected files

`src/desk/temp_ui.py` (`parse_open_with_widget_label`, doc text, changelog
tag `#041937`), `src/desk/shell/window.py` (`_notify_temp_ui`),
`tests/verify/verify_open_with_widget_label.py`.

## Decisions

- Fourth field rather than changing `parse_open_with_widget`'s return type,
  which many call sites unpack as `(widget_id, path)`; three-field files are
  unchanged.
- The "fall back to the target widget's own name" alternative is not done:
  whether a widget consumes a file can't be known without building it, and
  an explicit label covers the case.
