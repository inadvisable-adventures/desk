# Plan: TODO 294f8a2 (COMPLETED) — investigate `disabled_verify_file_explorer.py`

## Investigation

Two independent reasons this is obsolete, not one:

- It imports `widgets/file_explorer/` directly, renamed to
  `widgets/project_files/` by TODO `8385dcc`.
- Its actual assertions (`w._toolbar_style is not None`,
  `open_btn.style().objectName() == "fusion"`) test a per-widget
  manual Fusion-style-forcing workaround (TODO `593a464`) that TODO
  `8afef71` removed entirely, superseded by a generic
  `WidgetFrame._ContentStyleGuard` mechanism applied to every widget's
  content automatically. Confirmed directly: `_toolbar_style` no
  longer exists anywhere in `widgets/project_files/widget.py` — even
  fixing the import path alone wouldn't make this pass.

The Open Folder button/search-box interactions this script also
exercises aren't covered by an enabled script, but they were
incidental collateral verification in a script whose actual *purpose*
was the now-removed style workaround, not dedicated search/open
-folder coverage.

## Resolution

Delete outright. Writing fresh, dedicated search-box/Open-Folder
coverage for Project Files would be new work, not "fixing" this test —
out of scope here unless it comes up as its own need later.

## Verification

Full `tests/verify/` suite: disabled count drops to 10, 0 new failures.
